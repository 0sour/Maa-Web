<script setup lang="ts">
import { computed } from 'vue'
import { CLIENT_TYPES, CLIENT_TYPE_LABELS } from '../taskTypes'
import { useFormParams } from './useFormParams'
import DropSelect, { type DropOption } from './DropSelect.vue'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p } = useFormParams(props.params)

const clientTypeOpts = computed<DropOption[]>(() => [
  { value: '', label: '跟随设备' },
  ...CLIENT_TYPES.map((c) => ({ value: c, label: CLIENT_TYPE_LABELS[c] ?? c })),
])
const clientTypeModel = computed({
  get: () => String(p.value.client_type ?? ''),
  set: (v: string) => {
    p.value.client_type = v
  },
})
</script>

<template>
  <div class="params">
    <div class="f-title">▸ 关闭游戏参数</div>
    <div class="f-row">
      <label class="f-label">客户端版本<small>留空则跟随设备配置</small></label>
      <DropSelect v-model="clientTypeModel" :options="clientTypeOpts" placeholder="跟随设备" />
    </div>
  </div>
</template>
