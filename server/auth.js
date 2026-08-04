'use strict';

const path = require('path');
const crypto = require('crypto');
const fsp = require('fs/promises');

let token = '';
let tokenFile = '';

async function init(getTokenFile) {
  tokenFile = await getTokenFile();
  try {
    const j = JSON.parse(await fsp.readFile(tokenFile, 'utf8'));
    token = typeof j.token === 'string' ? j.token : '';
  } catch {
    token = '';
  }
}

function enabled() {
  return !!token;
}

function valid(t) {
  if (!token) return true;
  return !!t && t === token;
}

function extract(req) {
  const h = req.headers['authorization'] || '';
  if (h.startsWith('Bearer ')) return h.slice(7).trim();
  return String(req.query.token || '');
}

function requireToken(req, res, next) {
  if (!token) return next();
  if (req.path.startsWith('/token')) return next();
  if (valid(extract(req))) return next();
  res.status(401).json({ error: '未授权：访问令牌无效' });
}

async function saveToken(t) {
  token = t || '';
  if (!tokenFile) return;
  await fsp.mkdir(path.dirname(tokenFile), { recursive: true });
  await fsp.writeFile(tokenFile, JSON.stringify({ token }, null, 2), 'utf8');
}

async function generate() {
  const t = crypto.randomBytes(24).toString('hex');
  await saveToken(t);
  return t;
}

async function disable() {
  await saveToken('');
}

module.exports = { init, requireToken, enabled, valid, extract, generate, disable };
