<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDevicesStore } from '@/stores/devices'
import { useTasksStore } from '@/stores/tasks'
import { useTaskQueue } from '@/tasks/useTaskQueue'
import { useTaskSchemes, type TaskScheme } from '@/tasks/useTaskSchemes'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import TaskQueuePanel from '@/tasks/TaskQueuePanel.vue'
import TaskParamsPanel from '@/tasks/TaskParamsPanel.vue'
import type { PersistedTask } from '@/tasks/taskTypes'

const devices = useDevicesStore()
const tasks = useTasksStore()

// ── 编辑草稿（自动留底，刷新不丢；正式方案需显式命名保存） ──
const DRAFT_KEY = 'maaweb.tasks.draft'

function loadDraft(): PersistedTask[] | undefined {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return undefined
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? (parsed as PersistedTask[]) : undefined
  } catch {
    return undefined
  }
}

function saveDraft(list: PersistedTask[]) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(list))
  } catch {
    /* 忽略 */
  }
}

const {
  queue, adding, selectedTask, countChecked,
  addTask, selectTask, toggleChecked, removeTask, onDragStart, onDrop,
  payload, serialize, restore, clearQueue,
} = useTaskQueue(loadDraft())

watch(
  () => queue.value,
  () => saveDraft(serialize()),
  { deep: true },
)

// ── 方案「任务文件」管理 ─────────────────────────────
const { schemes, saveScheme, removeScheme } = useTaskSchemes()
const schemeName = ref('')
const tip = ref('')
const schemeErr = ref('')

function saveAsScheme() {
  const name = schemeName.value.trim()
  if (!name) {
    schemeErr.value = '请先为当前配置命名再保存'
    return
  }
  schemeErr.value = ''
  const s = saveScheme(name, serialize())
  tip.value = `✔ 已保存方案「${s.name}」（${s.tasks.length} 项任务）`
}

function loadScheme(s: TaskScheme) {
  restore(s.tasks)
  schemeName.value = s.name
  tip.value = `已加载方案「${s.name}」`
}

function removeSchemeConfirm(s: TaskScheme) {
  removeScheme(s.name)
  if (schemeName.value === s.name) schemeName.value = ''
  tip.value = `已删除方案「${s.name}」`
}

function newQueue() {
  clearQueue()
  schemeName.value = ''
  tip.value = '已清空，开始编排新任务队列'
}

// ── 目标设备 ─────────────────────────────────────────
const targetId = ref<number | null>(null)
const targetDevice = computed(
  () => devices.list.find((d) => d.id === targetId.value) ?? null,
)
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

// ── LINK START / STOP ───────────────────────────────
const canRun = computed(() => {
  if (tasks.busy || tasks.running) return false
  return targetDevice.value !== null && countChecked.value > 0
})

async function linkStart() {
  if (!targetDevice.value) {
    tasks.pushLog({ level: 'error', message: '⚠ 请先选择目标设备' })
    return
  }
  const items = payload()
  if (items.length === 0) {
    tasks.pushLog({ level: 'error', message: '⚠ 未勾选任何任务，请勾选后启动' })
    return
  }
  queue.value.forEach((t) => {
    if (t.once) { t.once = false; t.checked = false }
  })
  await tasks.run(targetDevice.value.id, items)
}

async function stopRun() {
  if (targetDevice.value) await tasks.stop(targetDevice.value.id)
}

// ── 日志 ─────────────────────────────────────────────
const logBox = ref<HTMLElement | null>(null)
watch(() => tasks.logs.length, async () => {
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
})

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

// ── 生命周期 ─────────────────────────────────────────
onMounted(() => {
  devices.fetchList()
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
})
</script>

<template>
  <div class="tasks">
    <div class="dashboard">
      <!-- 目标设备选择行 -->
      <div class="target-row">
        <span class="t">目标设备</span>
        <DropSelect v-model="targetModel" :options="deviceOpts" placeholder="未发现设备" />
        <span class="dev-state" :class="targetDevice?.status">
          {{ targetDevice ? `设备${targetDevice.status === 'online' ? '在线' : targetDevice.status}` : '未选择' }}
        </span>
      </div>

      <!-- 方案「任务文件」栏 -->
      <div class="scheme-bar">
        <span class="t">任务文件</span>
        <input
          v-model="schemeName"
          class="scheme-name"
          placeholder="为当前配置起名，如：每日日常"
          @keyup.enter="saveAsScheme"
        />
        <button class="add-btn" @click="saveAsScheme">保存为方案</button>
        <button class="add-btn ghost" @click="newQueue">新建队列</button>
        <span v-if="schemeErr" class="scheme-err">⚠ {{ schemeErr }}</span>
        <span v-else class="scheme-tip">{{ tip || `当前队列 ${countChecked} 项已勾选` }}</span>
      </div>

      <!-- 已有方案列表 -->
      <div v-if="schemes.length" class="scheme-list">
        <div v-for="s in schemes" :key="s.name" class="scheme-item">
          <span class="nm">{{ s.name }}</span>
          <span class="meta">{{ s.tasks.length }} 项任务 · {{ fmtTime(s.updatedAt) }}</span>
          <button class="mini" @click="loadScheme(s)">调出</button>
          <button class="mini del" @click="removeSchemeConfirm(s)">删除</button>
        </div>
      </div>

      <!-- 双栏：任务编排（共享组件）+ 执行日志 -->
      <div class="double">
        <div class="panel-col">
          <TaskQueuePanel
            :queue="queue"
            :adding="adding"
            title="任务编排"
            subtitle="与作战总览同一套任务与参数 UI"
            empty-text="暂无任务，从「添加任务」开始编排（可保存为任务文件）"
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

        <!-- 执行日志（当天日志，跨页面保留） -->
        <div class="panel">
          <div class="panel-hd">
            <span class="t">执行日志</span>
            <span class="sub">实时 · {{ tasks.todayLogs.length }} 行（当天）</span>
          </div>
          <div ref="logBox" class="log">
            <div v-if="tasks.todayLogs.length === 0" class="log-empty">今天暂无日志——执行队列后将实时显示于此</div>
            <div v-for="(l, i) in tasks.todayLogs" :key="i" class="l">
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
.tasks { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.dashboard {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 24px 26px;
  display: flex; flex-direction: column; gap: 14px;
}

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

/* ── 方案栏 ──────────────────────────── */
.scheme-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 9px 14px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-default);
}
.scheme-bar .t { font-size: var(--font-size-sm); color: var(--color-text-tertiary); letter-spacing: var(--font-tracking-widest); flex-shrink: 0; }
.scheme-name {
  background: var(--color-bg-panel); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 6px 11px; font-size: var(--font-size-md); outline: none;
  font-family: inherit; flex: 1; min-width: 180px;
}
.scheme-name:focus { border-color: var(--color-brand); }
.scheme-err { font-size: var(--font-size-sm); color: var(--color-danger); }
.scheme-tip { font-size: var(--font-size-sm); color: var(--color-text-secondary); letter-spacing: 0.3px; }

.scheme-list {
  display: flex; flex-wrap: wrap; gap: 8px;
  padding: 4px 2px;
}
.scheme-item {
  display: flex; align-items: center; gap: 10px;
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-panel);
  padding: 6px 10px;
}
.scheme-item .nm { font-size: var(--font-size-md); color: var(--color-text-primary); }
.scheme-item .meta { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.mini {
  background: none; border: 1px solid var(--color-border-default);
  color: var(--color-text-secondary); font-size: var(--font-size-xs);
  padding: 2px 8px; cursor: pointer; letter-spacing: 0.5px;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.mini:hover { border-color: var(--color-brand); color: var(--color-brand); }
.mini.del:hover { border-color: var(--color-danger); color: var(--color-danger); }

/* ── 双栏 ────────────────────────────── */
.double { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 14px; align-items: stretch; }
@media (max-width: 1080px) { .double { grid-template-columns: 1fr; } }
.panel-col { display: flex; flex-direction: column; gap: 14px; min-height: 0; }

/* ── 面板 ────────────────────────────── */
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
