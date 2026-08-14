<script setup lang="ts">
/** 关卡搜索下拉（「目标关卡」）：输入过滤 + 候选选择，允许自由输入。
 *  数据源：后端 /v1/resources/stages（引擎包 stages.json），失败回退内置常用列表。 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { resourcesApi } from '@/api/resources'

const props = withDefaults(defineProps<{ modelValue?: unknown; disabled?: boolean }>(), {})

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const FALLBACK = [
  '1-7', 'CE-6', 'CE-5', 'LS-6', 'LS-5', 'CA-5', 'AP-5', 'SK-5', 'PR-A-1', 'Annihilation',
]

const draft = ref(props.modelValue == null ? '' : String(props.modelValue))
watch(
  () => props.modelValue,
  (v) => {
    const s = v == null ? '' : String(v)
    if (s !== draft.value) draft.value = s
  },
)

const stages = ref<string[]>(FALLBACK)
let loaded = false
async function load() {
  if (loaded) return
  loaded = true
  try {
    const list = await resourcesApi.stages()
    if (Array.isArray(list) && list.length) stages.value = list
  } catch {
    /* 保留内置兜底列表 */
  }
}

const open = ref(false)
const matched = computed(() => {
  const q = draft.value.trim().toLowerCase()
  if (!q) return stages.value.slice(0, 8)
  const hit = stages.value.filter((s) => s.toLowerCase().includes(q))
  hit.sort((a, b) => {
    const pa = a.toLowerCase().startsWith(q) ? 0 : 1
    const pb = b.toLowerCase().startsWith(q) ? 0 : 1
    return pa - pb || a.localeCompare(b)
  })
  return hit.slice(0, 8)
})

function onInput(e: Event) {
  const t = (e.target as HTMLInputElement).value
  draft.value = t
  emit('update:modelValue', t)
  open.value = true
}

function pick(code: string) {
  draft.value = code
  emit('update:modelValue', code)
  open.value = false
}

function onFocus() {
  open.value = true
  load()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && matched.value.length) {
    e.preventDefault()
    pick(matched.value[0])
  } else if (e.key === 'Escape') {
    open.value = false
  }
}

let blurTimer: ReturnType<typeof setTimeout> | undefined
function onBlur() {
  blurTimer = setTimeout(() => (open.value = false), 120)
}
onBeforeUnmount(() => clearTimeout(blurTimer))
</script>

<template>
  <div class="sp">
    <input
      class="sp-input"
      :value="draft"
      :disabled="disabled"
      placeholder="输入或搜索关卡"
      @input="onInput"
      @focus="onFocus"
      @blur="onBlur"
      @keydown="onKeydown"
    />
    <ul v-if="open && matched.length" class="sp-list">
      <li
        v-for="s in matched" :key="s"
        class="sp-item"
        :class="{ on: s === String(props.modelValue ?? '') }"
        @mousedown.prevent="pick(s)"
      >{{ s }}</li>
    </ul>
  </div>
</template>

<style scoped>
.sp { position: relative; flex-shrink: 0; }

.sp-input {
  width: 150px;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 6px 11px;
  font-size: var(--font-size-md); outline: none; font-family: inherit;
  transition: border-color var(--motion-duration-fast) var(--motion-easing-standard);
  clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
}
.sp-input:focus { border-color: var(--color-brand); }
.sp-input:disabled { opacity: 0.4; cursor: not-allowed; }

.sp-list {
  position: absolute; z-index: 40; top: calc(100% + 4px); left: 0; min-width: 100%;
  max-height: 240px; overflow-y: auto;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  list-style: none; margin: 0; padding: 4px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
}
.sp-item {
  padding: 6px 10px; font-size: var(--font-size-md); cursor: pointer;
  color: var(--color-text-secondary); font-family: var(--font-family-mono);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.sp-item:hover, .sp-item.on { background: var(--color-bg-active); color: var(--color-brand); }
</style>
