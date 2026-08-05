'use strict';

const express = require('express');
const path = require('path');
const fs = require('fs');
const fsp = require('fs/promises');
const { execFile } = require('child_process');
const maa = require('./maa');
const { runner } = require('./taskRunner');
const { buildArgs, TASK_SCHEMAS, COMMON_OPTIONS } = require('./taskSchemas');
const { TASK_TYPES, generateTaskFile, BY_TYPE } = require('./dailyTaskTypes');
const results = require('./results');
const scheduler = require('./schedules');
const auth = require('./auth');
const update = require('./update');
const stages = require('./stages');
const roguelike = require('./roguelike');
const copilot = require('./copilot');
const minigames = require('./minigames');

const app = express();
const PORT = Number(process.env.PORT) || 3000;

app.use(express.json({ limit: '2mb' }));
app.use('/api', auth.requireToken);
app.use(express.static(path.join(__dirname, '..', 'public'), {
  etag: true,
  maxAge: 0,
  setHeaders: (res) => {
    res.setHeader('Cache-Control', 'no-cache, must-revalidate');
  },
}));

app.get('/README.md', (_req, res) => {
  res.type('text/plain').sendFile(path.join(__dirname, '..', 'README.md'));
});

const CONFIG_DIR = process.env.MAA_CONFIG_DIR;

let _itemIndex = null;
let _itemIndexPath = '';
async function itemNames(dataDir) {
  const p = path.join(dataDir || '', 'resource', 'item_index.json');
  if (_itemIndex && _itemIndexPath === p) return _itemIndex;
  try {
    const obj = JSON.parse(await fsp.readFile(p, 'utf8'));
    _itemIndex = {};
    _itemIndexPath = p;
    for (const [k, v] of Object.entries(obj)) if (v && v.name) _itemIndex[k] = v.name;
  } catch {
    _itemIndex = {};
    _itemIndexPath = p;
  }
  return _itemIndex;
}

async function formatDepot(details, names = {}) {
  const out = [];
  if (!details.done) return out;
  let data;
  try { data = JSON.parse(details.data || '{}'); } catch { return out; }
  const entries = Object.entries(data);
  if (!entries.length) { out.push('[仓库识别] 未识别到材料'); return out; }
  out.push(`[仓库识别] 共识别 ${entries.length} 种材料:`);
  for (const [id, count] of entries) {
    out.push(`  ${names[id] ? `${id} ${names[id]}` : id}: ${count}`);
  }
  return out;
}

async function extractTaskChains(logDir, startIso = null) {
  const chains = { starts: [], completed: [], failed: [] };
  try {
    const logFile = path.join(logDir, 'asst.log');
    const text = await fsp.readFile(logFile, 'utf8');
    const start = startIso ? new Date(startIso).getTime() : 0;
    for (const line of text.split('\n')) {
      const m = line.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*append_callback \| TaskChain(Start|Completed|Stopped|Error) \{"taskchain":"([^"]+)"/);
      if (!m) continue;
      const t = new Date(m[1].replace(' ', 'T')).getTime();
      if (start && t < start) continue;
      const kind = m[2];
      const chain = m[3];
      if (kind === 'Start') chains.starts.push(chain);
      else if (kind === 'Completed') chains.completed.push(chain);
      else chains.failed.push(chain);
    }
  } catch { /* ignore */ }
  return chains;
}

function matchQueueToChains(queue, chains) {
  const countBefore = new Map();
  return queue.map((q) => {
    const idx = countBefore.get(q.type) || 0;
    countBefore.set(q.type, idx + 1);
    const started = chains.starts.filter((c) => c === q.type).length > idx;
    if (!started) return { type: q.type, name: q.name, ok: null };
    const done = chains.completed.filter((c) => c === q.type).length > idx;
    const failed = chains.failed.filter((c) => c === q.type).length > idx;
    return { type: q.type, name: q.name, ok: done && !failed };
  });
}

async function extractCallback(logDir, what, startIso = null) {
  try {
    const logFile = path.join(logDir, 'asst.log');
    const text = await fsp.readFile(logFile, 'utf8');
    const start = startIso ? new Date(startIso).getTime() : 0;
    let lines = text.split('\n').filter((l) => l.includes(`"what":"${what}"`) || l.includes(`"what": "${what}"`) || (what === 'RecruitResult' && l.includes('RecruitResult')));
    if (start) {
      lines = lines.filter((l) => {
        const m = l.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
        return m ? new Date(m[1].replace(' ', 'T')).getTime() >= start : true;
      });
    }
    if (!lines.length) return null;
    const last = lines[lines.length - 1];
    const m = last.match(/append_callback \| (?:SubTask\w+ |TaskChain\w+ |ConnectionInfo |AsyncCallInfo )?(.*)$/);
    if (!m) return null;
    const payload = m[1].trim();
    const idx = payload.indexOf('{');
    if (idx < 0) return null;
    const data = JSON.parse(payload.slice(idx));
    return data && data.details ? data.details : null;
  } catch {
    return null;
  }
}

const extractRecruitResult = (logDir, startIso) => extractCallback(logDir, 'RecruitResult', startIso);

async function extractRecruitFailure(logDir, startIso) {
  try {
    const logFile = path.join(logDir, 'asst.log');
    const text = await fsp.readFile(logFile, 'utf8');
    const start = startIso ? new Date(startIso).getTime() : 0;
    const lines = text.split('\n').filter((l) => l.includes('SubTaskError') && l.includes('"taskchain":"Recruit"'));
    if (!lines.length) return '';
    let latest = null;
    for (const l of lines) {
      if (start) {
        const m = l.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
        if (m && new Date(m[1].replace(' ', 'T')).getTime() < start) continue;
      }
      latest = l;
    }
    if (!latest) return '';
    const idx = latest.indexOf('{');
    if (idx < 0) return '';
    const data = JSON.parse(latest.slice(idx));
    const first = Array.isArray(data.first) ? data.first.join(',') : '';
    return first ? `（最近失败任务：${first} 识别不到页面）` : '';
  } catch {
    return '';
  }
}

function formatRecruitResult(details) {
  const out = [];
  const tags = Array.isArray(details.tags) ? details.tags.filter(Boolean) : [];
  if (tags.length) out.push(`[公招识别] 识别词条: ${tags.join('、')}`);
  const combos = Array.isArray(details.result) ? details.result : null;
  if (combos) {
    if (!combos.length) { out.push('[公招识别] 未计算出推荐干员'); return out; }
    const byLevel = {};
    for (const c of combos) {
      const lv = Number(c.level) || 0;
      const names = (c.opers || []).map((o) => o.name).filter(Boolean);
      if (names.length) (byLevel[lv] ||= []).push(...names);
      else (byLevel[lv] ||= []).push(`(组合: ${(c.tags || []).join('、') || '无标签'})`);
    }
    for (const lv of Object.keys(byLevel).sort((a, b) => b - a)) {
      out.push(`[公招识别] ${lv}★ ${byLevel[lv].join('、')}`);
    }
    return out;
  }
  const list = Array.isArray(details.recruit_list) ? details.recruit_list : [];
  if (!list.length) { out.push('[公招识别] 未计算出推荐干员'); return out; }
  const byLevel = {};
  for (const r of list) {
    const lv = Number(r.level) || 0;
    (byLevel[lv] ||= []).push(r.name);
  }
  for (const lv of Object.keys(byLevel).sort((a, b) => b - a)) {
    out.push(`[公招识别] ${lv}★ ${byLevel[lv].join('、')}`);
  }
  return out;
}

function formatStageDrops(details) {
  const out = [];
  const stats = Array.isArray(details.stats) ? details.stats : null;
  if (stats) {
    for (const s of stats) out.push(`[掉落] ${s.itemName} x${s.quantity}${s.addQuantity ? `（本次 +${s.addQuantity}）` : ''}`);
    return out;
  }
  const drops = Array.isArray(details.drops) ? details.drops : [];
  for (const d of drops) out.push(`[掉落] ${d.itemName} x${d.quantity}`);
  return out;
}

function formatOperBox(details) {
  const out = [];
  if (!details.done) return out;
  const all = Array.isArray(details.all_opers) ? details.all_opers : (Array.isArray(details.all_oper) ? details.all_oper : []);
  const own = Array.isArray(details.own_opers) ? details.own_opers : [];
  if (!all.length) { out.push('[干员识别] 未获取到干员数据'); return out; }
  const owned = own.length;
  out.push(`[干员识别] 已拥有 ${owned}/${all.length} 名干员`);
  const byRarity = {};
  for (const o of own) (byRarity[o.rarity] ||= []).push(o.name);
  for (const r of Object.keys(byRarity).sort((a, b) => b - a)) {
    if (byRarity[r].length) out.push(`[干员识别] ${r}★ x${byRarity[r].length}`);
  }
  return out;
}

runner.onFinished(async (task) => {
  try {
    const postKey = pendingPostActions[task.id];
    if (postKey) await runPostAction(task, postKey);
    const cmd = task.command || [];
    if (cmd[0] !== 'run') return;
    const d = await configDirs();
    if (Array.isArray(task.queue) && task.queue.length) {
      const chains = await extractTaskChains(d.log, task.startedAt);
      task.results = matchQueueToChains(task.queue, chains);
    }
    let type = '';
    const file = path.join(d.config, 'tasks', cmd[1] === 'tool' ? 'tool.json' : 'daily.json');
    try {
      const tf = JSON.parse(await fsp.readFile(file, 'utf8'));
      type = (tf.tasks && tf.tasks[tf.tasks.length - 1] && tf.tasks[tf.tasks.length - 1].type) || '';
    } catch { /* ignore */ }
    if (type === 'Recruit') {
      const details = await extractRecruitResult(d.log, task.startedAt);
      if (!details) {
        const why = await extractRecruitFailure(d.log, task.startedAt);
        runner.appendOutput(task, `[公招识别] 本次运行未产生识别结果：请确认已进入公招词条选择页面，且存在空闲（未在招募中的）槽位${why}`);
        return;
      }
      const lines = formatRecruitResult(details);
      for (const line of lines) runner.appendOutput(task, line);
      try {
        const tags = Array.isArray(details.tags) ? details.tags : [];
        const combos = (Array.isArray(details.result) ? details.result : [])
          .map((c) => ({ tags: c.tags || [], level: Number(c.level) || 0, opers: (c.opers || []).map((o) => ({ name: o.name, level: Number(o.level) || 0 })) }));
        const top = combos.reduce((a, c) => (c.level > a ? c.level : a), 0);
        await results.addResult(d.config, {
          type: 'recruit',
          summary: tags.length ? `词条 ${tags.join('、')}` : '公招识别',
          data: { tags, level: Number(details.level) || top, combos },
        });
      } catch { /* ignore */ }
      return;
    }
    if (type === 'Depot') {
      const details = await extractCallback(d.log, 'DepotInfo', task.startedAt);
      if (!details) { runner.appendOutput(task, '[仓库识别] 未识别到仓库数据（请确认已进入仓库页面）'); return; }
      const names = await itemNames(d.data);
      const lines = await formatDepot(details, names);
      for (const line of lines) runner.appendOutput(task, line);
      try {
        const data = JSON.parse(details.data || '{}');
        const entries = Object.entries(data).map(([id, count]) => ({ id, name: names[id] || '', count }));
        await results.addResult(d.config, {
          type: 'depot',
          summary: `共 ${entries.length} 种材料`,
          data: { entries },
        });
      } catch { /* ignore */ }
      return;
    }
    if (type === 'OperBox') {
      const details = await extractCallback(d.log, 'OperBoxInfo', task.startedAt);
      if (!details) { runner.appendOutput(task, '[干员识别] 未识别到干员数据（请确认已进入干员页面）'); return; }
      const lines = formatOperBox(details);
      for (const line of lines) runner.appendOutput(task, line);
      try {
        const all = Array.isArray(details.all_opers) ? details.all_opers : [];
        const own = Array.isArray(details.own_opers) ? details.own_opers : [];
        const byRarity = {};
        for (const o of own) (byRarity[o.rarity] ||= []).push({ name: o.name, elite: o.elite, level: o.level, potential: o.potential });
        await results.addResult(d.config, {
          type: 'operbox',
          summary: `拥有 ${own.length}/${all.length} 名干员`,
          data: { total: all.length, owned: own.length, byRarity },
        });
      } catch { /* ignore */ }
      return;
    }
    if (type === 'Fight' || type === 'SingleStep') {
      const details = await extractCallback(d.log, 'StageDrops', task.startedAt);
      if (details) {
        for (const line of formatStageDrops(details)) runner.appendOutput(task, line);
      }
      return;
    }
  } catch { /* ignore */ }
});

async function configDirs() {
  const d = await maa.dirs();
  return {
    config: CONFIG_DIR || d.config,
    data: d.data,
    log: d.log,
    hotUpdate: d['hot-update'],
  };
}

function safeResolve(baseDir, rel) {
  if (!baseDir) throw new Error('配置目录不可用');
  const base = path.resolve(baseDir);
  const target = path.resolve(base, rel);
  if (target !== base && !target.startsWith(base + path.sep)) {
    throw new Error('非法路径');
  }
  return target;
}

async function listDir(dir, exts = null) {
  if (!dir) return [];
  try {
    const entries = await fsp.readdir(dir, { withFileTypes: true });
    const files = [];
    for (const e of entries) {
      if (e.isDirectory()) continue;
      if (exts && !exts.some((x) => e.name.endsWith(x))) continue;
      const full = path.join(dir, e.name);
      let size = 0;
      try {
        const stat = await fsp.stat(full);
        size = stat.size;
      } catch {
        /* ignore */
      }
      files.push({ name: e.name, size, mtime: (await fsp.stat(full).catch(() => null))?.mtime?.toISOString() || null });
    }
    return files.sort((a, b) => a.name.localeCompare(b.name));
  } catch {
    return [];
  }
}

/* ---------- daily task queue ---------- */

const DEFAULT_QUEUE = () => [
  { type: 'StartUp', name: '开始唤醒', enabled: true, params: { client_type: 'Official', start_game_enabled: true } },
  { type: 'Fight', name: '理智作战', enabled: true, params: { stage: '1-7' } },
  { type: 'Recruit', name: '公开招募', enabled: true, params: { select: [5, 4], confirm: [4, 3], times: 4, refresh: true } },
  { type: 'Infrast', name: '基建换班', enabled: true, params: { mode: 0, facility: ['Mfg', 'Trade', 'Reception', 'Control', 'Power', 'Office', 'Dorm'], drones: '_NotUse' } },
  { type: 'Mall', name: '信用收支', enabled: true, params: { visit_friends: true, shopping: true } },
  { type: 'Award', name: '领取奖励', enabled: true, params: { award: true } },
  { type: 'CloseDown', name: '关闭游戏', enabled: true, params: { client_type: 'Official' } },
];

async function queueFile() {
  const d = await configDirs();
  if (!d.config) return null;
  return path.join(d.config, 'maa-web', 'queue.json');
}

async function configsDir() {
  const d = await configDirs();
  if (!d.config) return null;
  return path.join(d.config, 'maa-web', 'configs');
}

/* ---------- 配置快照管理（多套队列配置切换） ---------- */

async function listConfigs() {
  const dir = await configsDir();
  if (!dir) return [];
  try {
    const entries = await fsp.readdir(dir);
    const out = [];
    for (const f of entries) {
      if (!f.endsWith('.json')) continue;
      try {
        const j = JSON.parse(await fsp.readFile(path.join(dir, f), 'utf8'));
        out.push({ name: f.slice(0, -5), queueCount: (j.queue || []).length, profile: j.profile || '', updatedAt: j.updatedAt || '' });
      } catch { /* ignore */ }
    }
    return out;
  } catch {
    return [];
  }
}

async function saveConfig(name) {
  const dir = await configsDir();
  if (!dir) throw new Error('配置目录不可用');
  if (!String(name || '').trim()) throw new Error('配置名称不能为空');
  if (/[/\\]/.test(name)) throw new Error('配置名称包含非法字符');
  const q = await readQueue();
  const conn = await readConnection();
  const data = { queue: q, profile: conn.profile || '', updatedAt: new Date().toISOString() };
  await fsp.mkdir(dir, { recursive: true });
  await fsp.writeFile(path.join(dir, `${name}.json`), JSON.stringify(data, null, 2), 'utf8');
  return data;
}

async function applyConfig(name) {
  const dir = await configsDir();
  if (!dir) throw new Error('配置目录不可用');
  const file = path.join(dir, `${name}.json`);
  const j = JSON.parse(await fsp.readFile(file, 'utf8'));
  if (!Array.isArray(j.queue)) throw new Error('配置内容无效');
  const f = await queueFile();
  if (f) await fsp.writeFile(f, JSON.stringify(j.queue, null, 2), 'utf8');
  if (j.profile) {
    const conn = await readConnection();
    await writeConnectionProfile({ ...conn, profile: j.profile });
  }
  return { queueCount: j.queue.length, profile: j.profile || '' };
}

async function deleteConfig(name) {
  const dir = await configsDir();
  if (!dir) return;
  await fsp.rm(path.join(dir, `${name}.json`), { force: true });
}

/* ---------- 配置快照路由 ---------- */
app.get('/api/configs', async (_req, res) => {
  try { res.json({ items: await listConfigs() }); } catch (err) { res.status(400).json({ error: err.message }); }
});

app.post('/api/configs', async (req, res) => {
  try {
    const { name } = req.body || {};
    await saveConfig(name);
    res.json({ ok: true, items: await listConfigs() });
  } catch (err) { res.status(400).json({ error: err.message }); }
});

app.post('/api/configs/:name/apply', async (req, res) => {
  try {
    const r = await applyConfig(req.params.name);
    res.json({ ok: true, ...r });
  } catch (err) { res.status(400).json({ error: err.message }); }
});

app.delete('/api/configs/:name', async (req, res) => {
  try {
    await deleteConfig(req.params.name);
    res.json({ ok: true, items: await listConfigs() });
  } catch (err) { res.status(400).json({ error: err.message }); }
});

async function readQueue() {
  const file = await queueFile();
  if (!file) return DEFAULT_QUEUE();
  try {
    const data = JSON.parse(await fsp.readFile(file, 'utf8'));
    if (Array.isArray(data)) return data;
  } catch {
    /* ignore */
  }
  return DEFAULT_QUEUE();
}

/* ---------- device history ---------- */

async function devicesFile() {
  const d = await configDirs();
  if (!d.config) return null;
  return path.join(d.config, 'maa-web', 'devices.json');
}

async function readDeviceHistory() {
  const file = await devicesFile();
  if (!file) return [];
  try {
    const data = JSON.parse(await fsp.readFile(file, 'utf8'));
    if (Array.isArray(data)) return data;
  } catch {
    /* ignore */
  }
  return [];
}

async function recordDevice(address, model = '') {
  const file = await devicesFile();
  if (!file || !address) return;
  const list = await readDeviceHistory();
  const existing = list.find((d) => d.address === address);
  if (existing) {
    existing.model = model || existing.model;
    existing.lastUsed = new Date().toISOString();
  } else {
    list.push({ address, model, lastUsed: new Date().toISOString() });
  }
  await fsp.mkdir(path.dirname(file), { recursive: true });
  await fsp.writeFile(file, JSON.stringify(list, null, 2), 'utf8');
}

app.get('/api/task-types', (_req, res) => {
  res.json({ types: TASK_TYPES });
});

app.get('/api/queue', async (_req, res) => {
  res.json({ queue: await readQueue() });
});

app.post('/api/queue', async (req, res) => {
  try {
    const { queue } = req.body || {};
    if (!Array.isArray(queue)) return res.status(400).json({ error: '参数错误' });
    const file = await queueFile();
    if (file) {
      await fsp.mkdir(path.dirname(file), { recursive: true });
      await fsp.writeFile(file, JSON.stringify(queue, null, 2), 'utf8');
    }
    res.json({ ok: true });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

async function writeDailyTaskFile(queue) {
  const d = await configDirs();
  if (!d.config) throw new Error('配置目录不可用');
  const tasksDir = path.join(d.config, 'tasks');
  await fsp.mkdir(tasksDir, { recursive: true });
  const content = generateTaskFile(queue);
  await fsp.writeFile(path.join(tasksDir, 'daily.json'), content, 'utf8');
  return content;
}

async function runDailyQueue({ queue, profile, logLevel, addr, common = {}, name, postAction = '' }) {
  const q = Array.isArray(queue) ? queue : await readQueue();
  await writeDailyTaskFile(q);
  const args = ['run', 'daily'];
  if (profile) args.push('-p', profile);
  if (addr) args.push('-a', addr);
  if (common.batch) args.push('--batch');
  if (common.dryRun) args.push('--dry-run');
  const env = {};
  if (logLevel) env.MAA_LOG = logLevel;
  const enabledCount = q.filter((t) => t.enabled && BY_TYPE[t.type]).length;
  const { id } = runner.start({
    command: args,
    name: name || `每日任务（${enabledCount} 项）`,
    env,
    queue: q.filter((t) => t.enabled && BY_TYPE[t.type]).map((t) => ({ type: t.type, name: t.name })),
  });
  if (postAction) pendingPostActions[id] = postAction;
  return { id, enabledCount };
}

const POST_ACTIONS = {
  close: { label: '关闭游戏' },
  suspend: { label: '休眠（systemctl suspend）' },
  shutdown: { label: '关机（systemctl poweroff）' },
};
const pendingPostActions = {}; // taskId -> action key

function canRunSystemAction() {
  try {
    return require('fs').existsSync('/run/systemd/system');
  } catch {
    return false;
  }
}

async function runPostAction(task, key) {
  delete pendingPostActions[task.id];
  const meta = POST_ACTIONS[key];
  if (!meta) return;
  const d = await configDirs();
  const maaBin = path.join(d.share, 'maa', 'bin', 'maa');
  runner.appendOutput(task, `\n[后置动作] ${meta.label}`);
  if (key === 'close') {
    const { execFile } = require('child_process');
    await new Promise((resolve) => {
      execFile(maaBin, ['closedown'], { timeout: 60000, env: process.env }, (err, stdout, stderr) => {
        const out = String(stdout || '') + String(stderr || '');
        if (out.trim()) runner.appendOutput(task, out.trim());
        if (err) runner.appendOutput(task, `[后置动作] 关闭游戏失败：${err.message}`);
        else runner.appendOutput(task, '[后置动作] 已执行关闭游戏');
        resolve();
      });
    });
    return;
  }
  if (key === 'suspend' || key === 'shutdown') {
    if (!canRunSystemAction()) {
      runner.appendOutput(task, '[后置动作] 容器/无 systemd 环境不可用，请改在宿主机执行');
      return;
    }
    const { execFile } = require('child_process');
    await new Promise((resolve) => {
      execFile('systemctl', [key === 'suspend' ? 'suspend' : 'poweroff'], { timeout: 15000 }, (err) => {
        if (err) runner.appendOutput(task, `[后置动作] 执行失败：${err.message}`);
        resolve();
      });
    });
  }
}

app.post('/api/queue/run', async (req, res) => {
  try {
    const { queue, profile, logLevel, addr, common = {}, postAction } = req.body || {};
    const r = await runDailyQueue({ queue, profile, logLevel, addr, common, postAction });
    res.json({ ok: true, ...r });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/tool', async (req, res) => {
  try {
    const { type, name, params = {}, logLevel, addr } = req.body || {};
    if (!BY_TYPE[type]) return res.status(400).json({ error: `未知任务类型: ${type}` });
    const d = await configDirs();
    if (!d.config) throw new Error('配置目录不可用');
    const tasksDir = path.join(d.config, 'tasks');
    await fsp.mkdir(tasksDir, { recursive: true });
    const meta = BY_TYPE[type];
    const entry = { type };
    if (Object.keys(params).length) entry.params = params;
    await fsp.writeFile(path.join(tasksDir, 'tool.json'), JSON.stringify({ client_type: 'Official', tasks: [entry] }, null, 2) + '\n', 'utf8');
    const env = {};
    if (logLevel) env.MAA_LOG = logLevel;
    const args = ['run', 'tool'];
    if (addr) args.push('-a', addr);
    const { id } = runner.start({ command: args, name: name || meta.label, env });
    res.json({ ok: true, id });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- connection profile ---------- */

function parseTomlSections(text) {
  const out = {};
  let section = null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const sec = line.match(/^\[(.+)\]$/);
    if (sec) { section = sec[1]; continue; }
    const eq = line.indexOf('=');
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if (/^".*"$/.test(val)) val = val.slice(1, -1);
    if (!section) out[key] = val;
    else {
      if (!out[section]) out[section] = {};
      out[section][key] = val;
    }
  }
  return out;
}

function tq(s) {
  return `"${String(s).replace(/"/g, '\\"')}"`;
}

async function readConnection() {
  const dirs = await configDirs();
  if (!dirs.config) return {};
  const candidates = [
    path.join(dirs.config, 'profiles', 'default.toml'),
    path.join(dirs.config, 'profiles', 'default.json'),
    path.join(dirs.config, 'asst.toml'),
  ];
  for (const file of candidates) {
    try {
      const text = await fsp.readFile(file, 'utf8');
      const parsed = file.endsWith('.json') ? JSON.parse(text) : parseTomlSections(text);
      const conn = parsed.connection || parsed.Connection || {};
      const inst = parsed.instance_options || parsed.InstanceOptions || {};
      const res = parsed.resource || parsed.Resource || {};
      const stat = parsed.static_options || parsed.StaticOptions || {};
      return {
        file,
        adb_path: conn.adb_path || '',
        address: conn.address || '',
        preset: conn.preset || '',
        config: conn.config || '',
        touch_mode: inst.touch_mode || 'MaaTouch',
        deployment_with_pause: inst.deployment_with_pause || '',
        adb_lite_enabled: inst.adb_lite_enabled || '',
        kill_adb_on_exit: inst.kill_adb_on_exit || '',
        user_resource: res.user_resource || '',
        cpu_ocr: stat.cpu_ocr || '',
      };
    } catch {
      /* try next */
    }
  }
  return {};
}

app.get('/api/connection', async (_req, res) => {
  res.json(await readConnection());
});

async function writeConnectionProfile(body) {
  const dirs = await configDirs();
  if (!dirs.config) throw new Error('配置目录不可用');
  const { adb_path, address, preset, config, touch_mode, deployment_with_pause, adb_lite_enabled, kill_adb_on_exit, user_resource, cpu_ocr } = body || {};
  const lines = [];
  if (preset) lines.push('[connection]', `preset = ${tq(preset)}`);
  else lines.push('[connection]');
  if (adb_path) lines.push(`adb_path = ${tq(adb_path)}`);
  if (address) lines.push(`address = ${tq(address)}`);
  if (config) lines.push(`config = ${tq(config)}`);
  if (!preset && !adb_path && !address && !config) lines.push('# 连接参数未配置，将使用默认值');
  lines.push('', '[instance_options]');
  if (touch_mode) lines.push(`touch_mode = ${tq(touch_mode)}`);
  if (deployment_with_pause !== undefined && deployment_with_pause !== '') lines.push(`deployment_with_pause = ${deployment_with_pause}`);
  if (adb_lite_enabled !== undefined && adb_lite_enabled !== '') lines.push(`adb_lite_enabled = ${adb_lite_enabled}`);
  if (kill_adb_on_exit !== undefined && kill_adb_on_exit !== '') lines.push(`kill_adb_on_exit = ${kill_adb_on_exit}`);
  if (user_resource !== undefined && user_resource !== '') {
    lines.push('', '[resource]', `user_resource = ${user_resource}`);
  }
  if (cpu_ocr !== undefined && cpu_ocr !== '') {
    lines.push('', '[static_options]', `cpu_ocr = ${cpu_ocr}`);
  }
  const file = path.join(dirs.config, 'profiles', 'default.toml');
  await fsp.mkdir(path.dirname(file), { recursive: true });
  await fsp.writeFile(file, lines.join('\n') + '\n', 'utf8');
  return file;
}

app.post('/api/connection', async (req, res) => {
  try {
    const file = await writeConnectionProfile(req.body);
    res.json({ ok: true, file });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- device connect / status ---------- */
app.post('/api/adb/detect', async (_req, res) => {
  try {
    const result = await maa.detectAdb();
    if (!result.adb) result.hint = '未找到 adb。Docker 容器内置 adb；本地可安装 android-tools-adb 或使用模拟器自带的 adb。';
    res.json(result);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

async function deviceStatus() {
  const configured = await readConnection();
  const adb = await maa.resolveAdb();
  let device = null;
  let connected = false;
  if (adb && configured.address) {
    device = await maa.adbDeviceStatus(adb.path, configured.address);
    if (device.state === 'absent' && maa.isHostPort(configured.address)) {
      await maa.adbConnect(adb.path, configured.address);
      device = await maa.adbDeviceStatus(adb.path, configured.address);
    }
    connected = device.state === 'device';
  }
  return { connected, adb, configured, device };
}

app.get('/api/device/status', async (_req, res) => {
  try {
    res.json(await deviceStatus());
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/devices', async (_req, res) => {
  try {
    const current = await readConnection();
    const st = await deviceStatus();
    const history = await readDeviceHistory();
    res.json({
      current: {
        address: current.address || '',
        model: (st.device && st.device.model) || '',
        connected: st.connected,
        touch_mode: current.touch_mode || 'MaaTouch',
      },
      history,
    });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

let screenChain = Promise.resolve();
let screenCache = { png: null, at: 0 };
app.get('/api/device/screen', async (req, res) => {
  const minInterval = 80;
  if (screenCache.png && Date.now() - screenCache.at < minInterval) {
    res.set('Content-Type', 'image/png');
    res.set('X-Screen-At', String(screenCache.at));
    res.set('X-Screen-Cached', '1');
    return res.send(screenCache.png);
  }
  const task = screenChain.then(async () => {
    const conn = await readConnection();
    if (!conn.address) throw new Error('未配置设备，请先在「设备连接」页连接设备');
    const adb = await maa.resolveAdb();
    if (!adb) throw new Error('未找到 adb');
    const bin = conn.adb_path || adb.path;
    const device = await maa.adbDeviceStatus(bin, conn.address);
    if (device.state !== 'device') throw new Error(`设备 ${conn.address} 当前不可用 (${device.state})`);
    const cap = await maa.screenCapture(bin, conn.address);
    if (!cap.ok) throw new Error(cap.err || '截图失败');
    const at = Date.now();
    screenCache = { png: cap.png, at };
    return { png: cap.png, at };
  }).catch((err) => ({ error: err.message }));
  screenChain = task.then(() => {});
  const r = await task;
  if (r.error) return res.status(400).json({ error: r.error });
  res.set('Content-Type', 'image/png');
  res.set('X-Screen-At', String(r.at));
  res.send(r.png);
});

app.post('/api/device/connect', async (req, res) => {
  try {
    const { adb_path, address, touch_mode } = req.body || {};
    if (!address) return res.status(400).json({ error: '缺少设备地址' });
    const adb = await maa.resolveAdb();
    if (!adb) return res.status(400).json({ error: '未找到 adb，无法连接设备' });
    const bin = adb_path || adb.path;
    let device = await maa.adbDeviceStatus(bin, address);
    if (device.state === 'absent' && maa.isHostPort(address)) {
      await maa.adbConnect(bin, address);
      device = await maa.adbDeviceStatus(bin, address);
    }
    if (device.state === 'absent') {
      return res.status(400).json({ error: `未找到设备「${address}」，请确认设备已连接、USB 调试已开启并已授权` });
    }
    const connected = device.state === 'device';
    await writeConnectionProfile({
      adb_path: bin,
      address,
      touch_mode: touch_mode || 'MaaTouch',
    });
    if (connected) await recordDevice(address, device.model);
    res.json({
      ok: true,
      connected,
      device,
      adb: { path: bin, version: adb.version },
      warning: connected ? undefined : `设备「${address}」当前状态为 ${device.state}，配置已保存但 MAA 可能无法连接`,
      file: await (async () => {
        const dirs = await configDirs();
        return dirs.config ? path.join(dirs.config, 'profiles', 'default.toml') : null;
      })(),
    });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- device resolution ---------- */
app.post('/api/device/resolution', async (req, res) => {
  try {
    const { action, width, height } = req.body || {};
    const configured = await readConnection();
    const adb = await maa.resolveAdb();
    if (!adb) return res.status(400).json({ error: '未找到 adb' });
    if (!configured.address) return res.status(400).json({ error: '未配置设备' });
    const bin = configured.adb_path || adb.path;
    const serial = configured.address;
    const SUPPORTED = maa.SUPPORTED_RESOLUTIONS.map((r) => `${r.w}x${r.h}`);
    if (action === 'get') {
      return res.json({ ok: true, address: serial, ...(await maa.getWmSize(bin, serial)), supported: SUPPORTED });
    }
    if (action === 'reset') {
      const r = await maa.adbShell(bin, serial, ['wm', 'size', 'reset']);
      if (!r.ok) return res.status(400).json({ error: r.err || r.out });
      return res.json({ ok: true, ...(await maa.getWmSize(bin, serial)) });
    }
    if (action === 'set') {
      if (!width || !height) return res.status(400).json({ error: '缺少分辨率' });
      const reso = `${width}x${height}`;
      if (!SUPPORTED.includes(reso)) return res.status(400).json({ error: `不支持的分辨率 ${reso}，仅支持 ${SUPPORTED.join(' / ')}` });
      const r = await maa.adbShell(bin, serial, ['wm', 'size', reso]);
      if (!r.ok) return res.status(400).json({ error: r.err || r.out });
      return res.json({ ok: true, ...(await maa.getWmSize(bin, serial)) });
    }
    res.status(400).json({ error: '未知操作' });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- status ---------- */
app.get('/api/status', async (_req, res) => {
  const [version, dirs, adb] = await Promise.all([maa.version(), configDirs(), maa.adbAvailable()]);
  res.json({
    version,
    dirs,
    adb,
    runner: runner.status,
    history: runner.history.slice(0, 5).map((t) => ({ ...runner.info(t.id), output: runner.output(t.id).slice(-100) })),
    logLevels: ['Error', 'Warn', 'Info', 'Debug', 'Trace'],
  });
});

/* ---------- task schemas ---------- */
app.get('/api/tasks', async (_req, res) => {
  const dirs = await configDirs();
  const customTasks = await listDir(dirs.config ? path.join(dirs.config, 'tasks') : null, [
    '.yaml', '.yml', '.toml', '.json',
  ]);
  res.json({
    schemas: TASK_SCHEMAS,
    commonOptions: COMMON_OPTIONS,
    customTasks: customTasks.map((f) => f.name.replace(/\.(yaml|yml|toml|json)$/i, '')),
  });
});

/* ---------- custom tasks ---------- */
app.get('/api/custom-tasks', async (_req, res) => {
  const dirs = await configDirs();
  const tasksDir = dirs.config ? path.join(dirs.config, 'tasks') : null;
  res.json({ dir: tasksDir, files: await listDir(tasksDir, ['.yaml', '.yml', '.toml', '.json']) });
});

/* ---------- activity ---------- */
app.get('/api/activity', async (req, res) => {
  const client = String(req.query.client || 'Official');
  res.json({ client, data: await maa.activity(client) });
});

/* ---------- log files ---------- */
app.get('/api/logs', async (req, res) => {
  const dirs = await configDirs();
  const files = await listDir(dirs.log);
  const tail = Math.min(Number(req.query.tail) || 200, 5000);
  let latestContent = '';
  if (files.length) {
    const latest = path.join(dirs.log, files[files.length - 1].name);
    try {
      const data = await fsp.readFile(latest, 'utf8');
      latestContent = data.split(/\r?\n/).slice(-tail).join('\n');
    } catch {
      /* ignore */
    }
  }
  res.json({ dir: dirs.log, files: files.slice(-50), latestContent });
});

/* ---------- config file management ---------- */
app.get('/api/results', async (req, res) => {
  try {
    const dirs = await configDirs();
    const type = String(req.query.type || '');
    res.json({ items: await results.listResults(dirs.config, type) });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/results/:id', async (req, res) => {
  try {
    const dirs = await configDirs();
    const item = await results.getResult(dirs.config, req.params.id);
    if (!item) return res.status(404).json({ error: '记录不存在' });
    res.json({ item });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.delete('/api/results/:id', async (req, res) => {
  try {
    const dirs = await configDirs();
    const ok = await results.removeResult(dirs.config, req.params.id);
    res.json({ ok });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- schedules ---------- */
app.get('/api/schedules', async (_req, res) => {
  res.json({ items: scheduler.withNextRuns() });
});

app.post('/api/schedules', async (req, res) => {
  try {
    const body = req.body || {};
    if (body.task && !TASK_SCHEMAS[body.task.type]) {
      return res.status(400).json({ error: `未知任务类型: ${body.task.type}` });
    }
    const item = await scheduler.add(body);
    res.json({ ok: true, item });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/schedules/:id', async (req, res) => {
  try {
    const body = req.body || {};
    if (body.task && !TASK_SCHEMAS[body.task.type]) {
      return res.status(400).json({ error: `未知任务类型: ${body.task.type}` });
    }
    const item = await scheduler.update(req.params.id, body);
    if (!item) return res.status(404).json({ error: '定时任务不存在' });
    res.json({ ok: true, item });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.delete('/api/schedules/:id', async (req, res) => {
  try {
    const ok = await scheduler.remove(req.params.id);
    res.json({ ok });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/config/files', async (req, res) => {
  const dirs = await configDirs();
  const sub = String(req.query.dir || 'root');
  const root = dirs.config;
  let target;
  if (sub === 'root') target = root;
  else if (sub === 'tasks') target = root ? path.join(root, 'tasks') : null;
  else if (sub === 'profiles') target = root ? path.join(root, 'profiles') : null;
  else if (sub === 'infrast') target = root ? path.join(root, 'infrast') : null;
  else return res.status(400).json({ error: '未知目录' });
  res.json({ dir: target, files: await listDir(target) });
});

app.get('/api/config/file', async (req, res) => {
  try {
    const dirs = await configDirs();
    const target = safeResolve(dirs.config, String(req.query.path || ''));
    const content = await fsp.readFile(target, 'utf8');
    res.json({ path: path.relative(dirs.config, target), content });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/config/file', async (req, res) => {
  try {
    const dirs = await configDirs();
    const { path: rel, content } = req.body || {};
    if (!rel || typeof content !== 'string') return res.status(400).json({ error: '参数错误' });
    const target = safeResolve(dirs.config, rel);
    await fsp.mkdir(path.dirname(target), { recursive: true });
    await fsp.writeFile(target, content, 'utf8');
    res.json({ ok: true, path: rel });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/config/file/delete', async (req, res) => {
  try {
    const dirs = await configDirs();
    const rel = String((req.body && req.body.path) || '');
    const target = safeResolve(dirs.config, rel);
    await fsp.rm(target, { force: true });
    res.json({ ok: true });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- run / stop ---------- */
app.post('/api/run', async (req, res) => {
  try {
    const { type, params = {}, common = {}, logLevel } = req.body || {};
    if (!TASK_SCHEMAS[type]) return res.status(400).json({ error: `未知任务类型: ${type}` });
    if (type === 'minigame') {
      const entry = String(params.entry || '').trim();
      if (!entry) return res.status(400).json({ error: '请选择小游戏' });
      const mg = await minigames.get(entry);
      if (!mg) return res.status(400).json({ error: `小游戏不存在（资源可能已更新）：${entry}` });
      const d = await configDirs();
      const tasksDir = path.join(d.config, 'tasks');
      await fsp.mkdir(tasksDir, { recursive: true });
      await fsp.writeFile(
        path.join(tasksDir, 'maa-web-minigame.json'),
        JSON.stringify({
          tasks: [{ name: `小游戏: ${mg.doc || entry}`, type: 'Custom', params: { task_names: [entry] } }],
        }, null, 2),
        'utf8'
      );
      const command = ['run', 'maa-web-minigame'];
      if (params.addr) command.push('-a', String(params.addr));
      if (params.profile) command.push('-p', String(params.profile));
      if (params.userResource) command.push('--user-resource');
      for (const [idx, f] of Object.entries(COMMON_OPTIONS)) {
        if (common[idx] === true) command.push(f.flag);
      }
      const env = {};
      if (logLevel) env.MAA_LOG = logLevel;
      const { id } = runner.start({ command, name: `小游戏: ${mg.doc || entry}`, env });
      return res.json({ ok: true, id, entry: mg.name });
    }
    const command = buildArgs(type, params, common);
    const env = {};
    if (logLevel) env.MAA_LOG = logLevel;
    const { id } = runner.start({ command, name: command.join(' '), env });
    res.json({ ok: true, id });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- update / maintenance ---------- */

let updateProxy = '';
const updateProxyFile = async () => {
  const d = await configDirs();
  return d.config ? path.join(d.config, 'maa-web', 'update.json') : '';
};

async function loadUpdateProxy() {
  try {
    const f = await updateProxyFile();
    if (!f) return;
    const j = JSON.parse(await fsp.readFile(f, 'utf8'));
    updateProxy = typeof j.proxy === 'string' ? j.proxy.trim() : '';
  } catch {
    updateProxy = '';
  }
}

function proxyEnv() {
  const env = {};
  if (updateProxy) {
    env.HTTP_PROXY = updateProxy;
    env.HTTPS_PROXY = updateProxy;
    env.ALL_PROXY = updateProxy;
    env.http_proxy = updateProxy;
    env.https_proxy = updateProxy;
  }
  return env;
}

app.get('/api/update/proxy', (_req, res) => {
  res.json({ proxy: updateProxy });
});

app.post('/api/update/proxy', async (req, res) => {
  try {
    const { proxy } = req.body || {};
    updateProxy = String(proxy || '').trim();
    const f = await updateProxyFile();
    if (f) {
      await fsp.mkdir(path.dirname(f), { recursive: true });
      await fsp.writeFile(f, JSON.stringify({ proxy: updateProxy }, null, 2), 'utf8');
    }
    res.json({ ok: true, proxy: updateProxy });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/update/proxy/test', async (req, res) => {
  const { proxy, url } = req.body || {};
  const p = String(proxy || '').trim();
  if (!p) return res.status(400).json({ error: '请先填写代理地址' });
  const target = String(url || 'https://api.github.com').trim();
  execFile('curl', [
    '-x', p, '-o', '/dev/null', '-s', '-m', '10',
    '-w', JSON.stringify({ code: '%{http_code}', time: '%{time_total}', speed: '%{speed_download}' }),
    target,
  ], { timeout: 15000 }, (err, stdout) => {
    if (err) {
      const msg = (err.stderr || err.message || '').trim().slice(0, 200);
      return res.json({ ok: false, error: msg || `curl 失败（${err.code || err.killed || ''}）` });
    }
    try {
      const j = JSON.parse(stdout);
      res.json({
        ok: String(j.code).startsWith('2'),
        code: j.code,
        time: parseFloat(j.time),
        speed: Math.round(parseFloat(j.speed) || 0),
        target,
      });
    } catch {
      res.json({ ok: false, error: '无法解析测试结果' });
    }
  });
});

app.post('/api/update', async (_req, res) => {
  try {
    const { id } = runner.start({ command: ['update'], name: 'maa update（更新 MaaCore 与资源）', env: proxyEnv() });
    res.json({ ok: true, id });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/install', async (_req, res) => {
  try {
    const { id } = runner.start({ command: ['install', '--force'], name: 'maa install（安装/重装 MaaCore 与资源）', env: proxyEnv() });
    res.json({ ok: true, id });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/self-update', async (_req, res) => {
  try {
    const { id } = runner.start({ command: ['self', 'update'], name: 'maa self update（更新 maa-cli）', env: proxyEnv() });
    res.json({ ok: true, id });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/stop', (_req, res) => {
  res.json({ stopped: runner.stop() });
});

app.get('/api/output', (req, res) => {
  const id = String(req.query.id || '');
  res.json({ lines: runner.output(id) });
});

/* ---------- SSE ---------- */
app.get('/api/events', (req, res) => {
  console.log(`[sse] + connect from ${req.ip} at ${new Date().toISOString()}`);
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (payload) => {
    res.write(`data: ${JSON.stringify(payload)}\n\n`);
  };

  const off = runner.onOutput(send);

  send({ type: 'hello', runner: runner.status });

  const heartbeat = setInterval(() => send({ type: 'ping' }), 25000);

  req.on('close', () => {
    console.log(`[sse] - close from ${req.ip} at ${new Date().toISOString()}`);
    clearInterval(heartbeat);
    off();
  });
});

const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`[maa-web] listening on http://0.0.0.0:${PORT}`);
  auth.init(async () => {
    const d = await configDirs();
    return d.config ? path.join(d.config, 'maa-web', 'token.json') : '';
  }).then(() => {
    if (auth.enabled()) console.log('[maa-web] 访问令牌已启用');
  });
  loadUpdateProxy();
  configDirs().then((d) => { stages.init(d.data); roguelike.init(d.data); copilot.init(d.data, d.config); minigames.init(d.data); });
  scheduler.init({
    getConfigDir: async () => (await configDirs()).config,
    applyConfig,
    runDailyQueue: async ({ profile, name, postAction }) => {
      const r = await runDailyQueue({ profile, name, postAction });
      return r.id;
    },
    runSingleTask: async ({ type, params, name, postAction }) => {
      if (!TASK_SCHEMAS[type]) throw new Error(`未知任务类型: ${type}`);
      const command = buildArgs(type, params || {}, {});
      const { id } = runner.start({ command, name });
      if (postAction) pendingPostActions[id] = postAction;
      return id;
    },
  });
});

/* ---------- copilot preview ---------- */
app.post('/api/copilot/preview', async (req, res) => {
  try {
    const { input } = req.body || {};
    if (!input || !String(input).trim()) return res.status(400).json({ error: '请输入作业 URI 或路径' });
    res.json(await copilot.preview(String(input).trim()));
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/copilot/files', async (_req, res) => {
  try {
    res.json({ files: await copilot.listFiles() });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/copilot/download', async (req, res) => {
  try {
    const { input } = req.body || {};
    if (!input || !String(input).trim()) return res.status(400).json({ error: '请输入作业代码或路径' });
    res.json(await copilot.download(String(input).trim()));
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/copilot/upload', async (req, res) => {
  try {
    const { content } = req.body || {};
    if (!content) return res.status(400).json({ error: '未收到作业内容' });
    res.json(await copilot.upload(content));
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- roguelike data ---------- */
app.get('/api/roguelike', async (req, res) => {
  try {
    res.json(await roguelike.list(String(req.query.theme || 'Sarkaz')));
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- today stages ---------- */
app.get('/api/stages/today', async (_req, res) => {
  try {
    res.json(await stages.today());
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/stages/list', async (req, res) => {
  try {
    const { q = '', limit } = req.query;
    res.json(await stages.list(q, limit));
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/items', async (req, res) => {
  try {
    const q = String(req.query.q || '');
    const limit = Number(req.query.limit) || 100;
    res.json({ items: await stages.items(q, limit) });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/minigames', async (_req, res) => {
  try {
    res.json({ items: await minigames.list() });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- update check ---------- */
app.get('/api/update/check', async (req, res) => {
  try {
    res.json(await update.check(req.query.force === '1'));
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/* ---------- access token ---------- */
app.get('/api/token/status', (_req, res) => {
  res.json({ enabled: auth.enabled() });
});

app.post('/api/token', async (req, res) => {
  try {
    const oldToken = auth.extract(req) || (req.body && req.body.currentToken) || '';
    if (auth.enabled() && !auth.valid(oldToken)) {
      return res.status(401).json({ error: '已启用访问令牌，需提供旧令牌后才能重置' });
    }
    const t = await auth.generate();
    res.json({ ok: true, token: t });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.delete('/api/token', async (req, res) => {
  try {
    const oldToken = auth.extract(req) || (req.body && req.body.currentToken) || '';
    if (auth.enabled() && !auth.valid(oldToken)) {
      return res.status(401).json({ error: '访问令牌无效' });
    }
    await auth.disable();
    res.json({ ok: true });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});
