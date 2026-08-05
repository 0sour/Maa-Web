'use strict';

const path = require('path');
const fsp = require('fs/promises');

let dataDir = '';
let entries = [];
let tasksMtime = 0;

/* 小游戏/商店入口任务筛选：
   - Store@Begin（绿票/黄票商店总入口）
   - *@Store@Begin（各商店链入口，如 GreenTicket@Store@Begin）
   - MiniGame@*（小游戏链，如 MiniGame@SecretFront）
   来源为 MaaCore 资源 tasks.json，会随 `maa update` 增删，按 mtime 自动重载 */
function isEntry(name) {
  if (name === 'Store@Begin') return true;
  if (/^MiniGame@/.test(name)) return true;
  return /@(Store|MiniGame)@Begin$/.test(name);
}

async function ensureLoaded() {
  const file = path.join(dataDir, 'resource', 'tasks', 'tasks.json');
  try {
    const st = await fsp.stat(file);
    if (st.mtimeMs !== tasksMtime) {
      tasksMtime = st.mtimeMs;
      let tasks = {};
      try {
        tasks = JSON.parse(await fsp.readFile(file, 'utf8'));
      } catch {
        tasks = {};
      }
      const list = [];
      for (const [name, def] of Object.entries(tasks)) {
        if (!isEntry(name)) continue;
        if (!def || typeof def !== 'object') continue;
        list.push({
          name,
          doc: (def.doc && String(def.doc)) || '',
          category: /^MiniGame@/.test(name) ? '小游戏' : '商店',
        });
      }
      list.sort((a, b) => {
        if (a.category !== b.category) return a.category.localeCompare(b.category, 'zh');
        return (a.doc || a.name).localeCompare(b.doc || b.name, 'zh');
      });
      entries = list;
    }
  } catch {
    /* 资源未就绪时保持空列表 */
  }
}

async function list() {
  await ensureLoaded();
  return entries;
}

async function get(name) {
  await ensureLoaded();
  return entries.find((e) => e.name === name) || null;
}

async function init(dir) {
  dataDir = dir || '';
  await ensureLoaded();
}

module.exports = { init, list, get };
