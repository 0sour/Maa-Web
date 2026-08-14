<script setup lang="ts">
/**
 * 可搜索下拉（对应 MAA `hc:ComboBox + MakeComboBoxSearchable`）：
 * 输入过滤 + 点选，选中后可一键清除。选项形如 {id, name}，搜索按名称/ID 子串匹配。
 */
import { computed, ref } from 'vue'

export interface SearchOption {
  id: string
  name: string
}

const props = withDefaults(
  defineProps<{
    modelValue?: string
    options: SearchOption[]
    placeholder?: string
    emptyText?: string
    max?: number
  }>(),
  { placeholder: '搜索选择…', emptyText: '无匹配选项', max: 80 },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
}>()

const open = ref(false)
const kw = ref('')

const selected = computed(() => props.options.find((o) => o.id === props.modelValue) ?? null)

/** 未聚焦时回显已选项名称，聚焦后显示搜索词 */
const display = computed(() => (open.value ? kw.value : selected.value?.name ?? ''))

const filtered = computed(() => {
  const q = kw.value.trim().toLowerCase()
  if (!q) return props.options.slice(0, props.max)
  return props.options
    .filter((o) => o.name.toLowerCase().includes(q) || o.id.toLowerCase().includes(q))
    .slice(0, props.max)
})

function openList() {
  open.value = true
}

function pick(o: SearchOption) {
  emit('update:modelValue', o.id)
  kw.value = ''
  open.value = false
}

function clear() {
  emit('update:modelValue', '')
  kw.value = ''
  open.value = false
}
</script>

<template>
  <div class="ss" :class="{ open }">
    <input
      class="ss-input"
      :value="display"
      :placeholder="selected ? selected.name : placeholder"
      @focus="openList"
      @input="openList"
      @blur="open = false"
      @keydown.esc="open = false"
    />
    <button v-if="modelValue" class="ss-clear" type="button" title="清除" @mousedown.prevent @click="clear">✕</button>
    <div v-if="open && filtered.length" class="ss-list">
      <button
        v-for="o in filtered"
        :key="o.id"
        class="ss-opt"
        type="button"
        :class="{ on: o.id === modelValue }"
        @mousedown.prevent
        @click="pick(o)"
      >
        <span class="nm">{{ o.name }}</span>
        <code class="id">{{ o.id }}</code>
      </button>
    </div>
    <div v-else-if="open" class="ss-empty">{{ emptyText }}</div>
  </div>
</template>

<style scoped>
.ss { position: relative; flex: 1; min-width: 0; }
.ss-input {
  width: 100%;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default); padding: 6px 11px;
  font-size: var(--font-size-md); outline: none; font-family: inherit;
}
.ss.open .ss-input { border-color: var(--color-brand); }
.ss-clear {
  position: absolute; top: 50%; right: 8px; transform: translateY(-50%);
  background: none; border: none; cursor: pointer;
  color: var(--color-text-tertiary); font-size: var(--font-size-sm); padding: 2px;
}
.ss-clear:hover { color: var(--color-brand); }
.ss-list {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 60;
  max-height: 240px; overflow-y: auto;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-strong);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
.ss-opt {
  display: flex; align-items: center; gap: 10px;
  width: 100%; text-align: left; cursor: pointer;
  background: none; border: none; color: var(--color-text-primary);
  padding: 7px 12px; font-size: var(--font-size-md); font-family: inherit;
  border-bottom: 1px dashed var(--color-border-default);
}
.ss-opt:last-child { border-bottom: none; }
.ss-opt:hover, .ss-opt.on { background: var(--color-bg-active); color: var(--color-brand); }
.ss-opt .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ss-opt .id { font-family: var(--font-family-mono); font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.ss-opt:hover .id, .ss-opt.on .id { color: var(--color-brand); }
.ss-empty {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 60;
  background: var(--color-bg-panel); border: 1px solid var(--color-border-strong);
  padding: 10px 12px; font-size: var(--font-size-sm); color: var(--color-text-tertiary);
}
</style>
