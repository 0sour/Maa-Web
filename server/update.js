'use strict';

const maa = require('./maa');

let cache = null;
let cacheAt = 0;
const CACHE_TTL = 6 * 3600 * 1000;

function parseVersion(str) {
  return String(str || '').replace(/^v/i, '').split('.')
    .map((n) => parseInt(n, 10) || 0);
}

function cmp(a, b) {
  const A = parseVersion(a);
  const B = parseVersion(b);
  for (let i = 0; i < 3; i++) {
    if (A[i] > B[i]) return 1;
    if (A[i] < B[i]) return -1;
  }
  return 0;
}

async function githubLatest(repo) {
  try {
    const res = await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
      headers: { 'User-Agent': 'maa-web' },
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) return null;
    const j = await res.json();
    return typeof j.tag_name === 'string' && j.tag_name ? j.tag_name : null;
  } catch {
    return null;
  }
}

async function check(force = false) {
  if (!force && cache && Date.now() - cacheAt < CACHE_TTL) return cache;
  const v = await maa.version();
  const cur = { cli: v.cli || '', core: v.core || '' };
  const [cliLatest, coreLatest] = await Promise.all([
    githubLatest('MaaAssistantArknights/maa-cli'),
    githubLatest('MaaAssistantArknights/MaaAssistantArknights'),
  ]);
  cache = {
    cli: {
      current: cur.cli,
      latest: cliLatest || cur.cli,
      hasUpdate: !!cliLatest && cmp(cliLatest, cur.cli) > 0,
    },
    core: {
      current: cur.core,
      latest: coreLatest || cur.core,
      hasUpdate: !!coreLatest && cmp(coreLatest, cur.core) > 0,
    },
    checkedAt: new Date().toISOString(),
  };
  cacheAt = Date.now();
  return cache;
}

module.exports = { check };
