<script setup lang="ts">
/**
 * 运行设置面板 —— 对齐 MAA 客户端 GameSettingsUserControl（PRD §4.4.1）。
 * 字段存 SQLite Setting 表（`game.*` 前缀）；脚本执行（S-03）待 M6 排期。
 */
import { onMounted, reactive, ref } from 'vue'
import { settingsApi } from '@/api/settings'
import { CLIENT_TYPES, CLIENT_TYPE_LABELS } from '@/tasks/taskTypes'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import NumberField from '@/tasks/forms/NumberField.vue'
import './panel.css'

const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref('')

const form = reactive({
  client_type: 'Official',
  enable_penguin: false,
  penguin_id: '',
  enable_yituliu: false,
  yituliu_id: '',
  enable_stall_timeout: false,
  stall_timeout_minutes: 10,
  reminder_interval_minutes: 5,
  starts_with_script: '',
  ends_with_script: '',
  copilot_with_script: false,
  manual_stop_with_script: false,
})

const clientTypeOpts = [
  ...CLIENT_TYPES.map((c) => ({ value: c, label: CLIENT_TYPE_LABELS[c] ?? c })),
] as DropOption[]

function assign(values: Record<string, unknown>) {
  for (const key of Object.keys(form)) {
    const v = values[key]
    if (v !== undefined) (form as Record<string, unknown>)[key] = v
  }
}

async function load() {
  loading.value = true
  try {
    const all = await settingsApi.getAll()
    assign(all.game)
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '读取设置失败'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    await settingsApi.saveGroup('game', { ...form })
    saved.value = true
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="panel-card">
    <div class="card-hd">
      <span class="diamond"></span>
      <b>运行设置</b>
      <span class="sub">对齐 MAA 客户端 GameSettings · 存储于 SQLite settings 表</span>
      <div class="right">
        <button class="btn" :disabled="loading" @click="load">⟳ 刷新</button>
        <button class="btn btn-gold" :disabled="saving || loading" @click="save">{{ saving ? '保存中…' : '保存设置' }}</button>
      </div>
    </div>
    <div v-if="error" class="err-bar">⚠ {{ error }}</div>
    <div v-if="saved" class="ok-bar">✔ 设置已保存</div>

    <div class="f-row">
      <label class="f-label">客户端版本<small>任务未显式指定时的默认客户端（崩溃重启等场景）</small></label>
      <div class="f-ctrl"><DropSelect v-model="form.client_type" :options="clientTypeOpts" /></div>
    </div>

    <div class="f-row">
      <label class="f-label">汇报企鹅物流<small>掉落/公招数据上报</small></label>
      <span class="f-switch" :class="{ on: form.enable_penguin }" @click="form.enable_penguin = !form.enable_penguin"></span>
    </div>
    <div class="f-row" v-if="form.enable_penguin">
      <label class="f-label">企鹅物流 ID</label>
      <div class="f-ctrl"><input v-model="form.penguin_id" type="text" placeholder="123456" /></div>
    </div>
    <div class="f-row">
      <label class="f-label">汇报一图流</label>
      <span class="f-switch" :class="{ on: form.enable_yituliu }" @click="form.enable_yituliu = !form.enable_yituliu"></span>
    </div>
    <div class="f-row" v-if="form.enable_yituliu">
      <label class="f-label">一图流 ID</label>
      <div class="f-ctrl"><input v-model="form.yituliu_id" type="text" placeholder="123456" /></div>
    </div>

    <div class="f-row">
      <label class="f-label">卡死检测<small>任务无响应超时提醒</small></label>
      <span class="f-switch" :class="{ on: form.enable_stall_timeout }" @click="form.enable_stall_timeout = !form.enable_stall_timeout"></span>
    </div>
    <template v-if="form.enable_stall_timeout">
      <div class="f-row">
        <label class="f-label">卡死超时（分钟）</label>
        <div class="f-ctrl"><NumberField v-model="form.stall_timeout_minutes" :min="1" :max="120" /></div>
      </div>
      <div class="f-row">
        <label class="f-label">卡死提醒间隔（分钟）</label>
        <div class="f-ctrl"><NumberField v-model="form.reminder_interval_minutes" :min="1" :max="60" /></div>
      </div>
    </template>

    <div class="f-row">
      <label class="f-label">开始前脚本<small>任务开始前执行（S-03 执行待排期，当前仅存储）</small></label>
      <div class="f-ctrl"><input v-model="form.starts_with_script" type="text" placeholder="脚本路径" /></div>
    </div>
    <div class="f-row">
      <label class="f-label">结束后脚本<small>任务结束后执行（S-03 执行待排期）</small></label>
      <div class="f-ctrl"><input v-model="form.ends_with_script" type="text" placeholder="脚本路径" /></div>
    </div>
    <div class="f-row">
      <label class="f-label">Copilot 结束后也执行脚本</label>
      <span class="f-switch" :class="{ on: form.copilot_with_script }" @click="form.copilot_with_script = !form.copilot_with_script"></span>
    </div>
    <div class="f-row">
      <label class="f-label">手动停止也执行脚本</label>
      <span class="f-switch" :class="{ on: form.manual_stop_with_script }" @click="form.manual_stop_with_script = !form.manual_stop_with_script"></span>
    </div>
  </div>
</template>

<style scoped>
.f-row.off { opacity: 0.45; }
</style>
