<script setup lang="ts">
/**
 * 定时执行页（M6）—— 星期 × 时间 自动在目标设备上执行任务方案。
 * 方案来自任务编排页「保存为方案」（localStorage），保存定时时固化为快照；
 * 行内编辑自动保存（防抖）；支持立即试跑。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { schedulesApi, type ScheduleJob } from '@/api/schedules'
import { useDevicesStore } from '@/stores/devices'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import TimeSelect from '@/tasks/forms/TimeSelect.vue'
import { useTaskSchemes } from '@/tasks/useTaskSchemes'

const devices = useDevicesStore()
const { schemes } = useTaskSchemes()

type Row = ScheduleJob & { _draft?: boolean }

/** 未填完整的定时任务草稿自动留底（localStorage），刷新/切页不丢；落库后移除 */
const DRAFT_KEY = 'maaweb.schedule.draft'

function loadDrafts(): Row[] {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.map((d) => ({ ...(d as object), id: 0, _draft: true })) as Row[]
  } catch {
    return []
  }
}

function persistDrafts() {
  const drafts = jobs.value
    .filter((j) => j._draft)
    .map(({ _draft, ...rest }) => rest)
  try {
    if (drafts.length) localStorage.setItem(DRAFT_KEY, JSON.stringify(drafts))
    else localStorage.removeItem(DRAFT_KEY)
  } catch {
    /* quota / 隐私模式 —— 忽略 */
  }
}

const loading = ref(true)
const err = ref('')
const tip = ref('')
const jobs = ref<Row[]>([])

// ── 目标设备（新增行默认使用） ─────────────────────
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

// ── 星期（一~日，存 Mon..Sun 与周计划一致） ────────
const WEEKDAYS: { k: string; l: string }[] = [
  { k: 'Mon', l: '一' }, { k: 'Tue', l: '二' }, { k: 'Wed', l: '三' },
  { k: 'Thu', l: '四' }, { k: 'Fri', l: '五' }, { k: 'Sat', l: '六' }, { k: 'Sun', l: '日' },
]

function toggleWeekday(j: Row, k: string) {
  const s = new Set(j.weekdays)
  if (s.has(k)) s.delete(k)
  else s.add(k)
  j.weekdays = WEEKDAYS.map((w) => w.k).filter((x) => s.has(x))
}

// ── 方案选择（从任务编排保存的方案取快照） ──────────
const schemeOpts = computed<DropOption[]>(() =>
  schemes.value.map((s) => ({
    value: s.name,
    label: `${s.name}（${s.tasks.length} 项）`,
  })),
)

function pickScheme(j: Row, name: string) {
  const s = schemes.value.find((x) => x.name === name)
  if (!s) return
  j.plan_name = s.name
  // 方案快照：只取勾选中的任务，映射为 API 下发格式（同队列 linkStart 的 payload）
  j.tasks = s.tasks
    .filter((t) => t.checked)
    .map((t) => ({ name: t.label, entry: t.entry, type: t.type, params: { ...t.params } }))
}

// ── 行内编辑自动保存（防抖 600ms；draft 行选好方案后落库） ──
let saveTimer: number | null = null

async function flushSaves() {
  for (const j of jobs.value) {
    if (!j.tasks.length || !j.name.trim() || !j.weekdays.length) continue
    const payload = {
      device_id: j.device_id,
      name: j.name.trim(),
      enabled: j.enabled,
      weekdays: j.weekdays,
      time: j.time,
      plan_name: j.plan_name,
      tasks: j.tasks,
    }
    try {
      if (j._draft) {
        const saved = await schedulesApi.create(payload)
        const idx = jobs.value.indexOf(j)
        if (idx >= 0) jobs.value[idx] = { ...saved }
      } else {
        await schedulesApi.update(j.id, payload)
      }
    } catch (e: unknown) {
      err.value = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        ?? '保存定时任务失败'
    }
  }
  persistDrafts() // 草稿落库/失败后同步草稿区
}

watch(
  jobs,
  () => {
    if (loading.value) return
    persistDrafts()
    if (saveTimer !== null) window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(() => void flushSaves(), 600)
  },
  { deep: true },
)

function addJob() {
  if (targetId.value == null) {
    tip.value = '请先选择目标设备'
    return
  }
  jobs.value.push({
    id: 0, device_id: targetId.value, name: '', enabled: true,
    weekdays: WEEKDAYS.map((w) => w.k), time: '06:00',
    plan_name: '', tasks: [], last_run_at: null, created_at: '',
    _draft: true,
  })
  persistDrafts() // 点击新增即留底：未填完整的行刷新/切页不丢，只能手动删除
}

function removeJob(j: Row) {
  if (!j._draft) {
    void schedulesApi.remove(j.id).catch(() => undefined)
  }
  jobs.value = jobs.value.filter((x) => x !== j)
  persistDrafts()
}

async function runNow(j: Row) {
  if (j._draft || !j.tasks.length) return
  tip.value = ''
  try {
    const updated = await schedulesApi.runNow(j.id)
    const idx = jobs.value.indexOf(j)
    if (idx >= 0) jobs.value[idx] = { ...updated }
    tip.value = `✔ 已触发「${updated.name}」，设备在线则立即执行`
  } catch (e: unknown) {
    err.value = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
      ?? '触发失败'
  }
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    jobs.value = (await schedulesApi.list()).map((j) => ({ ...j }))
    // 恢复未填完整的草稿行（填完整后自动落库并从草稿移除）
    jobs.value.push(...loadDrafts())
    persistDrafts() // 恢复后立即留底（旧数据/异常路径兜底）
  } catch (e: unknown) {
    err.value = (e as { message?: string })?.message ?? '读取定时任务失败'
  } finally {
    loading.value = false
  }
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
  load()
})
</script>

<template>
  <div class="sched">
    <div class="dashboard">
      <!-- 顶栏 -->
      <div class="top-row">
        <div class="ttl">
          <span class="diamond"></span>
          <div>
            <h2>定时执行</h2>
            <p class="sub">星期 × 时间 自动执行任务方案（方案来自任务编排「保存为方案」）</p>
          </div>
        </div>
        <div class="top-right">
          <span class="t">目标设备</span>
          <DropSelect v-model="targetModel" :options="deviceOpts" placeholder="未发现设备" />
          <button class="add-btn" :disabled="!targetId" @click="addJob">＋ 新增定时任务</button>
        </div>
      </div>

      <div v-if="err" class="err-bar">⚠ {{ err }}</div>
      <div v-if="tip" class="ok-bar">✔ {{ tip }}</div>

      <!-- 定时任务列表 -->
      <div class="jobs">
        <div v-if="!loading && jobs.length === 0" class="jobs-empty">
          <p>还没有定时任务——点「＋ 新增定时任务」开始：</p>
          <p>1. 在「任务编排」页把常用队列保存为方案</p>
          <p>2. 在这里选择方案 + 星期 + 时间，到点自动执行</p>
        </div>

        <div v-for="j in jobs" :key="j._draft ? 'draft-' + jobs.indexOf(j) : j.id" class="job panel" :class="{ draft: j._draft }">
          <div class="job-main">
            <!-- 启停 -->
            <span class="sw" :class="{ on: j.enabled }" :title="j.enabled ? '已启用' : '已停用'" @click="j.enabled = !j.enabled"></span>

            <!-- 名称 -->
            <input class="name" type="text" v-model="j.name" placeholder="定时任务名称（如：每日长草）" />

            <!-- 星期 chips -->
            <div class="wds">
              <span
                v-for="w in WEEKDAYS" :key="w.k"
                class="wd" :class="{ on: j.weekdays.includes(w.k) }"
                @click="toggleWeekday(j, w.k)"
              >{{ w.l }}</span>
            </div>

            <!-- 时间 -->
            <TimeSelect v-model="j.time" placeholder="选择时间" />

            <!-- 方案选择 -->
            <DropSelect
              :model-value="j.plan_name"
              :options="schemeOpts"
              placeholder="选择任务方案"
              empty-text="还没有已保存的方案——先在「任务编排」页把队列保存为方案"
              @update:model-value="(v: string) => pickScheme(j, v)"
            />
          </div>

          <div class="job-foot">
            <span class="meta">上次执行 {{ fmtTime(j.last_run_at) }}</span>
            <span v-if="j.tasks.length" class="meta">快照 {{ j.tasks.length }} 项</span>
            <span v-else class="meta warn">未选方案</span>
            <div class="ops">
              <button class="btn btn-sm" :disabled="j._draft || !j.tasks.length" @click="runNow(j)">▶ 试跑</button>
              <button class="btn btn-sm btn-del" @click="removeJob(j)">{{ j._draft ? '取消' : '删除' }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sched { flex: 1; min-height: 0; display: flex; flex-direction: column; }
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

/* ── 定时任务卡片 ── */
.jobs { display: flex; flex-direction: column; gap: 12px; }
.jobs-empty {
  border: 1px dashed var(--color-border-default);
  padding: 40px 20px; text-align: center;
  color: var(--color-text-secondary); letter-spacing: 0.5px; line-height: 2;
}
.job {
  padding: 14px 16px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  display: flex; flex-direction: column; gap: 10px;
}
.job.draft { border-style: dashed; opacity: 0.9; }
.job-main { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }

.sw {
  width: 34px; height: 16px; flex-shrink: 0;
  border: 1px solid var(--color-border-strong); position: relative; cursor: pointer;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
  clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
}
.sw.on { background: rgba(216, 177, 106, 0.25); border-color: var(--color-brand-strong); }
.sw::after {
  content: ""; position: absolute; top: 2px; left: 2px;
  width: 10px; height: 10px; background: var(--color-border-strong);
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.sw.on::after { left: 20px; background: var(--color-brand); }

.name {
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 6px 11px; font-size: var(--font-size-md); outline: none;
  min-width: 180px; flex: 1; max-width: 300px;
}
.name:focus { border-color: var(--color-brand); }

.wds { display: flex; gap: 5px; flex-wrap: wrap; }
.wd {
  width: 26px; height: 26px; line-height: 26px; text-align: center;
  border: 1px solid var(--color-border-default);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm); cursor: pointer; user-select: none;
  clip-path: polygon(4px 0, 100% 0, 100% calc(100% - 4px), calc(100% - 4px) 100%, 0 100%, 0 4px);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.wd.on {
  border-color: var(--color-brand-strong); color: var(--color-brand);
  background: var(--color-bg-active);
}

.job-foot { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.job-foot .meta { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-family: var(--font-family-mono); }
.job-foot .meta.warn { color: var(--color-warning); }
.ops { margin-left: auto; display: flex; gap: 8px; }
.btn {
  padding: 6px 12px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm); cursor: pointer;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.btn:hover:not(:disabled) { border-color: var(--color-brand-strong); color: var(--color-brand); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-del { border-color: var(--color-border-default); color: var(--color-text-secondary); }
.btn-del:hover { border-color: var(--color-danger); color: var(--color-danger); }
</style>
