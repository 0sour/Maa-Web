'use strict';

const { execFile, spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const MAA_BIN = process.env.MAA_BIN || path.join(__dirname, '..', 'bin', 'maa');
const HOME = os.homedir();

function baseEnv() {
  const env = { ...process.env };
  env.PATH = [path.dirname(MAA_BIN), env.PATH].filter(Boolean).join(path.delimiter);
  return env;
}

function run(args, { timeout = 60000 } = {}) {
  return new Promise((resolve, reject) => {
    execFile(MAA_BIN, args, { env: baseEnv(), timeout }, (err, stdout, stderr) => {
      if (err) {
        err.stdout = stdout;
        err.stderr = stderr;
        return reject(err);
      }
      resolve({ stdout: stdout.trim(), stderr: stderr.trim() });
    });
  });
}

async function version() {
  const out = {};
  try {
    const res = await run(['version']);
    const m = res.stdout.match(/(maa-cli|MaaCore) v?([\w.\-]+)/g) || [];
    for (const line of m) {
      const [name, ver] = line.split(/\s+v?/);
      out[name === 'maa-cli' ? 'cli' : 'core'] = ver;
    }
  } catch {
    /* ignore */
  }
  return out;
}

async function dirs() {
  const result = {};
  for (const d of ['config', 'data', 'log', 'hot-update']) {
    try {
      const res = await run(['dir', d]);
      result[d] = res.stdout;
    } catch {
      result[d] = null;
    }
  }
  return result;
}

async function listTasks() {
  try {
    const res = await run(['list'], { timeout: 30000 });
    return res.stdout.split('\n').filter(Boolean);
  } catch (err) {
    return { error: (err.stderr || err.message).trim() };
  }
}

async function activity(client = 'Official') {
  try {
    const res = await run(['activity', client], { timeout: 60000 });
    return res.stdout;
  } catch (err) {
    return { error: (err.stderr || err.message).trim() };
  }
}

async function adbAvailable() {
  for (const bin of adbCandidates()) {
    const ver = await adbVersion(bin);
    if (ver) return ver;
  }
  return null;
}

/* ---------- adb auto-detection ---------- */

function adbCandidates() {
  const list = ['adb'];
  const common = [
    path.join(__dirname, '..', 'bin', 'platform-tools', 'adb'),
    '/usr/bin/adb',
    '/usr/local/bin/adb',
    '/usr/lib/android-sdk/platform-tools/adb',
    '/usr/lib/android-sdk/adb',
    path.join(HOME, 'Android/Sdk/platform-tools/adb'),
    path.join(HOME, 'android-sdk/platform-tools/adb'),
    path.join(HOME, 'Android/android-sdk/platform-tools/adb'),
    path.join(HOME, 'Library/Android/sdk/platform-tools/adb'),
    '/opt/android-sdk/platform-tools/adb',
    '/opt/android/platform-tools/adb',
    '/opt/MuMuPlayer-12-0/shell/adb',
    '/opt/MuMuPlayer-12-1/shell/adb',
    '/opt/MuMuPlayer-12-2/shell/adb',
    '/opt/MuMuPlayer-12-4/shell/adb',
    '/opt/mumuplayer/shell/adb',
    '/opt/genymotion/tools/adb',
    '/opt/genymotion/arm64/adb',
  ];
  for (const p of common) {
    if (fs.existsSync(p)) list.push(p);
  }
  return list;
}

function adbVersion(bin) {
  return new Promise((resolve) => {
    execFile(bin, ['version'], { env: baseEnv(), timeout: 8000 }, (err, stdout) => {
      if (err) return resolve(null);
      const m = stdout.match(/Version\s+([\d.\-]+)/i);
      resolve(m ? m[1] : (stdout.trim().split('\n')[0] || 'available'));
    });
  });
}

function adbDevices(bin) {
  return new Promise((resolve) => {
    execFile(bin, ['start-server'], { env: baseEnv(), timeout: 15000 }, () => {
      execFile(bin, ['devices', '-l'], { env: baseEnv(), timeout: 15000 }, (err, stdout) => {
        if (err) return resolve([]);
        const out = [];
        for (const line of stdout.split('\n').slice(1)) {
          const parts = line.trim().split(/\s+/);
          if (parts.length >= 2 && parts[0]) {
            const model = parts.find((p) => p.startsWith('model:'));
            const product = parts.find((p) => p.startsWith('product:'));
            const transport = parts.find((p) => p.startsWith('transport_id:'));
            out.push({
              serial: parts[0],
              state: parts[1],
              model: model ? model.slice(6) : (product ? product.slice(8) : ''),
              transport: transport ? transport.slice(13) : '',
              emulator: /^emulator-\d+$/.test(parts[0]) || /^127\.0\.0\.1:\d+$/.test(parts[0]),
            });
          }
        }
        resolve(out);
      });
    });
  });
}

async function detectAdb() {
  const adb = await resolveAdb();
  if (!adb) return { adb: null, devices: [] };
  return { adb, devices: await adbDevices(adb.path) };
}

async function resolveAdb() {
  for (const bin of adbCandidates()) {
    const version = await adbVersion(bin);
    if (version) return { path: bin, version };
  }
  return null;
}

async function adbDeviceStatus(bin, serial) {
  const devices = await adbDevices(bin);
  const dev = devices.find((d) => d.serial === serial);
  return dev ? dev : { serial, state: 'absent', model: '' };
}

async function adbConnect(bin, address) {
  return new Promise((resolve) => {
    execFile(bin, ['connect', address], { env: baseEnv(), timeout: 15000 }, (err, stdout) => {
      resolve(err ? (err.stderr || err.message || '').trim() : (stdout || '').trim());
    });
  });
}

function adbShell(bin, serial, args) {
  return new Promise((resolve) => {
    execFile(bin, ['-s', serial, 'shell', ...args], { env: baseEnv(), timeout: 15000 }, (err, stdout, stderr) => {
      resolve({ ok: !err, out: (stdout || '').trim(), err: (stderr || '').trim() });
    });
  });
}

function screenCapture(bin, serial, timeout = 15000) {
  return new Promise((resolve) => {
    execFile(bin, ['-s', serial, 'exec-out', 'screencap', '-p'], { env: baseEnv(), timeout, encoding: 'buffer', maxBuffer: 32 * 1024 * 1024 }, (err, stdout) => {
      resolve({ ok: !err, png: err ? null : Buffer.from(stdout), err: err ? (err.stderr || err.message || '').trim() : '' });
    });
  });
}

async function getWmSize(bin, serial) {
  const r = await adbShell(bin, serial, ['wm', 'size']);
  const text = `${r.out}\n${r.err}`.trim();
  const m = (re) => { const x = text.match(re); return x ? x[1] : null; };
  return {
    physical: m(/Physical size:\s*(\d+x\d+)/),
    override: m(/Override size:\s*(\d+x\d+)/),
    raw: text || r.err,
    ok: !!r.ok,
  };
}

function isHostPort(address) {
  return /^[a-zA-Z0-9.\-]+:\d{1,5}$/.test(address);
}

const SUPPORTED_RESOLUTIONS = [
  { w: 720, h: 1280, label: '720x1280' },
  { w: 1080, h: 1920, label: '1080x1920' },
  { w: 1440, h: 2560, label: '1440x2560' },
];

module.exports = {
  MAA_BIN, run, version, dirs, listTasks, activity, adbAvailable,
  detectAdb, resolveAdb, adbDeviceStatus, adbConnect, adbShell, getWmSize, screenCapture,
  isHostPort, SUPPORTED_RESOLUTIONS, baseEnv,
};
