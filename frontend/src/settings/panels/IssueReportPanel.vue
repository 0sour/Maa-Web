<script setup lang="ts">
/**
 * 问题反馈面板 —— 对齐 MAA 客户端 IssueReportUserControl（PRD §4.4.10）。
 * 导出日志 zip（后端打包 data/logs）。
 */
import { ref } from 'vue'
import { settingsApi } from '@/api/settings'
import './panel.css'

const exporting = ref(false)
const msg = ref('')
const error = ref('')

async function exportLogs() {
  exporting.value = true
  msg.value = ''
  error.value = ''
  try {
    const blob = await settingsApi.exportLogs()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `maaweb-logs-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')}.zip`
    a.click()
    URL.revokeObjectURL(url)
    msg.value = '✔ 日志已导出（zip 压缩包已开始下载）'
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '导出失败'
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="panel-card">
    <div class="card-hd">
      <span class="diamond"></span>
      <b>问题反馈</b>
      <span class="sub">对齐 MAA 客户端 IssueReport · 导出日志压缩包便于排障</span>
    </div>
    <div v-if="error" class="err-bar">⚠ {{ error }}</div>
    <div v-if="msg" class="ok-bar">{{ msg }}</div>

    <div class="f-row">
      <label class="f-label">导出日志<small>打包后端日志目录（data/logs）为 zip 下载</small></label>
      <div class="f-ctrl">
        <button class="btn btn-gold" :disabled="exporting" @click="exportLogs">
          {{ exporting ? '导出中…' : '⤓ 导出日志' }}
        </button>
      </div>
    </div>
    <p class="hint">导出包含任务执行日志（LogEntry 持久化于 SQLite 与 data/logs 目录文件），可用于问题排查与反馈。</p>
  </div>
</template>
