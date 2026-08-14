<script setup lang="ts">
/**
 * 通知页（M6）—— 外部通知发送记录：时间/渠道/事件/内容/结果，支持重发。
 * 配置在设置中心「外部通知」面板。
 */
import { onMounted, ref } from 'vue'
import { notificationsApi, type NotifyLogEntry } from '@/api/notifications'

const loading = ref(true)
const err = ref('')
const tip = ref('')
const logs = ref<NotifyLogEntry[]>([])

const CHANNEL_LABEL: Record<string, string> = {
  serverchan: 'Server酱', dingtalk: '钉钉', custom: '自定义 Webhook',
}
const EVENT_LABEL: Record<string, string> = {
  complete: '完成', error: '出错', test: '测试',
}

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    logs.value = await notificationsApi.logs(100)
  } catch (e: unknown) {
    err.value = (e as { message?: string })?.message ?? '读取通知记录失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="nview">
    <div class="dashboard">
      <div class="top-row">
        <div class="ttl">
          <span class="diamond"></span>
          <div>
            <h2>通知</h2>
            <p class="sub">外部通知发送记录 · 配置在设置中心「外部通知」</p>
          </div>
        </div>
        <div class="top-right">
          <button class="add-btn" :disabled="loading" @click="load">{{ loading ? '加载中…' : '⟳ 刷新' }}</button>
        </div>
      </div>

      <div v-if="err" class="err-bar">⚠ {{ err }}</div>
      <div v-if="tip" class="ok-bar">✔ {{ tip }}</div>

      <!-- 测试提示：通知功能未经充分验证前，重发暂不可用 -->
      <div class="warn-bar">
        ⚠ 通知发送功能暂未经过相关测试：当前仅支持设置页「发送测试」手动验证，重发暂不可用。
      </div>

      <div v-if="!loading && logs.length === 0" class="empty">
        暂无通知记录——在设置中心「外部通知」配置渠道后，任务完成/出错会自动推送，也可点「发送测试」验证。
      </div>

      <div class="log-list">
        <div v-for="row in logs" :key="row.id" class="log-row">
          <span class="t">{{ fmtTime(row.ts) }}</span>
          <span class="ch">{{ CHANNEL_LABEL[row.channel] ?? row.channel }}</span>
          <span class="ev" :class="row.event">{{ EVENT_LABEL[row.event] ?? row.event }}</span>
          <span class="st" :class="row.ok ? 'ok' : 'bad'">{{ row.ok ? '✔' : '✖' }}</span>
          <div class="body">
            <b>{{ row.title }}</b>
            <span class="content">{{ row.content }}</span>
            <span v-if="!row.ok && row.error" class="err">✖ {{ row.error }}</span>
          </div>
          <button class="btn" disabled title="未经过相关测试，暂不可用">重发</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nview { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.dashboard {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 24px 26px;
  display: flex; flex-direction: column; gap: 14px;
}
.top-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.ttl { display: flex; align-items: center; gap: 12px; }
.ttl .diamond {
  width: 14px; height: 14px;
  border: 1px solid var(--color-brand);
  transform: rotate(45deg);
  flex-shrink: 0;
  background: rgba(216, 177, 106, 0.15);
}
.ttl h2 { font-size: var(--font-size-2xl); letter-spacing: var(--font-tracking-wide); }
.ttl .sub { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-top: 3px; letter-spacing: 0.5px; }
.top-right { margin-left: auto; }
.err-bar {
  border: 1px solid var(--color-danger);
  background: rgba(176, 91, 83, 0.12);
  color: #d48f87; padding: 10px 14px; font-size: var(--font-size-md);
}
.ok-bar {
  border: 1px solid var(--color-success);
  background: rgba(159, 181, 111, 0.12);
  color: var(--color-success); padding: 10px 14px; font-size: var(--font-size-md);
}
.warn-bar {
  border: 1px solid var(--color-warning);
  background: rgba(201, 143, 78, 0.12);
  color: var(--color-warning); padding: 10px 14px; font-size: var(--font-size-md);
  letter-spacing: 0.3px;
}
.empty {
  border: 1px dashed var(--color-border-default);
  padding: 40px 20px; text-align: center;
  color: var(--color-text-secondary); letter-spacing: 0.5px; line-height: 2;
}

.log-list {
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  display: flex; flex-direction: column;
}
.log-row {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px dashed var(--color-border-default);
  font-size: var(--font-size-sm);
}
.log-row:last-child { border-bottom: none; }
.log-row .t { color: var(--color-text-tertiary); font-family: var(--font-family-mono); flex-shrink: 0; }
.log-row .ch {
  flex-shrink: 0; font-size: var(--font-size-xs);
  border: 1px solid var(--color-border-default);
  padding: 1px 8px; letter-spacing: 0.5px;
}
.log-row .ev {
  flex-shrink: 0; font-size: var(--font-size-xs);
  padding: 1px 8px; letter-spacing: 0.5px;
  border: 1px solid var(--color-border-default);
}
.log-row .ev.complete { color: var(--color-success); border-color: var(--color-success); }
.log-row .ev.error { color: var(--color-danger); border-color: var(--color-danger); }
.log-row .st { flex-shrink: 0; }
.log-row .st.ok { color: var(--color-success); }
.log-row .st.bad { color: var(--color-danger); }
.log-row .body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.log-row .body b { color: var(--color-text-primary); }
.log-row .content { color: var(--color-text-secondary); white-space: pre-wrap; }
.log-row .err { color: var(--color-danger); font-size: var(--font-size-xs); font-family: var(--font-family-mono); }
.btn {
  flex-shrink: 0;
  padding: 4px 12px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm); cursor: pointer;
}
.btn:hover { border-color: var(--color-brand-strong); color: var(--color-brand); }
</style>
