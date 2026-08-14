<script setup lang="ts">
/**
 * 下拉选择 —— 对齐 UI 设计规范 §3.7 Select / 组件画廊「普通下拉」：
 * 方舟主题触发框（斜切直角）＋ ▼ 箭头旋转 ＋ 自定义下拉面板，选中项金色高亮 + 菱形勾选。
 * 键盘可达：Tab 聚焦 → Enter/Space 展开、↑↓ 选择、Esc 关闭；外部点击自动收起。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export interface DropOption {
  value: string
  label: string
  /** 禁用项：渲染置灰不可选（如暂未开放的功能），键盘 ↑↓ 自动跳过 */
  disabled?: boolean
  /** 选项右侧小标签（如职业组构成说明），对齐组件画廊 group-tag */
  desc?: string
}

const props = withDefaults(
  defineProps<{
    modelValue?: string
    options: DropOption[]
    placeholder?: string
    disabled?: boolean
    /** options 为空时下拉面板的提示文案 */
    emptyText?: string
  }>(),
  { placeholder: '请选择…', emptyText: '无可用选项' },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const open = ref(false)
const idx = ref(-1)
const root = ref<HTMLElement | null>(null)

const selected = computed(() => props.options.find((o) => o.value === props.modelValue) ?? null)

function toggle() {
  if (props.disabled) return
  open.value = !open.value
  idx.value = props.options.findIndex((o) => o.value === props.modelValue)
}

function close() {
  open.value = false
}

function pick(o: DropOption) {
  if (o.disabled) return
  emit('update:modelValue', o.value)
  open.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    toggle()
  } else if (e.key === 'Escape') {
    close()
  } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    const n = props.options.length
    if (!n) return
    if (!open.value) open.value = true
    const dir = e.key === 'ArrowDown' ? 1 : -1
    let i = idx.value
    for (let step = 0; step < n; step++) {
      i = (i + dir + n) % n
      if (!props.options[i]?.disabled) break
    }
    if (props.options[i] && !props.options[i].disabled) {
      idx.value = i
      emit('update:modelValue', props.options[i].value)
    }
  }
}

function onDocClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) close()
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div ref="root" class="ds" :class="{ open, disabled }">
    <div
      class="ds-box"
      role="combobox"
      :aria-expanded="open"
      :aria-disabled="disabled"
      tabindex="0"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span class="ds-val" :class="{ ph: !selected }">{{ selected?.label ?? placeholder }}</span>
      <span class="ds-arr">▼</span>
    </div>
    <div v-if="open" class="ds-drop">
      <div v-if="options.length === 0" class="ds-empty">{{ emptyText }}</div>
      <button
        v-for="(o, i) in options"
        :key="o.value"
        type="button"
        class="ds-opt"
        :class="{ sel: o.value === modelValue, hl: i === idx, off: o.disabled }"
        :disabled="o.disabled"
        @mousedown.prevent
        @click="pick(o)"
      >
        <span class="chk-d" :class="{ on: o.value === modelValue }"></span>
        <span class="opt-label">{{ o.label }}</span>
        <span v-if="o.desc" class="desc-tag">{{ o.desc }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.ds { position: relative; min-width: 120px; width: max-content; max-width: 100%; flex-shrink: 0; }
.ds.disabled { opacity: 0.45; cursor: not-allowed; }

/* 触发框（斜切直角，无圆角） */
.ds-box {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default); padding: 6px 11px;
  font-size: var(--font-size-md); cursor: pointer; outline: none;
  font-family: inherit; user-select: none;
  transition: border-color var(--motion-duration-fast) var(--motion-easing-standard);
}
.ds-box:hover, .ds-box:focus-visible, .ds.open .ds-box { border-color: var(--color-brand-strong); }
.ds-box:focus-visible { box-shadow: var(--shadow-glow-sm); }
.ds-box.disabled { cursor: not-allowed; }

.ds-val { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ds-val.ph { color: var(--color-text-tertiary); }

.ds-arr {
  font-size: 9px; color: var(--color-text-tertiary); flex-shrink: 0;
  transition: transform var(--motion-duration-fast) var(--motion-easing-standard);
}
.ds.open .ds-arr { transform: rotate(180deg); }

/* 下拉面板 */
.ds-drop {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 50;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-strong);
  max-height: 200px; overflow-y: auto;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
.ds-empty {
  padding: 12px 14px;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  letter-spacing: 0.3px; line-height: 1.6;
}
.ds-opt {
  display: flex; align-items: center; gap: 8px;
  width: 100%; text-align: left;
  padding: 8px 12px; font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  background: none; border: none; cursor: pointer; font-family: inherit;
  border-bottom: 1px dashed var(--color-border-default);
}
.ds-opt:last-child { border-bottom: none; }
.ds-opt:hover, .ds-opt.hl { background: var(--color-bg-active); color: var(--color-brand); }
.ds-opt.sel { color: var(--color-brand); background: var(--color-bg-active); }
.ds-opt.off { color: var(--color-text-tertiary); opacity: 0.5; cursor: not-allowed; }
.ds-opt.off:hover, .ds-opt.off.hl { background: none; color: var(--color-text-tertiary); }
.ds-opt .opt-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ds-opt .desc-tag {
  flex-shrink: 0;
  font-size: 9.5px; color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-default);
  padding: 0 5px; letter-spacing: 0.5px;
  white-space: nowrap;
}
.ds-opt:hover .desc-tag, .ds-opt.hl .desc-tag, .ds-opt.sel .desc-tag { color: var(--color-brand); border-color: var(--color-brand-strong); }

/* 选中菱形勾选（品牌形制） */
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
