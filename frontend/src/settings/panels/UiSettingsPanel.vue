<script setup lang="ts">
/**
 * 界面设置面板 —— 对齐 MAA 客户端 GuiSettingsUserControl（PRD §4.4.4）。
 * 主题（深色/浅色/自动）实际生效（html[data-theme] + CSS 变量覆盖）；
 * 自动 = 按当地日出日落 或 手动设定切换时间（每分钟重算）；
 * 语言仅存储（界面多语言切换后续迭代）。
 */
import { onMounted, reactive, ref, watch } from 'vue'
import { settingsApi } from '@/api/settings'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import NumberField from '@/tasks/forms/NumberField.vue'
import TimeSelect from '@/tasks/forms/TimeSelect.vue'
import { applyUiTheme } from '@/composables/useTheme'
import './panel.css'

const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref('')

const form = reactive({
  language: 'zh-cn',
  theme: 'dark',
  auto_theme_mode: 'sun',
  auto_theme_lat: 39.9042, // 默认北京（未定位/未填时的兜底）
  auto_theme_lon: 116.4074,
  auto_theme_light_start: '06:00',
  auto_theme_dark_start: '18:00',
})

const languageOpts: DropOption[] = [
  { value: 'zh-cn', label: '简体中文' },
  { value: 'zh-tw', label: '繁體中文' },
  { value: 'en-us', label: 'English' },
  { value: 'ja-jp', label: '日本語' },
  { value: 'ko-kr', label: '한국어' },
]
const themeOpts: DropOption[] = [
  { value: 'dark', label: '深色（方舟默认）' },
  { value: 'light', label: '浅色' },
  { value: 'auto', label: '自动' },
]
const modeOpts: DropOption[] = [
  { value: 'sun', label: '按当地日出日落' },
  { value: 'manual', label: '手动设定切换时间' },
]

/** IP 定位兜底：NAS 出口 IP → 当地经纬度（浏览器 geolocation 需 HTTPS/localhost，
 * 局域网 http 访问不可用，此时用 NAS 所在位置——正是「当地」） */
async function locateByIp() {
  try {
    const g = await settingsApi.geoip()
    form.auto_theme_lat = g.lat
    form.auto_theme_lon = g.lon
    error.value = g.city ? `✔ 已按 IP 定位：${g.city}` : '✔ 已按 IP 定位'
  } catch (e: unknown) {
    error.value = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
      ?? '定位失败，请手动输入经纬度（默认北京可先用）'
  }
}

function locate() {
  if ('geolocation' in navigator) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        form.auto_theme_lat = Math.round(pos.coords.latitude * 10000) / 10000
        form.auto_theme_lon = Math.round(pos.coords.longitude * 10000) / 10000
        error.value = ''
      },
      () => {
        void locateByIp()
      },
      { timeout: 4000, maximumAge: 600000 },
    )
  } else {
    void locateByIp()
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const all = await settingsApi.getAll()
    const ui = all.ui
    if (ui.language !== undefined) form.language = String(ui.language)
    if (ui.theme !== undefined) form.theme = String(ui.theme)
    if (ui.auto_theme_mode !== undefined) form.auto_theme_mode = String(ui.auto_theme_mode)
    if (ui.auto_theme_lat !== undefined) form.auto_theme_lat = Number(ui.auto_theme_lat)
    if (ui.auto_theme_lon !== undefined) form.auto_theme_lon = Number(ui.auto_theme_lon)
    if (ui.auto_theme_light_start !== undefined) form.auto_theme_light_start = String(ui.auto_theme_light_start)
    if (ui.auto_theme_dark_start !== undefined) form.auto_theme_dark_start = String(ui.auto_theme_dark_start)
    applyUiTheme(form)
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
    await settingsApi.saveGroup('ui', { ...form })
    applyUiTheme(form) // 立即生效
    saved.value = true
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '保存失败'
  } finally {
    saving.value = false
  }
}

// 主题及自动子项变更即时持久化 + 即时生效（对齐 MAA 客户端即时写配置）：
// 切换即保存，切走/刷新/重挂载面板后仍保持；语言字段走「保存设置」按钮。
watch(
  () => [
    form.theme,
    form.auto_theme_mode,
    form.auto_theme_lat,
    form.auto_theme_lon,
    form.auto_theme_light_start,
    form.auto_theme_dark_start,
  ],
  () => {
    applyUiTheme(form)
    if (loading.value) return // 首次载入由 load() 统一应用，不重复保存
    settingsApi
      .saveGroup('ui', {
        theme: form.theme,
        auto_theme_mode: form.auto_theme_mode,
        auto_theme_lat: form.auto_theme_lat,
        auto_theme_lon: form.auto_theme_lon,
        auto_theme_light_start: form.auto_theme_light_start,
        auto_theme_dark_start: form.auto_theme_dark_start,
      })
      .catch(() => undefined)
  },
)

onMounted(load)
</script>

<template>
  <div class="panel-card">
    <div class="card-hd">
      <span class="diamond"></span>
      <b>界面设置</b>
      <span class="sub">对齐 MAA 客户端 GuiSettings · 主题即时生效</span>
      <div class="right">
        <button class="btn" :disabled="loading" @click="load">⟳ 刷新</button>
        <button class="btn btn-gold" :disabled="saving || loading" @click="save">{{ saving ? '保存中…' : '保存设置' }}</button>
      </div>
    </div>
    <div v-if="error" class="err-bar">⚠ {{ error }}</div>
    <div v-if="saved" class="ok-bar">✔ 设置已保存</div>

    <div class="f-row">
      <label class="f-label">界面语言<small>存储预留；界面多语言切换后续迭代</small></label>
      <div class="f-ctrl"><DropSelect v-model="form.language" :options="languageOpts" /></div>
    </div>
    <div class="f-row">
      <label class="f-label">主题<small>切换即时预览，保存后全局生效</small></label>
      <div class="f-ctrl"><DropSelect v-model="form.theme" :options="themeOpts" /></div>
    </div>

    <div v-if="form.theme === 'auto'" class="f-sub">
      <div class="f-row">
        <label class="f-label">切换依据<small>自动主题的深浅切换方式</small></label>
        <div class="f-ctrl"><DropSelect v-model="form.auto_theme_mode" :options="modeOpts" /></div>
      </div>
      <div v-if="form.auto_theme_mode === 'sun'" class="f-row">
        <label class="f-label">纬度 / 经度<small>用于计算当地日出日落时间</small></label>
        <div class="f-ctrl">
          <NumberField v-model="form.auto_theme_lat" :min="-90" :max="90" :step="0.01" />
          <NumberField v-model="form.auto_theme_lon" :min="-180" :max="180" :step="0.01" />
          <button class="btn btn-sm" type="button" @click="locate">📍 定位</button>
        </div>
      </div>
      <div v-else class="f-row">
        <label class="f-label">浅色开始 / 深色开始<small>手动设定切换时间</small></label>
        <div class="f-ctrl">
          <TimeSelect v-model="form.auto_theme_light_start" />
          <TimeSelect v-model="form.auto_theme_dark_start" />
        </div>
      </div>
    </div>

    <p class="hint">日志卡片样式、主任务勾选语义、标题栏内容等为桌面客户端专属字段，WebUI 不需要。</p>
  </div>
</template>
