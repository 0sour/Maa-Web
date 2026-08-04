'use strict';

const { spawn } = require('child_process');
const crypto = require('crypto');
const { MAA_BIN, baseEnv } = require('./maa');

function taskInfo(task) {
  return {
    id: task.id,
    name: task.name,
    command: task.command,
    status: task.status,
    startedAt: task.startedAt,
    finishedAt: task.finishedAt,
    exitCode: task.exitCode,
    results: task.results || null,
    queue: task.queue || null,
  };
}

class TaskRunner {
  constructor() {
    this.current = null;
    this.history = [];
    this.maxHistory = 50;
    this.maxOutputLines = 5000;
    this.listeners = new Set();
    this.finishHooks = [];
  }

  onOutput(cb) {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  onFinished(cb) {
    this.finishHooks.push(cb);
  }

  appendOutput(task, line) {
    if (!task || !task.output) return;
    task.output.push(line);
    if (task.output.length > this.maxOutputLines) task.output.shift();
    this.emit({ type: 'task:output', id: task.id, line });
  }

  emit(payload) {
    for (const cb of this.listeners) {
      try {
        cb(payload);
      } catch {
        /* ignore listener errors */
      }
    }
  }

  get status() {
    if (this.current && this.current.status === 'running') {
      return { busy: true, ...taskInfo(this.current) };
    }
    return { busy: false };
  }

  start({ command, name, env = {}, queue = null }) {
    if (this.current && this.current.status === 'running') {
      throw new Error('已有任务在运行中，请先停止或等待其完成');
    }

    const id = crypto.randomUUID();
    const task = {
      id,
      name: name || command.join(' '),
      command,
      status: 'running',
      startedAt: new Date().toISOString(),
      finishedAt: null,
      exitCode: null,
      output: [],
      queue,
      results: null,
    };
    this.current = task;

    this.emit({ type: 'task:start', task: taskInfo(task) });

    const child = spawn(MAA_BIN, command, {
      env: { ...baseEnv(), ...env },
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    const onLine = (chunk) => {
      const text = chunk.toString();
      for (const line of text.split(/\r?\n/)) {
        if (!line) continue;
        task.output.push(line);
        if (task.output.length > this.maxOutputLines) task.output.shift();
        this.emit({ type: 'task:output', id, line });
      }
    };
    child.stdout.on('data', onLine);
    child.stderr.on('data', onLine);

    child.on('error', (err) => {
      task.output.push(`[runner] 启动失败: ${err.message}`);
      this.emit({ type: 'task:output', id, line: `[runner] 启动失败: ${err.message}` });
      this.finish(task);
    });

    child.on('close', (code) => {
      task.exitCode = code;
      this.finish(task);
    });

    task.stop = () => {
      if (child.exitCode === null) {
        child.kill('SIGTERM');
        setTimeout(() => {
          if (child.exitCode === null) child.kill('SIGKILL');
        }, 3000);
      }
    };

    return { id };
  }

  finish(task) {
    task.status = 'finished';
    task.finishedAt = new Date().toISOString();
    for (const fn of this.finishHooks) {
      try { fn(task); } catch { /* ignore hook errors */ }
    }
    this.emit({ type: 'task:end', task: taskInfo(task) });
    this.history.unshift(task);
    if (this.history.length > this.maxHistory) this.history.pop();
    if (this.current === task) this.current = null;
  }

  stop() {
    if (this.current && this.current.status === 'running') {
      this.current.stop();
      return true;
    }
    return false;
  }

  output(id) {
    if (this.current && this.current.id === id) return this.current.output;
    const t = this.history.find((x) => x.id === id);
    return t ? t.output : [];
  }

  info(id) {
    if (this.current && this.current.id === id) return taskInfo(this.current);
    const t = this.history.find((x) => x.id === id);
    return t ? taskInfo(t) : null;
  }
}

module.exports = { runner: new TaskRunner() };
