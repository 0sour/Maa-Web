'use strict';

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const state = {
  types: [],               // 每日任务类型 schema
  typeMap: {},
  queue: [],               // [{type, name, enabled, params}]
  selectedIndex: null,
  quickSchemas: {},
  currentType: 'fight',
  currentTaskId: null,
  logLines: [],
  status: null,
  currentRunner: null,
  lastTaskEnded: null,
  lastTaskFailed: false,
  deviceOptions: [],
  quickAddr: '',
  screenOn: false,
  screenTimer: null,
  screenBusy: false,
  screenFrames: 0,
  screenFrameAt: 0,
  screenFpsEma: 0,
  screenDevice: '',
  results: [],
  resultsFilter: '',
  currentResultId: null,
  schedules: [],
  scheduleProfiles: [],
  scheduleForm: { id: '', name: '', weekdays: [], times: [], profile: '' },
  configs: [],
  lastQueueResults: null,
};

/* ---------------- utilities ---------------- */

async function api(path, options = {}) {
  const token = localStorage.getItem('maa-web-token');
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const opts = { ...options, headers };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    toast('访问令牌无效，请到设置页更新令牌', 'error');
    throw new Error(data.error || '访问令牌无效');
  }
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

let toastTimer = null;
function toast(msg, type = '') {
  const el = $('#toast');
  el.textContent = msg;
  el.className = `toast show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmtTime(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('zh-CN', { hour12: false });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function elt(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k === 'value') node.value = v;
    else if (k === 'checked' || k === 'selected' || k === 'disabled') node[k] = !!v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c != null) node.append(c);
  }
  return node;
}

const TYPE_COLORS = {
  StartUp: '#4f8cff', Fight: '#f87171', Recruit: '#fbbf24', Infrast: '#34d399',
  Mall: '#f472b6', Award: '#e879f9', Roguelike: '#7c5cff', Reclamation: '#2dd4bf',
  Copilot: '#38bdf8', SSSCopilot: '#14b8a6', ParadoxCopilot: '#fb7185', Depot: '#a3e635',
  OperBox: '#f97316', VideoRecognition: '#60a5fa', Custom: '#94a3b8', CloseDown: '#94a3b8',
};

/* ---------------- navigation ---------------- */

function switchView(name) {
  $$('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${name}`));
  if (name === 'queue') { loadQueue(); loadStatus(); loadTodayStages(); }
  if (name === 'quick') loadQuickSchemas();
  if (name === 'device') { loadDeviceStatus(); loadResolution(); }
  if (name === 'config') { loadConfigFiles(); loadConnection(); }
  if (name === 'recognition') { renderResultsFilter(); loadResults(); }
  if (name === 'schedule') loadSchedules();
  if (name === 'settings') { loadStatus(); loadTokenStatus(); loadUpdateStatus(); loadUpdateProxy(); }
  if (name === 'about') loadAbout();
}

async function loadDeviceOptions() {
  try {
    const d = await api('/api/devices');
    const opts = [{ value: '', label: d.current.connected
      ? `跟随全局设备（当前：${d.current.model || d.current.address}）`
      : '跟随全局设备' }];
    if (d.current.address) {
      opts.push({ value: d.current.address, label: `${d.current.model || d.current.address}（当前连接）` });
    }
    for (const h of d.history || []) {
      if (!h.address) continue;
      if (opts.some((o) => o.value === h.address)) continue;
      opts.push({ value: h.address, label: h.model ? `${h.model} (${h.address})` : h.address });
    }
    state.deviceOptions = opts;
    if (!state.quickAddr && d.current.connected && d.current.address) state.quickAddr = d.current.address;
    for (const id of ['queue-device', 'tools-device']) {
      const sel = $(`#${id}`);
      if (!sel) continue;
      const prev = sel.value;
      sel.innerHTML = '';
      for (const o of opts) sel.append(elt('option', { value: o.value }, o.label));
      if (prev) sel.value = prev;
    }
  } catch {
    /* ignore */
  }
}

/* ---------------- task queue ---------------- */

async function loadQueueTypes() {
  const data = await api('/api/task-types');
  state.types = data.types;
  state.typeMap = Object.fromEntries(data.types.map((t) => [t.type, t]));
  const sel = $('#add-task-type');
  sel.innerHTML = '';
  for (const t of state.types) sel.append(elt('option', { value: t.type }, t.label));
}

async function loadQueue() {
  try {
    const data = await api('/api/queue');
    state.queue = data.queue || [];
    state.selectedIndex = Math.min(state.selectedIndex ?? 0, state.queue.length - 1);
    renderQueueList();
    renderQueueSettings();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function addTask() {
  const type = $('#add-task-type').value;
  const meta = state.typeMap[type];
  const params = {};
  for (const f of meta.fields) {
    if (f.default !== undefined) {
      params[f.name] = f.type === 'number' ? Number(f.default) : f.default;
    }
  }
  state.queue.push({ type, name: meta.label, enabled: true, params });
  state.selectedIndex = state.queue.length - 1;
  renderQueueList();
  renderQueueSettings();
  autosaveQueue();
}

/* ---------------- queue status indicators ---------------- */

function queueLastResult(item) {
  if (!state.lastQueueResults) return null;
  return state.lastQueueResults.results.find((r) => r.type === item.type && r.name === item.name) || null;
}

function queueStatusInfo(item) {
  const queueRunning = state.currentRunner && /每日任务/.test(String(state.currentRunner.name));
  if (queueRunning && item.enabled) return { mark: '●', cls: 'running', title: '本次运行中' };
  const r = queueLastResult(item);
  if (!r) return { mark: '·', cls: '', title: '上次运行未执行' };
  return r.ok ? { mark: '✓', cls: 'ok', title: '上次运行：成功' } : { mark: '✗', cls: 'fail', title: '上次运行：失败' };
}

function renderQueueList() {
  const list = $('#queue-list');
  list.innerHTML = '';
  state.queue.forEach((item, i) => {
    const meta = state.typeMap[item.type] || {};
    const row = elt('div', {
      class: `queue-item ${state.selectedIndex === i ? 'selected' : ''}`,
      'data-index': i,
      onclick: () => { state.selectedIndex = i; renderQueueList(); renderQueueSettings(); },
      oncontextmenu: (e) => { e.preventDefault(); e.stopPropagation(); openQueueContextMenu(e, i); },
      onpointerdown: (e) => queueDragStart(e, i),
    }, [
      elt('span', { class: 'queue-grip', title: '拖拽排序 / 右键更多操作' }, '⠿'),
      elt('input', { type: 'checkbox', class: 'enabled', checked: item.enabled, onclick: (e) => { e.stopPropagation(); item.enabled = e.target.checked; renderQueueList(); renderQueueSettings(); autosaveQueue(); } }),
      elt('span', { class: 'type-badge', style: `background:${TYPE_COLORS[item.type] || '#4f8cff'}` }, item.type),
      elt('div', { class: 'qinfo' }, [
        elt('span', { class: 'qname', title: item.name }, item.name),
        ...(taskOptionSummary(item, meta) ? [elt('div', { class: 'qsum', title: taskOptionSummary(item, meta) }, taskOptionSummary(item, meta))] : []),
      ]),
      elt('span', { class: `queue-status ${queueStatusInfo(item).cls}`, title: queueStatusInfo(item).title }, queueStatusInfo(item).mark),
      elt('div', { class: 'qacts' }, [
        elt('button', { class: 'qbtn', title: '上移', onclick: (e) => { e.stopPropagation(); moveTask(i, -1); } }, '▲'),
        elt('button', { class: 'qbtn', title: '下移', onclick: (e) => { e.stopPropagation(); moveTask(i, 1); } }, '▼'),
        elt('button', { class: 'qbtn del', title: '删除', onclick: (e) => { e.stopPropagation(); removeTask(i); } }, '✕'),
      ]),
    ]);
    list.append(row);
  });
  if (!state.queue.length) {
    list.append(elt('div', { class: 'queue-item', style: 'cursor:default;color:var(--muted)' }, '(队列为空，点击上方「添加任务」开始编排)'));
  }
}

/* ---------------- queue drag sort & context menu ---------------- */

const SUMMARY_MAX_PARTS = 4;
const SUMMARY_SKIP = new Set(['server']);

function taskOptionSummary(item, meta) {
  const opts = item.options || {};
  const parts = [];
  for (const f of meta.fields || []) {
    if (parts.length >= SUMMARY_MAX_PARTS) break;
    if (SUMMARY_SKIP.has(f.name)) continue;
    if (f.type === 'checkbox') {
      if (opts[f.name]) parts.push(f.label);
      continue;
    }
    const v = opts[f.name];
    if (v === undefined || v === null || v === '' || v === false) continue;
    if (Array.isArray(v) && !v.length) continue;
    if (typeof v === 'object' && !Object.keys(v).length) continue;
    if (f.default !== undefined && String(v) === String(f.default)) continue;
    let val;
    if (Array.isArray(v)) val = v.join('、');
    else if (typeof v === 'object') val = Object.keys(v).slice(0, 3).join('、');
    else val = String(v);
    parts.push(`${f.label}:${val}`);
  }
  return parts.join(' · ');
}

const queueDrag = { index: -1, startY: 0, active: false, over: -1, moved: false };

function queueDragStart(e, i) {
  if (e.button !== 0) return;
  if (e.target.closest('button, input, label, .qacts')) return;
  queueDrag.index = i;
  queueDrag.over = i;
  queueDrag.startY = e.clientY;
  queueDrag.active = false;
  queueDrag.moved = false;
  window.addEventListener('pointermove', queueDragMove);
  window.addEventListener('pointerup', queueDragEnd, { once: true });
}

function queueDragMove(e) {
  if (queueDrag.index < 0) return;
  if (!queueDrag.active) {
    if (Math.abs(e.clientY - queueDrag.startY) < 6) return;
    queueDrag.active = true;
    queueDrag.moved = true;
    document.body.classList.add('drag-active');
  }
  const rows = [...$$('#queue-list .queue-item')];
  let over = queueDrag.index;
  const rects = rows.map((r) => r.getBoundingClientRect());
  if (rects.every((r) => r.height <= 0)) {
    const h = 30;
    over = Math.max(0, Math.min(rows.length - 1, Math.floor(e.clientY / h)));
  } else {
    for (let j = 0; j < rows.length; j++) {
      const rect = rects[j];
      if (rect.height <= 0) continue;
      if (e.clientY < rect.top + rect.height / 2) { over = Number(rows[j].dataset.index); break; }
      over = Number(rows[j].dataset.index);
    }
  }
  if (over !== queueDrag.over) {
    queueDrag.over = over;
    rows.forEach((r) => r.classList.remove('drop-line'));
    const target = rows.find((r) => Number(r.dataset.index) === over);
    if (target) target.classList.add('drop-line');
  }
}

function queueDragEnd() {
  window.removeEventListener('pointermove', queueDragMove);
  if (queueDrag.active && queueDrag.over >= 0 && queueDrag.over !== queueDrag.index) {
    reorderTask(queueDrag.index, queueDrag.over);
  }
  queueDrag.index = -1;
  document.body.classList.remove('drag-active');
  $$('#queue-list .queue-item').forEach((r) => r.classList.remove('drop-line', 'dragging'));
}

function reorderTask(from, to) {
  const q = state.queue;
  const [item] = q.splice(from, 1);
  q.splice(to, 0, item);
  state.selectedIndex = to;
  renderQueueList();
  renderQueueSettings();
  autosaveQueue();
}

function openQueueContextMenu(e, i) {
  const existing = $('#ctx-menu');
  if (existing) existing.remove();
  const items = [
    { label: '置顶', action: () => reorderTask(i, 0) },
    { label: '上移', action: () => moveTask(i, -1) },
    { label: '下移', action: () => moveTask(i, 1) },
    { label: '置底', action: () => reorderTask(i, state.queue.length - 1) },
    { divider: true },
    { label: '启用', action: () => { state.queue[i].enabled = true; renderQueueList(); renderQueueSettings(); autosaveQueue(); } },
    { label: '停用', action: () => { state.queue[i].enabled = false; renderQueueList(); renderQueueSettings(); autosaveQueue(); } },
    { divider: true },
    { label: '删除', danger: true, action: () => removeTask(i) },
  ];
  const menu = elt('div', { class: 'ctx-menu', id: 'ctx-menu' });
  for (const it of items) {
    if (it.divider) { menu.append(elt('div', { class: 'ctx-sep' })); continue; }
    menu.append(elt('button', { class: `ctx-item${it.danger ? ' danger' : ''}`, onclick: () => { menu.remove(); it.action(); } }, it.label));
  }
  document.body.append(menu);
  const rect = menu.getBoundingClientRect();
  const x = Math.min(e.clientX, window.innerWidth - rect.width - 8);
  const y = Math.min(e.clientY, window.innerHeight - rect.height - 8);
  menu.style.left = `${Math.max(0, x)}px`;
  menu.style.top = `${Math.max(0, y)}px`;
  const close = () => menu.remove();
  setTimeout(() => window.addEventListener('click', close, { once: true }), 0);
  window.addEventListener('keydown', function esc(ev) { if (ev.key === 'Escape') { close(); window.removeEventListener('keydown', esc); } });
}

function moveTask(i, dir) {
  const j = i + dir;
  if (j < 0 || j >= state.queue.length) return;
  [state.queue[i], state.queue[j]] = [state.queue[j], state.queue[i]];
  state.selectedIndex = j;
  renderQueueList();
  renderQueueSettings();
  autosaveQueue();
}

function removeTask(i) {
  state.queue.splice(i, 1);
  if (state.selectedIndex >= state.queue.length) state.selectedIndex = state.queue.length - 1;
  renderQueueList();
  renderQueueSettings();
  autosaveQueue();
}

function renderQueueSettings() {
  const wrap = $('#queue-settings');
  const item = state.queue[state.selectedIndex];
  if (!item) {
    wrap.innerHTML = '<div class="empty">选择左侧任务以编辑其设置</div>';
    return;
  }
  const meta = state.typeMap[item.type];
  if (!meta) { wrap.innerHTML = ''; return; }

  const params = item.params || {};
  const basic = meta.fields.filter((f) => !f.group || f.group === 'basic');
  const advanced = meta.fields.filter((f) => f.group === 'advanced');

  wrap.innerHTML = '';
  wrap.append(elt('h2', { style: 'margin-bottom:6px' }, `${meta.label} — 设置`));
  wrap.append(elt('div', { class: 'desc', style: 'color:var(--muted);margin-bottom:14px' }, meta.desc));

  const groups = elt('div', { class: 'settings-groups' });
  groups.append(fieldsGroup('常规设置', basic, item));
  if (advanced.length) groups.append(fieldsGroup('高级设置', advanced, item, true));
  wrap.append(groups);
}

function fieldsGroup(title, fields, item, advanced = false) {
  const box = elt('div', { class: 'group fields' });
  const head = elt('div', { class: 'group-title' }, title);
  if (advanced) head.append(elt('span', { class: 'grp-badge' }, '高级'));
  box.append(head);
  for (const f of fields) {
    box.append(fieldInput(f, item));
  }
  return box;
}

/* 材料选择器（掉落停止条件）：搜索选择材料 + 数量，值格式 "id=count,id=count" */
function buildDropsPicker(initial, onValue) {
  const entries = [];
  const init = {};
  if (typeof initial === 'string') {
    for (const part of initial.split(',').map((s) => s.trim()).filter(Boolean)) {
      const [id, count] = part.split('=');
      if (id) init[id.trim()] = Number(count) || 0;
    }
  } else if (initial && typeof initial === 'object') {
    for (const [k, v] of Object.entries(initial)) init[k] = Number(v) || 0;
  }
  for (const [id, count] of Object.entries(init)) entries.push({ id, name: id, count });

  const box = elt('div', { class: 'drops-picker' });
  const chips = elt('div', { class: 'drops-chips' });
  const searchRow = elt('div', { class: 'drops-search-row' });
  const search = elt('input', { type: 'text', class: 'drops-search', placeholder: '搜索材料（如 固源岩 / 30012）' });
  const suggest = elt('div', { class: 'drops-suggest' });
  searchRow.append(search, suggest);
  box.append(chips, searchRow);

  let timer = null;
  const sync = () => {
    onValue(entries.map((e) => `${e.id}=${Math.max(1, e.count || 1)}`).join(','));
  };
  const render = () => {
    chips.replaceChildren();
    if (!entries.length) chips.append(elt('span', { class: 'desc' }, '（未设置：不限制掉落）'));
    for (const e of entries) {
      const num = elt('input', { type: 'number', min: '1', step: '1', value: String(Math.max(1, e.count || 1)) });
      num.addEventListener('change', () => {
        e.count = Math.max(1, Math.floor(Number(num.value) || 1));
        num.value = String(e.count);
        sync();
      });
      const del = elt('button', { class: 'chip-x', type: 'button', title: '移除', onclick: () => { entries.splice(entries.indexOf(e), 1); render(); sync(); } }, '×');
      const chip = elt('span', { class: 'chip' }, e.name);
      chip.append(num, del);
      chips.append(chip);
    }
  };

  /* 已有 ID 补全中文名 */
  const lookupNames = async () => {
    for (const e of entries) {
      if (e.name !== e.id) continue;
      try {
        const res = await api('/api/items?q=' + encodeURIComponent(e.id) + '&limit=5');
        const hit = (res.items || []).find((i) => String(i.id) === e.id);
        if (hit) e.name = hit.name;
      } catch { /* 保持 ID 显示 */ }
    }
    render();
  };

  search.addEventListener('input', () => {
    clearTimeout(timer);
    const q = search.value.trim();
    if (!q) { suggest.replaceChildren(); return; }
    timer = setTimeout(async () => {
      try {
        const res = await api('/api/items?q=' + encodeURIComponent(q) + '&limit=20');
        const list = res.items || [];
        suggest.replaceChildren();
        if (!list.length) suggest.append(elt('div', { class: 'desc' }, '无匹配材料'));
        for (const it of list) {
          const row = elt('div', { class: 'drops-item', tabindex: '0' }, `${it.name} (${it.id})`);
          row.addEventListener('click', () => {
            if (entries.some((e) => e.id === it.id)) { search.value = ''; suggest.replaceChildren(); return; }
            entries.push({ id: it.id, name: it.name, count: 1 });
            render(); sync(); search.value = ''; suggest.replaceChildren();
          });
          suggest.append(row);
        }
      } catch { suggest.replaceChildren(); }
    }, 250);
  });
  search.addEventListener('blur', () => setTimeout(() => suggest.replaceChildren(), 150));

  render();
  if (entries.length) lookupNames();
  return box;
}

function fieldInput(f, item) {
  // 队列抄作业：原始 rows 表单字段隐藏，统一用直观的作业列表区（值由导入功能维护）
  if (item.type === 'Copilot' && f.name === 'copilot_list') {
    return elt('div', { style: 'display:none' });
  }
  const wrap = elt('div', { class: `field ${f.type === 'chips' || f.type === 'drops' ? 'full' : ''}` });
  wrap.append(elt('label', {}, f.label));
  const cur = (item.params || {})[f.name];
  let input;
  const isRoguelike = item.type === 'Roguelike';
  const isCopilot = item.type === 'Copilot';
  if (isCopilot && f.name === 'filename') {
    // 队列侧抄作业：与快速任务一致的作业列表（预览/勾选/导入落地）+ 本地文件下拉
    const row = elt('div', { class: 'toolbar', style: 'gap:8px;width:100%' });
    const picker = buildPicker(cur !== undefined && cur !== null ? String(cur) : '', { 'data-param': f.name, placeholder: '选择本地作业文件或手输路径' }, (v) => setParam(item, f, v), () => {
      const files = state.copilotFiles || [];
      return files.map((fp) => ({ value: fp, label: fp.replace(/^.*[/\\]/, '') }));
    });
    const codeInput = elt('input', { type: 'text', placeholder: '作业代码导入，如 12345 / maa://12345 / 作业集' });
    const uploadBtn = elt('button', { class: 'btn sm', type: 'button', onclick: () => {
      uploadCopilotFile((res) => {
        renderQueueCopilotList(listBox, res.items || [], item);
        toast(`已上传 ${res.items.length} 个作业，勾选即添加`, 'success');
      });
    } }, '上传作业文件');
    row.append(picker, codeInput, uploadBtn);
    wrap.append(row);
    if (f.hint) wrap.append(elt('div', { class: 'desc' }, f.hint));
    // 作业列表区（自动预览 + 勾选即生效：勾选自动保存，取消自动移除）
    const listBox = elt('div', { class: 'copilot-list', id: `copilot-qlist-${item.type}` });
    const listWrap = elt('div', { class: 'field full' }, [
      elt('label', {}, '作业列表（输入代码后自动显示，勾选即添加到任务，取消即移除）'),
      listBox,
    ]);
    wrap.append(listWrap);
    codeInput.addEventListener('change', async () => {
      const code = codeInput.value.trim();
      if (!code) return;
      listBox.innerHTML = '<div class="copilot-loading">正在获取作业…</div>';
      try {
        const res = await api('/api/copilot/preview', { method: 'POST', body: JSON.stringify({ input: code }) });
        renderQueueCopilotList(listBox, res.items || [], item);
      } catch (err) {
        listBox.innerHTML = '';
        listBox.append(elt('div', { class: 'copilot-err' }, `作业获取失败：${err.message}`));
      }
    });
    return wrap;
  }
  switch (f.type) {
    case 'select': {
      input = elt('select');
      const opts = f.options.map((o) => (Array.isArray(o) ? { v: o[0], l: o[1] } : { v: o, l: o }));
      for (const o of opts) input.append(elt('option', { value: o.v }, o.l));
      if (cur !== undefined && cur !== '') input.value = String(cur);
      input.addEventListener('change', () => {
        setParam(item, f, input.value);
        // 队列侧肉鸽：切换主题刷新分队/难度/模式/干员选项并清空已选
        if (isRoguelike && f.name === 'theme') {
          loadRoguelikeData(input.value);
          const box = wrap.closest('.settings-groups');
          if (box) {
            for (const n of ['squad', 'roles', 'core_char', 'difficulty', 'mode', 'collectible_mode_squad']) {
              const el = box.querySelector(`[data-param="${n}"]`);
              if (el) { el.value = ''; delete el.dataset.raw; }
            }
          }
        }
      });
      break;
    }
    case 'checkbox': {
      input = elt('input', { type: 'checkbox', class: 'enabled' });
      if (cur) input.checked = true;
      input.addEventListener('change', () => setParam(item, f, input.checked));
      wrap.classList.add('chk-row');
      wrap.append(input);
      if (f.hint) wrap.append(elt('div', { class: 'desc' }, f.hint));
      return wrap;
    }
    case 'chips': {
      const vals = Array.isArray(cur) ? cur : [];
      const box = elt('div', { class: 'chips' });
      for (const opt of f.options) {
        const v = Array.isArray(opt) ? opt[0] : opt;
        const l = Array.isArray(opt) ? opt[1] : opt;
        const on = vals.includes(v);
        const chip = elt('span', { class: `chip ${on ? 'on' : ''}` }, l);
        chip.addEventListener('click', () => {
          const arr = Array.isArray(item.params[f.name]) ? item.params[f.name].slice() : [];
          const idx = arr.indexOf(v);
          if (idx >= 0) arr.splice(idx, 1); else arr.push(v);
          setParam(item, f, arr);
          renderQueueSettings();
        });
        box.append(chip);
      }
      input = box;
      break;
    }
    case 'drops': {
      input = buildDropsPicker(cur, (v) => setParam(item, f, v));
      break;
    }
    case 'strNumMap': {
      const val = Array.isArray(cur) ? cur.join(',') : (cur !== undefined && typeof cur === 'object' ? Object.entries(cur).map(([k, v]) => `${k}=${v}`).join(',') : (cur !== undefined ? String(cur) : ''));
      input = elt('input', { type: 'text', placeholder: f.placeholder || '', value: val });
      input.addEventListener('change', () => setParam(item, f, input.value));
      break;
    }
    case 'boolMap': {
      const vals = new Set(cur && typeof cur === 'object' && !Array.isArray(cur) ? Object.keys(cur) : []);
      const box = elt('div', { class: 'chips' });
      for (const opt of f.options) {
        const v = Array.isArray(opt) ? opt[0] : opt;
        const l = Array.isArray(opt) ? opt[1] : opt;
        const on = vals.has(v);
        const chip = elt('span', { class: `chip ${on ? 'on' : ''}` }, l);
        chip.addEventListener('click', () => {
          const arr = Array.isArray(item.params[f.name]) ? item.params[f.name].slice()
            : (item.params[f.name] && typeof item.params[f.name] === 'object' ? Object.keys(item.params[f.name]) : []);
          const idx = arr.indexOf(v);
          if (idx >= 0) arr.splice(idx, 1); else arr.push(v);
          setParam(item, f, arr);
          renderQueueSettings();
        });
        box.append(chip);
      }
      input = box;
      break;
    }
    case 'lines':
    case 'rows':
    case 'json': {
      const val = Array.isArray(cur) ? cur.map((r) => (typeof r === 'object' ? (f.cols || []).map((c) => String(r[c] ?? '')).join(',') : String(r))).join('\n')
        : (cur !== undefined && typeof cur === 'object' ? JSON.stringify(cur, null, 2) : (cur !== undefined ? String(cur) : ''));
      input = elt('textarea', { class: 'rows-input', placeholder: f.placeholder || '', rows: f.type === 'json' ? '4' : '3', value: val, spellcheck: 'false' });
      input.addEventListener('change', () => setParam(item, f, input.value));
      wrap.classList.add('full');
      break;
    }
    default: {
      if (f.name === 'stage') {
        input = buildStagePicker(cur !== undefined && cur !== null ? String(cur) : '', { 'data-param': f.name }, (v) => setParam(item, f, v));
        wrap.append(input);
        if (f.hint) wrap.append(elt('div', { class: 'desc' }, f.hint));
        return wrap;
      }
      if (isRoguelike && (f.name === 'squad' || f.name === 'roles' || f.name === 'core_char')) {
        input = buildPicker(cur !== undefined && cur !== null ? String(cur) : '', { 'data-param': f.name, placeholder: '选择' }, (v) => setParam(item, f, v), () => {
          const d = state.roguelikeData || {};
          if (f.name === 'squad') return (d.squads || []).map((s) => ({ value: s.value, label: s.label }));
          if (f.name === 'roles') return (d.roles || []).map((r) => ({ value: r.value, label: r.label }));
          return (d.operators || []).map((o) => ({ value: o, label: o }));
        });
        wrap.append(input);
        if (f.hint) wrap.append(elt('div', { class: 'desc' }, f.hint));
        return wrap;
      }
      if (isRoguelike && f.name === 'difficulty') {
        input = buildPicker(cur !== undefined && cur !== null ? String(cur) : '', { 'data-param': f.name, placeholder: '选择难度' }, (v) => setParam(item, f, v), () => {
          const d = state.roguelikeData || {};
          return (d.difficulties || []).map((x) => ({ value: x.value, label: x.label }));
        });
        wrap.append(input);
        if (f.hint) wrap.append(elt('div', { class: 'desc' }, f.hint));
        return wrap;
      }
      input = elt('input', {
        type: f.type === 'number' ? 'number' : 'text',
        placeholder: f.placeholder || '',
        value: cur !== undefined && cur !== null ? String(cur) : '',
        step: f.step,
      });
      input.addEventListener('change', () => setParam(item, f, input.value));
    }
  }
  if (input && typeof input.setAttribute === 'function') input.setAttribute('data-param', f.name);
  wrap.append(input);
  if (f.hint) wrap.append(elt('div', { class: 'desc' }, f.hint));
  return wrap;
}

function setParam(item, field, raw) {
  if (!item.params) item.params = {};
  const { valueToParam } = queueHelpers;
  const v = valueToParam(field, raw);
  if (v === undefined) delete item.params[field.name];
  else item.params[field.name] = v;
  autosaveQueue();
}

/* 队列自动保存：所有变更防抖 500ms 落盘 */
let queueSaveTimer = null;
function autosaveQueue() {
  clearTimeout(queueSaveTimer);
  queueSaveTimer = setTimeout(async () => {
    try {
      await api('/api/queue', { method: 'POST', body: JSON.stringify({ queue: state.queue }) });
    } catch { /* 静默失败，下次变更重试 */ }
  }, 500);
}

const queueHelpers = {
  valueToParam(field, raw) {
    if (raw === undefined || raw === null || raw === '') return undefined;
    switch (field.type) {
      case 'checkbox': return !!raw;
      case 'number': return Number(raw);
      case 'select': return String(raw);
    case 'multi':
    case 'multiNum':
    case 'lines':
    case 'chips':
    case 'rows':
      if (Array.isArray(raw)) {
        if (field.type === 'multi') return raw.map((s) => String(s)).filter(Boolean);
        if (field.type === 'multiNum') return raw.map((s) => Number(s)).filter((n) => !Number.isNaN(n));
        if (field.type === 'chips') return raw.map((s) => String(s)).filter(Boolean);
        return raw;
      }
      break;
    case 'drops':
    case 'strNumMap':
    case 'boolMap':
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) return raw;
      break;
    case 'json':
      if (raw && typeof raw === 'object') return raw;
      break;
    default:
      return String(raw);
  }
  switch (field.type) {
    case 'json': {
      if (raw === undefined || raw === null || String(raw).trim() === '') return undefined;
      try {
        const parsed = JSON.parse(String(raw));
        return parsed && typeof parsed === 'object' ? parsed : undefined;
      } catch {
        return undefined;
      }
    }
    case 'multi': return String(raw).split(',').map((s) => s.trim()).filter(Boolean);
    case 'multiNum': return String(raw).split(',').map((s) => Number(s.trim())).filter((n) => !Number.isNaN(n));
    case 'chips': return Array.isArray(raw) ? raw.map((s) => String(s)).filter(Boolean) : undefined;
    case 'lines': return String(raw).split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    case 'boolMap': {
      const arr = Array.isArray(raw) ? raw : String(raw).split(',');
      const keys = arr.map((s) => String(s).trim()).filter(Boolean);
      return keys.length ? Object.fromEntries(keys.map((k) => [k, true])) : undefined;
    }
    case 'strNumMap': {
      const out = {};
      for (const part of String(raw).split(',').map((s) => s.trim()).filter(Boolean)) {
        const [k, v] = part.split('=');
        if (k && v !== undefined && !Number.isNaN(Number(v))) out[k.trim()] = Number(v.trim());
      }
      return Object.keys(out).length ? out : undefined;
    }
    case 'rows': {
      const cols = field.cols || [];
      const numCols = new Set(field.numCols || []);
      const out = [];
      for (const line of String(raw).split(/\r?\n/).map((s) => s.trim()).filter(Boolean)) {
        const parts = line.split(',').map((s) => s.trim());
        const obj = {};
        cols.forEach((c, i) => {
          const v = parts[i];
          if (v === undefined || v === '') return;
          if (numCols.has(c)) obj[c] = Number(v);
          else if (v === 'true') obj[c] = true;
          else if (v === 'false') obj[c] = false;
          else obj[c] = v;
        });
        if (Object.keys(obj).length) out.push(obj);
      }
      return out.length ? out : undefined;
    }
      case 'drops': {
        const out = {};
        for (const part of String(raw).split(',').map((s) => s.trim()).filter(Boolean)) {
          const [id, count] = part.split('=');
          if (id && count !== undefined) out[id.trim()] = Number(count.trim());
        }
        return Object.keys(out).length ? out : undefined;
      }
      default: return String(raw);
    }
  },
};

async function saveQueue() {
  try {
    await api('/api/queue', { method: 'POST', body: JSON.stringify({ queue: state.queue }) });
    toast('队列已保存', 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function runQueue() {
  try {
    const body = { queue: state.queue, logLevel: $('#queue-log-level').value, common: {} };
    const addr = $('#queue-device').value;
    if (addr) body.addr = addr;
    if ($('#queue-batch').checked) body.common.batch = true;
    if ($('#queue-dryrun').checked) body.common.dryRun = true;
    const postAction = $('#queue-post-action').value;
    if (postAction) body.postAction = postAction;
    const res = await api('/api/queue/run', { method: 'POST', body: JSON.stringify(body) });
    state.currentTaskId = res.id;
    appendLog(`[队列] 开始每日任务（${res.enabledCount} 项启用）`, 'task');
    toast(`已开始每日任务（${res.enabledCount} 项）`, 'success');
    openSideLog();
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------------- quick tasks (CLI) ---------------- */

const QUICK_CATEGORY_ORDER = ['日常', '作战', '抄作业', '集成战略', '其他'];

function quickRecent() {
  try { return JSON.parse(localStorage.getItem('maa-web-quick-recent') || '[]'); } catch { return []; }
}

function quickRecentAdd(type) {
  const list = quickRecent().filter((t) => t !== type);
  list.unshift(type);
  localStorage.setItem('maa-web-quick-recent', JSON.stringify(list.slice(0, 5)));
}

async function loadQuickSchemas() {
  const data = await api('/api/tasks');
  state.quickSchemas = data.schemas;
  renderQuickCards();
  await loadDeviceOptions();
  try {
    const mg = await api('/api/minigames');
    state.minigameEntries = mg.items || [];
  } catch { state.minigameEntries = []; }
  const current = state.currentType;
  if (state.quickSchemas[current]) renderQuickForm();
}

function renderQuickCards() {
  const wrap = $('#quick-cards');
  wrap.innerHTML = '';
  const recent = quickRecent();
  const byCat = {};
  for (const [key, s] of Object.entries(state.quickSchemas)) {
    if (!s.label) continue;
    const cat = s.category || '其他';
    (byCat[cat] = byCat[cat] || []).push([key, s]);
  }
  for (const cat of QUICK_CATEGORY_ORDER) {
    if (!byCat[cat] || !byCat[cat].length) continue;
    const sec = elt('div', { class: 'quick-section' }, [
      elt('div', { class: 'quick-cat' }, cat),
      elt('div', { class: 'quick-card-grid' }),
    ]);
    const grid = sec.querySelector('.quick-card-grid');
    for (const [key, s] of byCat[cat]) {
      const card = elt('button', {
        class: `task-card ${state.currentType === key ? 'active' : ''}`,
        onclick: () => {
          state.currentType = key;
          renderQuickCards();
          renderQuickForm();
          quickRecentAdd(key);
        },
        title: s.desc || '',
      }, [
        elt('span', { class: 'task-card-name' }, s.label),
        ...(recent.includes(key) ? [elt('span', { class: 'task-card-recent' }, '最近')] : []),
      ]);
      grid.append(card);
    }
    wrap.append(sec);
  }
}

function renderQuickForm() {
  const schema = state.quickSchemas[state.currentType];
  const form = $('#quick-form');
  form.innerHTML = '';
  if (!schema) return;
  $('#quick-form-title').textContent = `${schema.label}${schema.desc ? ' — ' + schema.desc : ''}`;
  if (state.currentType === 'copilot') {
    const codeInput = elt('input', { type: 'text', placeholder: '输入作业代码导入，如 12345 / maa://12345 / prts://s12345' });
    const applyBtn = elt('button', { class: 'btn sm', type: 'button', onclick: () => {
      const raw = codeInput.value.trim();
      if (!raw) return;
      let uri = raw;
      if (/^\d+$/.test(raw)) uri = `maa://${raw}`;
      else if (/^s\d+$/.test(raw)) uri = `maa://${raw.slice(1)}s`;
      const input = form.querySelector('[data-name="uris"]');
      if (!input) return toast('未找到作业 URI 输入框', 'error');
      input.value = uri;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      toast(`已填入作业代码：${uri}，正在获取作业…`, 'success');
    } }, '填入作业');
    const uploadBtn = elt('button', { class: 'btn sm', type: 'button', onclick: () => {
      uploadCopilotFile((res) => {
        const input = form.querySelector('[data-name="uris"]');
        if (!input) return;
        const uris = res.items.map((it) => it.uri).join('\n');
        input.value = input.value.trim() ? `${input.value.trim()}\n${uris}` : uris;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      });
    } }, '上传作业文件');
    form.append(elt('div', { class: 'field full' }, [
      elt('label', {}, '作业代码导入 / 上传作业文件（可选）'),
      elt('div', { class: 'toolbar', style: 'gap:8px' }, [codeInput, applyBtn, uploadBtn]),
    ]));
  }
  if (state.currentType === 'ssscopilot' || state.currentType === 'paradoxcopilot') {
    const uploadBtn = elt('button', { class: 'btn sm', type: 'button', onclick: () => {
      uploadCopilotFile((res) => {
        const input = form.querySelector('[data-name="uri"]');
        if (!input) return toast('未找到作业路径输入框', 'error');
        input.value = res.items.map((it) => it.uri).join('\n');
      });
    } }, '上传作业文件');
    form.append(elt('div', { class: 'field full' }, [
      elt('label', {}, '上传作业文件（上传到服务器后自动填入路径）'),
      elt('div', { class: 'toolbar', style: 'gap:8px' }, [uploadBtn]),
    ]));
  }
  const adv = new Set(schema.advancedFields || []);
  const basic = schema.fields.filter((f) => !adv.has(f.name));
  const advanced = schema.fields.filter((f) => adv.has(f.name));

  for (const f of basic) {
    const wrap = elt('div', { class: 'field' });
    wrap.append(elt('label', {}, f.label));
    const input = buildQuickInput(f);
    if (state.currentType === 'roguelike' && f.name === 'theme' && input) {
      const select = input.tagName === 'SELECT' ? input : (input.querySelector ? input.querySelector('select') : null);
      if (select) select.addEventListener('change', () => {
        loadRoguelikeData(select.value);
        // 不同主题的模式/分队/难度/核心干员各不相同，切换主题清空已选值
        for (const n of ['mode', 'squad', 'coreChar', 'difficulty']) {
          const el = form.querySelector(`[data-name="${n}"]`);
          if (el) { el.value = ''; delete el.dataset.raw; }
        }
      });
    }
    wrap.append(input);
    if (f.description) wrap.append(elt('div', { class: 'desc' }, f.description));
    form.append(wrap);
  }
  if (advanced.length) {
    const details = elt('details', { class: 'opts', style: 'grid-column:1/-1' }, [
      elt('summary', {}, `进阶参数（${advanced.length} 项）`),
      elt('div', { class: 'task-form adv-form', style: 'padding-top:10px' }),
    ]);
    form.append(details);
    const inner = details.querySelector('.adv-form');
    for (const f of advanced) {
      const wrap = elt('div', { class: 'field' });
      wrap.append(elt('label', {}, f.label));
      wrap.append(buildQuickInput(f));
      if (f.description) wrap.append(elt('div', { class: 'desc' }, f.description));
      inner.append(wrap);
    }
  }
  if (state.currentType === 'copilot') {
    // 作业列表区：URI 变化后自动预览展示全部作业；已导入的作业常驻显示
    const urisEl = form.querySelector('[data-name="uris"]');
    const listBox = elt('div', { id: 'quick-copilot-list', class: 'copilot-list' });
    const listWrap = elt('div', { class: 'field full' }, [
      elt('label', {}, '作业列表（导入后自动显示，勾选要执行的作业）'),
      listBox,
    ]);
    form.append(listWrap);
    const jobs = loadCopilotJobs();
    if (jobs && jobs.length) renderCopilotList(listBox, { name: '', items: jobs });
    if (urisEl) {
      const doPreview = () => loadCopilotPreview(urisEl.value);
      urisEl.addEventListener('change', doPreview);
      urisEl.addEventListener('blur', doPreview);
      if (urisEl.value.trim()) doPreview();
    }
  }
}

function buildQuickInput(f) {
  if (f.name === 'addr') {
    const sel = elt('select', { 'data-name': f.name, title: '留空则使用「设备连接」页配置的全局设备' });
    for (const o of state.deviceOptions) sel.append(elt('option', { value: o.value }, o.label));
    sel.value = state.quickAddr;
    sel.addEventListener('change', () => { state.quickAddr = sel.value; });
    return sel;
  }
  if (f.name === 'stage') {
    return buildStagePicker('', { 'data-name': f.name });
  }
  if (f.name === 'squad' || f.name === 'coreChar') {
    return buildPicker('', { 'data-name': f.name, placeholder: f.name === 'squad' ? '选择分队' : '选择核心干员' }, null, () => {
      const d = state.roguelikeData || {};
      if (f.name === 'squad') return (d.squads || []).map((s) => ({ value: s.value, label: s.label }));
      return (d.operators || []).map((o) => ({ value: o, label: o }));
    });
  }
  if (f.name === 'difficulty' && state.currentType === 'roguelike') {
    return buildPicker('', { 'data-name': f.name, placeholder: '选择难度' }, null, () => {
      const d = state.roguelikeData || {};
      return (d.difficulties || []).map((x) => ({ value: x.value, label: x.label }));
    });
  }
  if (f.name === 'mode' && state.currentType === 'roguelike') {
    return buildPicker('', { 'data-name': f.name, placeholder: '选择模式' }, null, () => {
      const d = state.roguelikeData || {};
      return (d.modes || []).map((x) => ({ value: x.value, label: x.label }));
    });
  }
  if (f.type === 'minigameEntry') {
    return buildPicker('', { 'data-name': f.name, placeholder: '选择小游戏（随资源更新自动增删）' }, null, () => {
      return (state.minigameEntries || []).map((m) => ({ value: m.name, label: `${m.doc || m.name}（${m.category}）` }));
    });
  }
  if (f.type === 'select' || f.type === 'customTasks') {
    const sel = elt('select', { 'data-name': f.name });
    for (const opt of f.options || []) {
      const v = Array.isArray(opt) ? opt[0] : opt;
      const l = Array.isArray(opt) ? opt[1] : opt;
      sel.append(elt('option', { value: v }, l === '' ? '(默认)' : l));
    }
    if (f.defaultValue) sel.value = f.defaultValue;
    return sel;
  }
  if (f.name === 'drops') {
    const el = buildDropsPicker('', (v) => { el.dataset.raw = v; });
    el.dataset.name = f.name;
    return el;
  }
  if (f.type === 'checkbox') return elt('input', { type: 'checkbox', 'data-name': f.name });
  if (f.type === 'textarea') return elt('textarea', { 'data-name': f.name, placeholder: f.placeholder || '' });
  return elt('input', { type: f.type || 'text', 'data-name': f.name, placeholder: f.placeholder || '', value: f.defaultValue || '' });
}

async function runQuick() {
  const params = {};
  for (const el of $$('[data-name]', $('#quick-form'))) {
    if (el.type === 'checkbox') { if (el.checked) params[el.dataset.name] = true; }
    else if (el.dataset.raw !== undefined) params[el.dataset.name] = el.dataset.raw;
    else if (el.value !== '') params[el.dataset.name] = el.value;
  }
  // 抄作业：勾选的作业列表优先于手填 URI
  if (state.currentType === 'copilot' && $('#quick-copilot-list')) {
    const checked = [...$$('#quick-copilot-list input[type=checkbox]:checked')].map((c) => c.dataset.uri);
    if (checked.length) params.uris = checked.join('\n');
  }
  const common = {};
  for (const id of ['batch', 'dryRun', 'noSummary', 'noAutoReconnect']) {
    const el = $(`#quick-${id}`);
    if (el && el.checked) common[id] = true;
  }
  try {
    const schema = state.quickSchemas[state.currentType];
    if (schema && schema.viaTool) {
      const res = await api('/api/tool', { method: 'POST', body: JSON.stringify({ type: 'VideoRecognition', name: schema.label, params, logLevel: $('#quick-log-level').value }) });
      state.currentTaskId = res.id;
      appendLog(`[快速任务] 启动: ${state.currentType}`, 'task');
    } else {
      const res = await api('/api/run', { method: 'POST', body: JSON.stringify({ type: state.currentType, params, common, logLevel: $('#quick-log-level').value }) });
      state.currentTaskId = res.id;
      appendLog(`[快速任务] 启动: ${state.currentType}`, 'task');
    }
    openSideLog();
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------------- tools ---------------- */

async function runTool(type, params) {
  const meta = state.typeMap[type] || { label: type };
  const addr = $('#tools-device').value;
  try {
    const res = await api('/api/tool', { method: 'POST', body: JSON.stringify({ type, name: meta.label, params, logLevel: $('#queue-log-level').value, addr: addr || undefined }) });
    state.currentTaskId = res.id;
    appendLog(`[工具箱] 启动: ${meta.label}`, 'task');
    openSideLog();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function bindTools() {
  const TOOLS = {
    recruit: { type: 'Recruit', params: { times: 0, confirm: [], select: [5, 4, 3] } },
    depot: { type: 'Depot', params: {} },
    operbox: { type: 'OperBox', params: {} },
  };
  $$('.tool-card').forEach((card) => {
    card.querySelector('.run').addEventListener('click', () => {
      const tool = TOOLS[card.dataset.tool];
      const params = { ...tool.params };
      for (const inp of $$('.tool-input', card)) {
        if (inp.value.trim()) params[inp.dataset.param] = inp.value.trim();
      }
      runTool(tool.type, params);
    });
    const historyBtn = card.querySelector('.history');
    if (historyBtn) {
      historyBtn.addEventListener('click', () => {
        state.resultsFilter = historyBtn.dataset.resultType;
        switchView('recognition');
      });
    }
  });
}

/* 关卡选项（数据来自 MaaCore 资源 stages.json，随更新自动生效） */
async function loadStageOptions() {
  try {
    const res = await api('/api/stages/list?limit=1000');
    state.stageOptions = res.items || [];
  } catch { state.stageOptions = []; }
}

/* 通用搜索下拉组件（options: [{value, label, sub}]；选中显示 label、值存 data-raw） */
function buildPicker(value, attrs, onChange, options) {
  const wrap = elt('div', { class: 'stage-picker' });
  const input = elt('input', {
    type: 'text',
    placeholder: '输入或选择…',
    value: value || '',
    ...attrs,
  });
  const list = elt('div', { class: 'stage-picker-list', hidden: true });
  wrap.append(input, list);
  input.addEventListener('change', () => { if (onChange) onChange(input.dataset.raw !== undefined ? input.dataset.raw : input.value); });
  input.addEventListener('input', () => { delete input.dataset.raw; openList(); });

  const opts = () => (typeof options === 'function' ? options() : (options || []));
  function openList() {
    const q = input.value.trim().toUpperCase();
    const src = opts();
    const matched = (q ? src.filter((s) => s.value.toUpperCase().startsWith(q) || s.value.toUpperCase().includes(q) || (s.label || '').includes(q)) : src).slice(0, 30);
    list.innerHTML = '';
    for (const s of matched) {
      const opt = elt('button', {
        type: 'button',
        class: 'stage-opt',
        onclick: () => {
          input.value = s.label || s.value;
          if (s.label && s.label !== s.value) input.dataset.raw = s.value;
          else delete input.dataset.raw;
          input.dispatchEvent(new Event('change', { bubbles: true }));
          list.hidden = true;
        },
      }, [
        elt('span', { class: 'stage-opt-code' }, s.label || s.value),
        s.sub ? elt('span', { class: 'stage-opt-drops' }, s.sub) : null,
      ]);
      list.append(opt);
    }
    list.hidden = !list.children.length;
  }
  input.addEventListener('focus', openList);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 150));
  return wrap;
}

/* 关卡搜索下拉（数据来自 MaaCore 资源 stages.json，随更新自动生效） */
function buildStagePicker(value, attrs = {}, onChange) {
  return buildPicker(value, attrs, onChange, () => (state.stageOptions || []).map((s) => ({
    value: s.code,
    label: s.code,
    sub: `${s.drops && s.drops.length ? s.drops.map((d) => d.name).slice(0, 2).join('、') : ''}${s.apCost ? ` · ${s.apCost}理智` : ''}`,
  })));
}

/* ---------------- about / readme ---------------- */

function mdEscape(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function mdInline(s) {
  return mdEscape(s)
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

/* 极简 markdown 渲染（README 使用子集：标题/列表/代码块/表格/段落） */
function renderMarkdown(md) {
  const root = document.createElement('div');
  const lines = String(md || '').split(/\r?\n/);
  let i = 0;
  const push = (el) => { if (el) root.append(el); };
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++;
      const pre = elt('pre', { class: 'readme-code' }, buf.join('\n'));
      push(pre);
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const el = document.createElement(`h${h[1].length}`);
      el.className = 'readme-heading';
      el.innerHTML = mdInline(h[2]);
      push(el);
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const ul = document.createElement('ul');
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        const li = document.createElement('li');
        li.innerHTML = mdInline(lines[i].replace(/^\s*[-*]\s+/, ''));
        ul.append(li);
        i++;
      }
      push(ul);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const ol = document.createElement('ol');
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        const li = document.createElement('li');
        li.innerHTML = mdInline(lines[i].replace(/^\s*\d+\.\s+/, ''));
        ol.append(li);
        i++;
      }
      push(ol);
      continue;
    }
    if (line.trim().startsWith('|') && lines[i + 1] && /^\s*\|[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
      const table = elt('table', { class: 'readme-table' });
      const headRow = elt('tr');
      for (const c of line.trim().replace(/^\||\|$/g, '').split('|')) headRow.append(elt('th', {}, mdInline(c.trim())));
      const thead = elt('thead', {}, headRow);
      table.append(thead);
      i += 2;
      const tbody = elt('tbody');
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const tr = elt('tr');
        for (const c of lines[i].trim().replace(/^\||\|$/g, '').split('|')) tr.append(elt('td', {}, mdInline(c.trim())));
        tbody.append(tr);
        i++;
      }
      table.append(tbody);
      push(table);
      continue;
    }
    if (line.trim() === '') { i++; continue; }
    const p = document.createElement('p');
    p.innerHTML = mdInline(line);
    push(p);
    i++;
  }
  return root;
}

async function loadAbout() {
  const box = $('#readme-content');
  if (!box) return;
  try {
    const res = await fetch('README.md', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const md = await res.text();
    box.innerHTML = '';
    box.append(renderMarkdown(md));
  } catch {
    box.textContent = 'README.md 加载失败';
  }
}

/* 肉鸽数据（分队/干员，随主题变化） */
async function loadRoguelikeData(theme) {
  try {
    const res = await api(`/api/roguelike?theme=${encodeURIComponent(theme || 'Sarkaz')}`);
    state.roguelikeData = res;
  } catch {
    state.roguelikeData = { squads: [], groups: [], operators: [] };
  }
}

/* 队列侧抄作业：作业列表渲染——勾选即保存到 copilot_list，取消即移除 */
/* 选择本地作业 JSON 文件上传到服务器，onDone 回调接收 {path, items} */
function uploadCopilotFile(onDone) {
  const input = elt('input', { type: 'file', accept: '.json,application/json', style: 'display:none' });
  input.addEventListener('change', async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      const res = await api('/api/copilot/upload', { method: 'POST', body: JSON.stringify({ content: text }) });
      toast(`已上传作业：${(res.items || []).map((it) => it.stage).join('、') || file.name}`, 'success');
      if (onDone) onDone(res);
    } catch (err) {
      toast(`上传失败：${err.message}`, 'error');
    } finally {
      input.remove();
    }
  });
  document.body.append(input);
  input.click();
}

function copilotUriMap() {  try { return JSON.parse(localStorage.getItem('maa-web-copilot-uri-map') || '{}'); } catch { return {}; }
}
function saveCopilotUriMap(map) {
  try { localStorage.setItem('maa-web-copilot-uri-map', JSON.stringify(map)); } catch { /* ignore */ }
}

function renderQueueCopilotList(box, items, item) {
  box.innerHTML = '';
  if (!items.length) { box.append(elt('div', { class: 'muted', style: 'padding:8px' }, '未解析到作业')); return; }
  const uriMap = copilotUriMap();
  const existing = new Set((item.params.copilot_list || []).map((r) => r.filename));
  const list = elt('div', { class: 'copilot-list-inner' });
  const setAll = (v) => list.querySelectorAll('input[type=checkbox]').forEach((c) => { c.checked = v; c.dispatchEvent(new Event('change', { bubbles: true })); });
  const head = elt('div', { class: 'copilot-list-head' }, [
    elt('span', { class: 'copilot-count' }, `共 ${items.length} 项`),
    elt('div', { class: 'spacer' }),
    elt('button', { class: 'btn xs', type: 'button', onclick: () => setAll(true) }, '全选'),
    elt('button', { class: 'btn xs', type: 'button', onclick: () => setAll(false) }, '取消全选'),
  ]);
  for (const it of items) {
    const savedPath = uriMap[it.uri];
    const row = elt('label', { class: 'copilot-item' }, [
      elt('input', { type: 'checkbox', 'data-uri': it.uri, 'data-stage': it.stage || '' }),
      elt('span', { class: 'copilot-stage' }, it.stage || it.uri),
      ...(it.author ? [elt('span', { class: 'copilot-meta' }, `作者 ${it.author}${it.views ? ` · ${it.views} 浏览` : ''}`)] : []),
    ]);
    const cb = row.querySelector('input');
    cb.checked = !!savedPath && existing.has(savedPath);
    cb.addEventListener('change', async () => {
      try {
        item.params = item.params || {};
        const rows = item.params.copilot_list || [];
        if (cb.checked) {
          const r = await api('/api/copilot/download', { method: 'POST', body: JSON.stringify({ input: it.uri }) });
          if (r.items && r.items.length) {
            const row = r.items[0];
            uriMap[it.uri] = row.path;
            saveCopilotUriMap(uriMap);
            rows.push({ filename: row.path, stage_name: row.stage, is_raid: false });
            item.params.copilot_list = rows;
            toast(`已添加作业 ${row.stage}`, 'success');
          } else {
            cb.checked = false;
            toast('该作业无法保存', 'error');
          }
        } else {
          const path = uriMap[it.uri];
          if (path) item.params.copilot_list = rows.filter((r) => r.filename !== path);
        }
        autosaveQueue();
      } catch (err) {
        cb.checked = !cb.checked;
        toast(`操作失败：${err.message}`, 'error');
      }
    });
    list.append(row);
  }
  box.append(head, list);
}

/* 队列侧抄作业：本地作业文件列表 */
async function loadCopilotFiles() {
  try {
    const res = await api('/api/copilot/files');
    state.copilotFiles = res.files || [];
  } catch {
    state.copilotFiles = [];
  }
}

/* 抄作业：作业列表持久化（常驻） */
function saveCopilotJobs(items) {
  state.copilotJobs = items || [];
  try { localStorage.setItem('maa-web-copilot-jobs', JSON.stringify(items || [])); } catch { /* ignore */ }
}

function loadCopilotJobs() {
  if (state.copilotJobs) return state.copilotJobs;
  try { return JSON.parse(localStorage.getItem('maa-web-copilot-jobs') || 'null'); } catch { return null; }
}

function copilotCheckedState() {
  try { return JSON.parse(localStorage.getItem('maa-web-copilot-checked') || 'null'); } catch { return null; }
}

/* 抄作业：解析作业并展示列表（作业集自动展开） */
async function loadCopilotPreview(value) {
  const box = $('#quick-copilot-list');
  if (!box) return;
  const first = String(value || '').trim().split(/\n/)[0];
  if (!first) { box.innerHTML = ''; return; }
  box.innerHTML = '<div class="copilot-loading">正在获取作业…</div>';
  try {
    const res = await api('/api/copilot/preview', { method: 'POST', body: JSON.stringify({ input: first }) });
    saveCopilotJobs(res.items || []);
    renderCopilotList(box, res);
  } catch (err) {
    box.innerHTML = '';
    const errDiv = elt('div', { class: 'copilot-err' }, `作业获取失败：${err.message}`);
    box.append(errDiv);
  }
}

function renderCopilotList(box, data) {
  const items = data.items || [];
  box.innerHTML = '';
  if (!items.length) {
    box.append(elt('div', { class: 'muted', style: 'padding:8px' }, '未解析到作业'));
    return;
  }
  const savedChecked = copilotCheckedState();
  const list = elt('div', { class: 'copilot-list-inner' });
  const setAll = (v) => list.querySelectorAll('input[type=checkbox]').forEach((c) => { c.checked = v; saveChecked(); });
  const saveChecked = () => {
    const sel = [...list.querySelectorAll('input[type=checkbox]:checked')].map((c) => c.dataset.uri);
    try { localStorage.setItem('maa-web-copilot-checked', JSON.stringify(sel)); } catch { /* ignore */ }
  };
  const head = elt('div', { class: 'copilot-list-head' }, [
    elt('span', { class: 'copilot-count' }, `共 ${items.length} 项${data.name ? `（${data.name}）` : ''}`),
    elt('div', { class: 'spacer' }),
    elt('button', { class: 'btn xs', type: 'button', onclick: () => setAll(true) }, '全选'),
    elt('button', { class: 'btn xs', type: 'button', onclick: () => setAll(false) }, '取消全选'),
  ]);
  for (const it of items) {
    const row = elt('label', { class: 'copilot-item' }, [
      elt('input', { type: 'checkbox', 'data-uri': it.uri }),
      elt('span', { class: 'copilot-stage' }, it.stage || it.uri),
      ...(it.author ? [elt('span', { class: 'copilot-meta' }, `作者 ${it.author}${it.views ? ` · ${it.views} 浏览` : ''}`)] : []),
      ...(it.description ? [elt('span', { class: 'copilot-desc', title: it.description }, String(it.description).slice(0, 60))] : []),
      ...(it.difficulty && it.difficulty !== '0' ? [elt('span', { class: 'copilot-meta' }, `难度 ${it.difficulty}`)] : []),
    ]);
    const cb = row.querySelector('input');
    if (Array.isArray(savedChecked)) cb.checked = savedChecked.includes(it.uri);
    else cb.checked = true;
    cb.addEventListener('change', saveChecked);
    list.append(row);
  }
  box.append(head, list);
}

/* ---------------- today stages ---------------- */

async function loadTodayStages() {
  const wrap = $('#today-stages');
  if (!wrap) return;
  try {
    const st = await api('/api/stages/today');
    const weekNames = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日'];
    const secs = [];
    if (st.resource && st.resource.length) {
      secs.push(elt('div', { class: 'stages-section' }, [
        elt('div', { class: 'stages-title' }, `今日开放（${weekNames[st.weekDay] || ''}）`),
        elt('div', { class: 'stages-row' }, st.resource.map((s) => stageCard(s.code, s.apCost, s.drops.map((d) => d.name)))),
      ]));
    }
    if (st.activity && st.activity.length) {
      secs.push(elt('div', { class: 'stages-section' }, [
        elt('div', { class: 'stages-title' }, '当期活动'),
        elt('div', { class: 'stages-row' }, st.activity.map((a) => stageCard(a.code, null, a.drops))),
      ]));
    }
    wrap.innerHTML = '';
    if (secs.length) wrap.append(...secs);
  } catch { /* 加载失败不阻塞页面 */ }
}

function stageCard(code, apCost, drops) {
  return elt('button', {
    class: 'stage-card',
    title: '点击填入作战关卡',
    onclick: () => applyStage(code),
  }, [
    elt('span', { class: 'stage-code' }, code),
    ...(apCost ? [elt('span', { class: 'stage-ap' }, `${apCost} 理智`)] : []),
    drops && drops.length ? elt('span', { class: 'stage-drops', title: drops.join('、') }, drops.slice(0, 3).join('、')) : null,
  ]);
}

function applyStage(code) {
  const fight = (state.queue || []).find((t) => t.type === 'Fight');
  if (fight) {
    fight.params = fight.params || {};
    fight.params.stage = code;
    autosaveQueue();
    state.selectedIndex = state.queue.indexOf(fight);
    renderQueueList();
    renderQueueSettings();
    toast(`已在队列「${fight.name}」填入关卡 ${code}`, 'success');
    return;
  }
  state.currentType = 'fight';
  switchView('quick');
  const fill = () => {
    renderQuickForm();
    const input = $('#quick-form [data-name="stage"]');
    if (input) {
      input.value = code;
      toast(`队列中暂无「理智作战」，已在快速任务填入关卡 ${code}`, 'success');
    } else {
      toast(`请选择「理智作战」后输入关卡 ${code}`, 'success');
    }
  };
  if (state.quickSchemas && state.quickSchemas.fight) fill();
  else loadQuickSchemas().then(fill).catch(() => toast('加载任务参数失败', 'error'));
}

/* ---------------- recognition results ---------------- */

const RESULT_META = {
  recruit: { label: '公招', color: '#4f8cff' },
  depot: { label: '仓库', color: '#34d399' },
  operbox: { label: '干员', color: '#fbbf24' },
};

function renderResultsFilter() {
  $$('.results-filter .chip').forEach((c) => c.classList.toggle('active', c.dataset.filter === state.resultsFilter));
}

async function loadResults() {
  try {
    const q = state.resultsFilter ? `?type=${state.resultsFilter}` : '';
    const res = await api(`/api/results${q}`);
    state.results = res.items || [];
    renderResultsList();
    if (state.currentResultId) {
      const still = state.results.some((r) => r.id === state.currentResultId);
      if (!still) { state.currentResultId = null; $('#results-detail').innerHTML = '<div class="results-empty">选择左侧记录查看详情</div>'; }
    }
  } catch (err) {
    $('#results-list').innerHTML = `<div class="results-empty">加载失败：${esc(err.message)}</div>`;
  }
}

function renderResultsList() {
  const list = $('#results-list');
  list.innerHTML = '';
  if (!state.results.length) {
    list.innerHTML = '<div class="results-empty">暂无记录，先运行工具箱识别</div>';
    return;
  }
  for (const item of state.results) {
    const meta = RESULT_META[item.type] || { label: item.type, color: 'var(--muted)' };
    const row = elt('button', {
      class: `result-item${item.id === state.currentResultId ? ' active' : ''}`,
      onclick: () => selectResult(item.id),
    });
    row.append(
      elt('span', { class: 'result-time' }, fmtTime(item.time)),
      elt('div', { class: 'result-summ' }, [
        elt('span', { class: 'result-type', style: `background:${meta.color}22;color:${meta.color};border-color:${meta.color}55` }, meta.label),
        elt('span', { class: 'result-text' }, esc(item.summary || '')),
      ])
    );
    list.append(row);
  }
}

async function selectResult(id) {
  try {
    const res = await api(`/api/results/${id}`);
    state.currentResultId = id;
    renderResultsList();
    renderResultDetail(res.item);
  } catch (err) {
    toast(err.message, 'error');
  }
}

function renderResultDetail(item) {
  const box = $('#results-detail');
  box.innerHTML = '';
  const head = elt('div', { class: 'results-detail-head' });
  const meta = RESULT_META[item.type] || { label: item.type, color: 'var(--muted)' };
  head.append(
    elt('div', { class: 'rd-title' }, [
      elt('span', { class: 'result-type', style: `background:${meta.color}22;color:${meta.color};border-color:${meta.color}55` }, meta.label),
      elt('span', {}, esc(item.summary || '')),
    ]),
    elt('div', { class: 'rd-actions' }, [
      elt('span', { class: 'rd-time' }, fmtTime(item.time)),
      elt('button', { class: 'btn sm danger', onclick: async () => { await deleteResult(item.id); } }, '删除'),
    ])
  );
  box.append(head);
  box.append(elt('div', { class: 'results-detail-body' }, [renderDetailBody(item)]));
}

function renderDetailBody(item) {
  if (item.type === 'recruit') return renderRecruitDetail(item.data || {});
  if (item.type === 'depot') return renderDepotDetail(item.data || {});
  if (item.type === 'operbox') return renderOperBoxDetail(item.data || {});
  return elt('div', { class: 'results-empty' }, '未知记录类型');
}

function renderRecruitDetail(data) {
  const tags = Array.isArray(data.tags) ? data.tags : [];
  const combos = Array.isArray(data.combos) ? data.combos : [];
  const wrap = elt('div', {});
  if (tags.length) {
    wrap.append(elt('h4', {}, '识别词条'));
    wrap.append(elt('div', { class: 'chips' }, tags.map((t) => elt('span', { class: 'chip on' }, esc(t)))));
  }
  if (combos.length) {
    wrap.append(elt('h4', {}, '标签组合'));
    const table = elt('table', { class: 'table' });
    table.append(elt('thead', {}, elt('tr', {}, [
      elt('th', {}, '星级'),
      elt('th', {}, '标签'),
      elt('th', {}, '可招募干员'),
    ])));
    const tbody = elt('tbody', {});
    const sorted = [...combos].sort((a, b) => (b.level || 0) - (a.level || 0));
    for (const c of sorted) {
      const ops = (c.opers || []).map((o) => `${esc(o.name)}${o.level ? `<span class="rd-star">★${o.level}</span>` : ''}`).join('、');
      tbody.append(elt('tr', {}, [
        elt('td', {}, c.level ? `★${c.level}` : '-'),
        elt('td', {}, (c.tags || []).map((t) => `<span class="chip on">${esc(t)}</span>`).join('')),
        elt('td', {}, ops || '-'),
      ]));
    }
    table.append(tbody);
    wrap.append(table);
  }
  if (!tags.length && !combos.length) wrap.append(elt('div', { class: 'results-empty' }, '无数据'));
  return wrap;
}

function renderDepotDetail(data) {
  const entries = Array.isArray(data.entries) ? data.entries : [];
  const sorted = [...entries].sort((a, b) => (b.count || 0) - (a.count || 0));
  const wrap = elt('div', {});
  wrap.append(elt('div', { class: 'rd-stat' }, `共 ${entries.length} 种材料，总数量 ${sorted.reduce((s, e) => s + (e.count || 0), 0)}`));
  const table = elt('table', { class: 'table' });
  table.append(elt('thead', {}, elt('tr', {}, [elt('th', {}, '材料'), elt('th', {}, 'ID'), elt('th', {}, '数量')])));
  const tbody = elt('tbody', {});
  for (const e of sorted) {
    tbody.append(elt('tr', {}, [
      elt('td', {}, esc(e.name || '-')),
      elt('td', { class: 'muted' }, esc(String(e.id))),
      elt('td', {}, esc(String(e.count))),
    ]));
  }
  table.append(tbody);
  wrap.append(table);
  return wrap;
}

function renderOperBoxDetail(data) {
  const byRarity = data.byRarity || {};
  const wrap = elt('div', {});
  wrap.append(elt('div', { class: 'rd-stat' }, `已拥有 ${data.owned ?? 0} / ${data.total ?? 0} 名干员`));
  const rarities = Object.keys(byRarity).map(Number).sort((a, b) => b - a);
  if (!rarities.length) wrap.append(elt('div', { class: 'results-empty' }, '无数据'));
  for (const r of rarities) {
    const ops = byRarity[r] || [];
    wrap.append(elt('div', { class: 'rd-rarity' }, [
      elt('span', { class: 'rd-star-badge' }, `${r}★`),
      elt('span', { class: 'muted' }, `${ops.length} 名`),
    ]));
    const chips = elt('div', { class: 'chips' });
    for (const o of ops) {
      const parts = [esc(o.name || '-')];
      if (o.elite != null) parts.push(`精英${o.elite}`);
      if (o.level != null) parts.push(`LV${o.level}`);
      if (o.potential != null) parts.push(`潜${o.potential}`);
      chips.append(elt('span', { class: 'chip' }, parts.join(' ')));
    }
    wrap.append(chips);
  }
  return wrap;
}

async function deleteResult(id) {
  if (!confirm('确定删除这条识别记录？')) return;
  try {
    await api(`/api/results/${id}`, { method: 'DELETE' });
    state.currentResultId = null;
    $('#results-detail').innerHTML = '<div class="results-empty">选择左侧记录查看详情</div>';
    loadResults();
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------------- schedules ---------------- */

const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];

async function loadSchedules() {
  try {
    const res = await api('/api/schedules');
    state.schedules = res.items || [];
    renderSchedules();
  } catch (err) {
    $('#schedule-list').innerHTML = `<div class="schedule-empty">加载失败：${esc(err.message)}</div>`;
  }
}

async function loadScheduleProfiles() {
  try {
    const res = await api('/api/config/files?dir=profiles');
    state.scheduleProfiles = (res.files || [])
      .filter((f) => f.name.endsWith('.toml'))
      .map((f) => f.name.replace(/\.toml$/, ''));
    const sel = $('#schedule-profile');
    const current = sel.value;
    sel.innerHTML = '<option value="">跟随全局配置</option>';
    for (const p of state.scheduleProfiles) {
      sel.append(elt('option', { value: p }, p));
    }
    if (current) sel.value = current;
  } catch { /* ignore */ }
}

async function loadScheduleConfigs() {
  try {
    const res = await api('/api/configs');
    const sel = $('#schedule-config');
    const current = sel.value;
    sel.innerHTML = '<option value="">跟随当前队列</option>';
    for (const c of res.items || []) {
      sel.append(elt('option', { value: c.name }, `${c.name}（${c.queueCount} 项）`));
    }
    if (current) sel.value = current;
  } catch { /* ignore */ }
}

/* ---------------- 配置快照（多套队列配置切换） ---------------- */

async function loadConfigs() {
  try {
    const res = await api('/api/configs');
    state.configs = res.items || [];
    renderConfigs();
  } catch (err) {
    $('#config-list').innerHTML = `<div class="empty">加载失败：${esc(err.message)}</div>`;
  }
}

function renderConfigs() {
  const box = $('#config-list');
  box.innerHTML = '';
  if (!state.configs.length) {
    box.append(elt('div', { class: 'empty' }, '暂无已保存的配置。设置好任务队列后，输入名称点「保存当前队列为配置」。'));
    return;
  }
  for (const c of state.configs) {
    const row = elt('div', { class: 'config-row' }, [
      elt('div', { class: 'config-info' }, [
        elt('b', {}, esc(c.name)),
        elt('span', { class: 'muted' }, `${c.queueCount} 项任务${c.profile ? ' · 连接配置 ' + esc(c.profile) : ''}${c.updatedAt ? ' · 更新于 ' + fmtTime(c.updatedAt) : ''}`),
      ]),
      elt('div', { class: 'toolbar' }, [
        elt('button', { class: 'btn sm', onclick: () => applyConfigByName(c.name) }, '切换到此配置'),
        elt('button', { class: 'btn sm danger', onclick: () => deleteConfigByName(c.name) }, '删除'),
      ]),
    ]);
    box.append(row);
  }
}

async function saveConfig() {
  const name = $('#config-name').value.trim();
  if (!name) { toast('请填写配置名称', 'error'); return; }
  try {
    await api('/api/configs', { method: 'POST', body: JSON.stringify({ name }) });
    $('#config-name').value = '';
    toast(`已保存配置「${name}」`, 'success');
    loadConfigs();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function applyConfigByName(name) {
  if (!confirm(`切换到此配置？当前队列内容将被覆盖（${name}）`)) return;
  try {
    const r = await api(`/api/configs/${encodeURIComponent(name)}/apply`, { method: 'POST' });
    toast(`已切换到配置「${name}」（${r.queueCount} 项）`, 'success');
    loadQueue();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteConfigByName(name) {
  if (!confirm(`确定删除配置「${name}」？`)) return;
  try {
    await api(`/api/configs/${encodeURIComponent(name)}`, { method: 'DELETE' });
    toast('已删除', 'success');
    loadConfigs();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function renderSchedules() {
  const list = $('#schedule-list');
  list.innerHTML = '';
  if (!state.schedules.length) {
    list.innerHTML = '<div class="schedule-empty">暂无定时任务，点击右上角「新增定时任务」创建</div>';
    return;
  }
  for (const s of state.schedules) {
    const wdText = s.weekdays.length === 7 || !s.weekdays.length
      ? '每天'
      : s.weekdays.map((w) => `周${WEEKDAY_LABELS[w - 1]}`).join('、');
    const nextText = s.enabled && s.nextRun ? `下次：${fmtTime(s.nextRun)}` : '已停用';
    const card = elt('div', { class: `schedule-card${s.enabled ? '' : ' disabled'}` });
    card.append(
      elt('div', { class: 'schedule-top' }, [
        elt('div', { class: 'schedule-name' }, [
          esc(s.name),
          elt('span', { class: 'schedule-next' }, nextText),
        ]),
        elt('label', { class: 'chk' }, [
          elt('input', { type: 'checkbox', checked: s.enabled, onchange: (e) => toggleSchedule(s.id, e.target.checked) }),
          elt('span', {}, s.enabled ? '已启用' : '已停用'),
        ]),
      ]),
      elt('div', { class: 'schedule-row' }, [esc(wdText)]),
      elt('div', { class: 'schedule-times-row' }, s.times.map((t) => elt('span', { class: 'chip on' }, esc(t)))),
      elt('div', { class: 'schedule-actions' }, [
        elt('button', { class: 'btn sm', onclick: () => openScheduleModal(s.id) }, '编辑'),
        elt('button', { class: 'btn sm danger', onclick: () => deleteSchedule(s.id) }, '删除'),
      ])
    );
    list.append(card);
  }
}

async function toggleSchedule(id, enabled) {
  try {
    await api(`/api/schedules/${id}`, { method: 'POST', body: JSON.stringify({ enabled }) });
    loadSchedules();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteSchedule(id) {
  if (!confirm('确定删除这个定时任务？')) return;
  try {
    await api(`/api/schedules/${id}`, { method: 'DELETE' });
    loadSchedules();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function openScheduleModal(id = '') {
  const item = id ? state.schedules.find((s) => s.id === id) : null;
  state.scheduleForm = {
    id: id || '',
    name: item ? item.name : '',
    weekdays: item ? [...item.weekdays] : [],
    times: item ? [...item.times] : [],
    profile: item ? item.profile : '',
    config: item ? item.config : '',
    postAction: item ? item.postAction : '',
  };
  $('#schedule-modal-title').textContent = item ? '编辑定时任务' : '新增定时任务';
  $('#schedule-name').value = state.scheduleForm.name;
  $('#schedule-name').addEventListener('input', () => { state.scheduleForm.name = $('#schedule-name').value; });
  loadScheduleProfiles().then(() => {
    $('#schedule-profile').value = state.scheduleForm.profile;
  });
  loadScheduleConfigs().then(() => {
    $('#schedule-config').value = state.scheduleForm.config;
  });
  $('#schedule-post-action').value = state.scheduleForm.postAction;
  renderWeekdayPicker();
  renderScheduleTimes();
  $('#schedule-modal').showModal();
}

function renderWeekdayPicker() {
  const box = $('#schedule-weekdays');
  box.innerHTML = '';
  for (let w = 1; w <= 7; w++) {
    const on = state.scheduleForm.weekdays.includes(w);
    box.append(elt('span', {
      class: `chip${on ? ' on' : ''}`,
      onclick: () => {
        const set = state.scheduleForm.weekdays;
        if (on) state.scheduleForm.weekdays = set.filter((x) => x !== w);
        else state.scheduleForm.weekdays = [...set, w].sort((a, b) => a - b);
        renderWeekdayPicker();
      },
    }, WEEKDAY_LABELS[w - 1]));
  }
}

function renderScheduleTimes() {
  const box = $('#schedule-times');
  box.innerHTML = '';
  if (!state.scheduleForm.times.length) {
    box.append(elt('span', { class: 'muted' }, '未设置执行时间'));
    return;
  }
  for (const t of state.scheduleForm.times) {
    box.append(elt('span', {
      class: 'chip on schedule-times-chip',
      title: '点击删除',
      onclick: () => {
        state.scheduleForm.times = state.scheduleForm.times.filter((x) => x !== t);
        renderScheduleTimes();
      },
    }, esc(t)));
  }
}

function addScheduleTime() {
  const input = $('#schedule-time-input');
  const value = input.value;
  if (!value) { toast('请先选择时间'); return; }
  if (state.scheduleForm.times.includes(value)) { toast('该时间已添加'); return; }
  state.scheduleForm.times.push(value);
  renderScheduleTimes();
}

async function saveSchedule() {
  const f = state.scheduleForm;
  const name = $('#schedule-name').value.trim();
  const body = {
    name,
    weekdays: f.weekdays,
    times: f.times,
    profile: $('#schedule-profile').value,
    config: $('#schedule-config').value,
    postAction: $('#schedule-post-action').value,
  };
  if (!body.name) { toast('请填写任务名称', 'error'); return; }
  if (!body.times.length) { toast('请至少添加一个执行时间', 'error'); return; }
  try {
    const path = f.id ? `/api/schedules/${f.id}` : '/api/schedules';
    const method = f.id ? 'POST' : 'POST';
    await api(path, { method, body: JSON.stringify(body) });
    $('#schedule-modal').close();
    toast(f.id ? '已保存' : '已创建', 'success');
    loadSchedules();
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------------- config ---------- */

async function loadConfigFiles() {
  const dir = $('#config-dir-select').value;
  const data = await api(`/api/config/files?dir=${dir}`);
  $('#config-dir-hint').textContent = data.dir || '';
  const list = $('#config-file-list');
  list.innerHTML = '';
  if (!data.files.length) {
    list.append(elt('div', { class: 'file-item' }, elt('div', { class: 'name' }, '(暂无文件)')));
    return;
  }
  for (const f of data.files) {
    const item = elt('div', { class: 'file-item' }, [
      elt('div', { class: 'name' }, f.name),
      elt('div', { class: 'meta' }, `${(f.size / 1024).toFixed(1)} KB`),
      elt('div', { class: 'actions' }, [
        elt('button', { class: 'btn', onclick: () => editConfigFile(dir, f.name) }, '编辑'),
      ]),
    ]);
    list.append(item);
  }
}

async function editConfigFile(dir, name) {
  const rel = dir === 'root' ? name : `${dir}/${name}`;
  try {
    const data = await api(`/api/config/file?path=${rel}`);
    const panel = $('#config-editor-panel');
    panel.style.display = '';
    $('#config-editor-title').textContent = `编辑: ${rel}`;
    const ta = $('#config-editor');
    ta.value = data.content;
    ta.dataset.path = rel;
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function newConfigFile() {
  const dir = $('#config-dir-select').value;
  const name = prompt('新文件名（含扩展名，如 profile.toml）：');
  if (!name) return;
  if (/[/\\]|\.\./.test(name)) return toast('非法文件名', 'error');
  const rel = dir === 'root' ? name : `${dir}/${name}`;
  try {
    await api('/api/config/file', { method: 'POST', body: JSON.stringify({ path: rel, content: '' }) });
    toast('已创建', 'success');
    await loadConfigFiles();
    editConfigFile(dir, name);
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function saveConfigFile() {
  const ta = $('#config-editor');
  try {
    await api('/api/config/file', { method: 'POST', body: JSON.stringify({ path: ta.dataset.path, content: ta.value }) });
    toast('已保存', 'success');
    await loadConfigFiles();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function loadConnection() {
  try {
    const c = await api('/api/connection');
    $('#conn-adb').value = c.adb_path || '';
    $('#conn-address').value = c.address || '';
    $('#conn-touch').value = c.touch_mode || 'MaaTouch';
    $('#conn-preset').value = c.preset || '';
    $('#conn-deploy-pause').checked = c.deployment_with_pause === true || c.deployment_with_pause === 'true';
    $('#conn-adb-lite').checked = c.adb_lite_enabled === true || c.adb_lite_enabled === 'true';
    $('#conn-kill-adb').checked = c.kill_adb_on_exit === true || c.kill_adb_on_exit === 'true';
    $('#conn-user-res').checked = c.user_resource === true || c.user_resource === 'true';
    $('#conn-cpu-ocr').checked = c.cpu_ocr === false || c.cpu_ocr === 'false' ? false : true;
    if (c.file) $('#config-dir-hint').textContent = `连接配置: ${c.file}`;
  } catch { /* ignore */ }
}

async function saveConnection() {
  const body = {
    adb_path: $('#conn-adb').value.trim(),
    address: $('#conn-address').value.trim(),
    touch_mode: $('#conn-touch').value,
    preset: $('#conn-preset').value,
    deployment_with_pause: $('#conn-deploy-pause').checked,
    adb_lite_enabled: $('#conn-adb-lite').checked,
    kill_adb_on_exit: $('#conn-kill-adb').checked,
    user_resource: $('#conn-user-res').checked,
    cpu_ocr: $('#conn-cpu-ocr').checked,
  };
  try {
    const res = await api('/api/connection', { method: 'POST', body: JSON.stringify(body) });
    toast(`已保存到 ${res.file}`, 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------------- logs ---------------- */

const LOG_MAX = 2000;
const LOG_SHOWN = 500;
let followTail = true;

function logTime() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function renderSideLog() {
  const view = $('#side-log-output');
  const lines = state.logLines.slice(-LOG_SHOWN);
  view.innerHTML = '';
  for (const l of lines) {
    view.append(elt('div', { class: `l-${l.cls}` }, [elt('span', { class: 'log-ts' }, `[${l.ts}]`), l.line]));
  }
  const count = $('#side-log-count');
  if (count) count.textContent = `共 ${state.logLines.length} 行`;
  view.scrollTop = view.scrollHeight;
  followTail = true;
}

function appendLog(line, cls = 'info') {
  state.logLines.push({ line, cls, ts: logTime() });
  if (state.logLines.length > LOG_MAX) state.logLines.shift();
  const view = $('#side-log-output');
  if (!view) return;
  if (view.children.length >= LOG_SHOWN) view.removeChild(view.firstChild);
  view.append(elt('div', { class: `l-${cls}` }, [elt('span', { class: 'log-ts' }, `[${state.logLines[state.logLines.length - 1].ts}]`), line]));
  if (followTail) view.scrollTop = view.scrollHeight;
  const count = $('#side-log-count');
  if (count) count.textContent = `共 ${state.logLines.length} 行`;
}

function toggleSideLog(force) {
  const panel = $('#side-log');
  const open = force !== undefined ? force : panel.hidden;
  panel.hidden = !open;
  if (open) {
    renderSideLog();
    document.body.classList.add('side-log-open');
  } else {
    document.body.classList.remove('side-log-open');
  }
  const dot = $('#side-log-dot');
  if (dot) dot.classList.toggle('on', open);
  const btnText = $('#side-log-btn-text');
  if (btnText) btnText.textContent = open ? '收起日志' : '实时日志';
  try { localStorage.setItem('maa-web-side-log', open ? '1' : '0'); } catch { /* ignore */ }
}

function openSideLog() {
  toggleSideLog(true);
}

function colorClass(line) {
  const l = line.toLowerCase();
  if (l.includes('error') || l.includes('错误') || l.includes('失败')) return 'error';
  if (l.includes('warn') || l.includes('警告')) return 'warn';
  if (l.includes('debug') || l.includes('trace')) return 'debug';
  return 'info';
}

/* ---------------- runner indicator / panel ---------------- */

let runnerElapsedTimer = null;
const rpLines = [];

function fmtElapsed(startIso) {
  const diff = Math.max(0, Date.now() - new Date(startIso).getTime());
  const s = Math.floor(diff / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

function startRunnerElapsed() {
  clearInterval(runnerElapsedTimer);
  runnerElapsedTimer = setInterval(() => {
    if (state.currentRunner && state.currentRunner.startedAt && !$('#runner-panel').hidden) {
      $('#rp-elapsed').textContent = fmtElapsed(state.currentRunner.startedAt);
    }
  }, 1000);
}

function renderRunnerPanel() {
  const runner = state.currentRunner;
  const busy = !!(runner && runner.busy);
  $('#rp-stop-btn').style.display = busy ? '' : 'none';
  $('#rp-out').style.display = busy ? '' : 'none';
  $('#rp-meta').style.display = busy ? '' : 'none';
  $('#rp-title').textContent = busy ? (runner.name || '任务运行中') : (state.lastTaskEnded ? `已完成：${state.lastTaskEnded.name}（退出码 ${state.lastTaskEnded.exitCode}）` : '当前无运行任务');
  if (busy) {
    $('#rp-start').textContent = fmtTime(runner.startedAt);
    $('#rp-elapsed').textContent = fmtElapsed(runner.startedAt);
  }
  renderQueueListInPanel(busy ? runner.queue : null, busy ? runner.results : null, busy);
}

function renderQueueListInPanel(queue, results, running) {
  const qbox = $('#rp-queue');
  const qlist = $('#rp-queue-list');
  const q = Array.isArray(queue) && queue.length ? queue
    : (!running && Array.isArray(state.lastQueueQueue) && state.lastQueueQueue.length) ? state.lastQueueQueue : null;
  if (!q) {
    qbox.hidden = true;
    return;
  }
  if (!running && q) {
    results = results || (state.lastQueueResults ? state.lastQueueResults.results : null);
  }
  qbox.hidden = false;
  const resMap = {};
  for (const r of Array.isArray(results) ? results : []) resMap[r.type] = r;
  qlist.innerHTML = '';
  q.forEach((item, i) => {
    const res = resMap[item.type];
    let mark = '·', cls = 'queued';
    if (!running && res && res.ok === true) { mark = '✓'; cls = 'done'; }
    else if (!running && res && res.ok === false) { mark = '✗'; cls = 'failed'; }
    else if (running && i === 0 && !res) { mark = '●'; cls = 'running'; }
    qlist.append(elt('div', { class: `rp-qitem ${cls}`, title: item.name }, [
      elt('span', { class: 'rp-qmark' }, mark),
      elt('span', { class: 'rp-qname' }, item.name),
    ]));
  });
}

function updateRunnerBadge(runner) {
  state.currentRunner = (runner && runner.busy) ? runner : null;
  const badge = $('#runner-badge');
  const text = $('#runner-badge-text');
  const busy = !!state.currentRunner;
  badge.classList.toggle('running', busy);
  badge.classList.toggle('error', !!state.lastTaskFailed);
  text.textContent = busy ? '运行中' : (state.lastTaskFailed ? '上次失败' : '空闲');
  if (busy) startRunnerElapsed();
  else clearInterval(runnerElapsedTimer);
  renderRunnerPanel();
}

function toggleRunnerPanel(force) {
  const panel = $('#runner-panel');
  const show = force !== undefined ? force : panel.hidden;
  panel.hidden = !show;
  $('#runner-badge').classList.toggle('open', show);
  if (show) {
    const out = $('#rp-out');
    out.innerHTML = '';
    for (const line of rpLines) {
      out.append(elt('div', { class: `l-${colorClass(line)}` }, line));
    }
    out.scrollTop = out.scrollHeight;
    if (state.currentRunner) startRunnerElapsed();
  }
}

let ssePollTimer = null;
let pollSeenLines = new Set();
let pollBoot = true;

function startPolling() {
  if (ssePollTimer) return;
  ssePollTimer = setInterval(pollTick, 5000);
  pollTick();
}

async function pollTick() {
  let st;
  try {
    st = await api('/api/status');
  } catch { return; }
  state.status = st;
  const runner = st.runner || { busy: false };
  const busyNow = !!runner.busy;
  const prevId = state.currentTaskId;
  const task = (st.history || []).find((t) => t.id === runner.id) || null;

  if (busyNow && prevId !== runner.id) {
    state.currentTaskId = runner.id;
    state.lastTaskEnded = null;
    state.lastTaskFailed = false;
    rpLines.length = 0;
    $('#rp-out').textContent = '';
    toggleSideLog(true);
    if (!pollBoot) appendLog(`[任务开始] ${runner.name}`, 'task');
  }

  updateRunnerBadge(runner);

  if (busyNow) {
    try {
      const out = await api(`/api/output?id=${encodeURIComponent(runner.id)}`);
      for (const line of out.lines || []) {
        const key = `${runner.id}:${line}`;
        if (pollSeenLines.has(key)) continue;
        pollSeenLines.add(key);
        appendLog(line, colorClass(line));
        rpLines.push(line);
        if (rpLines.length > 60) rpLines.shift();
      }
    } catch { /* ignore */ }
    if (!$('#runner-panel').hidden) {
      const out = $('#rp-out');
      out.innerHTML = '';
      for (const line of rpLines) {
        out.append(elt('div', { class: `l-${colorClass(line)}` }, line));
      }
      out.scrollTop = out.scrollHeight;
    }
  } else if (prevId && state.currentTaskId === prevId) {
    state.currentTaskId = null;
    const done = task || (st.history || [])[0] || {};
    const ok = done.exitCode === 0;
    state.lastTaskEnded = { name: done.name || '任务', exitCode: done.exitCode ?? null };
    state.lastTaskFailed = !ok;
    if (!pollBoot) {
      appendLog(`[任务结束] ${state.lastTaskEnded.name} — ${ok ? '成功' : `退出码 ${state.lastTaskEnded.exitCode}`}`, ok ? 'info' : 'error');
      if (/公开招募|仓库识别|干员识别/.test(String(state.lastTaskEnded.name || ''))) {
        toast(`「${state.lastTaskEnded.name}」完成，结果已保存，可在「识别结果」页查看`, ok ? 'success' : 'error');
        if ($('#view-recognition').classList.contains('active')) loadResults();
      }
    }
    updateRunnerBadge({ busy: false });
    loadStatus();
    if ($('#view-queue').classList.contains('active')) renderQueueList();
  }

  if (pollSeenLines.size > 3000) pollSeenLines.clear();
  pollBoot = false;
}

/* ---------------- status / settings ---------------- */

async function loadUpdateStatus(force = false) {
  const info = $('#update-info');
  if (!info) return;
  try {
    const st = await api(`/api/update/check${force ? '?force=1' : ''}`);
    const parts = [];
    if (st.cli.hasUpdate) parts.push(`maa-cli ${st.cli.current} → <b>${st.cli.latest}</b>`);
    if (st.core.hasUpdate) parts.push(`MaaCore ${st.core.current} → <b>${st.core.latest}</b>`);
    if (parts.length) {
      info.innerHTML = `有新版本可用：${parts.join('，')}。可点击上方「更新」按钮升级。`;
      info.className = 'update-info has-update';
    } else {
      info.textContent = `当前已是最新版本（maa-cli ${st.cli.current} / MaaCore ${st.core.current}）`;
      info.className = 'update-info';
    }
  } catch {
    info.textContent = '检查更新失败（服务器可能无法访问 GitHub）';
    info.className = 'update-info';
  }
}

function bindUpdateEvents() {
  $('#check-update-btn').addEventListener('click', () => {
    loadUpdateStatus(true);
    toast('正在检查更新…');
  });
  $('#save-proxy-btn').addEventListener('click', async () => {
    try {
      await api('/api/update/proxy', { method: 'POST', body: JSON.stringify({ proxy: $('#update-proxy').value.trim() }) });
      toast('代理已保存', 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  });
  $('#test-proxy-btn').addEventListener('click', async () => {
    const proxy = $('#update-proxy').value.trim();
    const result = $('#proxy-test-result');
    if (!proxy) { result.textContent = '请先填写代理地址'; return; }
    const btn = $('#test-proxy-btn');
    btn.disabled = true;
    result.textContent = '正在通过代理测试 GitHub 连通性…';
    try {
      const r = await api('/api/update/proxy/test', { method: 'POST', body: JSON.stringify({ proxy }) });
      if (r.ok) {
        result.innerHTML = `代理可用：HTTP ${r.code}，耗时 ${r.time.toFixed(1)}s${r.speed ? `，速度 ${(r.speed / 1024).toFixed(1)} KB/s` : ''}`;
        result.className = 'update-info has-update';
      } else {
        result.textContent = `代理不可用：${r.error}`;
        result.className = 'update-info';
      }
    } catch (err) {
      result.textContent = `测试失败：${err.message}`;
      result.className = 'update-info';
    } finally {
      btn.disabled = false;
    }
  });
}

async function loadUpdateProxy() {
  try {
    const r = await api('/api/update/proxy');
    $('#update-proxy').value = r.proxy || '';
  } catch { /* ignore */ }
}

async function loadTokenStatus() {
  try {
    const st = await api('/api/token/status');
    $('#token-status').textContent = `状态：${st.enabled ? '已启用' : '未启用'}`;
    $('#token-status').style.color = st.enabled ? 'var(--ok)' : '';
    const stored = localStorage.getItem('maa-web-token');
    $('#token-holder').hidden = !st.enabled;
    if (st.enabled) {
      $('#token-value').value = stored || '';
      $('#token-current').value = '';
    }
  } catch { /* ignore */ }
}

async function bindTokenEvents() {
  $('#token-generate-btn').addEventListener('click', async () => {
    const btn = $('#token-generate-btn');
    btn.disabled = true;
    try {
      const current = $('#token-current').value.trim();
      const res = await api('/api/token', { method: 'POST', body: JSON.stringify({ currentToken: current }) });
      localStorage.setItem('maa-web-token', res.token);
      $('#token-value').value = res.token;
      $('#token-holder').hidden = false;
      $('#token-status').textContent = '状态：已启用';
      $('#token-status').style.color = 'var(--ok)';
      toast('访问令牌已生成并启用', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
    }
  });
  $('#token-disable-btn').addEventListener('click', async () => {
    if (!confirm('确定关闭访问令牌吗？关闭后局域网内任意设备都可访问')) return;
    try {
      const current = $('#token-current').value.trim();
      await api('/api/token', { method: 'DELETE', body: JSON.stringify({ currentToken: current }) });
      localStorage.removeItem('maa-web-token');
      $('#token-value').value = '';
      $('#token-holder').hidden = true;
      $('#token-status').textContent = '状态：未启用';
      $('#token-status').style.color = '';
      toast('访问令牌已关闭', 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  });
  $('#token-copy-btn').addEventListener('click', () => {
    const v = $('#token-value').value;
    if (!v) return;
    navigator.clipboard.writeText(v).then(() => toast('已复制', 'success')).catch(() => toast('复制失败', 'error'));
  });
}

async function loadStatus() {
  try {
    const st = await api('/api/status');
    state.status = st;
    const lastRun = (st.history || []).find((t) => Array.isArray(t.results) && t.results.length);
    state.lastQueueResults = lastRun ? { at: lastRun.finishedAt, results: lastRun.results } : null;
    const lastQueue = (st.history || []).find((t) => Array.isArray(t.queue) && t.queue.length);
    state.lastQueueQueue = lastQueue ? lastQueue.queue : null;
    state.lastQueueDone = lastQueue ? lastQueue.finishedAt : null;
    const cards = $('#status-cards');
    cards.innerHTML = '';
    const items = [
      ['maa-cli 版本', st.version.cli || '-', ''],
      ['MaaCore 版本', st.version.core || '-', ''],
      ['ADB', st.adb || '未安装', 'small'],
      ['配置目录', st.dirs.config || '-', 'small'],
      ['数据目录', st.dirs.data || '-', 'small'],
      ['日志目录', st.dirs.log || '-', 'small'],
    ];
    for (const [k, v, cls] of items) {
      cards.append(elt('div', { class: 'card' }, [elt('div', { class: 'k' }, k), elt('div', { class: `v ${cls}` }, v)]));
    }
    const tbody = $('#history-table tbody');
    tbody.innerHTML = '';
    const busy = !!(st.runner && st.runner.busy);
    for (const t of st.history || []) {
      const color = t.exitCode === 0 ? 'var(--ok)' : (t.exitCode === null ? 'var(--warn)' : 'var(--err)');
      const text = t.exitCode === 0 ? '完成' : (t.exitCode === null ? '中断' : `失败(${t.exitCode})`);
      tbody.append(elt('tr', {}, [
        elt('td', {}, t.name),
        elt('td', { style: `color:${color}` }, text),
        elt('td', {}, fmtTime(t.startedAt)),
        elt('td', {}, fmtTime(t.finishedAt)),
        elt('td', {}, String(t.exitCode ?? '-')),
        elt('td', {}, elt('button', {
          class: 'btn xs',
          disabled: busy,
          title: busy ? '有任务运行中' : '使用当前队列配置重新运行',
          onclick: () => {
            toast(`重新运行「${t.name}」…`);
            runQueue();
          },
        }, '重新运行')),
      ]));
    }
    updateRunnerBadge(st.runner);
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function runMaintenance(name) {
  try {
    const res = await api(`/api/${name}`, { method: 'POST' });
    state.currentTaskId = res.id;
    if (name === 'update' || name === 'install' || name === 'self-update') {
      toast('已开始更新…（maa-cli 在后台运行时无实时进度，完成或失败后会在日志显示结果）', 'success');
    } else {
      toast('已开始，可在日志页查看进度', 'success');
    }
    openSideLog();
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------------- device connect / status ---------------- */

let deviceSelected = null;
let deviceScanAdbPath = null;

async function loadDeviceStatus() {
  try {
    const st = await api('/api/device/status');
    renderDeviceStatus(st);
  } catch {
    /* ignore */
  }
}

function renderDeviceStatus(st) {
  const dot = $('#device-dot');
  const txt = $('#device-status-text');
  state.lastDeviceName = st.device ? (st.device.model || st.device.serial) : '';
  if (state.screenOn) $('#screen-device-name').textContent = state.lastDeviceName ? `· ${state.lastDeviceName}` : '';
  if (!st.adb) {
    dot.className = 'dev-dot';
    txt.innerHTML = '<span class="dev-name">未找到 adb</span><span class="dev-sub">点击配置</span>';
  } else if (st.connected && st.device) {
    dot.className = 'dev-dot online';
    const name = st.device.model || st.device.serial;
    txt.innerHTML = `<span class="dev-name">${esc(name)}</span><span class="dev-sub">${esc(st.device.serial)} · 已连接</span>`;
  } else if (st.configured && st.configured.address) {
    dot.className = 'dev-dot connecting';
    const sub = st.device ? `状态 ${st.device.state}` : '未连接';
    txt.innerHTML = `<span class="dev-name">${esc(st.configured.address)}</span><span class="dev-sub">${sub}</span>`;
  } else {
    dot.className = 'dev-dot';
    txt.innerHTML = '<span class="dev-name">未连接设备</span><span class="dev-sub">点击配置</span>';
  }
  renderDeviceCards(st);
  renderDeviceInstance(st);
}

function renderDeviceCards(st) {
  const wrap = $('#device-current-cards');
  if (!wrap) return;
  wrap.innerHTML = '';
  const connected = st.connected && st.device;
  const stateColor = connected ? 'var(--ok)' : 'var(--err)';
  const stateText = connected ? '已连接' : (st.adb ? (st.device ? `设备 ${st.device.state}` : '未配置设备') : '未找到 adb');
  const items = [
    ['连接状态', stateText, stateColor, ''],
    ['设备', connected ? `${st.device.model || '安卓设备'} (${st.device.serial})` : (st.configured.address || '-'), '', 'small'],
    ['adb', st.adb ? `${st.adb.path} (v${st.adb.version})` : '-', '', 'small'],
    ['触控模式', st.configured.touch_mode || 'MaaTouch', '', ''],
  ];
  for (const [k, v, color, cls] of items) {
    wrap.append(elt('div', { class: 'card' }, [
      elt('div', { class: 'k' }, k),
      elt('div', { class: `v ${cls}`, style: color ? `color:${color}` : '' }, v),
    ]));
  }
}

function openScrcpyWindow() {
  api('/api/connection').then((conn) => {
    const addr = conn && conn.address;
    if (!addr) return toast('请先在「设备连接」页连接设备', 'error');
    const base = `http://${location.hostname}:8000`;
    const theme = localStorage.getItem('maa-web-theme') || 'dark';
    window.open(`${base}/#!/?action=stream&udid=${encodeURIComponent(addr)}&theme=${encodeURIComponent(theme)}`, '_blank');
  }).catch((err) => toast(err.message, 'error'));
}

function renderDeviceInstance(st) {
  const card = $('#device-instance-card');
  if (!card) return;
  const connected = st.connected && st.device;
  card.innerHTML = '';

  const left = elt('div', { class: 'inst-left' }, [
    elt('div', { class: 'inst-dot-row' }, [
      elt('span', { class: `inst-dot${connected ? ' online' : ''}` }),
      elt('b', {}, connected ? (st.device.model || st.device.serial) : (st.configured.address || '未连接设备')),
    ]),
    elt('div', { class: 'inst-meta' }, [
      connected ? `序列号 ${st.device.serial}` : (st.adb ? (st.device ? `设备状态 ${st.device.state}` : '未配置设备') : '未找到 adb'),
      `触控 ${st.configured.touch_mode || 'MaaTouch'}`,
      st.adb ? `${st.adb.path} v${st.adb.version}` : '',
    ].filter(Boolean).join(' · ')),
  ]);

  const shot = elt('div', { class: 'inst-shot' });
  if (connected) {
    const img = elt('img', { src: `/api/device/screen?t=${Date.now()}`, alt: '实时画面', loading: 'lazy' });
    img.onerror = () => { shot.innerHTML = '<div class="empty">画面不可用</div>'; };
    shot.append(img);
  } else {
    shot.append(elt('div', { class: 'empty' }, '连接设备后显示实时画面'));
  }

  const busy = state.status && state.status.busy;
  const runnerName = state.currentRunner ? state.currentRunner.name : '';
  const right = elt('div', { class: 'inst-right' }, [
    elt('div', { class: 'inst-task' }, [
      elt('b', {}, busy ? '任务运行中' : '空闲'),
      elt('span', { class: 'muted' }, runnerName || (busy ? '队列任务执行中…' : '当前无运行任务')),
    ]),
    elt('div', { class: 'toolbar', style: 'flex-wrap:wrap' }, [
      elt('button', { class: 'btn', onclick: openScrcpyWindow }, '远程控制'),
      elt('button', { class: 'btn', onclick: () => toggleScreen() }, '全屏画面'),
      elt('button', { class: 'btn', onclick: () => switchView('config') }, '连接配置'),
    ]),
  ]);

  card.append(left, shot, right);
}

async function deviceScan() {
  const btn = $('#device-scan-btn');
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = '扫描中…';
  try {
    const res = await api('/api/adb/detect', { method: 'POST' });
    deviceSelected = null;
    deviceScanAdbPath = res.adb ? res.adb.path : null;
    const stateEl = $('#device-scan-state');
    const list = $('#device-scan-list');
    list.innerHTML = '';
    if (!res.adb) {
      stateEl.textContent = res.hint || '未找到 adb';
      stateEl.className = 'adb-state warn';
      $('#device-auto-apply-wrap').style.display = 'none';
      return;
    }
    stateEl.textContent = `adb: ${res.adb.path} (v${res.adb.version}) — 检测到 ${res.devices.length} 台设备`;
    stateEl.className = 'adb-state ok';
    if (!res.devices.length) {
      list.append(elt('div', { class: 'adb-state warn' }, '未检测到设备，请确认模拟器已启动，或手机已开启 USB 调试并在手机上点击「允许」'));
    }
    for (const d of res.devices) {
      const row = elt('div', { class: 'adb-device', onclick: () => selectDevice(d.serial) }, [
        elt('span', { class: 'serial' }, d.serial),
        d.model ? elt('span', {}, d.model) : null,
        elt('span', { class: 'tag' }, d.emulator ? '模拟器' : '真机'),
        elt('span', { class: d.state === 'device' ? 'tag' : 'state-offline' }, d.state),
      ]);
      row.dataset.serial = d.serial;
      list.append(row);
    }
    $('#device-auto-apply-wrap').style.display = 'block';
  } catch (err) {
    $('#device-scan-state').textContent = `扫描失败：${err.message}`;
    $('#device-scan-state').className = 'adb-state warn';
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

function selectDevice(serial) {
  deviceSelected = serial;
  $$('#device-scan-list .adb-device').forEach((row) => {
    row.classList.toggle('selected', row.dataset.serial === serial);
  });
}

async function deviceAutoConnect() {
  if (!deviceSelected) return toast('请先选择一台设备', 'error');
  await deviceConnect({ adb_path: deviceScanAdbPath, address: deviceSelected, touch_mode: 'MaaTouch' });
}

async function deviceManualConnect() {
  const address = $('#device-manual-address').value.trim();
  if (!address) return toast('请输入设备地址', 'error');
  await deviceConnect({
    address,
    adb_path: $('#device-manual-adb').value.trim(),
    touch_mode: $('#device-manual-touch').value,
  });
}

async function deviceConnect(body) {
  const btn = document.activeElement;
  const orig = btn && btn.textContent;
  if (btn && btn.tagName === 'BUTTON') { btn.disabled = true; btn.textContent = '连接中…'; }
  try {
    const res = await api('/api/device/connect', { method: 'POST', body: JSON.stringify(body) });
    if (res.connected) {
      toast(`已连接 ${res.device.model || res.device.serial}`, 'success');
    } else {
      toast(res.warning || '连接失败', 'error');
    }
    loadDeviceStatus();
    loadDeviceOptions();
  } catch (err) {
    toast(err.message, 'error');
  } finally {
    if (btn && btn.tagName === 'BUTTON') { btn.disabled = false; btn.textContent = orig; }
  }
}

/* ---------------- device resolution ---------------- */

async function loadResolution() {
  try {
    const r = await api('/api/device/resolution', { method: 'POST', body: JSON.stringify({ action: 'get' }) });
    const eff = r.override || r.physical || null;
    $('#res-current').textContent = eff ? `${eff}${r.override ? '（已调整）' : ''}` : (r.raw || '未知');
    const warn = $('#res-warning');
    if (eff && r.supported && !r.supported.includes(eff)) {
      warn.style.display = 'block';
      warn.textContent = `当前分辨率 ${eff} 不受 MAA 支持，任务会报 UnsupportedResolution。请调整为 ${r.supported.join(' / ')}。`;
    } else {
      warn.style.display = 'none';
    }
    return r;
  } catch (err) {
    $('#res-current').textContent = err.message;
    return null;
  }
}

async function resOp(action, width, height, label) {
  try {
    const r = await api('/api/device/resolution', { method: 'POST', body: JSON.stringify({ action, width, height }) });
    const eff = r.override || r.physical;
    if (action === 'reset') toast(`已重置为系统默认分辨率${eff ? `（当前 ${eff}）` : ''}`, 'success');
    else toast(`${label || `分辨率已调整为 ${width}x${height}`}`, 'success');
    await loadResolution();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function resAuto() {
  const btn = $('#res-auto-btn');
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = '调整中…';
  try {
    const r = await loadResolution();
    if (!r) return;
    const eff = r.override || r.physical;
    if (!eff) return toast('无法读取当前分辨率', 'error');
    if (r.supported.includes(eff)) return toast(`当前 ${eff} 已是 MAA 支持的分辨率`, 'success');
    const [cw, ch] = eff.split('x').map(Number);
    let pick = null;
    for (const s of r.supported) {
      const [sw, sh] = s.split('x').map(Number);
      if (sw === cw || sh === ch) { pick = s; break; }
    }
    if (!pick) pick = '1080x1920';
    const [w, h] = pick.split('x');
    await resOp('set', w, h, `已自动调整为 ${pick}（原 ${eff}）`);
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

function bindScrcpyEvents() {
  $('#wsscrcpy-btn').addEventListener('click', openScrcpyWindow);
}

/* ---------------- init ---------------- */

const SCREEN_FPS_OPTIONS = [
  { v: 'unlimited', label: '无限（尽力）', ms: 0 },
  { v: '5', label: '5 帧/秒', ms: 200 },
  { v: '1', label: '1 帧/秒', ms: 1000 },
  { v: '0.2', label: '每 5 秒', ms: 5000 },
  { v: '0.033', label: '每 30 秒', ms: 30000 },
];

function initScreenFpsSelect() {
  const sel = $('#screen-fps-select');
  for (const o of SCREEN_FPS_OPTIONS) {
    sel.append(elt('option', { value: o.v }, o.label));
  }
  sel.value = localStorage.getItem('maa-web-screen-fps') || 'unlimited';
  sel.addEventListener('change', () => {
    localStorage.setItem('maa-web-screen-fps', sel.value);
    if (state.screenOn) toast(`已切换帧率：${SCREEN_FPS_OPTIONS.find((o) => o.v === sel.value).label}`);
  });
}

function screenFpsMs() {
  const v = $('#screen-fps-select').value || 'unlimited';
  const o = SCREEN_FPS_OPTIONS.find((x) => x.v === v);
  return o ? o.ms : 0;
}

function toggleScreen() {
  state.screenOn = !state.screenOn;
  const overlay = $('#screen-overlay');
  const btnText = $('#screen-btn-text');
  const dot = $('#screen-dot');
  overlay.classList.toggle('open', state.screenOn);
  if (state.screenOn) {
    overlay.hidden = false;
    btnText.textContent = '关闭画面';
    dot.classList.add('on');
    if (state.lastDeviceName) $('#screen-device-name').textContent = `· ${state.lastDeviceName}`;
    state.screenFrames = 0;
    state.screenBusy = false;
    screenLoop();
  } else {
    overlay.hidden = true;
    btnText.textContent = '设备画面';
    dot.classList.remove('on');
    state.screenFrames = 0;
    $('#screen-fps').textContent = '-';
    $('#screen-status').classList.remove('show');
  }
}

async function screenLoop() {
  while (state.screenOn) {
    if (state.screenBusy) {
      await sleep(60);
      continue;
    }
    await pollScreenOnce();
    if (!state.screenOn) break;
    const interval = screenFpsMs();
    const elapsed = Date.now() - state.screenFrameAt;
    const waitMs = interval > 0 ? interval - elapsed : 0;
    if (waitMs > 0) await sleep(waitMs);
  }
}

async function pollScreenOnce() {
  if (state.screenBusy || !state.screenOn) return;
  state.screenBusy = true;
  const t0 = Date.now();
  try {
    const token = localStorage.getItem('maa-web-token');
    const headers = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`/api/device/screen?_=${t0}`, { cache: 'no-store', headers });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.error || `HTTP ${res.status}`);
    }
    const url = URL.createObjectURL(await res.blob());
    const img = $('#screen-img');
    const oldUrl = img.src && img.src.startsWith('blob:') ? img.src : null;
    img.src = url;
    if (oldUrl) setTimeout(() => URL.revokeObjectURL(oldUrl), 2000);
    $('#screen-status').classList.remove('show');
    state.screenFrames++;
    const elapsed = Date.now() - t0;
    state.screenFrameAt = Date.now();
    const fps = 1000 / Math.max(1, elapsed);
    state.screenFpsEma = state.screenFpsEma ? state.screenFpsEma * 0.7 + fps * 0.3 : fps;
    $('#screen-fps').textContent = `帧 ${state.screenFrames} · ${state.screenFpsEma.toFixed(1)} fps`;
    if (state.screenDevice !== img.dataset.device) {
      // placeholder for future multi-device; currently global device only
    }
  } catch (err) {
    const st = $('#screen-status');
    st.textContent = `画面获取失败：${err.message}`;
    st.classList.add('show');
  } finally {
    state.screenBusy = false;
  }
}

/* ---------------- theme ---------------- */

function syncAllViews() {
  const active = $('.view.active');
  const name = active ? active.id.replace('view-', '') : '';
  loadStatus();
  if (name === 'queue') loadQueue();
  if (name === 'recognition') loadResults();
  if (name === 'schedule') loadSchedules();
  if (name === 'device') { loadDeviceStatus(); }
}

function applyTheme() {
  const saved = localStorage.getItem('maa-web-theme') || 'dark';
  const media = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)');
  const theme = saved === 'system' ? (media && media.matches ? 'light' : 'dark') : saved;
  if (theme === 'light') document.documentElement.setAttribute('data-theme', 'light');
  else document.documentElement.removeAttribute('data-theme');
}

const PRESET_ACCENTS = [
  ['#4f8cff', '#7c5cff'],
  ['#7c5cff', '#4f8cff'],
  ['#22d3ee', '#4f8cff'],
  ['#34d399', '#22d3ee'],
  ['#fb923c', '#f87171'],
  ['#f472b6', '#fb923c'],
];

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function shadeHex(hex, pct) {
  const [r, g, b] = hexToRgb(hex).map((v) => Math.max(0, Math.min(255, Math.round(v * (1 + pct / 100)))));
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

function applyAccent(hex, hex2) {
  const [r, g, b] = hexToRgb(hex);
  const root = document.documentElement.style;
  root.setProperty('--accent', hex);
  root.setProperty('--accent2', hex2 || shadeHex(hex, -20));
  root.setProperty('--accent-soft', `rgba(${r},${g},${b},.12)`);
  localStorage.setItem('maa-web-accent', hex);
}

function initAccent() {
  const saved = localStorage.getItem('maa-web-accent');
  const swatches = $('#accent-swatches');
  for (const [a, a2] of PRESET_ACCENTS) {
    const s = elt('button', {
      class: 'accent-swatch',
      style: `background:${a}`,
      title: a,
      onclick: () => {
        applyAccent(a, a2);
        $('#accent-custom').value = a;
        renderAccentSwatches();
      },
    });
    s.dataset.hex = a;
    swatches.append(s);
  }
  const custom = $('#accent-custom');
  if (saved && /^#[0-9a-fA-F]{6}$/.test(saved)) {
    applyAccent(saved);
    custom.value = saved;
  }
  custom.addEventListener('input', () => applyAccent(custom.value));
  renderAccentSwatches();
}

function renderAccentSwatches() {
  const saved = localStorage.getItem('maa-web-accent');
  $$('#accent-swatches .accent-swatch').forEach((s) => s.classList.toggle('active', s.dataset.hex === saved));
}

function initTheme() {
  applyTheme();
  const sel = $('#theme-select');
  if (sel) {
    sel.value = localStorage.getItem('maa-web-theme') || 'dark';
    sel.addEventListener('change', () => {
      localStorage.setItem('maa-web-theme', sel.value);
      applyTheme();
    });
  }
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', applyTheme);
  }
}

function bindEvents() {
  $$('.nav-btn').forEach((b) => b.addEventListener('click', () => switchView(b.dataset.view)));
  $('#add-task-btn').addEventListener('click', addTask);
  $('#enable-all-btn').addEventListener('click', () => { state.queue.forEach((t) => (t.enabled = true)); renderQueueList(); renderQueueSettings(); autosaveQueue(); });
  $('#disable-all-btn').addEventListener('click', () => { state.queue.forEach((t) => (t.enabled = false)); renderQueueList(); renderQueueSettings(); autosaveQueue(); });
  $('#queue-save-btn').addEventListener('click', saveQueue);
  $('#queue-run-btn').addEventListener('click', runQueue);
  $('#queue-stop-btn').addEventListener('click', async () => {
    try {
      const res = await api('/api/stop', { method: 'POST' });
      toast(res.stopped ? '已发送停止信号' : '当前无运行任务');
    } catch (err) { toast(err.message, 'error'); }
  });
  $('#quick-run-btn').addEventListener('click', runQuick);
  $('#quick-stop-btn').addEventListener('click', async () => {
    try { await api('/api/stop', { method: 'POST' }); } catch (err) { toast(err.message, 'error'); }
  });
  $('#config-dir-select').addEventListener('change', loadConfigFiles);
  $('#new-file-btn').addEventListener('click', newConfigFile);
  $('#save-config-btn').addEventListener('click', saveConfigFile);
  $('#conn-load-btn').addEventListener('click', loadConnection);
  $('#conn-save-btn').addEventListener('click', saveConnection);
  $('#side-log-output').addEventListener('scroll', () => {
    const v = $('#side-log-output');
    followTail = v.scrollHeight - v.scrollTop - v.clientHeight <= 24;
  });
  $('#side-log-close').addEventListener('click', () => toggleSideLog(false));
  $('#side-log-btn').addEventListener('click', () => toggleSideLog());
  $('#side-log-copy').addEventListener('click', () => {
    const text = state.logLines.map((x) => `[${x.ts}] ${x.line}`).join('\n');
    navigator.clipboard.writeText(text).then(() => toast(`已复制 ${state.logLines.length} 行`, 'success')).catch(() => toast('复制失败', 'error'));
  });
  $('#side-log-clear').addEventListener('click', () => { $('#side-log-output').innerHTML = ''; state.logLines = []; followTail = true; });
  $('#install-core-btn').addEventListener('click', () => runMaintenance('install'));
  $('#update-core-btn').addEventListener('click', () => runMaintenance('update'));
  $('#self-update-btn').addEventListener('click', () => runMaintenance('self-update'));
  $('#device-scan-btn').addEventListener('click', deviceScan);
  $('#device-auto-connect-btn').addEventListener('click', deviceAutoConnect);
  $('#device-manual-connect-btn').addEventListener('click', deviceManualConnect);
  $('#device-badge').addEventListener('click', () => switchView('device'));
  $('#runner-badge').addEventListener('click', () => toggleRunnerPanel());
  $('#screen-btn').addEventListener('click', toggleScreen);
  $('#screen-close').addEventListener('click', toggleScreen);
  $('#screen-overlay').addEventListener('click', (e) => { if (e.target === e.currentTarget) toggleScreen(); });
  $('#rp-close').addEventListener('click', () => toggleRunnerPanel(false));
  $('#rp-stop-btn').addEventListener('click', async () => {
    try {
      const res = await api('/api/stop', { method: 'POST' });
      toast(res.stopped ? '已发送停止信号' : '当前无运行任务', 'success');
    } catch (err) { toast(err.message, 'error'); }
  });
  $('#device-manual-address').addEventListener('keydown', (e) => { if (e.key === 'Enter') deviceManualConnect(); });
  $('#res-auto-btn').addEventListener('click', resAuto);
  $('#res-reset-btn').addEventListener('click', () => resOp('reset'));
  $('#res-refresh-btn').addEventListener('click', loadResolution);
  $('#results-refresh').addEventListener('click', loadResults);
  $$('.results-filter .chip').forEach((c) => c.addEventListener('click', () => {
    state.resultsFilter = c.dataset.filter;
    state.currentResultId = null;
    renderResultsFilter();
    loadResults();
  }));
  $('#schedule-add').addEventListener('click', () => openScheduleModal());
  $('#schedule-close').addEventListener('click', () => $('#schedule-modal').close());
  $('#schedule-cancel').addEventListener('click', () => $('#schedule-modal').close());
  $('#schedule-save').addEventListener('click', saveSchedule);
  $('#schedule-time-add').addEventListener('click', addScheduleTime);
  $('#schedule-time-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); addScheduleTime(); }
  });
  $('#schedule-modal').addEventListener('close', () => { $('#schedule-form').reset(); });
  $('#config-save-btn').addEventListener('click', saveConfig);
}

async function init() {
  initTheme();
  initScreenFpsSelect();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => { /* 不支持时忽略 */ });
  }
  initAccent();
  bindEvents();
  bindScrcpyEvents();
  bindTokenEvents();
  bindUpdateEvents();
  bindTools();
  try { if (localStorage.getItem('maa-web-side-log') === '1') toggleSideLog(true); } catch { /* ignore */ }
  loadStageOptions();
  loadRoguelikeData('Sarkaz');
  loadCopilotFiles();
  startPolling();
  try {
    await Promise.all([loadQueueTypes(), loadQuickSchemas(), loadStatus()]);
    await loadQueue();
  } catch (err) {
    toast(`无法连接后端: ${err.message}`, 'error');
  }
  loadDeviceOptions();
  loadDeviceStatus();
  loadTodayStages();
  loadConfigs();
  setInterval(loadDeviceStatus, 5000);
  setInterval(() => { if ($('#view-queue').classList.contains('active')) loadTodayStages(); }, 600000);
}

init();
