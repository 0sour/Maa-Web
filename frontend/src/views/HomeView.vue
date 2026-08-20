<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { useDevicesStore } from '@/stores/devices'
import { useTasksStore } from '@/stores/tasks'
import { resourcesApi, type ResourceStatus, type TodayStages } from '@/api/resources'
import { useTaskQueue } from '@/tasks/useTaskQueue'
import { useQueueDraft } from '@/tasks/useQueueDraft'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import TaskQueuePanel from '@/tasks/TaskQueuePanel.vue'
import TaskParamsPanel from '@/tasks/TaskParamsPanel.vue'

const app = useAppStore()
const devices = useDevicesStore()
const tasks = useTasksStore()

// ── 作战队列（后端草稿：跨浏览器一致，防抖保存；刷新/切页不丢失） ──
const queueDraft = useQueueDraft('daily')

const {
  queue, adding, selectedTask, countChecked,
  addTask, selectTask, toggleChecked, removeTask, onDragStart, onDrop,
  payload, serialize, restore,
} = useTaskQueue()

// 任何队列/参数改动 → 防抖保存到后端
queueDraft.watchSave(queue, serialize)

// ── 目标设备（本次作战执行对象） ─────────────────────────
const targetId = ref<number | null>(null)
const targetDevice = computed(
  () => devices.list.find((d) => d.id === targetId.value) ?? null,
)
const onlineDevices = computed(() => devices.list.filter((d) => d.status === 'online'))
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

// ── LINK START / STOP（真实调用任务队列 API） ────────────
const canRun = computed(() => {
  if (tasks.busy || tasks.running) return false
  return targetDevice.value !== null && countChecked.value > 0
})

async function linkStart() {
  if (!targetDevice.value) {
    tasks.pushLog({ level: 'error', message: '⚠ 请先在顶部选择目标设备' })
    return
  }
  const items = payload()
  if (items.length === 0) {
    tasks.pushLog({ level: 'error', message: '⚠ 未勾选任何任务，请勾选后启动' })
    return
  }
  // 「仅一次」任务本次生效后自动复位
  queue.value.forEach((t) => {
    if (t.once) { t.once = false; t.checked = false }
  })
  await tasks.run(targetDevice.value.id, items)
}

async function stopRun() {
  if (targetDevice.value) await tasks.stop(targetDevice.value.id)
}

// ── 状态映射 ───────────────────────────────────────────
const runnerStatus = computed(() => {
  const s = tasks.status?.status ?? 'idle'
  const map: Record<string, { text: string; cls: string }> = {
    idle: { text: '待命', cls: 'idle' },
    running: { text: '运行中', cls: 'run' },
    stopping: { text: '停止中', cls: 'wait' },
    finished: { text: '已完成', cls: 'ok' },
    error: { text: '异常', cls: 'error' },
    stopped: { text: '已停止', cls: 'idle' },
  }
  return map[s] ?? { text: s, cls: 'idle' }
})

// ── KPI（真实数据） ─────────────────────────────────────
const kpis = computed(() => {
  const apiText: Record<string, string> = {
    ok: '运行中', degraded: '降级', starting: '启动中', error: '离线', unknown: '未知',
  }
  const eng = devices.detect
  return [
    {
      key: 'api', label: '后端服务',
      val: apiText[app.api.status] ?? '未知', unit: '',
      delta: app.api.version ? `v${app.api.version}` : '待连接',
      tone: app.api.status === 'ok' ? 'up' : app.api.status === 'error' ? 'down' : 'flat',
    },
    {
      key: 'eng', label: '识别引擎',
      val: eng?.engine_version && eng.engine_version !== 'unavailable' ? eng.engine_version : '—',
      unit: '',
      delta: eng?.engine_available ? 'Asst 引擎已就绪' : '引擎降级 · 仅 ADB',
      tone: eng?.engine_available ? 'up' : 'flat',
    },
    {
      key: 'dev', label: '可部署设备',
      val: String(devices.list.length), unit: ' 台',
      delta: onlineDevices.value.length > 0 ? `${onlineDevices.value.length} 台在线` : '无在线设备',
      tone: onlineDevices.value.length > 0 ? 'up' : 'flat',
    },
    {
      key: 'run', label: '作战队列',
      val: runnerStatus.value.text, unit: '',
      delta: tasks.status?.summary ? `当前：${tasks.status.summary}` : tasks.running ? '执行中…' : '待命',
      tone: tasks.running ? 'up' : tasks.status?.status === 'error' ? 'down' : 'flat',
    },
  ]
})

// ── 日志滚动 ───────────────────────────────────────────
const logBox = ref<HTMLElement | null>(null)
watch(() => tasks.logs.length, async () => {
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
})

// ── 日志级别展示 ───────────────────────────────────────
function levelCls(level?: string): string {
  return `c-${level ?? 'info'}`
}
function tagOf(level?: string): string {
  const map: Record<string, string> = {
    ok: '[OK]', warn: '[WARN]', error: '[ERR]', info: '[INFO]',
  }
  return map[level ?? 'info'] ?? '[INFO]'
}
function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--:--:--'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// ── MAA 引擎包（S-07 主动下载/更新） ───────────────────
const res = ref<ResourceStatus | null>(null)
const resPoll = ref<number | undefined>(undefined)
const syncPoll = ref<number | undefined>(undefined)

const dynamicInfo = computed(() => {
  const r = res.value
  if (!r) return ''
  if (r.dynamic_syncing) {
    return `动态资源同步中（${r.dynamic_mode === 'full' ? '全量' : '增量'} ${r.dynamic_done}/${r.dynamic_pending}）`
  }
  if (r.dynamic_error) return `动态资源异常：${r.dynamic_error}`
  if (r.dynamic_synced_at) {
    const d = new Date(r.dynamic_synced_at)
    const p = (n: number) => String(n).padStart(2, '0')
    return `动态资源已同步 ${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  }
  return '动态资源未同步（活动地图/模板）'
})

async function startDynamicSync() {
  if (res.value?.dynamic_syncing) return
  try {
    const r = await resourcesApi.sync()
    tasks.pushLog({ level: 'info', message: r.message })
    if (!r.updating) return
    // 同步期间轮询进度，完成后刷新状态
    window.clearInterval(syncPoll.value)
    syncPoll.value = window.setInterval(async () => {
      await loadResourceStatus()
      if (!res.value?.dynamic_syncing) {
        window.clearInterval(syncPoll.value)
        syncPoll.value = undefined
        const m = res.value?.dynamic_error
          ? `✖ 动态资源同步失败：${res.value.dynamic_error}`
          : '✔ 动态资源已更新'
        tasks.pushLog({ level: res.value?.dynamic_error ? 'error' : 'ok', message: m })
      }
    }, 3000)
  } catch (e: unknown) {
    tasks.pushLog({ level: 'error', message: `✖ 动态资源同步失败：${(e as { message?: string })?.message ?? e}` })
  }
}

const resChip = computed(() => {
  if (!res.value) return { cls: 'idle', text: '检查中…' }
  if (res.value.updating) {
    const pct = Math.round((res.value.progress ?? 0) * 100)
    return { cls: 'wait', text: `更新中 ${pct}%` }
  }
  if (res.value.ready) {
    return res.value.update_available
      ? { cls: 'wait', text: '可更新' }
      : { cls: 'on', text: '就绪' }
  }
  if (res.value.update_error) return { cls: 'off', text: '更新失败' }
  return { cls: 'off', text: '未安装' }
})

const resBtnText = computed(() => {
  if (res.value?.updating) return '更新中…'
  if (res.value?.ready) return res.value.update_available ? '更新引擎包' : '已是最新'
  return '下载引擎包'
})

async function loadResourceStatus() {
  try {
    res.value = await resourcesApi.status()
  } catch {
    /* 后端不可达时保持空，不阻塞页面 */
  }
}

async function startResourceUpdate() {
  if (res.value?.updating) return
  try {
    await resourcesApi.update()
    await loadResourceStatus()
  } catch (e: unknown) {
    tasks.pushLog({ level: 'error', message: `✖ 引擎包更新失败：${(e as { message?: string })?.message ?? e}` })
    return
  }
  // 更新期间轮询进度，完成后刷新任务状态（resource_ready 变化）
  window.clearInterval(resPoll.value)
  resPoll.value = window.setInterval(async () => {
    await loadResourceStatus()
    if (!res.value?.updating) {
      window.clearInterval(resPoll.value)
      resPoll.value = undefined
      if (targetId.value != null) tasks.fetchStatus(targetId.value)
      if (res.value?.update_error) {
        tasks.pushLog({ level: 'error', message: `✖ 引擎包更新失败：${res.value.update_error}` })
      } else {
        tasks.pushLog({ level: 'ok', message: `✔ 引擎包已更新（${res.value?.local_version ?? ''}）` })
      }
    }
  }, 3000)
}

// ── 今日开放关卡（对齐 MAA 客户端主界面提示） ──────────
const stagesToday = ref<TodayStages | null>(null)
const stagesTodayErr = ref('')

const sourceLabels: Record<string, string> = {
  web: '官方数据', cache: '缓存数据', local: '本地常驻',
}

function daysLeftText(n: number | null | undefined): string {
  if (n == null) return '—'
  return n > 0 ? `剩余 ${n} 天` : '不足一日'
}

async function loadStagesToday() {
  try {
    stagesToday.value = await resourcesApi.stagesToday()
    stagesTodayErr.value = ''
  } catch (e: unknown) {
    stagesTodayErr.value = (e as { message?: string })?.message ?? '读取今日开放失败'
  }
}

// ── 生命周期 ───────────────────────────────────────────
onMounted(async () => {
  app.probeBackend()
  devices.fetchList()
  devices.detectDevices()
  loadResourceStatus()
  loadStagesToday()
  // 后端草稿回填（跨浏览器一致；加载完成后 watchSave 才生效）
  const draft = await queueDraft.loadDraft()
  if (draft) restore(draft)
  // 默认选中第一台在线设备
  watch(
    () => devices.list,
    (list) => {
      if (targetId.value == null) {
        const online = list.find((d) => d.status === 'online')
        targetId.value = online?.id ?? list[0]?.id ?? null
      }
    },
    { immediate: true },
  )
})

watch(targetId, async (id) => {
  tasks.closeStream()
  if (id == null) return
  // 当天日志持久化：切页面/设备自动回填当天记录，跨天自动归档到历史（/logs）
  tasks.connectStream(id)
  await tasks.loadToday(id)
  tasks.fetchStatus(id)
})

onBeforeUnmount(() => {
  tasks.closeStream()
  window.clearInterval(resPoll.value)
  window.clearInterval(syncPoll.value)
})
</script>

<template>
  <div class="home">
    <div class="dashboard">
      <!-- KPI 区（真实数据） -->
      <div class="kpis">
        <div v-for="k in kpis" :key="k.key" class="kpi">
          <div class="label">{{ k.label }}</div>
          <div class="val">{{ k.val }}<small v-if="k.unit">{{ k.unit }}</small></div>
          <div class="delta" :class="k.tone">{{ k.delta }}</div>
        </div>
      </div>

      <!-- 目标设备选择行 -->
      <div class="target-row">
        <span class="t">目标设备</span>
        <DropSelect v-model="targetModel" :options="deviceOpts" placeholder="未发现设备" />
        <span class="dev-state" :class="targetDevice?.status">
          {{ targetDevice ? `设备${targetDevice.status === 'online' ? '在线' : targetDevice.status}` : '未选择' }}
        </span>
        <span v-if="targetDevice?.last_error" class="dev-err" :title="targetDevice.last_error">
          ⚠ {{ targetDevice.last_error }}
        </span>
      </div>

      <!-- MAA 引擎包状态条（S-07 主动下载/更新） -->
      <div class="res-row">
        <span class="t">MAA 引擎包</span>
        <span class="res-chip" :class="resChip.cls">
          <span class="d"></span>{{ resChip.text }}
        </span>
        <template v-if="res">
          <span class="res-info">
            <template v-if="res.ready">
              版本 {{ res.local_version }} · pipeline ×{{ res.pipelines }}
              <template v-if="res.update_available">（远端 {{ res.remote_latest }}）</template>
            </template>
            <template v-else-if="res.update_error">{{ res.update_error }}</template>
            <template v-else-if="!res.installed">未安装 · 点击右侧按钮从官方源下载（{{ res.remote_latest ?? '…' }}）</template>
          </span>
          <progress
            v-if="res.updating"
            class="res-progress"
            :value="res.progress"
            max="1"
          ></progress>
        </template>
        <span class="dynamic-info">{{ dynamicInfo }}</span>
        <button class="add-btn res-btn" :disabled="res?.updating" @click="startResourceUpdate">
          {{ resBtnText }}
        </button>
        <button
          class="add-btn ghost res-btn"
          :disabled="res?.updating || res?.dynamic_syncing"
          @click="startDynamicSync"
        >同步动态资源</button>
      </div>

      <!-- 今日开放关卡（对齐 MAA 客户端主界面提示） -->
      <div v-if="stagesToday" class="panel today-panel">
        <div class="panel-hd">
          <span class="t">今日开放</span>
          <span class="sub">游戏日 {{ stagesToday.game_day.weekday }} · {{ sourceLabels[stagesToday.source] ?? stagesToday.source }}</span>
          <button class="today-refresh" title="刷新" @click="loadStagesToday">⟳</button>
        </div>
        <div v-if="stagesTodayErr" class="today-err">⚠ {{ stagesTodayErr }}</div>
        <div class="today-body">
          <template v-if="stagesToday.resource_collection">
            <div class="rc-line">｢{{ stagesToday.resource_collection.name }}｣ {{ daysLeftText(stagesToday.resource_collection.days_left) }}</div>
          </template>
          <template v-for="act in stagesToday.activities" :key="act.name">
            <div class="act-block">
              <div class="act-head">｢{{ act.name }}｣ {{ daysLeftText(act.days_left) }}</div>
              <div v-for="(s, si) in act.stages" :key="si" class="today-stage">
                <span class="st">{{ s.stage }}</span>
                <span class="dp">{{ s.drop }}</span>
              </div>
            </div>
          </template>
          <div class="perm-block">
            <div v-for="(s, si) in stagesToday.open_stages" :key="si" class="today-stage">
              <span class="st">{{ s.stage }}</span>
              <span class="lbl">{{ s.label }}</span>
              <span class="dp">{{ s.drops.map((g) => g.join(' / ')).join(' 或 ') }}</span>
            </div>
          </div>
          <div
            v-if="!stagesToday.resource_collection && stagesToday.activities.length === 0 && stagesToday.open_stages.length === 0"
            class="today-empty"
          >暂无可开放的关卡信息——网络不可用时可查看下方常驻关卡</div>
        </div>
      </div>

      <!-- 双栏：作战部署（共享组件）+ 作战记录 -->
      <div class="double">
        <div class="panel-col">
          <TaskQueuePanel
            :queue="queue"
            :adding="adding"
            title="作战部署"
            subtitle="自动保存 · 拖拽排序 · 勾选启用"
            @toggle-add="adding = !adding"
            @add="addTask"
            @select="selectTask"
            @toggle-checked="toggleChecked"
            @remove="removeTask"
            @dragstart="onDragStart"
            @drop="onDrop"
          />
          <TaskParamsPanel :selected-task="selectedTask" />
        </div>

        <!-- 作战记录（当天日志，跨页面保留；仅普通任务，自动任务见「自动任务」页） -->
        <div class="panel">
          <div class="panel-hd">
            <span class="t">作战记录</span>
            <span class="sub">实时情报 · {{ tasks.normalTodayLogs.length }} 行（当天）</span>
          </div>
          <div ref="logBox" class="log">
            <div v-if="tasks.normalTodayLogs.length === 0" class="log-empty">今天暂无日志——等待作战开始后实时显示</div>
            <div v-for="(l, i) in tasks.normalTodayLogs" :key="i" class="l">
              <span class="t">{{ fmtTime(l.ts ?? '') }}</span>
              <span :class="levelCls(l.level)">{{ tagOf(l.level) }}</span>
              <span class="c-dim">{{ l.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- LINK START / STOP 底栏 -->
    <div class="start-row">
      <button v-if="!tasks.running" class="linkstart" :disabled="!canRun" @click="linkStart">▶ LINK START</button>
      <button v-else class="linkstart stop" @click="stopRun">■ STOP</button>
      <div class="start-hint">
        <template v-if="targetDevice">
          执行 {{ targetDevice.name }} · 队列 {{ countChecked }} 项
          <span v-if="tasks.status?.summary"> · {{ tasks.status.summary }}</span><br>
          <template v-if="tasks.running">运行中 · 点击 STOP 停止当前队列</template>
          <template v-else>就绪 · 勾选任务后启动</template>
        </template>
        <template v-else>请先在设备管理添加并连接设备</template>
      </div>
      <span v-if="tasks.error" class="run-err">⚠ {{ tasks.error }}</span>
    </div>
  </div>
</template>

<style scoped>
.home { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.dashboard {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 24px 26px;
  display: flex; flex-direction: column; gap: 14px;
}

/* ── KPI ─────────────────────────────── */
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 4px; }
@media (max-width: 1080px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
.kpi {
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  padding: 16px 18px; position: relative;
  transition: border-color var(--motion-duration-normal) var(--motion-easing-standard);
}
.kpi::after {
  content: ""; position: absolute; top: -1px; right: -1px;
  width: 12px; height: 12px;
  border-top: 2px solid var(--color-brand-strong);
  border-right: 2px solid var(--color-brand-strong);
  opacity: 0.7;
}
.kpi .label { color: var(--color-text-tertiary); font-size: var(--font-size-sm); letter-spacing: var(--font-tracking-widest); }
.kpi .val {
  font-size: var(--font-size-hero); font-weight: var(--font-weight-bold);
  margin-top: 7px; color: var(--color-text-primary);
  font-family: var(--font-family-serif); line-height: 1.25;
}
.kpi .val small { font-size: var(--font-size-md); color: var(--color-text-secondary); font-weight: 400; }
.kpi .delta { font-size: var(--font-size-sm); margin-top: 5px; letter-spacing: 0.5px; }
.up { color: var(--color-success); }
.down { color: var(--color-danger); }
.flat { color: var(--color-text-secondary); }

/* ── 目标设备行 ──────────────────────── */
.target-row {
  display: flex; align-items: center; gap: 12px;
  padding: 9px 14px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-default);
}
.target-row .t { font-size: var(--font-size-sm); color: var(--color-text-tertiary); letter-spacing: var(--font-tracking-widest); }
.dev-select {
  background: var(--color-bg-panel); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 6px 11px; font-size: var(--font-size-md); outline: none;
  font-family: inherit; min-width: 300px;
}
.dev-select:focus { border-color: var(--color-brand); }
.dev-state { font-size: var(--font-size-sm); color: var(--color-text-secondary); letter-spacing: 0.5px; }
.dev-state.online { color: var(--color-success); }
.dev-state.error { color: var(--color-danger); }
.dev-err { font-size: var(--font-size-xs); color: var(--color-warning); max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── MAA 引擎包行 ─────────────────────── */
.res-row {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 14px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-default);
  border-top: none;
}
.res-row .t { font-size: var(--font-size-sm); color: var(--color-text-tertiary); letter-spacing: var(--font-tracking-widest); }
.res-chip {
  font-size: var(--font-size-sm); color: var(--color-text-secondary);
  border: 1px solid var(--color-border-default);
  padding: 4px 12px; display: flex; align-items: center; gap: 7px;
  letter-spacing: 0.5px; flex-shrink: 0;
}
.res-chip .d { width: 8px; height: 8px; border: 1px solid; transform: rotate(45deg); }
.res-chip.on { border-color: var(--color-success); color: var(--color-success); }
.res-chip.on .d { border-color: var(--color-success); background: rgba(159, 181, 111, 0.4); }
.res-chip.wait { border-color: var(--color-warning); color: var(--color-warning); }
.res-chip.wait .d { border-color: var(--color-warning); background: rgba(201, 143, 78, 0.4); }
.res-chip.off { border-color: var(--color-danger); color: #d48f87; }
.res-chip.off .d { border-color: var(--color-danger); background: rgba(176, 91, 83, 0.4); }
.res-chip.idle { border-color: var(--color-text-tertiary); }
.res-chip.idle .d { border-color: var(--color-text-tertiary); }
.res-info {
  flex: 1; font-size: var(--font-size-sm); color: var(--color-text-tertiary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dynamic-info {
  flex-shrink: 0; font-size: var(--font-size-xs); color: var(--color-text-secondary);
  letter-spacing: 0.3px; max-width: 300px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ── 今日开放面板 ─────────────────────── */
.today-panel {
  border-top: 1px solid var(--color-border-default);
}
.today-panel .panel-hd { display: flex; align-items: center; gap: 10px; padding: 10px 14px; }
.today-panel .panel-hd .t { font-size: var(--font-size-sm); color: var(--color-text-secondary); letter-spacing: var(--font-tracking-widest); }
.today-panel .panel-hd .sub { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); letter-spacing: 0.5px; }
.today-panel .today-refresh {
  margin-left: auto; border: 1px solid var(--color-border-default); background: none;
  color: var(--color-text-tertiary); font-size: var(--font-size-sm);
  padding: 2px 8px; cursor: pointer; transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.today-panel .today-refresh:hover { color: var(--color-brand); border-color: var(--color-brand); }
.today-panel .today-body {
  display: flex; flex-direction: column; gap: 4px;
  padding: 0 14px 10px; max-height: 300px; overflow-y: auto;
}
.today-err { font-size: var(--font-size-xs); color: var(--color-danger); padding: 0 14px 8px; }
.today-empty { font-size: var(--font-size-xs); color: var(--color-text-tertiary); padding: 12px 0; text-align: center; border: 1px dashed var(--color-border-default); }
.rc-line {
  font-size: var(--font-size-xs); color: var(--color-brand);
  letter-spacing: 0.5px; padding: 5px 0;
}
.act-block { display: flex; flex-direction: column; gap: 2px; }
.act-head {
  font-size: var(--font-size-xs); color: var(--color-warning);
  letter-spacing: 0.5px; padding: 6px 0 2px;
}
.today-stage {
  display: flex; align-items: baseline; gap: 10px;
  font-size: var(--font-size-xs); color: var(--color-text-secondary);
  padding: 2px 0; line-height: 1.6;
}
.today-stage .st { font-family: var(--font-family-mono); color: var(--color-text-primary); min-width: 64px; flex-shrink: 0; }
.today-stage .lbl { color: var(--color-text-tertiary); flex-shrink: 0; }
.today-stage .dp { flex: 1; min-width: 0; }
.perm-block { display: flex; flex-direction: column; gap: 2px; margin-top: 2px; }
.perm-block::before {
  content: "常驻资源本（今日开放）"; display: block;
  font-size: var(--font-size-2xs); color: var(--color-text-tertiary);
  letter-spacing: 1px; padding: 6px 0 2px;
}
.res-progress {
  width: 120px; height: 6px; flex-shrink: 0;
  accent-color: var(--color-brand);
}
.res-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* ── 双栏 ────────────────────────────── */
.double { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 14px; align-items: stretch; }
@media (max-width: 1080px) { .double { grid-template-columns: 1fr; } }
.panel-col { display: flex; flex-direction: column; gap: 14px; min-height: 0; }

/* ── 面板（作战记录） ─────────────────── */
.panel {
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  position: relative; display: flex; flex-direction: column;
}
.panel-hd { display: flex; align-items: center; gap: 12px; padding: 14px 18px; border-bottom: 1px solid var(--color-border-default); }
.panel-hd::before {
  content: ""; width: 14px; height: 14px;
  border: 1px solid var(--color-brand); transform: rotate(45deg); flex-shrink: 0;
}
.panel-hd .t { font-size: var(--font-size-xl); font-weight: var(--font-weight-bold); letter-spacing: var(--font-tracking-wide); }
.panel-hd .sub { margin-left: auto; font-size: var(--font-size-sm); color: var(--color-text-tertiary); letter-spacing: 0.5px; }
.add-btn {
  background: none; border: 1px solid var(--color-brand-strong);
  color: var(--color-brand); font-size: var(--font-size-sm);
  padding: 4px 10px; cursor: pointer; letter-spacing: 0.5px;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.add-btn:hover { background: var(--color-bg-active); }
.add-btn.ghost { border-color: var(--color-border-default); color: var(--color-text-secondary); }
.add-btn.ghost:hover { border-color: var(--color-danger); color: var(--color-danger); background: none; }

/* ── 日志流 ──────────────────────────── */
.log {
  flex: 1; font-family: var(--font-family-mono); font-size: var(--font-size-md);
  padding: 12px 18px; min-height: 260px; max-height: 420px; overflow-y: auto;
  background: var(--color-bg-subtle); line-height: 1.6;
}
.log-empty { color: var(--color-text-tertiary); text-align: center; padding: 60px 0; font-family: var(--font-family-sans); letter-spacing: 0.5px; }
.log .l { display: flex; gap: 10px; padding: 4px 0; }
.log .t { color: var(--color-text-tertiary); flex-shrink: 0; }
.c-info { color: var(--color-brand); }
.c-ok { color: var(--color-success); }
.c-warn { color: var(--color-warning); }
.c-error { color: var(--color-danger); }
.c-dim { color: var(--color-text-secondary); }

/* ── LINK START 底栏 ─────────────────── */
.start-row {
  flex-shrink: 0; display: flex; align-items: center; gap: 18px;
  padding: 16px 26px; border-top: 1px solid var(--color-border-default);
  background: var(--color-bg-subtle);
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.25);
  position: relative; z-index: var(--z-index-sticky);
}
.linkstart {
  display: flex; align-items: center; gap: 11px;
  padding: 13px 32px; border: none; cursor: pointer;
  background: linear-gradient(180deg, var(--color-surface-700), var(--color-surface-800));
  color: var(--color-brand); font-size: 15px; font-weight: 800; letter-spacing: 3px;
  clip-path: polygon(12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px);
  border: 1px solid var(--color-brand-strong);
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
  font-family: var(--font-family-sans);
}
.linkstart:hover:not(:disabled) {
  background: linear-gradient(180deg, var(--color-bg-active), var(--color-surface-800));
  box-shadow: var(--shadow-glow-lg);
}
.linkstart:disabled { opacity: 0.45; cursor: not-allowed; }
.linkstart.stop { border-color: var(--color-danger); color: #d48f87; }
.start-hint { font-size: var(--font-size-sm); color: var(--color-text-tertiary); line-height: 1.8; letter-spacing: 0.3px; }
.start-hint b { color: var(--color-warning); }
.run-err { margin-left: auto; font-size: var(--font-size-sm); color: var(--color-danger); max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
