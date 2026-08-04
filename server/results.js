'use strict';

const path = require('path');
const fsp = require('fs/promises');
const crypto = require('crypto');

const MAX_ITEMS = 200;

function resultsFile(configDir) {
  return path.join(configDir, 'maa-web', 'results.json');
}

async function loadAll(configDir) {
  try {
    const text = await fsp.readFile(resultsFile(configDir), 'utf8');
    const parsed = JSON.parse(text);
    if (parsed && Array.isArray(parsed.items)) return parsed.items;
  } catch { /* ignore */ }
  return [];
}

async function saveAll(configDir, items) {
  const file = resultsFile(configDir);
  await fsp.mkdir(path.dirname(file), { recursive: true });
  await fsp.writeFile(file, JSON.stringify({ version: 1, items }, null, 2), 'utf8');
}

async function addResult(configDir, { type, time, summary, data }) {
  const items = await loadAll(configDir);
  const item = {
    id: crypto.randomUUID(),
    type,
    time: time || new Date().toISOString(),
    summary,
    data,
  };
  items.unshift(item);
  if (items.length > MAX_ITEMS) items.length = MAX_ITEMS;
  await saveAll(configDir, items);
  return item;
}

async function listResults(configDir, type = '') {
  const items = await loadAll(configDir);
  return items
    .filter((i) => !type || i.type === type)
    .map(({ id, type, time, summary }) => ({ id, type, time, summary }));
}

async function getResult(configDir, id) {
  const items = await loadAll(configDir);
  return items.find((i) => i.id === id) || null;
}

async function removeResult(configDir, id) {
  const items = await loadAll(configDir);
  const next = items.filter((i) => i.id !== id);
  if (next.length === items.length) return false;
  await saveAll(configDir, next);
  return true;
}

module.exports = { addResult, listResults, getResult, removeResult, resultsFile };
