<script setup lang="ts">
/**
 * 作战日志页 —— 当天实时日志 + 按天分割的历史归档。
 * 左侧：当天日志（DB 持久化回填 + 实时流，跨页面保留，跨天自动归档）；
 * 右侧：历史日志按天分组（仅今天之前，跨 run 跨设备），分区管理。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDevicesStore } from '@/stores/devices'
import { useTasksStore } from '@/stores/tasks'
import { tasksApi, type LogDayGroup } from '@/api/tasks'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'

const devices = useDevicesStore()
const tasks = useTasksStore()

// ── 实时区（会话总体日志） ──
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

async function watchDevice() {
  tasks.closeStream()
  if (targetId.value == null) return
  tasks.connectStream(targetId.value)
  await tasks.loadToday(targetId.value)
  tasks.fetchStatus(targetId.value)
}

// ── 历史区（按天分割，仅今天之前） ──
const daysOpts: DropOption[] = [
  { value: '1', label: '过去 1 天' },
  { value: '3', label: '过去 3 天' },
  { value: '7', label: '过去 7 天' },
  { value: '14', label: '过去 14 天' },
  { value: '30', label: '过去 30 天' },
]
const daysRange = ref('7')
const loading = ref(false)
const history = ref<LogDayGroup[]>([])
const expanded = ref<Record<string, boolean>>({})
const historyErr = ref('')

async function loadHistory() {
  loading.value = true
  historyErr.value = ''
  try {
    const r = await tasksApi.logsByDay(Number(daysRange.value))
    history.value = r.days
    // 默认展开最新一天
    if (r.days.length && expanded.value[r.days[0].date] === undefined) {
      expanded.value[r.days[0].date] = true
    }
  } catch (e: unknown) {
    historyErr.value = (e as { message?: string })?.message ?? '历史日志加载失败'
  } finally {
    loading.value = false
  }
}

function toggleDay(date: string) {
  expanded.value[date] = !expanded.value[date]
}

// ── 分级过滤 + 关键字搜索（本地过滤，实时/历史共用） ──
const LEVELS = ['info', 'ok', 'warn', 'error']
const LEVEL_LABELS: Record<string, string> = { info: 'INFO', ok: 'OK', warn: 'WARN', error: 'ERROR' }
const levelFilter = ref<Set<string>>(new Set(LEVELS))
const keyword = ref('')

function toggleLevel(lv: string) {
  const s = new Set(levelFilter.value)
  if (s.has(lv)) s.delete(lv)
  else s.add(lv)
  levelFilter.value = s
}

function matches(e: { level?: string; message?: string }): boolean {
  if (!levelFilter.value.has(e.level ?? 'info')) return false
  const kw = keyword.value.trim().toLowerCase()
  if (kw && !(e.message ?? '').toLowerCase().includes(kw)) return false
  return true
}

const filteredLive = computed(() => tasks.todayLogs.filter(matches))
function filteredCount(g: LogDayGroup): number {
  return g.entries.filter(matches).length
}
function filteredEntries(g: LogDayGroup): LogDayGroup['entries'] {
  return g.entries.filter(matches)
}

// ── 日志渲染 ──
const logBox = ref<HTMLElement | null>(null)
watch(
  () => tasks.logs.length,
  async () => {
    await nextTick()
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  },
)

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
  watch(targetId, watchDevice, { immediate: true })
  loadHistory()
})

onBeforeUnmount(() => {
  tasks.closeStream()
})
</script>

<template>
  <div class="logs">
    <div class="dashboard">
      <div class="top-row">
        <div class="ttl">
          <span class="diamond"></span>
          <div>
            <h2>作战日志</h2>
            <p class="sub">总体日志 · 会话实时流 + 按天分割的历史</p>
          </div>
        </div>
        <div class="top-right">
          <span class="t">实时设备</span>
          <DropSelect v-model="targetModel" :options="deviceOpts" placeholder="未发现设备" />
        </div>
      </div>

      <div class="double">
        <!-- 过滤条（实时/历史共用） -->
        <div class="filter-bar">
          <input v-model="keyword" class="kw" type="text" placeholder="搜索日志关键字…（如 公招 / CE-6 / 错误）" />
          <div class="lv-chips">
            <span
              v-for="lv in LEVELS" :key="lv"
              class="lv-chip" :class="{ on: levelFilter.has(lv), off: !levelFilter.has(lv) }"
              @click="toggleLevel(lv)"
            >{{ LEVEL_LABELS[lv] }}</span>
          </div>
        </div>

        <!-- 左：实时日志（当天，跨页面保留；当天过了归档到右侧历史） -->
        <div class="panel">
          <div class="panel-hd">
            <span class="t">实时日志</span>
            <span class="sub">{{ filteredLive.length }} / {{ tasks.todayLogs.length }} 行（当天）</span>
          </div>
          <div ref="logBox" class="log">
            <div v-if="filteredLive.length === 0" class="log-empty">
              {{ tasks.todayLogs.length === 0 ? '今天暂无日志——执行任务后将实时显示于此' : '无匹配日志（调整级别筛选或关键字）' }}
            </div>
            <div v-for="(l, i) in filteredLive" :key="i" class="l">
              <span class="t">{{ fmtTime(l.ts ?? '') }}</span>
              <span :class="levelCls(l.level)">{{ tagOf(l.level) }}</span>
              <span class="c-dim">{{ l.message }}</span>
            </div>
          </div>
        </div>

        <!-- 右：历史日志 · 按天分割 -->
        <div class="panel">
          <div class="panel-hd">
            <span class="t">历史日志</span>
            <span class="sub">按天分割 · 跨运行</span>
            <div class="hd-right">
              <DropSelect v-model="daysRange" :options="daysOpts" />
              <button class="add-btn" :disabled="loading" @click="loadHistory">
                {{ loading ? '加载中…' : '⟳ 加载' }}
              </button>
            </div>
          </div>
          <div class="hist">
            <div v-if="historyErr" class="hist-err">⚠ {{ historyErr }}</div>
            <div v-else-if="history.length === 0" class="hist-empty">
              暂无历史日志（过去 {{ daysRange }} 天内）——当天日志在左侧实时区，次日归档到这里
            </div>
            <div v-for="g in history" :key="g.date" class="day">
              <button type="button" class="day-hd" @click="toggleDay(g.date)">
                <span class="mark" :class="{ open: expanded[g.date] }"></span>
                <span class="date">{{ g.date }}</span>
                <span class="count">{{ filteredCount(g) }} / {{ g.count }} 行</span>
              </button>
              <div v-if="expanded[g.date]" class="day-body">
                <div v-for="(e, i) in filteredEntries(g)" :key="i" class="l">
                  <span class="t">{{ fmtTime(e.ts) }}</span>
                  <span :class="levelCls(e.level)">{{ tagOf(e.level) }}</span>
                  <span class="c-dim">{{ e.message }}</span>
                </div>
                <div v-if="filteredCount(g) === 0" class="hist-empty-sm">无匹配日志</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.logs { flex: 1; min-height: 0; display: flex; flex-direction: column; }
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

.double { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start; }
@media (max-width: 1080px) { .double { grid-template-columns: 1fr; } }

/* 过滤条（级别筛选 + 搜索，跨整行） */
.filter-bar {
  grid-column: 1 / -1;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 14px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
}
.filter-bar .kw {
  flex: 1; min-width: 200px;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 6px 11px; font-size: var(--font-size-md); outline: none;
  font-family: var(--font-family-mono);
}
.filter-bar .kw:focus { border-color: var(--color-brand); }
.lv-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.lv-chip {
  border: 1px solid var(--color-border-default);
  color: var(--color-text-tertiary);
  padding: 3px 10px; cursor: pointer;
  font-size: var(--font-size-xs); letter-spacing: 0.5px; user-select: none;
  clip-path: polygon(5px 0, 100% 0, 100% calc(100% - 5px), calc(100% - 5px) 100%, 0 100%, 0 5px);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.lv-chip.on { border-color: var(--color-brand-strong); color: var(--color-brand); background: var(--color-bg-active); }
.lv-chip.off { opacity: 0.4; }
.hist-empty-sm { color: var(--color-text-tertiary); padding: 8px 4px; font-size: var(--font-size-xs); letter-spacing: 0.5px; }

.panel {
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  display: flex; flex-direction: column;
}
.panel-hd {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px; border-bottom: 1px solid var(--color-border-default);
}
.panel-hd::before {
  content: ""; width: 14px; height: 14px;
  border: 1px solid var(--color-brand); transform: rotate(45deg); flex-shrink: 0;
}
.panel-hd .t { font-size: var(--font-size-xl); font-weight: var(--font-weight-bold); letter-spacing: var(--font-tracking-wide); }
.panel-hd .sub { margin-left: auto; font-size: var(--font-size-sm); color: var(--color-text-tertiary); letter-spacing: 0.5px; }
.hd-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.hd-right .ds { min-width: 120px; }
.add-btn {
  background: none; border: 1px solid var(--color-brand-strong);
  color: var(--color-brand); font-size: var(--font-size-sm);
  padding: 4px 10px; cursor: pointer; letter-spacing: 0.5px;
}
.add-btn.ghost { border-color: var(--color-border-default); color: var(--color-text-secondary); }
.add-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.log {
  flex: 1; font-family: var(--font-family-mono); font-size: var(--font-size-md);
  padding: 12px 18px; min-height: 320px; max-height: 60vh; overflow-y: auto;
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

/* 历史区 */
.hist { flex: 1; overflow-y: auto; padding: 8px 10px; max-height: 60vh; font-family: var(--font-family-mono); font-size: var(--font-size-md); }
.hist-empty, .hist-err { color: var(--color-text-tertiary); text-align: center; padding: 50px 10px; font-family: var(--font-family-sans); letter-spacing: 0.5px; }
.hist-err { color: var(--color-danger); }
.day { border: 1px solid var(--color-border-default); margin-bottom: 8px; background: var(--color-bg-subtle); }
.day-hd {
  width: 100%; display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; cursor: pointer;
  background: none; border: none; color: var(--color-text-primary);
  font-family: inherit; font-size: var(--font-size-md); letter-spacing: 0.5px;
}
.day-hd:hover { color: var(--color-brand); }
.day-hd .mark {
  width: 8px; height: 8px; flex-shrink: 0;
  border: 1px solid var(--color-border-strong);
  transform: rotate(45deg);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.day-hd .mark.open { border-color: var(--color-brand); background: rgba(216, 177, 106, 0.3); }
.day-hd .date { font-family: var(--font-family-mono); }
.day-hd .count { margin-left: auto; font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.day-body { border-top: 1px dashed var(--color-border-default); padding: 6px 12px; max-height: 320px; overflow-y: auto; }
.day-body .l { display: flex; gap: 10px; padding: 3px 0; line-height: 1.6; }
.day-body .l .t { color: var(--color-text-tertiary); flex-shrink: 0; }
</style>
