<script setup lang="ts">
import { computed } from 'vue'

/** 数字微调（对应 MAA `hc:NumericUpDown`）：数字输入 + 上下步进按钮，受 min/max 约束。
 * specialValue/specialLabel：特定值用文字显示（如 -1 →「不限」，MAA 默认 int.MaxValue 语义）。 */
const props = withDefaults(
  defineProps<{
    modelValue?: unknown
    min?: number
    max?: number
    step?: number
    disabled?: boolean
    specialValue?: number
    specialLabel?: string
  }>(),
  { step: 1 },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: number): void
}>()

function toNum(v: unknown): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isNaN(n) ? 0 : n
}

const displayText = computed(() => {
  const v = props.modelValue
  if (props.specialValue !== undefined && toNum(v) === props.specialValue) {
    return props.specialLabel ?? String(props.specialValue)
  }
  return v === undefined || v === null || v === '' ? '' : String(v)
})

function clamp(v: number): number {
  let x = v
  if (props.min !== undefined && x < props.min) x = props.min
  if (props.max !== undefined && x > props.max) x = props.max
  return x
}

function set(v: number) {
  if (Number.isNaN(v)) return
  emit('update:modelValue', clamp(v))
}

function up() {
  set(toNum(props.modelValue) + props.step)
}

function down() {
  set(toNum(props.modelValue) - props.step)
}

function onInput(e: Event) {
  const t = (e.target as HTMLInputElement).value
  if (t === '') return
  const n = Number(t)
  if (!Number.isNaN(n)) set(n)
}
</script>

<template>
  <div class="nf" :class="{ disabled }">
    <input
      class="nf-input"
      type="text"
      inputmode="numeric"
      :value="displayText"
      :disabled="disabled"
      @input="onInput"
    />
    <div class="nf-steppers">
      <button class="nf-btn up" type="button" :disabled="disabled" title="增加" @click="up">▲</button>
      <button class="nf-btn down" type="button" :disabled="disabled" title="减少" @click="down">▼</button>
    </div>
  </div>
</template>

<style scoped>
.nf {
  display: flex; align-items: stretch; gap: 3px; flex-shrink: 0;
}
.nf.disabled { opacity: 0.4; cursor: not-allowed; }

.nf-input {
  width: 64px;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 5px 10px;
  font-size: var(--font-size-md); text-align: right; outline: none;
  font-family: var(--font-family-mono);
  clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
}
.nf-input:focus { border-color: var(--color-brand); }
.nf-input:disabled { cursor: not-allowed; }

.nf-steppers {
  display: flex; flex-direction: column; gap: 3px;
}
.nf-btn {
  flex: 1; min-height: 13px; padding: 0 7px;
  background: var(--color-bg-subtle); color: var(--color-text-secondary);
  border: 1px solid var(--color-border-default);
  font-size: 8px; line-height: 1; cursor: pointer;
  clip-path: polygon(5px 0, 100% 0, 100% calc(100% - 5px), calc(100% - 5px) 100%, 0 100%, 0 5px);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.nf-btn:hover:not(:disabled) { border-color: var(--color-brand); color: var(--color-brand); background: var(--color-bg-active); }
.nf-btn:disabled { cursor: not-allowed; }
</style>
