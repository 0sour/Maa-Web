'use strict';

const fsp = require('fs/promises');

const PRTS_COPILOT_GET = 'https://prts.maa.plus/copilot/get/';
const PRTS_SET_GET = 'https://prts.maa.plus/set/get?id=';

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

async function getSingle(id) {
  const j = await fetchJson(PRTS_COPILOT_GET + id);
  if (j.status_code !== 200 || !j.data || !j.data.content) return null;
  const c = j.data.content;
  return {
    id: Number(j.data.id || id),
    uri: `maa://${id}`,
    stage: c.stage_name || '',
    difficulty: c.difficulty || '',
    author: j.data.uploader || '',
    views: j.data.views || 0,
    description: (c.documentation && (c.documentation.title || c.documentation.details || '')) || '',
    minVersion: c.minimum_required || '',
  };
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
    stage: t.stage_name,
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

module.exports = { preview, parseCode };
