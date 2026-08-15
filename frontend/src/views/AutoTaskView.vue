<script setup lang="ts">
/**
 * 自动任务页（M6+）—— 定时执行中心（原「定时执行」）。
 * 一个自动任务 = 多个时间槽（各自名称/星期/时间/启停/冲突策略）；
 * 每槽独立账号列表（来自设置·账号组，勾选启用）；每账号绑定方案快照 + 可选参数微调；
 * RUN TEST 手动测试（日志带「自动任务(手动运行)」标签）；页内独立自动任务日志。
 * 整体保存（PUT /auto-tasks/{id}，slots 全量替换）；未落库的组/槽/账号留底 localStorage。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  autoTasksApi,
  type AutoSlot,
  type AutoSlotAccount,
  type AutoTask,
  type AutoTaskIn,
} from '@/api/auto-tasks'
import { parseAccountGroups, settingsApi } from '@/api/settings'
import { useDevicesStore } from '@/stores/devices'
import { useTasksStore } from '@/stores/tasks'
import { useTaskSchemes } from '@/tasks/useTaskSchemes'
import { useTaskQueue } from '@/tasks/useTaskQueue'
import type { PersistedTask } from '@/tasks/taskTypes'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'
import TimeSelect from '@/tasks/forms/TimeSelect.vue'
import TaskQueuePanel from '@/tasks/TaskQueuePanel.vue'
import TaskParamsPanel from '@/tasks/TaskParamsPanel.vue'

const devices = useDevicesStore()
const tasksStore = useTasksStore()
const router = useRouter()
const { schemes, load: loadSchemes } = useTaskSchemes()

// ── 数据与选择状态 ─────────────────────────────────
const loading = ref(true)
const err = ref('')
const tip = ref('')
const tasksList = ref<AutoTask[]>([])
const currentTaskId = ref<number | null>(null)
const selectedSlotId = ref<number | null>(null)
const selectedAccountId = ref<number | null>(null)

const currentTask = computed(
  () => tasksList.value.find((t) => t.id === currentTaskId.value) ?? null,
)
const selectedSlot = computed(
  () => currentTask.value?.slots.find((s) => s.id === selectedSlotId.value) ?? null,
)
const selectedAccount = computed(
  () => selectedSlot.value?.accounts.find((a) => a.id === selectedAccountId.value) ?? null,
)

const taskOpts = computed<DropOption[]>(() =>
  tasksList.value.map((t) => ({
    value: String(t.id),
    label: `${t.name || '未命名'}（${t.slots.length} 槽）`,
  })),
)
const taskModel = computed({
  get: () => (currentTaskId.value == null ? '' : String(currentTaskId.value)),
  set: (v: string) => {
    currentTaskId.value = v === '' ? null : Number(v)
  },
})

watch(currentTaskId, () => {
  const slots = currentTask.value?.slots ?? []
  selectedSlotId.value = slots[0]?.id ?? null
  selectedAccountId.value = null
  accPickerOpen.value = false
})

// ── 设备（新建组默认 / 日志流） ─────────────────────
const targetId = ref<number | null>(null)
const deviceOpts = computed<DropOption[]>(() =>
  devices.list.map((d) => ({
    value: String(d.id),
    label: `${d.name} · ${d.adb_host}:${d.adb_port}（${d.status}）`,
  })),
)
const deviceModel = computed({
  get: () => String(currentTask.value?.device_id ?? targetId.value ?? ''),
  set: (v: string) => {
    const id = v === '' ? null : Number(v)
    if (currentTask.value) {
      if (id != null) currentTask.value.device_id = id
    } else {
      targetId.value = id
    }
  },
})

// 日志流：跟随当前组的设备（自动任务日志独立面板）
const streamDeviceId = computed(() => currentTask.value?.device_id ?? targetId.value)
watch(streamDeviceId, async (id) => {
  tasksStore.closeStream()
  if (id == null) return
  tasksStore.connectStream(id)
  await tasksStore.loadToday(id)
})

// ── 星期 chips ─────────────────────────────────────
const WEEKDAYS: { k: string; l: string }[] = [
  { k: 'Mon', l: '一' }, { k: 'Tue', l: '二' }, { k: 'Wed', l: '三' },
  { k: 'Thu', l: '四' }, { k: 'Fri', l: '五' }, { k: 'Sat', l: '六' }, { k: 'Sun', l: '日' },
]
const ALL_WEEKDAYS = WEEKDAYS.map((w) => w.k)

function toggleWeekday(slot: AutoSlot, k: string) {
  const s = new Set(slot.weekdays)
  if (s.has(k)) s.delete(k)
  else s.add(k)
  slot.weekdays = WEEKDAYS.map((w) => w.k).filter((x) => s.has(x))
}

// ── 冲突策略 ───────────────────────────────────────
const CONFLICT_OPTS: DropOption[] = [
  { value: 'queue', label: '排队等待上一任务完成' },
  { value: 'skip', label: '跳过本次' },
  { value: 'force', label: '强制结束上一任务' },
]

// ── 临时 id（槽/账号本地标识；组已落库，槽/账号随整体 PUT 由后端重建） ──
let draftSeq = 0
function tempId(): number {
  return --draftSeq
}

// ── 旧草稿迁移（2026-08-16 起无 localStorage 草稿：组创建即落库，
//    后端为空时把旧浏览器草稿组一次性迁移到后端） ────
const LEGACY_DRAFT_KEY = 'maaweb.autotask.draft'

async function migrateLegacyDrafts() {
  if (tasksList.value.length) return
  let legacy: unknown
  try {
    const raw = localStorage.getItem(LEGACY_DRAFT_KEY)
    if (!raw) return
    legacy = JSON.parse(raw)
  } catch {
    return
  }
  if (!Array.isArray(legacy) || !legacy.length) return
  for (const g of legacy) {
    if (typeof g !== 'object' || g === null) continue
    try {
      const created = await autoTasksApi.create(toPayload({ ...(g as object), id: 0 } as AutoTask))
      tasksList.value.push(created)
    } catch {
      /* 单条迁移失败不阻塞其余 */
    }
  }
  try {
    localStorage.removeItem(LEGACY_DRAFT_KEY)
  } catch {
    /* 忽略 */
  }
}

// ── 保存（防抖 600ms；整体 PUT；组一旦创建即存在于后端） ──
function toPayload(t: AutoTask): AutoTaskIn {
  return {
    name: t.name.trim(),
    device_id: t.device_id,
    enabled: t.enabled,
    slots: t.slots.map((s) => ({
      name: s.name.trim(),
      enabled: s.enabled,
      weekdays: s.weekdays,
      time: s.time,
      conflict: s.conflict,
      accounts: s.accounts.map((a) => ({
        account_name: a.account_name,
        client_type: a.client_type,
        enabled: a.enabled,
        plan_name: a.plan_name,
        tasks: a.tasks,
      })),
    })),
  }
}

/** 保存响应替换旧对象；选择状态按索引映射（后端按输入顺序重建） */
function replaceTask(oldT: AutoTask, newT: AutoTask) {
  const idx = tasksList.value.indexOf(oldT)
  if (idx < 0) return
  const slotIdx = oldT.slots.findIndex((s) => s.id === selectedSlotId.value)
  const accIdx =
    slotIdx >= 0
      ? oldT.slots[slotIdx]?.accounts.findIndex((a) => a.id === selectedAccountId.value) ?? -1
      : -1
  tasksList.value[idx] = newT
  if (currentTaskId.value === oldT.id) {
    currentTaskId.value = newT.id
    selectedSlotId.value = slotIdx >= 0 ? (newT.slots[slotIdx]?.id ?? null) : null
    selectedAccountId.value =
      slotIdx >= 0 && accIdx >= 0 ? (newT.slots[slotIdx]?.accounts[accIdx]?.id ?? null) : null
  }
}

let saveTimer: number | null = null

async function flushSaves() {
  for (const t of [...tasksList.value]) {
    try {
      const saved = await autoTasksApi.update(t.id, toPayload(t))
      replaceTask(t, saved)
    } catch (e: unknown) {
      err.value = detailOf(e) || '保存自动任务失败'
    }
  }
}

watch(
  tasksList,
  () => {
    if (loading.value) return
    if (saveTimer !== null) window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(() => void flushSaves(), 600)
  },
  { deep: true },
)

// ── 组 / 槽 / 账号操作 ─────────────────────────────
async function addTaskGroup() {
  if (targetId.value == null) {
    tip.value = '请先选择目标设备'
    return
  }
  try {
    // 新建组立即落库（允许未命名，显示「未命名」）——跨浏览器一致
    const created = await autoTasksApi.create({
      name: '', device_id: targetId.value, enabled: true, slots: [],
    })
    tasksList.value.push(created)
    currentTaskId.value = created.id
  } catch (e: unknown) {
    err.value = detailOf(e) || '新建自动任务失败'
  }
}

function removeTaskGroup(t: AutoTask) {
  if (t.id > 0) void autoTasksApi.remove(t.id).catch(() => undefined)
  const idx = tasksList.value.indexOf(t)
  tasksList.value = tasksList.value.filter((x) => x !== t)
  if (currentTaskId.value === t.id) {
    const next = tasksList.value[idx] ?? tasksList.value[idx - 1] ?? null
    currentTaskId.value = next ? next.id : null
  }
}

function addSlot() {
  if (!currentTask.value) return
  const s: AutoSlot = {
    id: tempId(), name: '', enabled: true, weekdays: [...ALL_WEEKDAYS],
    time: '06:00', conflict: 'queue', accounts: [], last_run_at: null,
  }
  currentTask.value.slots.push(s)
  selectedSlotId.value = s.id
}

function removeSlot(slot: AutoSlot) {
  if (!currentTask.value) return
  currentTask.value.slots = currentTask.value.slots.filter((s) => s !== slot)
  if (selectedSlotId.value === slot.id) {
    selectedSlotId.value = currentTask.value.slots[0]?.id ?? null
    selectedAccountId.value = null
  }
}

function removeAccount(acc: AutoSlotAccount) {
  if (!selectedSlot.value) return
  selectedSlot.value.accounts = selectedSlot.value.accounts.filter((a) => a !== acc)
  if (selectedAccountId.value === acc.id) selectedAccountId.value = null
}

// ── 账号组选择（从设置·账号组添加账号） ────────────
const accPickerOpen = ref(false)
const accGroup = ref<{ name: string; client_type: string }[]>([])
const accPicked = ref<Set<string>>(new Set())

async function openAccPicker() {
  if (!selectedSlot.value) return
  try {
    const groups = await settingsApi.getAll()
    accGroup.value = parseAccountGroups(groups)
    accPicked.value = new Set(selectedSlot.value.accounts.map((a) => a.account_name))
    accPickerOpen.value = true
  } catch (e: unknown) {
    err.value = (e as { message?: string })?.message ?? '读取账号组失败'
  }
}

function toggleAccPick(name: string) {
  const s = new Set(accPicked.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  accPicked.value = s
}

function confirmAccPick() {
  if (!selectedSlot.value) return
  const existing = new Set(selectedSlot.value.accounts.map((a) => a.account_name))
  for (const g of accGroup.value) {
    if (accPicked.value.has(g.name) && !existing.has(g.name)) {
      selectedSlot.value.accounts.push({
        id: tempId(), account_name: g.name, client_type: g.client_type,
        enabled: true, plan_name: '', tasks: [], position: selectedSlot.value.accounts.length,
        last_run_at: null, last_ok: null,
      })
    }
  }
  accPickerOpen.value = false
}

// ── 方案选择（快照到账号） ─────────────────────────
const schemeOpts = computed<DropOption[]>(() =>
  schemes.value.map((s) => ({
    value: s.name,
    label: `${s.name}（${s.tasks.length} 项）`,
  })),
)

function pickScheme(acc: AutoSlotAccount, name: string) {
  const s = schemes.value.find((x) => x.name === name)
  if (!s) return
  acc.plan_name = s.name
  acc.tasks = (s.tasks as unknown as PersistedTask[])
    .filter((t) => t.checked)
    .map((t) => ({ name: t.label, entry: t.entry, type: t.type, params: { ...t.params } }))
}

// ── 参数微调（编辑该账号的执行快照副本） ────────────
const editing = ref(false)
const {
  queue: editQueue,
  adding: editAdding,
  selectedTask: editSelected,
  addTask: editAddTask,
  selectTask: editSelectTask,
  toggleChecked: editToggleChecked,
  removeTask: editRemoveTask,
  onDragStart: editDragStart,
  onDrop: editDrop,
  restore: editRestore,
  payload: editPayload,
} = useTaskQueue()

function openEdit() {
  const acc = selectedAccount.value
  if (!acc) return
  const list: PersistedTask[] = acc.tasks.map((t) => ({
    type: t.type, entry: t.entry, label: t.name,
    params: { ...t.params }, checked: true, once: false,
  }))
  editRestore(list)
  editing.value = true
}

function saveEdit() {
  const acc = selectedAccount.value
  if (!acc) return
  acc.tasks = editPayload()
  editing.value = false
  tip.value = `✔ 参数微调已保存（「${acc.account_name}」执行时按调整后快照，共 ${acc.tasks.length} 项）`
}

// ── RUN TEST（手动测试，真实执行走定时触发） ───────
const testing = ref(false)
const canRunTest = computed(() => {
  const task = currentTask.value
  if (!task || !selectedSlot.value) return false
  if (task.id < 0) return false // 未落库组先保存
  if (tasksStore.running || tasksStore.busy) return false
  return selectedSlot.value.accounts.some((a) => a.enabled)
})

async function runTest() {
  const task = currentTask.value
  const slot = selectedSlot.value
  if (!task || !slot) return
  testing.value = true
  err.value = ''
  try {
    const res = await autoTasksApi.runTest(task.id, slot.id)
    tip.value = res.message
  } catch (e: unknown) {
    err.value = detailOf(e) || '测试运行失败'
  } finally {
    testing.value = false
  }
}

// ── 展示辅助 ───────────────────────────────────────

/** 后端错误 → 人话：pydantic 校验失败（detail 为数组）时提取 msg 拼接 */
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

const CLIENT_LABELS: Record<string, string> = {
  Official: '官服', Bilibili: 'B服', txwy: 'txwy',
  YoStarEN: '悠星EN', YoStarKR: '悠星KR', YoStarJP: '悠星JP', YoStarTW: '悠星TW',
}

function clientLabel(ct: string): string {
  return CLIENT_LABELS[ct] ?? ct
}

function lastText(acc: AutoSlotAccount): string {
  if (acc.last_run_at == null) return '未运行'
  const d = new Date(acc.last_run_at)
  if (Number.isNaN(d.getTime())) return '未运行'
  const p = (n: number) => String(n).padStart(2, '0')
  const hm = `${p(d.getHours())}:${p(d.getMinutes())}`
  return acc.last_ok ? `上次 ✓ ${hm}` : `上次 ✗ ${hm}`
}

function slotName(): string {
  return selectedSlot.value?.name?.trim() || '未命名时间点'
}

function accName(): string {
  const a = selectedAccount.value
  return a ? `${a.account_name}（${clientLabel(a.client_type)}）` : '未选账号'
}

const logBox = ref<HTMLElement | null>(null)
watch(
  () => tasksStore.autoTodayLogs.length,
  async () => {
    await nextTick()
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  },
)

function levelCls(level?: string): string {
  return `c-${level ?? 'info'}`
}

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--:--:--'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// ── 生命周期 ───────────────────────────────────────
async function load() {
  loading.value = true
  err.value = ''
  try {
    await loadSchemes()  // 方案存后端（跨浏览器一致），加载后再选方案
    tasksList.value = (await autoTasksApi.list()).map((t) => ({ ...t }))
    // 旧浏览器 localStorage 草稿组 → 后端（一次性迁移；此后无草稿机制）
    await migrateLegacyDrafts()
    currentTaskId.value = tasksList.value[0]?.id ?? null
  } catch (e: unknown) {
    err.value = (e as { message?: string })?.message ?? '读取自动任务失败'
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
  void load()
})

function goSettings() {
  accPickerOpen.value = false
  void router.push('/settings')
}
</script>

<template>
  <div class="auto">
    <div class="dashboard">
      <!-- 顶栏 -->
      <div class="top-row">
        <div class="ttl">
          <span class="diamond"></span>
          <div>
            <h2>自动任务</h2>
            <p class="sub">定时执行 · 时间槽 × 账号 × 方案（账号切换由引擎完成，失败自动跳过）</p>
          </div>
        </div>
        <div class="top-right">
          <span class="t">任务组</span>
          <DropSelect v-model="taskModel" :options="taskOpts" placeholder="未创建任务组" />
          <input
            v-if="currentTask"
            v-model="currentTask.name"
            class="group-name"
            :class="{ empty: currentTask && !currentTask.name.trim() }"
            type="text"
            placeholder="组名称（如：每日长草）"
          />
          <span v-if="currentTask && !currentTask.name.trim()" class="group-name-hint">⚠ 请填写组名</span>
          <span class="t">目标设备</span>
          <DropSelect v-model="deviceModel" :options="deviceOpts" placeholder="未发现设备" />
          <button class="add-btn" :disabled="!targetId" @click="addTaskGroup">＋ 新建组</button>
          <button
            v-if="currentTask"
            class="add-btn ghost"
            @click="removeTaskGroup(currentTask)"
          >删除组</button>
        </div>
      </div>

      <div v-if="err" class="err-bar">⚠ {{ err }}</div>
      <div v-if="tip" class="ok-bar">✔ {{ tip }}</div>

      <!-- 空态 -->
      <div v-if="!loading && tasksList.length === 0" class="jobs-empty">
        <p>还没有自动任务——点「＋ 新建组」开始：</p>
        <p>1. 在「任务编排」页把常用队列保存为方案</p>
        <p>2. 在「设置 → 账号组」添加游戏账号（用于自动切换）</p>
        <p>3. 在这里新建组 → 添加时间 → 为时间点添加账号并选择方案</p>
      </div>

      <div v-else-if="currentTask" class="body">
        <!-- 左列：执行时间 + 账号 -->
        <div class="left">
          <div class="panel">
            <div class="ph">
              <span class="diamond"></span><b>执行时间</b>
              <small>各自星期 · 冲突策略可配</small>
              <button class="add" @click="addSlot">＋ 添加时间</button>
            </div>
            <div class="slots">
              <div
                v-for="s in currentTask.slots"
                :key="s.id"
                class="slot"
                :class="{ sel: s.id === selectedSlotId, off: !s.enabled }"
                @click="selectedSlotId = s.id"
              >
                <div class="slot-hd">
                  <span class="sw" :class="{ on: s.enabled }" :title="s.enabled ? '已启用' : '已停用'" @click.stop="s.enabled = !s.enabled"></span>
                  <input class="nm" v-model="s.name" placeholder="时间点名称（如：早间长草）" @click.stop />
                  <span class="x" @click.stop="removeSlot(s)">✕</span>
                </div>
                <div class="slot-row">
                  <div class="wds">
                    <span
                      v-for="w in WEEKDAYS" :key="w.k"
                      class="wd" :class="{ on: s.weekdays.includes(w.k) }"
                      @click.stop="toggleWeekday(s, w.k)"
                    >{{ w.l }}</span>
                  </div>
                  <TimeSelect v-model="s.time" placeholder="选择时间" />
                </div>
                <div class="conflict">
                  <label>到点冲突</label>
                  <DropSelect v-model="s.conflict" :options="CONFLICT_OPTS" placeholder="冲突策略" />
                </div>
              </div>
            </div>
          </div>

          <div class="panel">
            <div class="ph">
              <span class="diamond"></span><b>账号</b>
              <small>{{ selectedSlot ? `「${slotName()}」的账号 · 每时间点独立` : '选择时间点后配置' }}</small>
            </div>
            <template v-if="selectedSlot">
              <div class="acc-list">
                <div
                  v-for="(a, i) in selectedSlot.accounts"
                  :key="a.id"
                  class="acc"
                  :class="{ sel: a.id === selectedAccountId, off: !a.enabled }"
                  @click="selectedAccountId = a.id"
                >
                  <span class="chk" :class="{ on: a.enabled }" :title="a.enabled ? '已启用' : '已停用'" @click.stop="a.enabled = !a.enabled"></span>
                  <span class="idx">{{ i + 1 }}</span>
                  <b>{{ a.account_name }}（{{ clientLabel(a.client_type) }}）</b>
                  <small>{{ a.tasks.length ? `${a.plan_name || '自定义'} · ${a.tasks.length} 项` : '未选方案' }}</small>
                  <span class="last" :class="{ bad: a.last_run_at != null && a.last_ok === false }">{{ lastText(a) }}</span>
                  <span class="x" @click.stop="removeAccount(a)">✕</span>
                </div>
                <div v-if="selectedSlot.accounts.length === 0" class="empty">还没有账号——点下方「添加账号」从设置·账号组选择</div>
                <button class="add" @click="openAccPicker">＋ 添加账号（从设置·账号组选择）</button>

                <!-- 账号组选择展开 -->
                <div v-if="accPickerOpen" class="acc-picker">
                  <div class="picker-hd">
                    <b>设置 · 账号组</b>
                    <button class="mini" @click="goSettings">去设置维护</button>
                  </div>
                  <div v-if="accGroup.length === 0" class="empty">账号组为空——先在「设置 → 账号组」添加账号</div>
                  <div
                    v-for="g in accGroup" :key="g.name"
                    class="pick-item"
                    @click="toggleAccPick(g.name)"
                  >
                    <span class="chk" :class="{ on: accPicked.has(g.name) }"></span>
                    <b>{{ g.name }}</b>
                    <small>{{ clientLabel(g.client_type) }}</small>
                  </div>
                  <div class="picker-foot">
                    <button class="btn btn-sm" @click="confirmAccPick">确认添加</button>
                    <button class="btn btn-sm" @click="accPickerOpen = false">取消</button>
                  </div>
                </div>
              </div>
              <p class="note">复选框：勾选启用、取消勾选停用（保留配置不删除）。账号来自「设置 → 账号组」维护的账号。</p>
            </template>
            <div v-else class="empty">选择左侧时间点后在此配置账号</div>
          </div>
        </div>

        <!-- 右列：方案配置 + 自动任务日志 -->
        <div class="right">
          <div class="panel">
            <div class="ph2">
              <span class="diamond"></span>
              <b>{{ slotName() }}<span class="sep">▸</span>{{ accName() }} · 方案配置</b>
              <small>该时间点该账号的任务与参数</small>
            </div>
            <template v-if="selectedAccount">
              <div class="frow">
                <label>执行方案<small>从任务编排保存的方案中选择</small></label>
                <DropSelect
                  :model-value="selectedAccount.plan_name"
                  :options="schemeOpts"
                  placeholder="选择任务方案"
                  empty-text="还没有已保存的方案——先在「任务编排」页把队列保存为方案"
                  @update:model-value="(v: string) => pickScheme(selectedAccount!, v)"
                />
              </div>
              <div class="frow">
                <label>任务预览<small>方案快照 · 执行时按此</small></label>
                <div class="tasks-preview">
                  <template v-if="selectedAccount.tasks.length">
                    <div v-for="(t, i) in selectedAccount.tasks" :key="i">
                      <span class="t">{{ i + 1 }}.</span> {{ t.name }}<span class="e">（{{ t.entry }}）</span>
                    </div>
                  </template>
                  <div v-else class="dim">未选方案——选择执行方案，或展开参数微调自建任务</div>
                </div>
              </div>
              <div class="frow">
                <label>参数微调<small>可选：编辑该账号的执行快照（不影响原方案）</small></label>
                <button class="btn" @click="editing ? saveEdit() : openEdit()">
                  {{ editing ? '✔ 保存微调' : '展开任务参数…' }}
                </button>
              </div>
              <div v-if="editing" class="edit-box">
                <TaskQueuePanel
                  :queue="editQueue"
                  :adding="editAdding"
                  title="任务与参数（该账号副本）"
                  subtitle="勾选 = 执行；修改仅作用于本账号"
                  empty-text="暂无任务——从「添加任务」开始自建"
                  @toggle-add="editAdding = !editAdding"
                  @add="editAddTask"
                  @select="editSelectTask"
                  @toggle-checked="editToggleChecked"
                  @remove="editRemoveTask"
                  @dragstart="editDragStart"
                  @drop="editDrop"
                />
                <TaskParamsPanel :selected-task="editSelected" />
              </div>
            </template>
            <div v-else class="empty">选择左侧账号查看并配置其方案</div>
          </div>

          <div class="panel">
            <div class="ph2">
              <span class="diamond"></span><b>自动任务日志</b>
              <small>独立存储 · 与普通任务日志分开</small>
            </div>
            <div ref="logBox" class="log">
              <div v-if="tasksStore.autoTodayLogs.length === 0" class="log-empty">今天暂无自动任务日志——触发后实时显示于此</div>
              <div v-for="(l, i) in tasksStore.autoTodayLogs" :key="l.id ?? i" class="l">
                <span class="t">{{ fmtTime(l.ts ?? '') }}</span>
                <span class="src" :class="l.source === 'manual_auto' ? 'manual' : 'auto'">
                  {{ l.source === 'manual_auto' ? '自动任务(手动运行)' : '自动任务' }}
                </span>
                <span :class="levelCls(l.level)">{{ l.message }}</span>
              </div>
            </div>
            <p class="note">本页日志只显示自动任务相关（含 RUN TEST 手动运行，带「自动任务(手动运行)」标签）；作战日志页可按「普通任务 / 自动任务」筛选。</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部执行栏：RUN TEST 为页面级主操作（对齐首页 LINK START 位置，避免误解为测试单个账号） -->
    <div class="exec-row">
      <span class="exec-hint">
        测试运行：仅执行当前时间点（{{ slotName() }}）的启用账号；真实执行走定时触发
      </span>
      <button class="run-test" :disabled="!canRunTest || testing" @click="runTest">▶ RUN TEST</button>
    </div>
  </div>
</template>

<style scoped>
.auto { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.dashboard {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 24px 26px;
  display: flex; flex-direction: column; gap: 14px;
}

/* ── 顶栏 ───────────────────────────── */
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
.top-right { margin-left: auto; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.top-right .t { font-size: var(--font-size-sm); color: var(--color-text-tertiary); letter-spacing: var(--font-tracking-widest); }
.group-name {
  background: var(--color-bg-subtle) !important; color: var(--color-text-primary) !important;
  border: 1px solid var(--color-border-default) !important;
  padding: 6px 11px !important; font-size: var(--font-size-md) !important; outline: none !important;
  min-width: 140px !important; max-width: 200px !important;
  /* 显式固定尺寸：空名提醒（.empty）等任何状态下输入框大小不变 */
  height: 30px !important;
  line-height: 16px !important;
  font-family: var(--font-family-sans) !important;
  box-sizing: border-box !important;
  vertical-align: middle !important;
}
.group-name:focus { border-color: var(--color-brand); }
/* 组名未填写：暗红边框 + 微红底 + 提示文字（强提醒） */
.group-name.empty {
  border-color: var(--color-danger);
  background: rgba(176, 91, 83, 0.1);
}
.group-name-hint {
  font-size: var(--font-size-2xs); color: var(--color-danger);
  letter-spacing: 0.5px; font-weight: var(--font-weight-bold);
}

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
.jobs-empty {
  border: 1px dashed var(--color-border-default);
  padding: 40px 20px; text-align: center;
  color: var(--color-text-secondary); letter-spacing: 0.5px; line-height: 2;
}

.add-btn {
  background: none; border: 1px solid var(--color-brand-strong);
  color: var(--color-brand); font-size: var(--font-size-sm);
  padding: 6px 14px; cursor: pointer; letter-spacing: 0.5px;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.add-btn:hover:not(:disabled) { background: var(--color-bg-active); }
.add-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.add-btn.ghost { border-color: var(--color-border-default); color: var(--color-text-secondary); }
.add-btn.ghost:hover { border-color: var(--color-danger); color: var(--color-danger); background: none; }

/* ── 主体双栏 ────────────────────────── */
.body { display: grid; grid-template-columns: 400px 1fr; gap: 16px; align-items: start; }
@media (max-width: 1200px) { .body { grid-template-columns: 1fr; } }
.left { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.right { display: flex; flex-direction: column; gap: 16px; min-width: 0; }

.panel { background: var(--color-bg-panel); border: 1px solid var(--color-border-default); padding: 16px; }
.ph { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.ph .diamond { width: 10px; height: 10px; border: 1px solid var(--color-brand); transform: rotate(45deg); flex-shrink: 0; background: rgba(216, 177, 106, 0.15); }
.ph b { font-size: var(--font-size-md); letter-spacing: 1px; }
.ph small { margin-left: auto; color: var(--color-text-tertiary); font-size: var(--font-size-2xs); letter-spacing: 0.5px; }
.ph .add {
  border: 1px dashed var(--color-border-strong); background: none;
  color: var(--color-text-secondary); padding: 3px 10px;
  font-size: var(--font-size-xs); cursor: pointer;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.ph .add:hover { color: var(--color-brand); border-color: var(--color-brand-strong); }

.ph2 { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.ph2 .diamond { width: 10px; height: 10px; border: 1px solid var(--color-brand); transform: rotate(45deg); flex-shrink: 0; background: rgba(216, 177, 106, 0.15); }
.ph2 b { font-size: var(--font-size-md); letter-spacing: 1px; }
.ph2 .sep { color: var(--color-brand); margin: 0 6px; }
.ph2 small { margin-left: auto; color: var(--color-text-tertiary); font-size: var(--font-size-2xs); letter-spacing: 0.5px; }

/* ── 时间槽卡片 ──────────────────────── */
.slots { display: flex; flex-direction: column; gap: 8px; }
.slot {
  border: 1px solid var(--color-border-default);
  border-left: 2px solid transparent;
  padding: 10px 12px;
  display: flex; flex-direction: column; gap: 8px;
  cursor: pointer;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.slot:hover { border-color: var(--color-brand-strong); }
.slot.sel { background: var(--color-bg-active); border-color: var(--color-brand-strong); border-left: 2px solid var(--color-brand-strong); }
.slot.off { opacity: 0.55; }
.slot-hd { display: flex; align-items: center; gap: 8px; }
.slot-hd .nm {
  background: none; border: none; outline: none;
  color: var(--color-text-primary); font-size: var(--font-size-md);
  flex: 1; min-width: 0; letter-spacing: 0.5px;
}
.slot-hd .x { cursor: pointer; color: var(--color-text-tertiary); font-size: var(--font-size-sm); }
.slot-hd .x:hover { color: var(--color-danger); }
.slot-row { display: flex; align-items: center; gap: 10px; }

.sw {
  width: 30px; height: 14px; flex-shrink: 0;
  border: 1px solid var(--color-border-strong); position: relative; cursor: pointer;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
  clip-path: polygon(5px 0, 100% 0, 100% calc(100% - 5px), calc(100% - 5px) 100%, 0 100%, 0 5px);
}
.sw.on { background: rgba(216, 177, 106, 0.25); border-color: var(--color-brand-strong); }
.sw::after {
  content: ""; position: absolute; top: 1px; left: 1px;
  width: 10px; height: 10px; background: var(--color-border-strong);
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.sw.on::after { left: 17px; background: var(--color-brand); }

.wds { display: flex; gap: 4px; flex-wrap: wrap; }
.wd {
  width: 24px; height: 24px; line-height: 24px; text-align: center;
  border: 1px solid var(--color-border-default);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs); cursor: pointer; user-select: none;
  clip-path: polygon(4px 0, 100% 0, 100% calc(100% - 4px), calc(100% - 4px) 100%, 0 100%, 0 4px);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.wd.on {
  border-color: var(--color-brand-strong); color: var(--color-brand);
  background: var(--color-bg-active);
}

.conflict { display: flex; align-items: center; gap: 8px; border-top: 1px dashed var(--color-border-default); padding-top: 8px; }
.conflict label { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); letter-spacing: 0.5px; flex-shrink: 0; }

/* ── 账号列表 ────────────────────────── */
.acc-list { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.acc {
  display: flex; align-items: center; gap: 8px;
  border: 1px solid var(--color-border-default);
  border-left: 2px solid transparent;
  padding: 9px 11px; cursor: pointer; font-size: var(--font-size-md);
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.acc:hover { border-color: var(--color-brand-strong); }
.acc.sel { background: var(--color-bg-active); border-color: var(--color-brand-strong); border-left: 2px solid var(--color-brand-strong); }
.acc.off { opacity: 0.5; }
.acc .chk {
  width: 14px; height: 14px; border: 1px solid var(--color-border-strong);
  flex-shrink: 0; transform: rotate(45deg);
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; cursor: pointer;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.acc .chk.on { background: var(--color-brand); border-color: var(--color-brand); }
.acc .chk.on::after { content: "✓"; transform: rotate(-45deg); font-weight: 700; color: var(--color-text-inverse); }
.acc .idx { font-family: var(--font-family-mono); font-size: var(--font-size-2xs); color: var(--color-brand); width: 14px; text-align: center; }
.acc b { flex: 1; font-size: var(--font-size-md); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.acc small { color: var(--color-text-tertiary); font-size: var(--font-size-2xs); font-family: var(--font-family-mono); flex-shrink: 0; }
.acc .last { color: var(--color-success); font-size: var(--font-size-2xs); flex-shrink: 0; }
.acc .last.bad { color: var(--color-danger); }
.acc .x { cursor: pointer; color: var(--color-text-tertiary); flex-shrink: 0; }
.acc .x:hover { color: var(--color-danger); }
.add {
  width: 100%; border: 1px dashed var(--color-border-strong); background: none;
  color: var(--color-text-secondary); padding: 8px;
  font-size: var(--font-size-sm); cursor: pointer; margin-top: 6px;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.add:hover { color: var(--color-brand); border-color: var(--color-brand-strong); }
.empty {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border-default); padding: 14px;
  text-align: center; line-height: 1.7;
}
.note { font-size: var(--font-size-2xs); color: var(--color-text-tertiary); margin-top: 10px; line-height: 1.7; }

/* ── 账号组选择展开 ───────────────────── */
.acc-picker {
  border: 1px solid var(--color-brand-strong); background: var(--color-bg-subtle);
  padding: 10px 12px; margin-top: 8px;
  display: flex; flex-direction: column; gap: 6px;
}
.picker-hd { display: flex; align-items: center; gap: 10px; }
.picker-hd b { font-size: var(--font-size-sm); letter-spacing: 0.5px; }
.picker-hd .mini { margin-left: auto; }
.mini {
  background: none; border: 1px solid var(--color-border-default);
  color: var(--color-text-secondary); font-size: var(--font-size-2xs);
  padding: 2px 8px; cursor: pointer; letter-spacing: 0.5px;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.mini:hover { border-color: var(--color-brand); color: var(--color-brand); }
.pick-item {
  display: flex; align-items: center; gap: 8px; padding: 5px 4px;
  cursor: pointer; font-size: var(--font-size-sm);
}
.pick-item:hover { background: var(--color-bg-hover); }
.pick-item .chk {
  width: 13px; height: 13px; border: 1px solid var(--color-border-strong);
  transform: rotate(45deg); display: flex; align-items: center; justify-content: center;
  font-size: 8px; flex-shrink: 0;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.pick-item .chk.on { background: var(--color-brand); border-color: var(--color-brand); }
.pick-item .chk.on::after { content: "✓"; transform: rotate(-45deg); font-weight: 700; color: var(--color-text-inverse); }
.pick-item b { flex: 1; color: var(--color-text-primary); }
.pick-item small { color: var(--color-text-tertiary); font-family: var(--font-family-mono); }
.picker-foot { display: flex; gap: 8px; justify-content: flex-end; border-top: 1px dashed var(--color-border-default); padding-top: 8px; }

/* ── 方案配置 ────────────────────────── */
.frow { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px dashed var(--color-border-default); }
.frow:last-child { border: none; }
.frow label { flex: 1; font-size: var(--font-size-md); color: var(--color-text-secondary); }
.frow label small { display: block; font-size: var(--font-size-2xs); color: var(--color-text-tertiary); margin-top: 2px; letter-spacing: 0.3px; }
.frow .ds { min-width: 220px; }

.tasks-preview {
  font-family: var(--font-family-mono); font-size: var(--font-size-xs);
  color: var(--color-text-secondary); background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-default);
  padding: 10px 12px; line-height: 1.9; flex: 1; min-width: 0;
}
.tasks-preview .t { color: var(--color-brand); margin-right: 6px; }
.tasks-preview .e { color: var(--color-text-tertiary); }
.tasks-preview .dim { color: var(--color-text-tertiary); }

.btn {
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
  padding: 6px 14px; font-size: var(--font-size-sm); cursor: pointer;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.btn:hover:not(:disabled) { border-color: var(--color-brand-strong); color: var(--color-brand); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: var(--font-size-xs); }

.edit-box {
  border: 1px dashed var(--color-brand-strong);
  padding: 12px; margin-top: 4px;
  display: flex; flex-direction: column; gap: 10px;
  background: var(--color-bg-subtle);
}

/* ── 底部执行栏（RUN TEST 主操作，对齐首页 LINK START 位置） ── */
.exec-row {
  flex-shrink: 0; display: flex; align-items: center; gap: 18px;
  padding: 14px 26px; border-top: 1px solid var(--color-border-default);
  background: var(--color-bg-subtle);
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.25);
  position: relative; z-index: var(--z-index-sticky);
}
.exec-hint { font-size: var(--font-size-xs); color: var(--color-text-tertiary); line-height: 1.6; letter-spacing: 0.3px; }
.run-test {
  margin-left: auto; background: rgba(216, 177, 106, 0.18);
  border: 1px solid var(--color-brand-strong); color: var(--color-brand);
  font-size: var(--font-size-md); font-weight: 700;
  padding: 9px 26px; cursor: pointer; letter-spacing: 1.5px;
  clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
  font-family: var(--font-family-sans);
}
.run-test:hover:not(:disabled) { box-shadow: var(--shadow-glow-lg); }
.run-test:disabled { opacity: 0.45; cursor: not-allowed; }

/* ── 自动任务日志 ─────────────────────── */
.log {
  font-family: var(--font-family-mono); font-size: var(--font-size-xs);
  line-height: 1.9; color: var(--color-text-secondary);
  max-height: 240px; overflow-y: auto;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-default);
  padding: 10px 12px;
}
.log-empty { color: var(--color-text-tertiary); text-align: center; padding: 40px 0; font-family: var(--font-family-sans); font-size: var(--font-size-sm); }
.log .l { display: flex; gap: 8px; padding: 2px 0; align-items: baseline; }
.log .t { color: var(--color-text-tertiary); flex-shrink: 0; }
.src {
  font-size: var(--font-size-2xs); border: 1px solid var(--color-border-default);
  padding: 0 5px; margin-right: 2px; letter-spacing: 0.5px; flex-shrink: 0;
  line-height: 1.6;
}
.src.auto { color: var(--color-brand); border-color: var(--color-brand-strong); }
.src.manual { color: var(--color-warning); border-color: var(--color-warning); }
.c-info { color: var(--color-brand); }
.c-ok { color: var(--color-success); }
.c-warn { color: var(--color-warning); }
.c-error { color: var(--color-danger); }
</style>
