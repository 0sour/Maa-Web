'use strict';

const path = require('path');
const fsp = require('fs/promises');
const maa = require('./maa');

let stagesByCode = null;
let itemNames = null;
let stagesMtime = 0;
let itemsMtime = 0;
let dataDir = '';

/* 资源关星期开放表（周一=1 … 周日=7） */
const WEEK_RESOURCE = {
  1: ['LS-6', 'AP-5'],
  2: ['CE-6', 'SK-5'],
  3: ['LS-6', 'AP-5'],
  4: ['CE-6', 'SK-5'],
  5: ['LS-6', 'AP-5'],
  6: ['CE-6', 'SK-5'],
  7: ['LS-6', 'CE-6', 'AP-5', 'SK-5', 'CA-5'],
};

async function loadJson(file) {
  try {
    return JSON.parse(await fsp.readFile(file, 'utf8'));
  } catch {
    return null;
  }
}

/* stages.json/item_index.json 来自 MaaCore 资源，会随 `maa update` 更新；
   通过 mtime 检测自动重载，无需重启服务 */
async function ensureLoaded() {
  const stageFile = path.join(dataDir, 'resource', 'stages.json');
  const itemFile = path.join(dataDir, 'resource', 'item_index.json');
  try {
    const sst = await fsp.stat(stageFile);
    if (sst.mtimeMs !== stagesMtime) {
      stagesMtime = sst.mtimeMs;
      const stages = await loadJson(stageFile);
      stagesByCode = {};
      if (Array.isArray(stages)) {
        for (const s of stages) if (s && s.code) stagesByCode[s.code] = s;
      }
    }
  } catch { /* ignore */ }
  try {
    const ist = await fsp.stat(itemFile);
    if (ist.mtimeMs !== itemsMtime) {
      itemsMtime = ist.mtimeMs;
      const items = await loadJson(itemFile);
      itemNames = {};
      if (items) {
        for (const [k, v] of Object.entries(items)) if (v && v.name) itemNames[k] = v.name;
      }
    }
  } catch { /* ignore */ }
}

async function init(dir) {
  dataDir = dir || '';
  await ensureLoaded();
}

function stageInfo(code) {
  const s = stagesByCode && stagesByCode[code];
  if (!s) return null;
  const ids = [...new Set((s.dropInfos || []).map((d) => d.itemId).filter((id) => id && id !== 'furni'))];
  return {
    code,
    apCost: s.apCost || null,
    drops: ids.map((id) => ({ id, name: itemNames[id] || id })),
  };
}

async function activityStages() {
  try {
    const res = await maa.run(['activity']);
    const stages = [];
    for (const line of res.stdout.split('\n')) {
      const m = line.match(/^\s*-\s+([A-Za-z0-9\-_]+):\s*(.+)$/);
      if (m) {
        stages.push({ code: m[1], drops: m[2].split(/[、,，]/).map((x) => x.trim()).filter(Boolean) });
      }
    }
    return stages;
  } catch {
    return [];
  }
}

/* 游戏日边界：每日凌晨 4 点刷新，4 点前视为前一天 */
function gameDayWeekday() {
  const now = new Date();
  const day = now.getHours() < 4 ? new Date(now.getTime() - 86400000) : now;
  return ((day.getDay() + 6) % 7) + 1;
}

async function today() {
  await ensureLoaded();
  const weekDay = gameDayWeekday();
  const resource = (WEEK_RESOURCE[weekDay] || []).map((code) => stageInfo(code)).filter(Boolean);
  const activity = await activityStages();
  const activityWithDrops = activity.map((a) => {
    const info = stageInfo(a.code);
    return {
      code: a.code,
      drops: info && info.drops.length ? info.drops.map((d) => d.name) : a.drops,
    };
  });
  return { weekDay, resource, activity: activityWithDrops };
}

/* 关卡搜索（code 前缀/包含匹配），随资源更新自动重载 */
async function list(q = '', limit = 50) {
  await ensureLoaded();
  const query = String(q || '').trim().toUpperCase();
  const codes = Object.keys(stagesByCode || {});
  /* 字母开头的资源关/剿灭关优先显示 */
  codes.sort((a, b) => {
    const aL = /^[A-Z]/.test(a) ? 0 : 1;
    const bL = /^[A-Z]/.test(b) ? 0 : 1;
    if (aL !== bL) return aL - bL;
    return a.localeCompare(b);
  });
  let matched = query
    ? codes.filter((c) => c.startsWith(query) || c.includes(query))
    : codes;
  const items = matched.slice(0, Math.max(1, Math.min(1000, Number(limit) || 50))).map(stageInfo);
  return { items, total: matched.length };
}

module.exports = { init, today, list };
