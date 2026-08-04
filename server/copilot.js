'use strict';

const path = require('path');
const fsp = require('fs/promises');

const PRTS_COPILOT_GET = 'https://prts.maa.plus/copilot/get/';
const PRTS_SET_GET = 'https://prts.maa.plus/set/get?id=';

let dataDir = '';
let configDir = '';
let stageIdMap = {}; // stageId -> code
let overviewMtime = 0;

function init(dir, cfg) {
  dataDir = dir || '';
  configDir = cfg || '';
}

/* 加载关卡 stageId→code 映射（MAA 资源 overview.json，mtime 自动重载） */
async function ensureStageMap() {
  const file = path.join(dataDir, 'resource', 'Arknights-Tile-Pos', 'overview.json');
  try {
    const st = await fsp.stat(file);
    if (st.mtimeMs === overviewMtime && Object.keys(stageIdMap).length) return;
    overviewMtime = st.mtimeMs;
    const o = JSON.parse(await fsp.readFile(file, 'utf8'));
    stageIdMap = {};
    for (const v of Object.values(o)) {
      if (v && v.stageId && v.code) stageIdMap[v.stageId] = v.code;
    }
  } catch { /* ignore */ }
}

function stageCode(stageId) {
  return stageIdMap[String(stageId || '')] || String(stageId || '');
}

/* 解析作业 content（可能是字符串形式的嵌套 JSON） */
function parseContent(raw) {
  if (typeof raw === 'string') {
    try { return JSON.parse(raw); } catch { return null; }
  }
  return raw || null;
}

async function getSingle(id) {
  await ensureStageMap();
  const j = await fetchJson(PRTS_COPILOT_GET + id);
  if (j.status_code !== 200 || !j.data) return null;
  const c = parseContent(j.data.content);
  if (!c) return null;
  const stageId = c.stage_name || '';
  return {
    id: Number(j.data.id || id),
    uri: `maa://${id}`,
    stage: stageCode(stageId) || stageId || `作业 ${id}`,
    difficulty: c.difficulty || '',
    author: j.data.uploader || '',
    views: j.data.views || 0,
    description: (c.documentation && (c.documentation.title || c.documentation.details || '')) || '',
    minVersion: c.minimum_required || '',
  };
}

/* 解析作业输入为 { type: 'code'|'set'|'file', id/path } */
function parseCode(input) {
  const s = String(input || '').trim();
  if (!s) return null;
  if (/^maa:\/\/s\d+$/.test(s)) return { type: 'set', id: s.slice(7) };
  if (/^prts:\/\/s\d+$/.test(s)) return { type: 'set', id: s.slice(8) };
  if (/^s\d+$/.test(s)) return { type: 'set', id: s.slice(1) };
  if (/^maa:\/\/\d+$/.test(s)) return { type: 'code', id: s.slice(6) };
  if (/^prts:\/\/\d+$/.test(s)) return { type: 'code', id: s.slice(7) };
  if (/^\d+$/.test(s)) return { type: 'code', id: s };
  return { type: 'file', path: s.replace(/^file:\/\//, '') };
}

async function fetchJson(url, timeout = 10000) {
  const res = await fetch(url, { signal: AbortSignal.timeout(timeout), headers: { 'User-Agent': 'maa-web' } });
  if (!res.ok) throw new Error(`作业站返回 HTTP ${res.status}`);
  return res.json();
}

async function getSet(id) {
  const j = await fetchJson(PRTS_SET_GET + id);
  if (j.status_code !== 200 || !j.data) throw new Error(`作业集不存在（${j.message || ''}）`);
  const ids = Array.isArray(j.data.copilot_ids) ? j.data.copilot_ids : [];
  const items = [];
  for (const cid of ids) {
    try {
      const one = await getSingle(cid);
      if (one) items.push(one);
    } catch { /* 单个作业获取失败跳过 */ }
  }
  return { name: j.data.name || '', description: j.data.description || '', items };
}

async function getFile(path) {
  const text = await fsp.readFile(path, 'utf8');
  const j = JSON.parse(text);
  const tasks = Array.isArray(j.tasks) ? j.tasks : [j];
  const items = tasks.filter((t) => t && t.stage_name).map((t) => ({
    id: 0,
    uri: path,
    stage: stageCode(t.stage_name) || t.stage_name,
    difficulty: t.difficulty || '',
    author: '',
    views: 0,
    description: (t.documentation && (t.documentation.title || t.documentation.details || '')) || '',
    minVersion: t.minimum_required || '',
  }));
  return { name: '', description: '', items };
}

async function preview(input) {
  const parsed = parseCode(input);
  if (!parsed) throw new Error('无法识别的作业输入');
  if (parsed.type === 'file') return getFile(parsed.path);
  if (parsed.type === 'set') return getSet(parsed.id);
  const one = await getSingle(parsed.id);
  if (!one) throw new Error('作业不存在或已被删除');
  return { name: one.stage, description: one.description, items: [one] };
}

/* 列出本地可用作业 JSON 文件（MAA 资源 copilot 目录 + 配置 copilot 目录） */
async function listFiles() {
  const dirs = [
    path.join(dataDir, 'resource', 'copilot'),
    path.join(configDir, 'copilot'),
  ];
  const files = [];
  const seen = new Set();
  const walk = async (dir) => {
    let entries = [];
    try { entries = await fsp.readdir(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) await walk(p);
      else if (e.name.endsWith('.json')) {
        if (!seen.has(p)) { seen.add(p); files.push(p); }
      }
    }
  };
  for (const d of dirs) await walk(d);
  return files.sort();
}

/* 从作业站下载作业保存为本地 JSON，返回 {path, items} */
async function download(input) {
  const parsed = parseCode(input);
  if (!parsed) throw new Error('无法识别的作业输入');
  if (parsed.type === 'file') return getFile(parsed.path);
  await ensureStageMap();
  const saveDir = path.join(configDir, 'copilot');
  await fsp.mkdir(saveDir, { recursive: true });
  if (parsed.type === 'set') {
    const j = await fetchJson(PRTS_SET_GET + parsed.id);
    if (j.status_code !== 200 || !j.data) throw new Error(`作业集不存在（${j.message || ''}）`);
    const ids = Array.isArray(j.data.copilot_ids) ? j.data.copilot_ids : [];
    const items = [];
    for (let i = 0; i < ids.length; i++) {
      try {
        const raw = await fetchRaw(ids[i]);
        const c = parseContent(raw);
        const stageId = (c && c.stage_name) || '';
        const file = path.join(saveDir, `set-${parsed.id}-${i + 1}.json`);
        await fsp.writeFile(file, JSON.stringify(c, null, 2), 'utf8');
        items.push({ path: file, stage: stageCode(stageId) || stageId || `作业 ${ids[i]}` });
      } catch { /* 单个失败跳过 */ }
    }
    if (!items.length) throw new Error('作业集内没有可用的作业');
    return { items };
  }
  const raw = await fetchRaw(parsed.id);
  const c = parseContent(raw);
  if (!c) throw new Error('作业解析失败');
  const stageId = c.stage_name || '';
  const file = path.join(saveDir, `maa-${parsed.id}.json`);
  await fsp.writeFile(file, JSON.stringify(c, null, 2), 'utf8');
  return { items: [{ path: file, stage: stageCode(stageId) || stageId || `作业 ${parsed.id}` }] };
}

/* 获取作业原始 content（JSON 字符串） */
async function fetchRaw(id) {
  const j = await fetchJson(PRTS_COPILOT_GET + id);
  if (j.status_code !== 200 || !j.data) throw new Error('作业不存在或已被删除');
  const content = j.data.content;
  if (typeof content === 'string') return content;
  return JSON.stringify(content);
}

module.exports = { init, preview, parseCode, listFiles, download };
