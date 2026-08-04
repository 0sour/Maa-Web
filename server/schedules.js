'use strict';

const path = require('path');
const fsp = require('fs/promises');
const crypto = require('crypto');

const TICK_MS = 30000;
const SLOT_TTL_MS = 48 * 3600 * 1000;
const COMPENSATE_MS = 3 * 3600 * 1000;
const TIME_RE = /^([01]?\d|2[0-3]):([0-5]\d)$/;

function fmtSlot(date) {
  const p = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}`;
}

function weekday1(date) {
  const d = date.getDay();
  return d === 0 ? 7 : d;
}

function validate(data) {
  const name = String(data.name || '').trim();
  if (!name) throw new Error('任务名称不能为空');
  const times = Array.isArray(data.times) ? data.times.map(String) : [];
  if (!times.length) throw new Error('至少设置一个执行时间');
  for (const t of times) {
    if (!TIME_RE.test(t)) throw new Error(`时间格式不正确: ${t}`);
  }
  const weekdays = Array.isArray(data.weekdays)
    ? [...new Set(data.weekdays.map(Number))].filter((w) => w >= 1 && w <= 7).sort((a, b) => a - b)
    : [];
  return {
    name,
    times,
    weekdays,
    profile: String(data.profile || '').trim(),
    enabled: data.enabled !== false,
  };
}

class Scheduler {
  constructor() {
    this.items = [];
    this.file = '';
    this.getConfigDir = null;
    this.runDailyQueue = null;
    this.tickAt = 0;
    this.triggered = new Map();
    this.timer = null;
  }

  init({ getConfigDir, runDailyQueue, intervalMs = TICK_MS }) {
    this.getConfigDir = getConfigDir;
    this.runDailyQueue = runDailyQueue;
    this.timer = setInterval(() => this.tick(), intervalMs);
    if (this.timer.unref) this.timer.unref();
    this.tickAt = Date.now();
    this.load().catch(() => {});
  }

  async resolveFile() {
    const dir = await this.getConfigDir();
    return path.join(dir, 'maa-web', 'schedules.json');
  }

  async load() {
    try {
      const text = await fsp.readFile(await this.resolveFile(), 'utf8');
      const parsed = JSON.parse(text);
      if (parsed && Array.isArray(parsed.items)) this.items = parsed.items;
    } catch { /* ignore */ }
  }

  async save() {
    const file = await this.resolveFile();
    await fsp.mkdir(path.dirname(file), { recursive: true });
    await fsp.writeFile(file, JSON.stringify({ version: 1, items: this.items }, null, 2), 'utf8');
  }

  async add(data) {
    const item = { id: crypto.randomUUID(), createdAt: new Date().toISOString(), ...validate(data) };
    this.items.push(item);
    await this.save();
    return item;
  }

  async update(id, data) {
    const item = this.items.find((i) => i.id === id);
    if (!item) return null;
    Object.assign(item, validate({ ...item, ...data }));
    await this.save();
    return item;
  }

  async remove(id) {
    const next = this.items.filter((i) => i.id !== id);
    if (next.length === this.items.length) return false;
    this.items = next;
    this.triggered.delete(id);
    await this.save();
    return true;
  }

  nextRun(item, from = Date.now()) {
    for (let day = 0; day < 8; day++) {
      const d = new Date(from + day * 86400000);
      if (item.weekdays.length && !item.weekdays.includes(weekday1(d))) continue;
      for (const t of item.times) {
        const [h, m] = t.split(':').map(Number);
        const at = new Date(d);
        at.setHours(h, m, 0, 0);
        if (at.getTime() > from) return at;
      }
    }
    return null;
  }

  withNextRuns() {
    const now = Date.now();
    return this.items.map((item) => {
      const next = this.nextRun(item, now);
      return {
        id: item.id,
        name: item.name,
        enabled: item.enabled,
        weekdays: item.weekdays,
        times: item.times,
        profile: item.profile,
        nextRun: next ? next.toISOString() : null,
      };
    });
  }

  tick() {
    const now = Date.now();
    const from = this.tickAt;
    this.tickAt = now;
    for (const item of this.items) {
      if (!item.enabled) continue;
      for (const t of item.times) {
        const [h, m] = t.split(':').map(Number);
        let slot = new Date(from);
        slot.setHours(h, m, 0, 0);
        if (slot.getTime() < from) slot = new Date(slot.getTime() + 86400000);
        while (slot.getTime() < now) {
          if (!item.weekdays.length || item.weekdays.includes(weekday1(slot))) {
            const key = fmtSlot(slot);
            const fired = this.triggered.get(item.id);
            if (!fired) this.triggered.set(item.id, new Set());
            if (!this.triggered.get(item.id).has(key)) {
              this.triggered.get(item.id).add(key);
              if (now - slot.getTime() <= COMPENSATE_MS) {
                this.fire(item, slot).catch(() => {});
              }
            }
          }
          slot = new Date(slot.getTime() + 86400000);
        }
      }
    }
    this.cleanup();
  }

  async fire(item, at) {
    if (!this.runDailyQueue) return;
    try {
      await this.runDailyQueue({ profile: item.profile, name: `[定时] ${item.name}` });
      console.log(`[scheduler] fired ${item.name} at ${fmtSlot(at)}`);
    } catch (err) {
      console.log(`[scheduler] skip ${item.name}: ${err.message}`);
    }
  }

  cleanup() {
    const cutoff = Date.now() - SLOT_TTL_MS;
    for (const [id, set] of this.triggered) {
      for (const key of [...set]) {
        const ts = new Date(key.replace(' ', 'T') + ':00').getTime();
        if (ts < cutoff) set.delete(key);
      }
      if (!set.size) this.triggered.delete(id);
    }
  }
}

module.exports = new Scheduler();
