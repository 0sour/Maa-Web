<script setup lang="ts">
/**
 * 外部通知面板 —— 对齐 MAA 客户端 ExternalNotification。
 * 触发开关（完成/详情/出错/卡住）+ 渠道配置（Server酱/钉钉/自定义 Webhook），
 * 多渠道可同时启用；「发送测试」先保存配置再逐渠道发一条测试消息。
 */
import { onMounted, reactive, ref } from 'vue'
import { notificationsApi } from '@/api/notifications'
import { settingsApi } from '@/api/settings'
import './panel.css'

interface ChannelCfg {
  type: string
  enabled: boolean
  [k: string]: unknown
}

const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref('')
const testResult = ref<{ channel: string; ok: boolean; error: string | null }[]>([])
const testing = ref(false)

const form = reactive({
  enabled_complete: true,
  details: false,
  enabled_error: true,
  enabled_stalled: false,
  channels: [
    { type: 'serverchan', enabled: false, send_key: '' },
    { type: 'dingtalk', enabled: false, access_token: '', secret: '' },
    { type: 'custom', enabled: false, url: '', headers: '', body: '' },
  ] as ChannelCfg[],
})

const CHANNEL_LABEL: Record<string, string> = {
  serverchan: 'Server酱',
  dingtalk: '钉钉群机器人',
  custom: '自定义 Webhook',
}

// ── Webhook 预置模板（对齐客户端 WebhookPresetTemplate；v6.17 新增 WeCom/ntfy） ──
const WEBHOOK_PRESETS = [
  { id: '__custom__', label: '自定义（手动填写）', url: '', headers: '', body: '' },
  { id: 'Discord', label: 'Discord Webhook', url: '', headers: '', body: '{"content": "{content}"}' },
  {
    id: 'KOOK-Channel', label: 'KOOK 频道消息',
    url: 'https://www.kookapp.cn/api/v3/message/create',
    headers: 'Authorization: Bot <bot_token>',
    body: '{"type": 9, "target_id": "<channel_id>", "content": "**{title}**\\n{content}"}',
  },
  {
    id: 'KOOK-Direct', label: 'KOOK 私信',
    url: 'https://www.kookapp.cn/api/v3/direct-message/create',
    headers: 'Authorization: Bot <bot_token>',
    body: '{"type": 9, "target_id": "<user_id>", "content": "**{title}**\\n{content}"}',
  },
  {
    id: 'MeoW', label: 'MeoW',
    url: 'https://api.chuckfang.com/<nickname>',
    headers: '',
    body: '{"title":"{title}","msg":"{content}\\n{time}"}',
  },
  {
    id: 'ntfy', label: 'ntfy',
    url: 'https://ntfy.sh/<topic>',
    headers: '',
    body: '{"message": "{content}", "title": "{title}"}',
  },
  {
    id: 'WeCom', label: '企业微信 WeCom',
    url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<key>',
    headers: '',
    body: '{"msgtype": "text", "text": {"content": "{content}"}}',
  },
]
function applyPreset(presetId: string) {
  const ch = form.channels.find((c) => c.type === 'custom')
  if (!ch) return
  const preset = WEBHOOK_PRESETS.find((p) => p.id === presetId)
  if (!preset) return
  ch.url = preset.url
  ch.headers = preset.headers
  ch.body = preset.body
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const n = (await settingsApi.getAll()).notify
    if (n.enabled_complete !== undefined) form.enabled_complete = Boolean(n.enabled_complete)
    if (n.details !== undefined) form.details = Boolean(n.details)
    if (n.enabled_error !== undefined) form.enabled_error = Boolean(n.enabled_error)
    if (n.enabled_stalled !== undefined) form.enabled_stalled = Boolean(n.enabled_stalled)
    if (Array.isArray(n.channels)) {
      const savedCh = n.channels as ChannelCfg[]
      for (const ch of form.channels) {
        const hit = savedCh.find((x) => x.type === ch.type)
        if (hit) Object.assign(ch, hit)
      }
    }
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '读取通知设置失败'
  } finally {
    loading.value = false
  }
}

function channelPayload(): ChannelCfg[] {
  return form.channels.map((ch) => ({ ...ch }))
}

async function save() {
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    await settingsApi.saveGroup('notify', {
      enabled_complete: form.enabled_complete,
      details: form.details,
      enabled_error: form.enabled_error,
      enabled_stalled: form.enabled_stalled,
      channels: channelPayload(),
    })
    saved.value = true
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '保存失败'
  } finally {
    saving.value = false
  }
}

async function testSend() {
  testing.value = true
  error.value = ''
  testResult.value = []
  try {
    // 先保存当前配置，后端按保存后的配置逐渠道发送
    await settingsApi.saveGroup('notify', {
      enabled_complete: form.enabled_complete,
      details: form.details,
      enabled_error: form.enabled_error,
      enabled_stalled: form.enabled_stalled,
      channels: channelPayload(),
    })
    const r = await notificationsApi.testSend()
    testResult.value = r.results
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '测试发送失败'
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="panel-card">
    <div class="card-hd">
      <span class="diamond"></span>
      <b>外部通知</b>
      <span class="sub">对齐 MAA 客户端 ExternalNotification · 完成/出错推送</span>
      <div class="right">
        <button class="btn" :disabled="loading" @click="load">⟳ 刷新</button>
        <button class="btn btn-gold" :disabled="saving || loading" @click="save">{{ saving ? '保存中…' : '保存设置' }}</button>
        <button class="btn" :disabled="testing || loading" @click="testSend">{{ testing ? '发送中…' : '✉ 发送测试' }}</button>
      </div>
    </div>
    <div v-if="error" class="err-bar">⚠ {{ error }}</div>
    <div v-if="saved" class="ok-bar">✔ 设置已保存</div>

    <!-- 测试提示：功能未经充分验证 -->
    <div class="warn-bar">
      ⚠ 通知发送功能暂未经过相关测试：「发送测试」可手动验证配置，推送链路将在后续版本充分验证后启用。
    </div>

    <!-- 触发开关 -->
    <div class="f-row">
      <label class="f-label">完成时发送<small>任务队列全部完成 → 推送</small></label>
      <span class="f-switch" :class="{ on: form.enabled_complete }" @click="form.enabled_complete = !form.enabled_complete"></span>
    </div>
    <div class="f-row" :class="{ disabled: !form.enabled_complete }">
      <label class="f-label">完成时带详情<small>推送内容附带队列摘要</small></label>
      <span class="f-switch" :class="{ on: form.enabled_complete && form.details }" @click="form.enabled_complete && (form.details = !form.details)"></span>
    </div>
    <div class="f-row">
      <label class="f-label">出错时发送<small>任务失败/异常 → 推送（默认开启）</small></label>
      <span class="f-switch" :class="{ on: form.enabled_error }" @click="form.enabled_error = !form.enabled_error"></span>
    </div>
    <div class="f-row">
      <label class="f-label">卡住时发送<small>长时间无进展（停滞检测，暂未接入）</small></label>
      <span class="f-switch" :class="{ on: form.enabled_stalled }" @click="form.enabled_stalled = !form.enabled_stalled"></span>
    </div>

    <!-- 渠道配置 -->
    <div class="f-sec">推送渠道<small>可同时启用多个；任一渠道失败不影响其他</small></div>
    <div
      v-for="ch in form.channels" :key="ch.type"
      class="chan" :class="{ off: !ch.enabled }"
    >
      <div class="chan-hd">
        <label class="f-label">{{ CHANNEL_LABEL[ch.type] }}</label>
        <span class="f-switch" :class="{ on: ch.enabled }" @click="ch.enabled = !ch.enabled"></span>
      </div>
      <template v-if="ch.enabled">
        <div v-if="ch.type === 'serverchan'" class="f-row">
          <label class="f-label">SendKey<small>Server酱 官网 sct.ftqq.com 获取</small></label>
          <div class="f-ctrl"><input class="f-text" type="text" v-model="ch.send_key" placeholder="SCTxxxxxxxxxxxxxxxxxxxx" /></div>
        </div>
        <div v-if="ch.type === 'dingtalk'" class="chan-fields">
          <div class="f-row">
            <label class="f-label">AccessToken<small>钉钉群机器人 Webhook 中的 access_token</small></label>
            <div class="f-ctrl"><input class="f-text" type="text" v-model="ch.access_token" placeholder="xxxxx" /></div>
          </div>
          <div class="f-row">
            <label class="f-label">Secret<small>加签密钥（留空则不加签）</small></label>
            <div class="f-ctrl"><input class="f-text" type="password" v-model="ch.secret" placeholder="SECxxxxx" /></div>
          </div>
        </div>
        <div v-if="ch.type === 'custom'" class="chan-fields">
          <div class="f-row">
            <label class="f-label">预置模板<small>对齐客户端 v6.17 预置，填入后仍可修改</small></label>
            <div class="f-ctrl">
              <select class="f-text" value="__custom__" @change="applyPreset(($event.target as HTMLSelectElement).value)">
                <option v-for="p in WEBHOOK_PRESETS" :key="p.id" :value="p.id">{{ p.label }}</option>
              </select>
            </div>
          </div>
          <div class="f-row">
            <label class="f-label">Webhook URL<small>企业微信机器人等一切 webhook 地址</small></label>
            <div class="f-ctrl"><input class="f-text wide" type="text" v-model="ch.url" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…" /></div>
          </div>
          <div class="f-row">
            <label class="f-label">Headers<small>每行一个「键: 值」，可空</small></label>
            <div class="f-ctrl"><input class="f-text wide" type="text" v-model="ch.headers" placeholder="Content-Type: application/json" /></div>
          </div>
          <div class="f-row">
            <label class="f-label">Body 模板<small>可空（默认 JSON）；占位 {title} {content} {time}</small></label>
            <div class="f-ctrl"><input class="f-text wide" type="text" v-model="ch.body" placeholder='{"msgtype":"text","text":{"content":"{title}\n{content}"}}' /></div>
          </div>
        </div>
      </template>
    </div>

    <!-- 测试结果 -->
    <div v-if="testResult.length" class="test-results">
      <div v-for="r in testResult" :key="r.channel" class="test-row" :class="r.ok ? 'ok' : 'bad'">
        <span class="ch">{{ CHANNEL_LABEL[r.channel] ?? r.channel }}</span>
        <span class="st">{{ r.ok ? '✔ 发送成功' : '✖ 发送失败' }}</span>
        <span v-if="!r.ok && r.error" class="err">{{ r.error }}</span>
      </div>
    </div>

    <p class="hint">推送内容：设备名 + 队列摘要 + 完成/出错结果 + 错误详情（出错时）。发送记录见侧栏「通知」页。</p>
  </div>
</template>

<style scoped>
.f-sec {
  margin-top: 14px; padding-top: 12px;
  border-top: 1px dashed var(--color-border-default);
  font-size: var(--font-size-md); font-weight: 700; letter-spacing: 1px;
  display: flex; align-items: baseline; gap: 8px;
}
.warn-bar {
  border: 1px solid var(--color-warning);
  background: rgba(201, 143, 78, 0.12);
  color: var(--color-warning); padding: 10px 14px; font-size: var(--font-size-md);
  letter-spacing: 0.3px;
}
.f-sec small { font-weight: 400; color: var(--color-text-tertiary); font-size: var(--font-size-xs); letter-spacing: 0.3px; }
.chan { margin-top: 10px; }
.chan.off { opacity: 0.5; }
.chan-hd { display: flex; align-items: center; }
.chan-hd .f-label { font-weight: 700; }
.chan-fields { margin-left: 22px; padding-left: 14px; border-left: 1px dashed var(--color-border-default); }
.f-text { flex: 1; }
.f-text.wide { min-width: 280px; }

.test-results {
  margin-top: 12px;
  border: 1px solid var(--color-border-default);
  padding: 10px 14px; display: flex; flex-direction: column; gap: 6px;
}
.test-row { display: flex; align-items: center; gap: 10px; font-size: var(--font-size-sm); }
.test-row .ch { font-weight: 700; letter-spacing: 0.5px; min-width: 90px; }
.test-row.ok .st { color: var(--color-success); }
.test-row.bad .st { color: var(--color-danger); }
.test-row .err { color: var(--color-text-tertiary); font-family: var(--font-family-mono); font-size: var(--font-size-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
