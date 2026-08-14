<script setup lang="ts">
/**
 * 多选下拉 —— 对齐 UI 设计规范 / 组件画廊「多选下拉（标签多选）」：
 * 触发框显示已选数量与摘要，面板选项带品牌菱形勾选（chk-d），
 * 勾选后保持展开可连续多选，外部点击自动收起。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export interface MultiOption {
  value: string
  label: string
}

const props = withDefaults(
  defineProps<{
    modelValue?: string[]
    options: MultiOption[]
    placeholder?: string
    max?: number
  }>(),
  { placeholder: '选择…', max: 4 },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: string[]): void }>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const selected = computed(() => {
  const list = props.modelValue ?? []
  return props.options.filter((o) => list.includes(o.value))
})

const summary = computed(() => {
  const sel = selected.value
  if (!sel.length) return ''
  const names = sel.slice(0, props.max).map((o) => o.label).join('、')
  return sel.length > props.max ? `${names}… 等 ${sel.length} 项` : names
})

function toggle() {
  open.value = !open.value
}

function pick(o: MultiOption) {
  const list = [...(props.modelValue ?? [])]
  const i = list.indexOf(o.value)
  if (i >= 0) list.splice(i, 1)
  else list.push(o.value)
  emit('update:modelValue', list)
}

function onDocClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div ref="root" class="ms" :class="{ open }">
    <div class="ms-box" role="listbox" :aria-expanded="open" tabindex="0" @click="toggle" @keydown.enter.prevent="toggle" @keydown.space.prevent="toggle" @keydown.esc="open = false">
      <span class="ms-val" :class="{ ph: !selected.length }">
        <template v-if="selected.length">{{ placeholder }}（{{ selected.length }}）：{{ summary }}</template>
        <template v-else>{{ placeholder }}</template>
      </span>
      <span class="ms-arr">▼</span>
    </div>
    <div v-if="open" class="ms-drop">
      <button
        v-for="o in options"
        :key="o.value"
        type="button"
        class="ms-opt"
        :class="{ on: selected.some((s) => s.value === o.value) }"
        @mousedown.prevent
        @click="pick(o)"
      >
        <span class="chk-d" :class="{ on: selected.some((s) => s.value === o.value) }"></span>
        {{ o.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.ms { position: relative; flex: 1; min-width: 0; }

/* 触发框 */
.ms-box {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default); padding: 6px 11px;
  font-size: var(--font-size-md); cursor: pointer; outline: none;
  font-family: inherit; user-select: none;
  transition: border-color var(--motion-duration-fast) var(--motion-easing-standard);
}
.ms-box:hover, .ms-box:focus-visible, .ms.open .ms-box { border-color: var(--color-brand-strong); }
.ms-box:focus-visible { box-shadow: var(--shadow-glow-sm); }
.ms-val { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ms-val.ph { color: var(--color-text-tertiary); }
.ms-arr {
  font-size: 9px; color: var(--color-text-tertiary); flex-shrink: 0;
  transition: transform var(--motion-duration-fast) var(--motion-easing-standard);
}
.ms.open .ms-arr { transform: rotate(180deg); }

/* 下拉面板（勾选保持展开） */
.ms-drop {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 50;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-strong);
  max-height: 220px; overflow-y: auto;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
.ms-opt {
  display: flex; align-items: center; gap: 8px;
  width: 100%; text-align: left;
  padding: 8px 12px; font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  background: none; border: none; cursor: pointer; font-family: inherit;
  border-bottom: 1px dashed var(--color-border-default);
}
.ms-opt:last-child { border-bottom: none; }
.ms-opt:hover { background: var(--color-bg-active); color: var(--color-brand); }
.ms-opt.on { color: var(--color-brand); background: var(--color-bg-active); }

/* 品牌菱形勾选 */
.chk-d {
  width: 13px; height: 13px; flex-shrink: 0;
  border: 1px solid var(--color-border-strong);
  transform: rotate(45deg);
  display: flex; align-items: center; justify-content: center;
  font-size: 8px; color: var(--color-text-inverse);
}
.chk-d.on { background: var(--color-brand); border-color: var(--color-brand); }
.chk-d.on::after { content: "✓"; transform: rotate(-45deg); font-weight: 700; }
</style>
