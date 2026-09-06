<script setup lang="ts">
/**
 * 工具箱页（M5）—— 公招 / 仓库 / 干员识别 + 小游戏（牛杂）+ 历史记录 + 招募联动。
 * 抽卡 / 窥屏为「规划中」占位。
 * 识别流程：POST recognize → 轮询任务状态 → 结果展示 + 自动保存历史记录。
 * 小游戏：列表选游戏（活动/常驻）→ 配参（隐秘战线/像素画）→ 走任务队列入队执行，
 * 进度经引擎 extra_info → WS 日志流回显到页内迷你日志（对齐客户端页内日志区）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDevicesStore } from '@/stores/devices'
import { resourcesApi, type MiniGameEntry } from '@/api/resources'
import { toolboxApi, type RecognizeResult, type ToolboxRecord, type ToolboxTool } from '@/api/toolbox'
import { tasksApi, openLogStream } from '@/api/tasks'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import PixelPaintPanel from '@/components/PixelPaintPanel.vue'
import type { PixelPaintResult } from '@/pixelPaint/PixelPaintHelper'

const devices = useDevicesStore()

// ── 工具导航 ─────────────────────────────────────────
interface ToolDef {
  key: ToolboxTool | 'minigame' | 'gacha' | 'peep'
  label: string
  desc: string
  ico: string
  group: '识别工具' | '小游戏' | '执行工具'
  planned?: boolean
  danger?: boolean
}

const TOOLS: ToolDef[] = [
  { key: 'recruit', label: '公招识别', desc: '识别当前公招界面 · 计算推荐', ico: '招', group: '识别工具' },
  { key: 'depot', label: '仓库识别', desc: '扫描仓库材料与数量', ico: '仓', group: '识别工具' },
  { key: 'operbox', label: '干员识别', desc: '扫描已拥有干员与练度', ico: '员', group: '识别工具' },
  { key: 'minigame', label: '小游戏', desc: '牛杂 · 隐秘战线 / 像素画 / 商店', ico: '戏', group: '小游戏' },
  { key: 'gacha', label: '抽卡', desc: '自动执行寻访（高危）', ico: '抽', group: '执行工具', planned: true, danger: true },
  { key: 'peep', label: '窥屏', desc: '实时查看设备画面', ico: '屏', group: '执行工具', planned: true },
]
const activeTool = ref<ToolboxTool | 'minigame'>('recruit')

// ── 小游戏（牛杂）────────────────────────────────────
const minigames = ref<MiniGameEntry[]>([])
const minigamesErr = ref('')
const mgSelected = ref<MiniGameEntry | null>(null)
const sfEnding = ref('A')
const sfEvent = ref('')
const ppPanel = ref<InstanceType<typeof PixelPaintPanel> | null>(null)
const mgBusy = ref(false)

const sfEndingOpts: DropOption[] = [
  { value: 'A', label: 'A · 物资线（管理）' },
  { value: 'B', label: 'B · 物资线' },
  { value: 'C', label: 'C · 情报线' },
  { value: 'D', label: 'D · 医疗线' },
  { value: 'E', label: 'E · 医疗线' },
]
const sfEventOpts: DropOption[] = [
  { value: '', label: '不指定事件' },
  { value: '支援作战平台', label: '支援作战平台' },
  { value: '游侠', label: '游侠' },
  { value: '诡影迷踪', label: '诡影迷踪' },
]

const mgActivity = computed(() => minigames.value.filter((m) => m.source === 'activity'))
const mgPermanent = computed(() => minigames.value.filter((m) => m.source === 'permanent'))
const isPixelPaint = computed(() => mgSelected.value?.value.startsWith('MiniGame@PixelPaint') ?? false)
const isSecretFront = computed(() => mgSelected.value?.value === 'MiniGame@SecretFront')

function selectMinigame(m: MiniGameEntry) {
  mgSelected.value = m
  taskError.value = ''
}

async function loadMinigames() {
  minigamesErr.value = ''
  try {
    const r = await resourcesApi.stagesToday()
    minigames.value = (r.minigames ?? []) as MiniGameEntry[]
    if (!mgSelected.value) {
      mgSelected.value = minigames.value[0] ?? null
    }
  } catch (e: unknown) {
    minigamesErr.value = (e as { message?: string })?.message ?? '读取小游戏列表失败'
  }
}

// ── 小游戏执行（任务队列通道 + 页内迷你日志） ────────
interface MiniLogLine {
  level: string
  message: string
  ts?: string
}
const miniLogs = ref<MiniLogLine[]>([])
let miniWs: WebSocket | null = null
const MINI_LOG_MAX = 80

function pushMiniLog(line: MiniLogLine) {
  miniLogs.value.unshift(line)
  if (miniLogs.value.length > MINI_LOG_MAX) miniLogs.value.pop()
}

function connectMiniLog(deviceId: number) {
  closeMiniLog()
  const ws = openLogStream(deviceId)
  miniWs = ws
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data as string) as { event?: string; status?: string; level?: string; message?: string; ts?: string }
      if (data.event === 'run_finished') {
        pushMiniLog({ level: 'warn', message: `■ 运行结束（${data.status ?? 'unknown'}）` })
      } else if (data.message) {
        pushMiniLog({ level: data.level ?? 'info', message: data.message, ts: data.ts })
      }
    } catch {
      /* malformed frame — ignore */
    }
  }
}

function closeMiniLog() {
  if (miniWs) {
    miniWs.onclose = null
    miniWs.close()
    miniWs = null
  }
}

async function startMinigame() {
  const dev = targetDevice.value
  if (!dev || dev.status !== 'online') {
    taskError.value = '请先选择在线设备'
    return
  }
  const sel = mgSelected.value
  if (!sel) {
    taskError.value = '请先选择一个小游戏'
    return
  }
  const params: Record<string, unknown> = { game_value: sel.value }
  if (isSecretFront.value) {
    params.ending = sfEnding.value
    params.event = sfEvent.value
  } else if (isPixelPaint.value) {
    const r: PixelPaintResult | null = ppPanel.value?.getResult() ?? null
    if (!r) {
      taskError.value = '请先导入图片并完成转换'
      return
    }
    params.pixel_paint = { swipe: r.swipe, grid_delay: r.grid_delay, groups: r.groups }
  }
  mgBusy.value = true
  taskError.value = ''
  try {
    await tasksApi.run(dev.id, [
      { name: `小游戏 · ${sel.display}`, entry: 'MiniGame', type: '小游戏', params },
    ])
    tip.value = `✔ 「${sel.display}」已加入执行队列${isPixelPaint.value ? '——请确保游戏已停在 24×24 编辑页' : ''}`
    miniLogs.value = []
    connectMiniLog(dev.id)
  } catch (e: unknown) {
    taskError.value = detailOf(e) || '小游戏启动失败'
  } finally {
    mgBusy.value = false
  }
}

// ── 设备 ─────────────────────────────────────────────
const targetId = ref<number | null>(null)
const deviceOpts = computed<DropOption[]>(() =>
  devices.list.map((d) => ({
    value: String(d.id),
    label: `${d.name} · ${d.adb_host}:${d.adb_port}（${d.status}）`,
  })),
)
const targetModel = computed({
  get: () => (targetId.value == null ? '' : String(targetId.value)),
  set: (v: string) => {
    targetId.value = v === '' ? null : Number(v)
  },
})
const targetDevice = computed(
  () => devices.list.find((d) => d.id === targetId.value) ?? null,
)

// ── 名称映射（识别结果 id → 中文名） ─────────────────
const itemNames = ref<Record<string, string>>({})
const operNames = ref<Record<string, string>>({})

// ── 识别流程 ─────────────────────────────────────────
const recognizing = ref(false)
const taskError = ref('')
const taskResult = ref<RecognizeResult | null>(null)
const viewRecord = ref<ToolboxRecord | null>(null)  // 历史调用中的记录（非空=展示历史）
let pollTimer: number | null = null

async function startRecognize() {
  if (!targetDevice.value || targetDevice.value.status !== 'online') {
    taskError.value = '请先选择在线设备'
    return
  }
  recognizing.value = true
  taskError.value = ''
  taskResult.value = null
  viewRecord.value = null
  try {
    const { task_id } = await toolboxApi.recognize(targetDevice.value.id, activeTool.value as ToolboxTool)
    await pollTask(task_id)
  } catch (e: unknown) {
    taskError.value = detailOf(e) || '识别启动失败'
  } finally {
    recognizing.value = false
  }
}

async function pollTask(taskId: string) {
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => { pollTimer = window.setTimeout(r, 2000) })
    try {
      const st = await toolboxApi.taskStatus(taskId)
      if (st.status === 'done') {
        taskResult.value = st.result ?? null
        await loadRecords()
        return
      }
      if (st.status === 'error') {
        taskError.value = st.error ?? '识别失败'
        return
      }
    } catch (e: unknown) {
      taskError.value = (e as { message?: string })?.message ?? '查询识别状态失败'
      return
    }
  }
  taskError.value = '识别超时，请重试'
}

// ── 历史记录（不分设备展示；可筛选指定设备） ──────────
const records = ref<ToolboxRecord[]>([])
const recordsErr = ref('')
const filterDev = ref<number | null>(null)

const devFilterOptions = computed<DropOption[]>(() => [
  { value: '', label: '全部设备' },
  ...devices.list.map((d) => ({
    value: String(d.id),
    label: `${d.name}（${d.status === 'online' ? '在线' : d.status}）`,
  })),
])
const devFilterModel = computed({
  get: () => (filterDev.value == null ? '' : String(filterDev.value)),
  set: (v: string) => {
    filterDev.value = v === '' ? null : Number(v)
  },
})

function devName(id: number): string {
  return devices.list.find((d) => d.id === id)?.name ?? `设备#${id}`
}

async function loadRecords() {
  if (activeTool.value === 'minigame') return // 小游戏无识别历史
  try {
    const r = await toolboxApi.records(activeTool.value as ToolboxTool, filterDev.value ?? undefined)
    records.value = r.records
  } catch (e: unknown) {
    recordsErr.value = (e as { message?: string })?.message ?? '读取历史记录失败'
  }
}

async function viewHistory(rec: ToolboxRecord) {
  viewRecord.value = rec
  taskResult.value = rec.result
  taskError.value = ''
}

async function removeRecord(rec: ToolboxRecord) {
  try {
    await toolboxApi.deleteRecord(rec.id)
    records.value = records.value.filter((r) => r.id !== rec.id)
    if (viewRecord.value?.id === rec.id) {
      viewRecord.value = null
      taskResult.value = null
    }
  } catch (e: unknown) {
    recordsErr.value = (e as { message?: string })?.message ?? '删除记录失败'
  }
}

// ── 招募联动（按识别结果执行真实公招） ───────────────
const executing = ref(false)
const tip = ref('')

async function executeRecruit(level: number) {
  if (!targetDevice.value) return
  const ok = window.confirm(
    `将按 ${level}★ 组合执行真实公招：自动选中对应 Tag 组合并开始招募。\n` +
    '此操作会消耗招募许可并占用公招栏位（9 小时 CD），确认执行？',
  )
  if (!ok) return
  executing.value = true
  taskError.value = ''
  try {
    const res = await toolboxApi.executeRecruit(targetDevice.value.id, level)
    tip.value = `✔ ${res.message}`
  } catch (e: unknown) {
    taskError.value = detailOf(e) || '执行公招失败'
  } finally {
    executing.value = false
  }
}

// ── 展示辅助 ─────────────────────────────────────────
function detailOf(e: unknown): string {
  const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
  const d = err?.response?.data?.detail
  if (Array.isArray(d)) {
    const msgs = d
      .map((x) => (typeof x === 'object' && x !== null && 'msg' in x ? String((x as { msg: unknown }).msg) : ''))
      .filter(Boolean)
    return msgs.length ? msgs.join('；') : '参数校验失败'
  }
  if (typeof d === 'string' && d) return d
  return err?.message ?? '操作失败'
}

function itemName(id: string): string {
  return itemNames.value[id] || id
}

function operName(id: string): string {
  return operNames.value[id] || id
}

function rarityStars(rarity: number): string {
  // battle_data rarity = 星级数（1-6），直接标星（与客户端 OperBox 一致）
  return '★'.repeat(Math.min(6, Math.max(1, rarity)))
}

// ── 干员结果排序与星级筛选 ───────────────────────────
const filterRarity = ref<number | null>(null)
const rarityFilterOptions = computed<DropOption[]>(() => [
  { value: '', label: '全部星级' },
  ...[6, 5, 4, 3, 2, 1].map((r) => ({ value: String(r), label: '★'.repeat(r) })),
])
const rarityFilterModel = computed({
  get: () => (filterRarity.value == null ? '' : String(filterRarity.value)),
  set: (v: string) => {
    filterRarity.value = v === '' ? null : Number(v)
  },
})

/** 干员展示列表：默认高星→低星，同星按名称排序（中文拼音 / 英文首字母） */
const shownOpers = computed(() => {
  const list = taskResult.value?.opers ?? []
  const filtered = filterRarity.value == null ? list : list.filter((o) => o.rarity === filterRarity.value)
  return [...filtered].sort((a, b) => {
    if (a.rarity !== b.rarity) return b.rarity - a.rarity
    return operName(a.id).localeCompare(operName(b.id), 'zh-Hans-CN')
  })
})

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function sortRecruitResults(results: RecognizeResult['results']): RecognizeResult['results'] {
  return results ? [...results].sort((a, b) => b.level - a.level) : []
}

// ── 生命周期 ─────────────────────────────────────────
onMounted(async () => {
  devices.fetchList()
  const [items, opers] = await Promise.all([
    resourcesApi.items().catch(() => []),
    resourcesApi.operators().catch(() => []),
  ])
  itemNames.value = Object.fromEntries(items.map((i) => [i.id, i.name]))
  operNames.value = Object.fromEntries(opers.map((o) => [o.id, o.name]))
  watchDeviceAuto()
  void loadRecords()
  void loadMinigames()
})

function watchDeviceAuto() {
  // 设备列表就绪后默认选在线设备（用于识别操作）
  const stop = watch(
    () => devices.list,
    (list) => {
      if (targetId.value == null) {
        const online = list.find((d) => d.status === 'online')
        targetId.value = online?.id ?? list[0]?.id ?? null
      } else {
        stop()
      }
    },
    { immediate: true },
  )
}

watch(activeTool, () => {
  taskResult.value = null
  viewRecord.value = null
  taskError.value = ''
  tip.value = ''
  if (activeTool.value === 'minigame') {
    // 小游戏：关闭识别历史拉取，接上目标设备日志流
    closeMiniLog()
    miniLogs.value = []
    if (targetId.value != null) connectMiniLog(targetId.value)
    void loadMinigames()
  } else {
    closeMiniLog()
    void loadRecords()
  }
})

// 切换目标设备时：小游戏页重连日志流
watch(targetId, (id) => {
  if (activeTool.value === 'minigame') {
    closeMiniLog()
    miniLogs.value = []
    if (id != null) connectMiniLog(id)
  }
})

watch(filterDev, () => {
  viewRecord.value = null
  taskResult.value = null
  void loadRecords()
})

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer)
  closeMiniLog()
})
</script>

<template>
  <div class="tbx">
    <div class="dashboard">
      <!-- 顶栏 -->
      <div class="top-row">
        <div class="ttl">
          <span class="diamond"></span>
          <div>
            <h2>工具箱</h2>
            <p class="sub">识别工具 · 结果与历史记录（识别需设备在线）</p>
          </div>
        </div>
        <div class="top-right">
          <span class="t">目标设备</span>
          <DropSelect v-model="targetModel" :options="deviceOpts" placeholder="未发现设备" />
          <span class="dev-state" :class="targetDevice?.status">
            {{ targetDevice ? `设备${targetDevice.status === 'online' ? '在线' : targetDevice.status}` : '未选择' }}
          </span>
        </div>
      </div>

      <div v-if="taskError" class="err-bar">⚠ {{ taskError }}</div>
      <div v-if="tip" class="ok-bar">✔ {{ tip }}</div>

      <div class="body">
        <!-- 左：工具导航 -->
        <div class="panel nav-panel">
          <div class="ph"><span class="diamond"></span><b>工具</b><small>设备在线可用</small></div>
          <div class="tools">
            <div class="group-t">识别工具</div>
            <div
              v-for="t in TOOLS.filter((x) => x.group === '识别工具')"
              :key="t.key"
              class="tool"
              :class="{ sel: activeTool === t.key }"
              @click="activeTool = t.key as ToolboxTool"
            >
              <span class="ico"><span>{{ t.ico }}</span></span>
              <div class="ti">
                <div class="nm">{{ t.label }}</div>
                <div class="desc">{{ t.desc }}</div>
              </div>
            </div>
            <div class="group-t">小游戏</div>
            <div
              v-for="t in TOOLS.filter((x) => x.group === '小游戏')"
              :key="t.key"
              class="tool"
              :class="{ sel: activeTool === t.key }"
              @click="activeTool = t.key as 'minigame'"
            >
              <span class="ico"><span>{{ t.ico }}</span></span>
              <div class="ti">
                <div class="nm">{{ t.label }}</div>
                <div class="desc">{{ t.desc }}</div>
              </div>
            </div>
            <div class="group-t">执行工具</div>
            <div
              v-for="t in TOOLS.filter((x) => x.group === '执行工具')"
              :key="t.key"
              class="tool planned"
            >
              <span class="ico"><span>{{ t.ico }}</span></span>
              <div class="ti">
                <div class="nm">{{ t.label }}<span v-if="t.danger" class="tag">高危</span></div>
                <div class="desc">{{ t.desc }} · 规划中</div>
              </div>
            </div>
          </div>
          <p class="note">识别结果自动保存为历史记录；小游戏需设备在线（对齐 MAA 工具箱）。</p>
        </div>

        <!-- 右：内容区 -->
        <div class="right">
          <!-- 小游戏（牛杂） -->
          <template v-if="activeTool === 'minigame'">
            <div class="panel">
              <div class="ph2">
                <span class="diamond"></span>
                <b>小游戏 · 牛杂</b>
                <small>隐秘战线 / 像素画 / 商店 —— 对齐 MAA 工具箱</small>
              </div>
              <div v-if="minigamesErr" class="err-bar">⚠ {{ minigamesErr }}</div>
              <div class="mg-grid">
                <!-- 左：小游戏列表 -->
                <div class="mg-list">
                  <template v-if="mgActivity.length">
                    <div class="mg-group">进行中活动</div>
                    <div
                      v-for="m in mgActivity" :key="m.value"
                      class="mg-item" :class="{ sel: mgSelected?.value === m.value }"
                      @click="selectMinigame(m)"
                    >
                      <span class="nm">{{ m.display }}</span>
                      <span v-if="m.days_left != null" class="dl">{{ m.days_left }} 天</span>
                    </div>
                  </template>
                  <div class="mg-group">常驻</div>
                  <div
                    v-for="m in mgPermanent" :key="m.value"
                    class="mg-item" :class="{ sel: mgSelected?.value === m.value }"
                    @click="selectMinigame(m)"
                  >
                    <span class="nm">{{ m.display }}</span>
                  </div>
                  <div v-if="!minigames.length" class="empty">小游戏列表为空——请先在设置页下载引擎资源</div>
                </div>
                <!-- 右：参数 + 执行 -->
                <div class="mg-detail">
                  <div v-if="mgSelected" class="mg-tip">{{ mgSelected.tip || mgSelected.display }}</div>
                  <!-- 隐秘战线 -->
                  <template v-if="isSecretFront">
                    <div class="f-row">
                      <label class="f-label">结局<small>决定路线与分队（A/B 物资 · C 情报 · D/E 医疗）</small></label>
                      <DropSelect v-model="sfEnding" :options="sfEndingOpts" />
                    </div>
                    <div class="f-row">
                      <label class="f-label">目标事件<small>指定后优先进该事件（可空）</small></label>
                      <DropSelect v-model="sfEvent" :options="sfEventOpts" />
                    </div>
                  </template>
                  <!-- 像素画 -->
                  <PixelPaintPanel v-else-if="isPixelPaint" ref="ppPanel" :disabled="mgBusy" />
                  <!-- 商店 / 其他 -->
                  <div v-else-if="mgSelected" class="empty">
                    将自动导航并执行「{{ mgSelected.display }}」；
                    <template v-if="mgSelected.value.includes('Store')">请确认库存充足，任务会在购买完成后停止。</template>
                    <template v-else>执行前请确认设备画面可回到主界面。</template>
                  </div>
                  <div class="mg-start">
                    <button class="btn-gold" :disabled="mgBusy || !targetDevice || targetDevice.status !== 'online' || !mgSelected" @click="startMinigame">
                      {{ mgBusy ? '入队中…' : '▶ LINK START!' }}
                    </button>
                    <span class="t">执行经任务队列（与作战任务互斥）</span>
                  </div>
                  <!-- 迷你日志 -->
                  <div v-if="miniLogs.length" class="mg-log">
                    <div v-for="(l, i) in miniLogs" :key="i" class="mg-log-row" :class="l.level">
                      <span class="msg">{{ l.message }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- 识别操作 -->
          <div class="panel" v-else>
            <div class="ph2">
              <span class="diamond"></span>
              <b>{{ TOOLS.find((t) => t.key === activeTool)?.label }}</b>
              <small>{{ TOOLS.find((t) => t.key === activeTool)?.desc }}</small>
              <DropSelect
                v-if="activeTool === 'operbox'"
                v-model="rarityFilterModel"
                :options="rarityFilterOptions"
                class="rare-filter"
              />
            </div>
            <div class="op-row">
              <span class="t">
                设备：{{ targetDevice ? targetDevice.name : '未选择' }}
                <template v-if="viewRecord">· 正在查看历史记录（{{ fmtTime(viewRecord.created_at) }}）</template>
                <template v-else-if="taskResult">· 上次识别完成</template>
              </span>
              <button class="btn-gold" :disabled="recognizing || !targetDevice || targetDevice.status !== 'online'" @click="startRecognize">
                {{ recognizing ? '识别中…' : '▶ 开始识别' }}
              </button>
            </div>

            <!-- 结果区 -->
            <template v-if="viewRecord || taskResult">
              <!-- 公招结果 -->
              <template v-if="activeTool === 'recruit'">
                <div v-if="taskResult?.results?.length" class="recruit-grid">
                  <div v-for="(r, i) in sortRecruitResults(taskResult.results)" :key="i" class="rec-card">
                    <div class="star">{{ '★'.repeat(r.level) }}</div>
                    <div class="tag-line"><b>{{ r.tags.join(' · ') }}</b></div>
                    <div class="opers">{{ r.opers.map((o) => o.name).join(' / ') || '—' }}</div>
                    <div class="act">
                      <button class="mini" :disabled="executing" @click="executeRecruit(r.level)">▶ 按此结果执行招募</button>
                    </div>
                  </div>
                </div>
                <div v-else class="empty">未识别到推荐组合——请确认设备画面在公招界面</div>
              </template>

              <!-- 仓库结果 -->
              <template v-else-if="activeTool === 'depot'">
                <div v-if="taskResult?.items && Object.keys(taskResult.items).length" class="depot-list">
                  <div v-for="(cnt, id) in taskResult.items" :key="id" class="depot-row">
                    <span class="item">{{ itemName(id) }}</span>
                    <span class="cnt">{{ cnt }}</span>
                  </div>
                </div>
                <div v-else class="empty">未识别到仓库数据——请确认设备画面在仓库/物品界面</div>
              </template>

              <!-- 干员结果 -->
              <template v-else>
                <div v-if="shownOpers.length" class="oper-list">
                  <div v-for="o in shownOpers" :key="o.id" class="oper-row">
                    <span class="rare" :class="`r${Math.min(6, o.rarity)}`">{{ rarityStars(o.rarity) }}</span>
                    <span class="nm">{{ operName(o.id) }}</span>
                    <span class="lvl">精{{ o.elite }} Lv.{{ o.level }} · 潜{{ o.potential }}</span>
                  </div>
                </div>
                <div v-else-if="taskResult?.opers?.length" class="empty">当前星级筛选下没有干员</div>
                <div v-else class="empty">未识别到干员数据——请确认设备画面在干员界面</div>
              </template>
            </template>
            <div v-else class="empty placeholder">点击「▶ 开始识别」获取当前设备画面识别结果；识别完成后自动保存到历史记录</div>
          </div>

          <!-- 历史记录 -->
          <div class="panel" v-if="activeTool !== 'minigame'">
            <div class="ph2">
              <span class="diamond"></span><b>历史识别记录</b>
              <small>保存每次识别结果 · 点击查看详情</small>
              <DropSelect v-model="devFilterModel" :options="devFilterOptions" class="dev-filter" />
            </div>
            <div v-if="recordsErr" class="hist-err">⚠ {{ recordsErr }}</div>
            <div v-if="records.length === 0" class="hist-empty">暂无历史记录——识别一次后自动保存</div>
            <div class="hist">
              <div
                v-for="rec in records"
                :key="rec.id"
                class="h-item"
                :class="{ sel: viewRecord?.id === rec.id }"
                @click="viewHistory(rec)"
              >
                <span class="time">{{ fmtTime(rec.created_at) }}</span>
                <span class="dev">{{ devName(rec.device_id) }}</span>
                <span class="sum">{{ rec.summary }}</span>
                <span class="h-ops">
                  <button class="mini" @click.stop="removeRecord(rec)">删除</button>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tbx { flex: 1; min-height: 0; display: flex; flex-direction: column; }
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
.top-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.top-right .t { font-size: var(--font-size-sm); color: var(--color-text-tertiary); letter-spacing: var(--font-tracking-widest); }
.dev-state { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.dev-state.online { color: var(--color-success); }

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

.body { display: grid; grid-template-columns: 250px 1fr; gap: 16px; align-items: start; }
@media (max-width: 1080px) { .body { grid-template-columns: 1fr; } }
.panel { background: var(--color-bg-panel); border: 1px solid var(--color-border-default); padding: 16px; }
.ph { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.ph .diamond { width: 10px; height: 10px; border: 1px solid var(--color-brand); transform: rotate(45deg); flex-shrink: 0; background: rgba(216, 177, 106, 0.15); }
.ph b { font-size: var(--font-size-md); letter-spacing: 1px; }
.ph small { margin-left: auto; color: var(--color-text-tertiary); font-size: var(--font-size-2xs); }
.ph2 { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.ph2 .diamond { width: 10px; height: 10px; border: 1px solid var(--color-brand); transform: rotate(45deg); flex-shrink: 0; background: rgba(216, 177, 106, 0.15); }
.ph2 b { font-size: var(--font-size-md); letter-spacing: 1px; }
.ph2 small { margin-left: auto; color: var(--color-text-tertiary); font-size: var(--font-size-2xs); }

/* 工具导航 */
.tools { display: flex; flex-direction: column; gap: 6px; }
.group-t { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); letter-spacing: 2px; margin: 12px 2px 4px; }
.tool {
  border: 1px solid var(--color-border-default);
  border-left: 2px solid transparent;
  padding: 9px 12px; cursor: pointer;
  display: flex; align-items: center; gap: 10px;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.tool:hover { border-color: var(--color-brand-strong); }
.tool.sel { background: var(--color-bg-active); border-color: var(--color-brand-strong); border-left: 2px solid var(--color-brand-strong); }
.tool.planned { opacity: 0.5; cursor: not-allowed; }
.tool .ico {
  width: 22px; height: 22px; border: 1px solid var(--color-border-strong);
  transform: rotate(45deg); display: flex; align-items: center; justify-content: center;
  font-size: var(--font-size-2xs); flex-shrink: 0; color: var(--color-text-secondary);
}
.tool.sel .ico { border-color: var(--color-brand-strong); color: var(--color-brand); }
.tool .ico span { transform: rotate(-45deg); }
.tool .ti { min-width: 0; }
.tool .nm { font-size: var(--font-size-md); }
.tool .nm .tag { font-size: var(--font-size-2xs); color: var(--color-warning); border: 1px solid var(--color-warning); padding: 0 5px; letter-spacing: 1px; margin-left: 6px; }
.tool .desc { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); margin-top: 2px; }

/* 操作行 */
.op-row { display: flex; align-items: center; gap: 14px; padding: 10px 0; border-bottom: 1px dashed var(--color-border-default); }
.op-row .t { font-size: var(--font-size-xs); color: var(--color-text-tertiary); flex: 1; line-height: 1.7; }
.btn-gold {
  background: rgba(216, 177, 106, 0.18);
  border: 1px solid var(--color-brand-strong); color: var(--color-brand);
  font-weight: 700; padding: 9px 24px; letter-spacing: 1.5px; cursor: pointer;
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.btn-gold:hover:not(:disabled) { box-shadow: var(--shadow-glow-lg); }
.btn-gold:disabled { opacity: 0.45; cursor: not-allowed; }

/* 公招结果 */
.recruit-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 12px; }
@media (max-width: 1200px) { .recruit-grid { grid-template-columns: repeat(2, 1fr); } }
.rec-card { border: 1px solid var(--color-border-default); padding: 10px 12px; background: var(--color-bg-subtle); }
.rec-card .star { color: var(--color-brand); font-size: var(--font-size-md); letter-spacing: 2px; }
.rec-card .tag-line { font-size: var(--font-size-xs); color: var(--color-text-secondary); margin-top: 6px; line-height: 1.7; }
.rec-card .tag-line b { color: var(--color-brand); font-weight: 400; }
.rec-card .opers { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); margin-top: 6px; line-height: 1.7; }
.rec-card .act { margin-top: 8px; display: flex; gap: 6px; }
.mini {
  border: 1px solid var(--color-border-default); background: none;
  color: var(--color-text-secondary); font-size: var(--font-size-2xs);
  padding: 2px 8px; cursor: pointer;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.mini:hover:not(:disabled) { border-color: var(--color-brand); color: var(--color-brand); }
.mini:disabled { opacity: 0.45; cursor: not-allowed; }

/* 仓库结果 */
.depot-list { margin-top: 12px; max-height: 360px; overflow-y: auto; }
.depot-row { display: flex; align-items: center; gap: 10px; padding: 5px 0; border-bottom: 1px dashed var(--color-border-default); font-size: var(--font-size-md); }
.depot-row .item { flex: 1; }
.depot-row .cnt { font-family: var(--font-family-mono); color: var(--color-brand); font-size: var(--font-size-md); }

/* 干员结果 */
.oper-list { margin-top: 12px; max-height: 360px; overflow-y: auto; }
.oper-row { display: flex; align-items: center; gap: 10px; padding: 5px 0; border-bottom: 1px dashed var(--color-border-default); font-size: var(--font-size-md); }
.oper-row .rare { font-size: var(--font-size-xs); letter-spacing: 1px; }
.oper-row .rare.r6 { color: var(--color-brand); }
.oper-row .rare.r5 { color: var(--color-warning); }
.oper-row .rare.r4 { color: var(--color-success); }
.oper-row .nm { flex: 1; }
.oper-row .lvl { font-family: var(--font-family-mono); color: var(--color-text-tertiary); font-size: var(--font-size-2xs); }

.empty {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border-default); padding: 22px;
  text-align: center; line-height: 1.7; margin-top: 12px;
}
.empty.placeholder { padding: 46px 20px; }

/* 历史记录 */
.hist { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.hist-empty { font-size: var(--font-size-xs); color: var(--color-text-tertiary); border: 1px dashed var(--color-border-default); padding: 18px; text-align: center; }
.hist-err { font-size: var(--font-size-xs); color: var(--color-danger); padding: 8px 0; }
.h-item {
  border: 1px solid var(--color-border-default); padding: 8px 12px;
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  background: var(--color-bg-subtle);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.h-item:hover { border-color: var(--color-brand-strong); }
.h-item.sel { border-color: var(--color-brand-strong); background: var(--color-bg-active); }
.h-item .time { font-family: var(--font-family-mono); font-size: var(--font-size-2xs); color: var(--color-text-tertiary); flex-shrink: 0; }
.h-item .dev {
  flex-shrink: 0;
  font-size: var(--font-size-2xs); color: var(--color-text-secondary);
  border: 1px solid var(--color-border-default); padding: 0 6px;
  letter-spacing: 0.5px; white-space: nowrap;
}
.h-item .sum { flex: 1; font-size: var(--font-size-xs); color: var(--color-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.h-item .h-ops { flex-shrink: 0; }
.note { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); margin-top: 10px; line-height: 1.7; }

/* 小游戏（牛杂） */
.mg-grid { display: grid; grid-template-columns: 240px 1fr; gap: 16px; margin-top: 8px; }
@media (max-width: 1080px) { .mg-grid { grid-template-columns: 1fr; } }
.mg-list { border: 1px solid var(--color-border-default); background: var(--color-bg-subtle); padding: 8px; max-height: 420px; overflow-y: auto; }
.mg-group { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); letter-spacing: 2px; margin: 6px 2px; }
.mg-item {
  display: flex; align-items: center; gap: 8px;
  border: 1px solid transparent; padding: 8px 10px; cursor: pointer;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.mg-item:hover { border-color: var(--color-brand-strong); }
.mg-item.sel { background: var(--color-bg-active); border-color: var(--color-brand-strong); }
.mg-item .nm { flex: 1; font-size: var(--font-size-sm); }
.mg-item .dl {
  font-size: var(--font-size-2xs); color: var(--color-warning);
  border: 1px solid var(--color-warning); padding: 0 5px; white-space: nowrap;
}
.mg-detail { min-width: 0; }
.mg-tip {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border-default); padding: 8px 12px; margin-bottom: 10px; line-height: 1.7;
}
.mg-start { display: flex; align-items: center; gap: 14px; margin-top: 14px; }
.mg-start .t { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); }
.mg-log {
  margin-top: 12px; max-height: 220px; overflow-y: auto;
  border: 1px solid var(--color-border-default); background: var(--color-bg-subtle); padding: 8px 12px;
}
.mg-log-row { font-size: var(--font-size-2xs); line-height: 1.9; color: var(--color-text-secondary); }
.mg-log-row.warn { color: var(--color-warning); }
.mg-log-row.error { color: var(--color-danger); }
.mg-log-row.ok { color: var(--color-success); }
.mg-log-row .msg { word-break: break-all; }
</style>
