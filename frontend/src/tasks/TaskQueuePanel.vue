<script setup lang="ts">
/** 任务队列编辑面板（作战总览 / 任务编排 两页复用，UI 与交互保持一致）。 */
import { TASK_TYPES, type QueueTask } from './taskTypes'

defineProps<{
  queue: QueueTask[]
  adding: boolean
  /** 面板标题与副标题（两页可各自命名） */
  title?: string
  subtitle?: string
  emptyText?: string
}>()

const emit = defineEmits<{
  (e: 'toggle-add'): void
  (e: 'add', type: (typeof TASK_TYPES)[number]): void
  (e: 'select', id: number): void
  (e: 'toggle-checked', id: number): void
  (e: 'remove', id: number): void
  (e: 'dragstart', index: number): void
  (e: 'drop', index: number): void
}>()
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <span class="t">{{ title ?? '任务编排' }}</span>
      <span class="sub">{{ subtitle ?? '拖拽排序 · 勾选启用' }}</span>
      <button class="add-btn" @click="emit('toggle-add')">＋ 添加任务</button>
    </div>

    <!-- 添加任务下拉 -->
    <div v-if="adding" class="add-menu">
      <button
        v-for="tt in TASK_TYPES"
        :key="tt.entry"
        class="add-item"
        @click="emit('add', tt)"
      >{{ tt.label }}</button>
    </div>

    <div class="panel-bd">
      <!-- 空态 -->
      <div v-if="queue.length === 0" class="empty">
        {{ emptyText ?? '暂无部署任务，点击右上「添加任务」开始编排' }}
      </div>

      <!-- 任务队列 -->
      <div
        v-for="(t, i) in queue"
        :key="t.id"
        class="task"
        :class="{ selected: t.selected }"
        draggable="true"
        @click="emit('select', t.id)"
        @dragstart="emit('dragstart', i)"
        @dragover.prevent
        @drop.prevent="emit('drop', i)"
      >
        <span class="chk" :class="{ on: t.checked }" @click.stop="emit('toggle-checked', t.id)"></span>
        <span class="nm">{{ t.label }}</span>
        <span v-if="t.once" class="once" title="仅执行一次">ONCE</span>
        <span class="del" title="移除任务" @click.stop="emit('remove', t.id)">✕</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
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

.add-menu {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px;
  padding: 10px 14px; background: var(--color-bg-subtle);
  border-bottom: 1px solid var(--color-border-default);
}
.add-item {
  background: var(--color-bg-panel); border: 1px solid var(--color-border-default);
  color: var(--color-text-secondary); padding: 7px 10px; cursor: pointer;
  font-size: var(--font-size-sm); text-align: left; letter-spacing: 0.3px;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.add-item:hover { border-color: var(--color-brand); color: var(--color-brand); background: var(--color-bg-active); }

.panel-bd { padding: 6px; min-height: 120px; }

.empty {
  padding: 34px 18px; text-align: center;
  color: var(--color-text-tertiary); font-size: var(--font-size-sm); letter-spacing: 0.5px;
}

/* ── 任务项 ──────────────────────────── */
.task {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; cursor: pointer;
  transition: background var(--motion-duration-fast) var(--motion-easing-standard);
  border-left: 2px solid transparent;
}
.task:hover { background: var(--color-bg-hover); }
.task.selected { border-left-color: var(--color-brand); background: var(--color-bg-active); }
.task .chk {
  width: 15px; height: 15px;
  border: 1px solid var(--color-border-strong);
  transform: rotate(45deg); flex-shrink: 0;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
  position: relative; cursor: pointer;
}
.task .chk.on { background: var(--color-brand); border-color: var(--color-brand); }
.task .chk.on::before {
  content: "✓"; position: absolute; inset: 0; transform: rotate(-45deg);
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; color: var(--color-text-inverse); font-weight: 800;
}
.task .nm { flex: 1; font-size: var(--font-size-lg); color: var(--color-text-primary); }
.task .once {
  font-size: var(--font-size-2xs); color: var(--color-warning);
  border: 1px solid var(--color-warning); padding: 1px 5px; letter-spacing: 1px;
}
.task .del {
  color: var(--color-text-tertiary); cursor: pointer; padding: 0 4px; font-size: var(--font-size-sm);
  visibility: hidden;
}
.task:hover .del { visibility: visible; }
.task .del:hover { color: var(--color-danger); }
</style>
