<script setup lang="ts">
/**
 * 任务编排页（纯编辑）—— 编排任务队列 + 保存/调出方案。
 * 执行（LINK START）已移至「自动任务」页（RUN TEST / 定时触发）。
 */
import { onMounted, ref } from 'vue'
import { useTaskQueue } from '@/tasks/useTaskQueue'
import { useQueueDraft } from '@/tasks/useQueueDraft'
import { useTaskSchemes } from '@/tasks/useTaskSchemes'
import type { TaskScheme } from '@/api/task-schemes'
import TaskQueuePanel from '@/tasks/TaskQueuePanel.vue'
import TaskParamsPanel from '@/tasks/TaskParamsPanel.vue'
import type { PersistedTask } from '@/tasks/taskTypes'

// ── 编辑草稿（后端留底，跨浏览器一致；正式方案需显式命名保存） ──
const queueDraft = useQueueDraft('tasks')

const {
  queue, adding, selectedTask, countChecked,
  addTask, selectTask, toggleChecked, removeTask, onDragStart, onDrop,
  serialize, restore, clearQueue,
} = useTaskQueue()

// 队列改动 → 防抖保存到后端（加载完成前不覆盖）
queueDraft.watchSave(queue, serialize)

// ── 方案「任务文件」管理（后端 task_schemes 表） ──────
const { schemes, load: loadSchemes, saveScheme, removeScheme } = useTaskSchemes()
const schemeName = ref('')
const tip = ref('')
const schemeErr = ref('')
const loadedName = ref('')

async function saveAsScheme() {
  const name = schemeName.value.trim()
  if (!name) {
    schemeErr.value = '请先为当前配置命名再保存'
    return
  }
  schemeErr.value = ''
  try {
    const s = await saveScheme(name, serialize())
    schemeName.value = s.name
    loadedName.value = s.name
    tip.value = `✔ 已保存方案「${s.name}」（${s.tasks.length} 项任务）`
  } catch (e: unknown) {
    schemeErr.value =
      (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
      ?? '保存方案失败'
  }
}

function loadScheme(s: TaskScheme) {
  restore(s.tasks as unknown as PersistedTask[])
  schemeName.value = s.name
  loadedName.value = s.name
  tip.value = `已加载方案「${s.name}」`
}

async function removeSchemeConfirm(s: TaskScheme) {
  try {
    await removeScheme(s.name)
    if (loadedName.value === s.name) {
      loadedName.value = ''
      schemeName.value = ''
    }
    tip.value = `已删除方案「${s.name}」`
  } catch (e: unknown) {
    schemeErr.value =
      (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
      ?? '删除方案失败'
  }
}

function newQueue() {
  clearQueue()
  schemeName.value = ''
  loadedName.value = ''
  tip.value = '已清空，开始编排新任务队列'
}

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

onMounted(async () => {
  // 方案与草稿均从后端加载（跨浏览器一致）
  await loadSchemes()
  const draft = await queueDraft.loadDraft()
  if (draft && draft.length) {
    restore(draft)
    // 当前队列若与某方案一致则标注（可辨识当前编辑位置）
    const hit = schemes.value.find((s) => {
      const a = JSON.stringify(s.tasks)
      const b = JSON.stringify(draft)
      return a === b
    })
    if (hit) {
      loadedName.value = hit.name
      schemeName.value = hit.name
    }
  }
})
</script>

<template>
  <div class="tasks">
    <div class="dashboard">
      <!-- 方案「任务文件」栏（显眼：页面顶部独立卡片） -->
      <div class="scheme-card">
        <div class="scheme-hd">
          <span class="diamond"></span>
          <span class="t">任务文件</span>
          <span class="sub">
            {{ loadedName ? `当前方案「${loadedName}」` : '未命名配置' }}
            · 队列 {{ countChecked }} 项已勾选
          </span>
        </div>
        <div class="scheme-row">
          <input
            v-model="schemeName"
            class="scheme-name"
            placeholder="为当前配置起名，如：每日日常"
            @keyup.enter="saveAsScheme"
          />
          <button class="add-btn" @click="saveAsScheme">保存为方案</button>
          <button class="add-btn ghost" @click="newQueue">新建队列</button>
          <span v-if="schemeErr" class="scheme-err">⚠ {{ schemeErr }}</span>
          <span v-else class="scheme-tip">{{ tip }}</span>
        </div>
        <div v-if="schemes.length" class="scheme-list">
          <div
            v-for="s in schemes"
            :key="s.name"
            class="scheme-item"
            :class="{ current: loadedName === s.name }"
          >
            <span class="nm">{{ s.name }}</span>
            <span class="meta">{{ s.tasks.length }} 项任务 · {{ fmtTime(s.updated_at) }}</span>
            <button class="mini" @click="loadScheme(s)">调出</button>
            <button class="mini del" @click="removeSchemeConfirm(s)">删除</button>
          </div>
        </div>
      </div>

      <!-- 双栏：左侧任务列表 + 右侧参数面板（未选中任务时显示占位框） -->
      <div class="double">
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
        <div class="params-panel">
          <TaskParamsPanel :selected-task="selectedTask" />
        </div>
      </div>
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

/* ── 方案卡片（顶部显眼区） ──────────────── */
.scheme-card {
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-subtle);
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;
}
.scheme-hd { display: flex; align-items: center; gap: 10px; }
.scheme-hd .diamond {
  width: 12px; height: 12px;
  border: 1px solid var(--color-brand); transform: rotate(45deg);
  background: rgba(216, 177, 106, 0.15); flex-shrink: 0;
}
.scheme-hd .t {
  font-size: var(--font-size-lg); font-weight: var(--font-weight-bold);
  letter-spacing: var(--font-tracking-wide);
}
.scheme-hd .sub {
  margin-left: auto; font-size: var(--font-size-sm);
  color: var(--color-text-tertiary); letter-spacing: 0.5px;
}
.scheme-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.scheme-name {
  background: var(--color-bg-panel); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 7px 12px; font-size: var(--font-size-md); outline: none;
  flex: 1; min-width: 200px; max-width: 380px;
}
.scheme-name:focus { border-color: var(--color-brand); }
.scheme-err { font-size: var(--font-size-sm); color: var(--color-danger); }
.scheme-tip { font-size: var(--font-size-sm); color: var(--color-text-secondary); letter-spacing: 0.3px; }

.add-btn {
  background: none; border: 1px solid var(--color-brand-strong);
  color: var(--color-brand); font-size: var(--font-size-sm);
  padding: 6px 14px; cursor: pointer; letter-spacing: 0.5px;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.add-btn:hover { background: var(--color-bg-active); }
.add-btn.ghost { border-color: var(--color-border-default); color: var(--color-text-secondary); }
.add-btn.ghost:hover { border-color: var(--color-danger); color: var(--color-danger); background: none; }

.scheme-list { display: flex; flex-wrap: wrap; gap: 8px; }
.scheme-item {
  display: flex; align-items: center; gap: 10px;
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-panel);
  padding: 6px 10px;
}
.scheme-item.current { border-color: var(--color-brand-strong); background: var(--color-bg-active); }
.scheme-item.current .nm { color: var(--color-brand); }
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

/* ── 双栏：左侧任务列表 + 右侧参数面板 ────── */
.double {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr);
  gap: 14px; align-items: start;
}
@media (max-width: 1080px) { .double { grid-template-columns: 1fr; } }

/* 右侧参数面板容器（选中任务显示设置；未选中显示占位框） */
.params-panel {
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  min-height: 220px;
  display: flex; flex-direction: column;
}
/* 表单自身的顶部边框在面板容器内去掉（面板边框已提供分隔） */
.params-panel :deep(.params) { border-top: none; }
/* 未选中任务的占位框 */
.params-panel :deep(.params-note) {
  flex: 1; display: flex; align-items: center; justify-content: center;
  padding: 70px 20px; text-align: center;
  font-size: var(--font-size-md); color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border-default);
  background: var(--color-bg-subtle);
  letter-spacing: 0.5px;
}
</style>
