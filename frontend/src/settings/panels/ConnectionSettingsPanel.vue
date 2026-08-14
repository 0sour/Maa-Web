<script setup lang="ts">
/**
 * 连接设置面板 —— 对齐 MAA 客户端 ConnectSettingsUserControl（PRD §4.4.2）。
 * ADB 路径写入 runtime_settings.json（热更新，立即生效）；
 * 其余字段存 SQLite（connection.* 前缀）。
 */
import { onMounted, reactive, ref } from 'vue'
import { settingsApi } from '@/api/settings'
import { devicesApi } from '@/api/devices'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import './panel.css'

const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref('')
const effectiveAdb = ref('') // 当前生效的 ADB 路径（含 env/PATH 回退）

const form = reactive({
  adb_path: '',
  touch_mode: 'Minitouch',
  screencap_method: 'auto',
})

const touchModeOpts: DropOption[] = [
  { value: 'Minitouch', label: 'Minitouch' },
  { value: 'MaaTouch', label: 'MaaTouch' },
  { value: 'Adb', label: 'Adb' },
]
const screencapOpts: DropOption[] = [
  { value: 'auto', label: '自动' },
  { value: 'raw_with_gzip', label: 'RawWithGzip' },
  { value: 'encode_to_jpg', label: 'EncodeToJpg' },
]

async function load() {
  loading.value = true
  error.value = ''
  try {
    const all = await settingsApi.getAll()
    const c = all.connection
    form.adb_path = String(c.adb_path ?? '')
    if (c.touch_mode !== undefined) form.touch_mode = String(c.touch_mode)
    if (c.screencap_method !== undefined) form.screencap_method = String(c.screencap_method)
    const detect = await devicesApi.detect()
    effectiveAdb.value = detect.adb_path ?? ''
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
    await settingsApi.saveGroup('connection', { ...form })
    // ADB 路径热更新生效：保存后重新探测确认
    const detect = await devicesApi.detect()
    effectiveAdb.value = detect.adb_path ?? ''
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
      <b>连接设置</b>
      <span class="sub">对齐 MAA 客户端 ConnectSettings · ADB 路径保存即生效</span>
      <div class="right">
        <button class="btn" :disabled="loading" @click="load">⟳ 刷新</button>
        <button class="btn btn-gold" :disabled="saving || loading" @click="save">{{ saving ? '保存中…' : '保存设置' }}</button>
      </div>
    </div>
    <div v-if="error" class="err-bar">⚠ {{ error }}</div>
    <div v-if="saved" class="ok-bar">✔ 设置已保存（ADB 路径已热更新生效）</div>

    <div class="f-row">
      <label class="f-label">ADB 路径<small>留空 = 自动查找（PATH / MAAWEB_ADB_PATH）；填写后无需重启立即生效</small></label>
      <div class="f-ctrl"><input v-model="form.adb_path" type="text" placeholder="如 C:\platform-tools\adb.exe" /></div>
    </div>
    <div class="f-row">
      <label class="f-label">当前生效路径</label>
      <div class="f-ctrl"><code class="eff">{{ effectiveAdb || '—' }}</code></div>
    </div>

    <div class="f-row">
      <label class="f-label">默认触控模式<small>新添加设备的默认值（设备管理页可单独调整）</small></label>
      <div class="f-ctrl"><DropSelect v-model="form.touch_mode" :options="touchModeOpts" /></div>
    </div>
    <div class="f-row">
      <label class="f-label">截图方式<small>存储预留；引擎侧当前自动选择</small></label>
      <div class="f-ctrl"><DropSelect v-model="form.screencap_method" :options="screencapOpts" /></div>
    </div>

    <p class="hint">连接预设（BlueStacks/MuMu12/雷电 等 13 种）、自动检测、ADB 重启策略等字段随 M6 排期接入。</p>
  </div>
</template>

<style scoped>
.eff {
  font-family: var(--font-family-mono); font-size: var(--font-size-xs);
  color: var(--color-brand); border: 1px solid var(--color-border-default);
  padding: 4px 10px; letter-spacing: 0.3px;
}
</style>
