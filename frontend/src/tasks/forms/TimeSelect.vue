<script setup lang="ts">
/**
 * 时间选择 —— 对齐 UI 组件画廊「时间选择（TimeSelect）」：
 * 触发框（斜切直角 + ▼ 旋转，同普通下拉）+ 双列面板（时 00-23 / 分 00-59）。
 * 选中项金色高亮 + 菱形标记；键盘可达（Tab 聚焦 → Enter 展开、Esc 关闭，外部点击收起）。
 * v-model 为 "HH:MM"（与 schedule_jobs.time / 主题自动切换时间同格式）。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    disabled?: boolean
  }>(),
  { placeholder: '选择时间' },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const hourList = ref<HTMLElement | null>(null)
const minList = ref<HTMLElement | null>(null)

const m = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(props.modelValue ?? '')
const hour = ref(m ? m[1] : '')
const minute = ref(m ? m[2] : '')

const HOURS = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const MINS = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'))

const display = computed(() =>
  hour.value && minute.value ? `${hour.value}:${minute.value}` : '',
)

function commit() {
  if (hour.value && minute.value) emit('update:modelValue', `${hour.value}:${minute.value}`)
}

function pickHour(h: string) {
  hour.value = h
  commit()
  open.value = false
}

function pickMin(mn: string) {
  minute.value = mn
  commit()
  open.value = false
}

function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    // 面板打开后把选中项滚动到可见位置
    void nextTick(() => {
      const target = (list: HTMLElement | null, v: string) => {
        const el = list?.querySelector(`[data-v="${v}"]`)
        el?.scrollIntoView({ block: 'center' })
      }
      target(hourList.value, hour.value || '06')
      target(minList.value, minute.value || '00')
    })
  }
}

function close() {
  open.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    toggle()
  } else if (e.key === 'Escape') {
    close()
  }
}

function onDocClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) close()
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div ref="root" class="ts" :class="{ open, disabled }">
    <div
      class="ts-box"
      role="combobox"
      :aria-expanded="open"
      :aria-disabled="disabled"
      tabindex="0"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span class="ts-val" :class="{ ph: !display }">{{ display || placeholder }}</span>
      <span class="ts-arr">▼</span>
    </div>

    <div v-if="open" class="ts-drop">
      <!-- 时 -->
      <div ref="hourList" class="ts-col">
        <div
          v-for="h in HOURS" :key="h"
          :data-v="h"
          class="ts-opt"
          :class="{ sel: h === hour }"
          @mousedown.prevent
          @click="pickHour(h)"
        >
          <span class="chk-d" :class="{ on: h === hour }"></span>
          <span class="opt-label">{{ h }}</span>
        </div>
      </div>
      <span class="ts-sep">:</span>
      <!-- 分 -->
      <div ref="minList" class="ts-col">
        <div
          v-for="mn in MINS" :key="mn"
          :data-v="mn"
          class="ts-opt"
          :class="{ sel: mn === minute }"
          @mousedown.prevent
          @click="pickMin(mn)"
        >
          <span class="chk-d" :class="{ on: mn === minute }"></span>
          <span class="opt-label">{{ mn }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ts { position: relative; min-width: 120px; flex-shrink: 0; }
.ts.disabled { opacity: 0.45; cursor: not-allowed; }

/* 触发框（斜切直角，同普通下拉） */
.ts-box {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default); padding: 6px 11px;
  font-size: var(--font-size-md); cursor: pointer; outline: none;
  font-family: var(--font-family-mono); user-select: none;
  clip-path: polygon(7px 0, 100% 0, 100% calc(100% - 7px), calc(100% - 7px) 100%, 0 100%, 0 7px);
  transition: border-color var(--motion-duration-fast) var(--motion-easing-standard);
}
.ts-box:hover, .ts-box:focus-visible, .ts.open .ts-box { border-color: var(--color-brand-strong); }
.ts-box:focus-visible { box-shadow: var(--shadow-glow-sm); }

.ts-val { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; letter-spacing: 0.5px; }
.ts-val.ph { color: var(--color-text-tertiary); font-family: var(--font-family-sans); }

.ts-arr {
  font-size: 9px; color: var(--color-text-tertiary); flex-shrink: 0;
  transition: transform var(--motion-duration-fast) var(--motion-easing-standard);
}
.ts.open .ts-arr { transform: rotate(180deg); }

/* 下拉面板：双列滚动（时 / 分） */
.ts-drop {
  position: absolute; top: calc(100% + 4px); left: 0; z-index: 50;
  display: flex; align-items: stretch; gap: 6px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-strong);
  padding: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
.ts-col { max-height: 208px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--color-border-strong) transparent; }
.ts-col::-webkit-scrollbar { width: 5px; }
.ts-col::-webkit-scrollbar-track { background: transparent; }
.ts-col::-webkit-scrollbar-thumb { background: var(--color-border-strong); }
.ts-col::-webkit-scrollbar-thumb:hover { background: var(--color-brand-strong); }
.ts-sep { align-self: center; color: var(--color-text-tertiary); font-family: var(--font-family-mono); }
.ts-opt {
  display: flex; align-items: center; gap: 7px;
  width: 52px; text-align: left;
  padding: 5px 8px; font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  background: none; border: none; cursor: pointer; font-family: var(--font-family-mono);
}
.ts-opt:hover { background: var(--color-bg-active); color: var(--color-brand); }
.ts-opt.sel { color: var(--color-brand); background: var(--color-bg-active); }
.ts-opt .opt-label { flex: 1; letter-spacing: 0.5px; }

/* 选中菱形勾选（品牌形制） */
.chk-d {
  width: 11px; height: 11px; flex-shrink: 0;
  border: 1px solid var(--color-border-strong);
  transform: rotate(45deg);
  display: flex; align-items: center; justify-content: center;
  font-size: 7px; color: var(--color-text-inverse);
}
.chk-d.on { background: var(--color-brand); border-color: var(--color-brand); }
.chk-d.on::after { content: "✓"; transform: rotate(-45deg); font-weight: 700; }
</style>
