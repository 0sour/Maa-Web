<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useDevicesStore } from '@/stores/devices'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import type { Device, DevicePayload, DeviceStatus, DetectedDevice } from '@/api/devices'

const store = useDevicesStore()

// ── 状态文案映射 ───────────────────────────
const statusMeta: Record<DeviceStatus, { text: string; cls: string }> = {
  online: { text: '已连接', cls: 's-online' },
  offline: { text: '离线', cls: 's-offline' },
  connecting: { text: '连接中', cls: 's-connecting' },
  error: { text: '异常', cls: 's-error' },
}

// ── 环境状态（来自 /detect） ───────────────
const envChips = computed(() => {
  const d = store.detect
  if (!d) return []
  return [
    {
      key: 'adb',
      label: 'ADB 引擎',
      text: d.adb_available ? '就绪' : '缺失',
      cls: d.adb_available ? 'env-ok' : 'env-bad',
      detail: d.adb_path ?? (d.reason ?? ''),
    },
    {
      key: 'engine',
      label: 'MAA 引擎',
      text: d.engine_available ? `已加载 v${d.engine_version}` : '未加载',
      cls: d.engine_available ? 'env-ok' : 'env-warn',
      detail: d.engine_available ? '识别/自动化可用' : '仅 ADB 连接，识别任务不可用（请先下载引擎包）',
    },
  ]
})

// ── 新增/编辑表单（Modal） ─────────────────
const showForm = ref(false)
const editingId = ref<number | null>(null) // null = 新增
const formErr = ref('')
const form = reactive({
  name: '',
  adb_host: '',
  adb_port: 5555,
  touch_mode: 'Minitouch' as Device['touch_mode'],
  client_type: 'Official',
})

const touchModes: Device['touch_mode'][] = ['Minitouch', 'MaaTouch', 'Adb']
const clientTypes = ['Official', 'Bilibili', 'YoStarEN', 'YoStarJP', 'YoStarKR']

const touchModeOpts = computed<DropOption[]>(() =>
  touchModes.map((m) => ({ value: m, label: m })),
)
const clientTypeOpts = computed<DropOption[]>(() =>
  clientTypes.map((c) => ({ value: c, label: c })),
)

function openAdd() {
  editingId.value = null
  Object.assign(form, { name: '', adb_host: '', adb_port: 5555, touch_mode: 'Minitouch', client_type: 'Official' })
  formErr.value = ''
  showForm.value = true
}

function openEdit(d: Device) {
  editingId.value = d.id
  Object.assign(form, {
    name: d.name, adb_host: d.adb_host, adb_port: d.adb_port,
    touch_mode: d.touch_mode, client_type: d.client_type,
  })
  formErr.value = ''
  showForm.value = true
}

/** 检测到的设备 → 预填添加表单（port=0 表示 USB/本地 serial 设备） */
function prefillFromDetected(d: DetectedDevice) {
  openAdd()
  const usb = d.port <= 0
  form.name = d.model ? `${d.model}${usb ? ' (USB)' : `@${d.port}`}` : d.serial
  form.adb_host = d.host
  form.adb_port = d.port || 0
}

/** 检测到的设备是否已在列表（host + port 相同即视为同一设备） */
function isRegistered(d: DetectedDevice): boolean {
  return store.list.some(
    (dev) => dev.adb_host === d.host && (dev.adb_port ?? 0) === (d.port || 0),
  )
}

// ── 分辨率弹窗（MAA 仅支持 16:9 / 9:16；真机临时调整后需重置） ───
// 竖屏真机（USB serial）分辨率是短边×长边 → 9:16（1080×1920 / 720×1280）；
// 模拟器为横屏 → 16:9（1920×1080 / 1280×720 / 2560×1440）。
const isUsbDevice = (d: Device) => (d.adb_port ?? 0) <= 0
const RES_PRESETS: [number, number, string][] = [
  [1080, 1920, '1080×1920（竖屏真机 推荐）'],
  [1920, 1080, '1920×1080（模拟器 推荐）'],
  [1280, 720, '1280×720'],
  [2560, 1440, '2560×1440'],
]
const resDlg = ref<{
  device: Device
  cur: string
  width: number
  height: number
  msg: string
  busy: boolean
} | null>(null)

function openResolution(d: Device) {
  const [dW, dH] = isUsbDevice(d) ? [1080, 1920] : [1920, 1080]
  resDlg.value = { device: d, cur: '查询中…', width: dW, height: dH, msg: '', busy: true }
  store
    .getResolution(d.id)
    .then((r) => {
      if (!resDlg.value) return
      resDlg.value.cur = r.width ? `${r.width}×${r.height}` : r.message
      resDlg.value.width = r.width ?? dW
      resDlg.value.height = r.height ?? dH
    })
    .catch(() => {
      if (resDlg.value) resDlg.value.cur = '查询失败'
    })
    .finally(() => {
      if (resDlg.value) resDlg.value.busy = false
    })
}

async function applyResolution() {
  const d = resDlg.value
  if (!d || d.busy) return
  d.busy = true
  d.msg = ''
  try {
    const r = await store.setResolution(d.device.id, d.width, d.height)
    d.cur = `${r.width}×${r.height}`
    d.msg = r.message || '已应用'
  } catch (e: unknown) {
    d.msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '设置失败'
  } finally {
    d.busy = false
  }
}

async function resetResolution() {
  const d = resDlg.value
  if (!d || d.busy) return
  d.busy = true
  d.msg = ''
  try {
    const r = await store.resetResolution(d.device.id)
    d.msg = r.message || '已重置'
  } catch (e: unknown) {
    d.msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '重置失败'
  } finally {
    d.busy = false
  }
}

async function submitForm() {
  formErr.value = ''
  const payload: DevicePayload = {
    name: form.name.trim(),
    adb_host: form.adb_host.trim(),
    adb_port: form.adb_port,
    touch_mode: form.touch_mode,
    client_type: form.client_type,
  }
  if (!payload.name || !payload.adb_host) {
    formErr.value = '名称与 ADB 地址为必填项'
    return
  }
  try {
    if (editingId.value == null) await store.add(payload)
    else await store.update(editingId.value, payload)
    showForm.value = false
  } catch (e: unknown) {
    formErr.value = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? (e as { message?: string })?.message ?? '保存失败'
  }
}

// ── 删除（两步确认） ───────────────────────
const confirmId = ref<number | null>(null)
function toggleDelete(d: Device) {
  if (confirmId.value === d.id) {
    confirmId.value = null
    store.remove(d.id).catch(() => undefined)
  } else {
    confirmId.value = d.id
  }
}

// ── 时间格式化 ────────────────────────────
function fmtTime(iso: string | null): string {
  if (!iso) return '从未连接'
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

onMounted(() => {
  store.fetchList()
  store.detectDevices() // 进入页面自动检测环境，始终展示
})
</script>

<template>
  <div class="dv-wrap">
    <!-- 顶栏：标题 + 统计 + 操作 -->
    <div class="dv-top">
      <div class="dv-title">
        <span class="diamond"></span>
        <div>
          <h2>设备管理</h2>
          <p class="sub">ADB 连接 · 模拟器 / 实机接入控制</p>
        </div>
      </div>
      <div class="dv-top-right">
        <span class="count">在线 {{ store.onlineCount }} / 共 {{ store.list.length }}</span>
        <button class="btn" @click="store.fetchList()" :disabled="store.loading">
          {{ store.loading ? '刷新中…' : '⟳ 刷新' }}
        </button>
        <button class="btn" @click="store.detectDevices()" :disabled="store.detecting">
          {{ store.detecting ? '扫描中…' : '⌁ 检测设备' }}
        </button>
        <button class="btn btn-gold" @click="openAdd">＋ 添加设备</button>
      </div>
    </div>

    <!-- 错误条 -->
    <div v-if="store.error" class="dv-error">⚠ {{ store.error }}</div>

    <!-- 检测结果面板（始终显示：自动检测环境 + 发现的设备） -->
    <div class="detect panel">
      <div class="detect-hd">
        <span class="diamond"></span>
        <b>环境检测</b>
        <span v-if="store.detect?.adb_available && store.detect.adb_version" class="sub">
          {{ store.detect.adb_version }}
        </span>
        <span v-else class="sub">{{ store.detecting ? '检测中…' : '' }}</span>
      </div>
      <template v-if="store.detect">
        <div class="detect-env">
          <div v-for="c in envChips" :key="c.key" class="env-chip" :class="c.cls">
            <span class="dot"></span>
            <div>
              <div class="env-label">{{ c.label }}</div>
              <div class="env-text">{{ c.text }}</div>
              <div v-if="c.detail" class="env-detail">{{ c.detail }}</div>
            </div>
          </div>
        </div>

        <div v-if="!store.detect.adb_available" class="detect-warn">
          ⚠ {{ store.detect.reason }}
        </div>

        <template v-else>
          <div v-if="store.detect.devices.length === 0" class="detect-empty">
            未发现可连接的 ADB 设备 — 请确认模拟器/真机已开启并启用 ADB 调试。
          </div>
          <div v-else class="detect-list">
            <div v-for="d in store.detect.devices" :key="d.serial" class="detect-item">
              <span class="dev-mark"></span>
              <div class="di-info">
                <b>{{ d.model || d.serial }}</b>
                <code>{{ d.serial }}</code>
              </div>
              <span class="di-state" :class="d.state === 'device' ? 'st-ok' : 'st-warn'">
                {{ d.state }}
              </span>
              <button
                v-if="!isRegistered(d)"
                class="btn btn-sm btn-gold"
                @click="prefillFromDetected(d)"
              >添加</button>
              <span v-else class="di-added">已添加</span>
            </div>
          </div>
        </template>
      </template>
      <div v-else class="detect-empty">
        {{ store.detecting ? '正在检测环境…' : '环境检测不可用，可点击右上角「⌁ 检测设备」重试。' }}
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!store.loading && store.list.length === 0" class="dv-empty panel">
      <div class="ph-diamond"><span>◇</span></div>
      <h3>尚未登记任何设备</h3>
      <p>点击「⌁ 检测设备」扫描局域网内模拟器，或手动「＋ 添加设备」登记 ADB 地址。</p>
      <div class="empty-ops">
        <button class="btn" @click="store.detectDevices()" :disabled="store.detecting">
          {{ store.detecting ? '扫描中…' : '⌁ 检测设备' }}
        </button>
        <button class="btn btn-gold" @click="openAdd">＋ 添加设备</button>
      </div>
    </div>

    <!-- 设备卡片网格 -->
    <div v-else class="dv-grid">
      <div v-for="d in store.list" :key="d.id" class="dev panel">
        <div class="dev-hd">
          <div class="dev-name">
            <span class="dev-mark"></span>
            <b>{{ d.name }}</b>
          </div>
          <span class="st" :class="statusMeta[d.status].cls">
            <span class="dot"></span>{{ statusMeta[d.status].text }}
          </span>
        </div>

        <div class="dev-body">
          <div class="addr-row">
            <label>ADB</label>
            <code>{{ d.adb_port > 0 ? `${d.adb_host}:${d.adb_port}` : `${d.adb_host}（USB）` }}</code>
          </div>
          <div class="addr-row">
            <label>触控</label>
            <span>{{ d.touch_mode }}</span>
          </div>
          <div class="addr-row">
            <label>客户端</label>
            <span>{{ d.client_type }}</span>
          </div>
          <div class="addr-row">
            <label>最近在线</label>
            <span class="dim">{{ fmtTime(d.last_online_at) }}</span>
          </div>
          <div v-if="d.last_error" class="dev-err">⚠ {{ d.last_error }}</div>
        </div>

        <div class="dev-ops">
          <button
            v-if="d.status !== 'online'"
            class="btn btn-sm btn-connect"
            :disabled="store.busyId === d.id"
            @click="store.connect(d.id)"
          >{{ store.busyId === d.id ? '连接中…' : '连接' }}</button>
          <button
            v-else
            class="btn btn-sm btn-disconnect"
            :disabled="store.busyId === d.id"
            @click="store.disconnect(d.id)"
          >断开</button>
          <button class="btn btn-sm" @click="openResolution(d)">分辨率</button>
          <button class="btn btn-sm" @click="openEdit(d)">编辑</button>
          <button
            class="btn btn-sm btn-del"
            :class="{ confirm: confirmId === d.id }"
            @click="toggleDelete(d)"
          >{{ confirmId === d.id ? '确认删除?' : '删除' }}</button>
        </div>
      </div>
    </div>

    <!-- 新增 / 编辑 Modal -->
    <div v-if="showForm" class="modal-mask" @click.self="showForm = false">
      <div class="modal">
        <div class="modal-hd">
          <span class="diamond"></span>
          <b>{{ editingId == null ? '登记设备' : '编辑设备' }}</b>
          <button class="modal-x" @click="showForm = false">✕</button>
        </div>
        <div class="modal-bd">
          <div class="f-row">
            <label>名称 <i>*</i></label>
            <input v-model="form.name" type="text" placeholder="如 MuMu12 · NAS" maxlength="64">
          </div>
          <div class="f-row">
            <label>ADB 地址 <i>*</i></label>
            <input v-model="form.adb_host" type="text" placeholder="如 192.168.1.10" maxlength="128">
          </div>
          <div class="f-row f-half">
            <div class="f-cell">
              <label>ADB 端口 <small>0 = USB</small></label>
              <input v-model.number="form.adb_port" type="number" min="0" max="65535">
            </div>
            <div class="f-cell">
              <label>触控模式</label>
              <DropSelect v-model="form.touch_mode" :options="touchModeOpts" />
            </div>
          </div>
          <div v-if="form.adb_port === 0" class="form-hint">
            ℹ 端口 0 表示 USB/本地 serial 设备：ADB 地址填设备序列号（如 9b65ff77），无需 adb connect。
          </div>
          <div class="f-row">
            <label>客户端类型</label>
            <DropSelect v-model="form.client_type" :options="clientTypeOpts" />
          </div>
          <div v-if="formErr" class="form-err">⚠ {{ formErr }}</div>
        </div>
        <div class="modal-ft">
          <button class="btn" @click="showForm = false">取消</button>
          <button class="btn btn-gold" @click="submitForm">保存</button>
        </div>
      </div>
    </div>

    <!-- 分辨率弹窗 -->
    <div v-if="resDlg" class="modal-mask" @click.self="resDlg = null">
      <div class="modal">
        <div class="modal-hd">
          <span class="diamond"></span>
          <b>分辨率 · {{ resDlg.device.name }}</b>
          <button class="modal-x" @click="resDlg = null">✕</button>
        </div>
        <div class="modal-bd">
          <div class="res-cur">当前：{{ resDlg.cur }}</div>
          <div class="res-presets">
            <button
              v-for="[w, h, label] in RES_PRESETS" :key="`${w}x${h}`"
              class="btn btn-sm"
              :class="{ active: resDlg.width === w && resDlg.height === h }"
              @click="resDlg.width = w; resDlg.height = h"
            >{{ label }}</button>
          </div>
          <div class="f-row f-half">
            <div class="f-cell">
              <label>宽度</label>
              <input v-model.number="resDlg.width" type="number" min="480" max="4096">
            </div>
            <div class="f-cell">
              <label>高度</label>
              <input v-model.number="resDlg.height" type="number" min="480" max="4096">
            </div>
          </div>
          <p class="res-tip">MAA 仅支持 16:9 / 9:16 分辨率：竖屏真机用 1080×1920（短边×长边），模拟器用 1920×1080。调整后建议在任务结束前「重置」恢复原始分辨率。</p>
          <div v-if="resDlg.msg" class="form-err">{{ resDlg.msg }}</div>
        </div>
        <div class="modal-ft">
          <button class="btn" :disabled="resDlg.busy" @click="resetResolution">重置</button>
          <button class="btn btn-gold" :disabled="resDlg.busy" @click="applyResolution">
            {{ resDlg.busy ? '应用中…' : '应用' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dv-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 26px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* ── 顶栏 ─────────────────────────────── */
.dv-top {
  display: flex; align-items: center; gap: 14px;
  flex-wrap: wrap;
}
.dv-title { display: flex; align-items: center; gap: 12px; }
.dv-title .diamond {
  width: 14px; height: 14px;
  border: 1px solid var(--color-brand);
  transform: rotate(45deg);
  flex-shrink: 0;
  background: rgba(216, 177, 106, 0.15);
}
.dv-title h2 { font-size: var(--font-size-2xl); letter-spacing: var(--font-tracking-wide); }
.dv-title .sub { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-top: 3px; letter-spacing: 0.5px; }
.dv-top-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.count {
  font-size: var(--font-size-sm); color: var(--color-text-secondary);
  font-family: var(--font-family-mono); letter-spacing: 0.5px;
  padding: 6px 12px; border: 1px solid var(--color-border-default);
}

/* ── 按钮（全局风格统一） ──────────────── */
.btn {
  padding: 8px 16px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
  font-size: var(--font-size-md);
  letter-spacing: 0.5px;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.btn:hover:not(:disabled) { border-color: var(--color-brand-strong); color: var(--color-brand); box-shadow: var(--shadow-glow-sm); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-gold { background: rgba(216, 177, 106, 0.14); border-color: var(--color-brand-strong); color: var(--color-brand); }
.btn-sm { padding: 5px 12px; font-size: var(--font-size-sm); }
.btn-connect { border-color: var(--color-success); color: var(--color-success); }
.btn-disconnect { border-color: var(--color-warning); color: var(--color-warning); }
.btn-del { border-color: var(--color-border-default); color: var(--color-text-secondary); }
.btn-del:hover { border-color: var(--color-danger); color: var(--color-danger); }
.btn-del.confirm { border-color: var(--color-danger); color: var(--color-danger); background: rgba(176, 91, 83, 0.15); }

/* ── 错误条 ───────────────────────────── */
.dv-error {
  border: 1px solid var(--color-danger);
  background: rgba(176, 91, 83, 0.12);
  color: #d48f87;
  padding: 10px 16px;
  font-size: var(--font-size-md);
  letter-spacing: 0.5px;
}

/* ── 检测面板 ─────────────────────────── */
.detect {
  padding: 16px 18px; display: flex; flex-direction: column; gap: 14px;
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-panel);
}
.detect-hd { display: flex; align-items: center; gap: 10px; }
.detect-hd .diamond {
  width: 12px; height: 12px;
  border: 1px solid var(--color-brand);
  transform: rotate(45deg); flex-shrink: 0;
}
.detect-hd b { font-size: var(--font-size-xl); letter-spacing: var(--font-tracking-wide); }
.detect-hd .sub { margin-left: auto; font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-family: var(--font-family-mono); }

.detect-env { display: flex; gap: 12px; flex-wrap: wrap; }
.env-chip {
  flex: 1; min-width: 210px;
  display: flex; gap: 10px; align-items: flex-start;
  border: 1px solid var(--color-border-default);
  padding: 10px 14px;
  background: var(--color-bg-subtle);
}
.env-chip .dot {
  width: 9px; height: 9px; flex-shrink: 0; margin-top: 4px;
  border: 1px solid; transform: rotate(45deg);
}
.env-ok { color: var(--color-success); border-color: var(--color-success); }
.env-ok .dot { border-color: var(--color-success); background: rgba(159, 181, 111, 0.4); }
.env-bad { color: #d48f87; border-color: var(--color-danger); }
.env-bad .dot { border-color: var(--color-danger); background: rgba(176, 91, 83, 0.4); }
.env-warn { color: var(--color-warning); border-color: var(--color-warning); }
.env-warn .dot { border-color: var(--color-warning); background: rgba(201, 143, 78, 0.4); }
.env-label { font-size: var(--font-size-xs); letter-spacing: 1px; opacity: 0.8; }
.env-text { font-size: var(--font-size-lg); font-weight: 700; margin-top: 2px; }
.env-detail {
  font-size: var(--font-size-xs); opacity: 0.75; margin-top: 3px;
  font-family: var(--font-family-mono); word-break: break-all;
}

.detect-warn {
  border: 1px solid var(--color-danger);
  background: rgba(176, 91, 83, 0.12);
  color: #d48f87; padding: 10px 14px; font-size: var(--font-size-md);
}
.detect-empty {
  color: var(--color-text-secondary); font-size: var(--font-size-md);
  padding: 6px 2px; letter-spacing: 0.3px;
}
.detect-list { display: flex; flex-direction: column; gap: 8px; }
.detect-item {
  display: flex; align-items: center; gap: 12px;
  padding: 9px 12px;
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-subtle);
}
.dev-mark {
  width: 9px; height: 9px; flex-shrink: 0;
  border: 1px solid var(--color-brand);
  transform: rotate(45deg);
  background: rgba(216, 177, 106, 0.3);
}
.di-info { display: flex; flex-direction: column; gap: 1px; flex: 1; min-width: 0; }
.di-info b { font-size: var(--font-size-md); }
.di-info code {
  font-family: var(--font-family-mono); font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.di-state {
  font-size: var(--font-size-xs); padding: 2px 9px; letter-spacing: 1px;
  border: 1px solid var(--color-border-default); text-transform: uppercase;
}
.st-ok { color: var(--color-success); border-color: var(--color-success); }
.st-warn { color: var(--color-warning); border-color: var(--color-warning); }
.di-added {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border-default);
  padding: 5px 12px; letter-spacing: 1px; flex-shrink: 0;
}

/* ── 空状态 ───────────────────────────── */
.dv-empty { padding: 56px 24px; text-align: center; }
.ph-diamond {
  width: 44px; height: 44px; margin: 0 auto 18px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--color-brand-strong);
  transform: rotate(45deg);
  color: var(--color-brand); font-size: 16px;
}
.ph-diamond span { transform: rotate(-45deg); display: block; }
.dv-empty h3 { font-size: var(--font-size-2xl); margin-bottom: 8px; letter-spacing: var(--font-tracking-wide); }
.dv-empty p { color: var(--color-text-secondary); margin-bottom: var(--spacing-xl); font-size: var(--font-size-md); }
.empty-ops { display: flex; gap: 10px; justify-content: center; }

/* ── 设备卡片网格 ─────────────────────── */
.dv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
  align-items: start;
}
.dev {
  padding: 16px 18px; display: flex; flex-direction: column; gap: 14px;
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-panel);
}
.dev-hd { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.dev-name { display: flex; align-items: center; gap: 10px; min-width: 0; }
.dev-name b {
  font-size: var(--font-size-xl); letter-spacing: 0.5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* 状态芯片 */
.st {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--font-size-xs);
  padding: 3px 10px;
  border: 1px solid var(--color-border-default);
  letter-spacing: 1px; flex-shrink: 0;
}
.st .dot { width: 7px; height: 7px; border: 1px solid; transform: rotate(45deg); }
.s-online { color: var(--color-success); border-color: var(--color-success); }
.s-online .dot { border-color: var(--color-success); background: rgba(159, 181, 111, 0.4); }
.s-offline { color: var(--color-text-tertiary); }
.s-offline .dot { border-color: var(--color-text-tertiary); }
.s-connecting { color: var(--color-warning); border-color: var(--color-warning); }
.s-connecting .dot { border-color: var(--color-warning); background: rgba(201, 143, 78, 0.4); animation: blink 1s infinite; }
.s-error { color: #d48f87; border-color: var(--color-danger); }
.s-error .dot { border-color: var(--color-danger); background: rgba(176, 91, 83, 0.4); }
@keyframes blink { 50% { opacity: 0.3; } }

/* 信息行 */
.dev-body { display: flex; flex-direction: column; }
.addr-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 0;
  border-bottom: 1px dashed var(--color-border-default);
  font-size: var(--font-size-md);
}
.addr-row:last-child { border: none; }
.addr-row label { width: 62px; flex-shrink: 0; color: var(--color-text-tertiary); letter-spacing: 1px; font-size: var(--font-size-sm); }
.addr-row code {
  font-family: var(--font-family-mono);
  color: var(--color-brand);
  font-size: var(--font-size-md);
  letter-spacing: 0.5px;
}
.addr-row .dim { color: var(--color-text-secondary); font-size: var(--font-size-sm); }

/* 连接错误原因 */
.dev-err {
  margin-top: 10px;
  border: 1px solid var(--color-danger);
  background: rgba(176, 91, 83, 0.12);
  color: #d48f87;
  padding: 8px 12px;
  font-size: var(--font-size-sm);
  letter-spacing: 0.3px;
  word-break: break-all;
}

/* 操作区 */
.dev-ops { display: flex; gap: 8px; border-top: 1px solid var(--color-border-default); padding-top: 12px; }

/* ── Modal ────────────────────────────── */
.modal-mask {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(10, 12, 15, 0.65);
  display: flex; align-items: center; justify-content: center;
}
.modal {
  width: 460px; max-width: calc(100vw - 48px);
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-strong);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
}
.modal-hd {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--color-border-default);
}
.modal-hd .diamond {
  width: 12px; height: 12px;
  border: 1px solid var(--color-brand);
  transform: rotate(45deg); flex-shrink: 0;
}
.modal-hd b { font-size: var(--font-size-xl); letter-spacing: var(--font-tracking-wide); }
.modal-x { margin-left: auto; color: var(--color-text-tertiary); font-size: var(--font-size-lg); }
.modal-x:hover { color: var(--color-brand); }
.modal-bd { padding: 18px; display: flex; flex-direction: column; gap: 14px; }
.f-row { display: flex; flex-direction: column; gap: 6px; }
.f-row label, .f-cell label { font-size: var(--font-size-sm); color: var(--color-text-secondary); letter-spacing: 1px; }
.f-row label i { color: var(--color-danger); font-style: normal; }
.f-half { flex-direction: row; gap: 14px; }
.f-cell { flex: 1; display: flex; flex-direction: column; gap: 6px; }
input[type='text'], input[type='number'], select {
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 8px 11px;
  font-size: var(--font-size-md);
  font-family: inherit;
  outline: none;
  width: 100%;
}
input:focus, select:focus { border-color: var(--color-brand); }
.form-err { color: #d48f87; font-size: var(--font-size-sm); letter-spacing: 0.5px; }
.form-hint { color: var(--color-text-tertiary); font-size: var(--font-size-xs); line-height: 1.5; }
.res-cur { font-size: var(--font-size-md); color: var(--color-text-primary); margin-bottom: 12px; }
.res-presets { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.res-presets .btn.active { border-color: var(--color-brand); color: var(--color-brand); background: var(--color-bg-active); }
.res-tip { font-size: var(--font-size-xs); color: var(--color-text-tertiary); line-height: 1.6; margin: 10px 0 6px; }
.modal-ft {
  display: flex; justify-content: flex-end; gap: 10px;
  padding: 14px 18px;
  border-top: 1px solid var(--color-border-default);
}
</style>
