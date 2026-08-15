<script setup lang="ts">
/**
 * 问题反馈面板 —— 对齐 MAA 客户端 IssueReportUserControl（PRD §4.4.10）。
 * 导出日志 zip（后端打包 data/logs）+ 全量配置导出/导入（备份与恢复）。
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

// ── 全量配置导出 / 导入（备份与恢复；跨机迁移） ──
const exportingCfg = ref(false)
const importingCfg = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

async function exportConfig() {
  exportingCfg.value = true
  msg.value = ''
  error.value = ''
  try {
    const blob = await settingsApi.exportConfig()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `maaweb-config-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')}.zip`
    a.click()
    URL.revokeObjectURL(url)
    msg.value = '✔ 全量配置已导出（含设备/方案/自动任务/账号组/设置，zip 已开始下载）'
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '导出配置失败'
  } finally {
    exportingCfg.value = false
  }
}

function pickImportFile() {
  fileInput.value?.click()
}

async function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const ok = window.confirm(
    '导入配置将覆盖当前全部配置（设备/方案/自动任务/设置等）。\n导入前会自动备份当前配置到后端日志目录。\n确定继续？',
  )
  if (!ok) return
  importingCfg.value = true
  msg.value = ''
  error.value = ''
  try {
    const res = await settingsApi.importConfig(file)
    msg.value = `✔ ${res.message}${res.backup ? `（导入前备份：${res.backup}）` : ''}`
  } catch (e: unknown) {
    error.value =
      (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
      ?? '导入失败'
  } finally {
    importingCfg.value = false
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

    <div class="f-sec">数据备份与恢复</div>
    <div class="f-row">
      <label class="f-label">导出全部配置<small>设备 / 任务方案 / 队列草稿 / 自动任务 / 账号组 / 全部设置 / 镜像源与代理</small></label>
      <div class="f-ctrl">
        <button class="btn btn-gold" :disabled="exportingCfg" @click="exportConfig">
          {{ exportingCfg ? '导出中…' : '⤓ 导出配置' }}
        </button>
      </div>
    </div>
    <div class="f-row">
      <label class="f-label">导入配置<small>覆盖恢复备份（导入前自动备份当前配置；支持 zip 或 json）</small></label>
      <div class="f-ctrl">
        <button class="btn" :disabled="importingCfg" @click="pickImportFile">
          {{ importingCfg ? '导入中…' : '⤒ 导入配置' }}
        </button>
        <input ref="fileInput" type="file" accept=".zip,.json" style="display: none" @change="onImportFile" />
      </div>
    </div>
    <p class="hint">
      所有持久数据（数据库 + 设置）存放在 Docker 卷 <code>maaweb-config</code>（/data/config），
      容器重启 / 重建 / 删除重建均不丢失；导出 zip 用于跨机迁移或手动备份。
    </p>
  </div>
</template>

<style scoped>
.f-sec {
  margin-top: 4px; padding: 10px 0 4px;
  border-top: 1px solid var(--color-border-default);
  font-size: var(--font-size-sm); color: var(--color-text-tertiary);
  letter-spacing: 1px;
}
.f-ctrl { display: flex; gap: 8px; align-items: center; }
</style>
