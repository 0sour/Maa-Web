<script setup lang="ts">
/**
 * 开始唤醒参数表单 —— 对齐 MAA 客户端 StartUpTaskUserControl。
 * 客户端无高级区；切换账号需先勾选「切换账号」开关才下发 account_name。
 */
import { computed } from 'vue'
import { CLIENT_TYPES, CLIENT_TYPE_LABELS } from '../taskTypes'
import { useFormParams } from './useFormParams'
import DropSelect, { type DropOption } from './DropSelect.vue'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p } = useFormParams(props.params)

// 旧数据兼容：有 account_name 但无开关时视为开启
if (p.value.account_switch_enabled === undefined) {
  p.value.account_switch_enabled = !!p.value.account_name
}

// ── 客户端版本（留空跟随设备配置） ──
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
    <div class="f-title">▸ 开始唤醒参数</div>
    <div class="f-row">
      <label class="f-label">客户端版本<small>留空则跟随设备配置</small></label>
      <DropSelect v-model="clientTypeModel" :options="clientTypeOpts" placeholder="跟随设备" />
    </div>
    <div class="f-row">
      <label class="f-label">自动启动客户端</label>
      <span class="f-switch" :class="{ on: p.start_game_enabled }" @click="p.start_game_enabled = !p.start_game_enabled"></span>
    </div>
    <div class="f-row">
      <label class="f-label">切换账号</label>
      <span class="f-switch" :class="{ on: p.account_switch_enabled }" @click="p.account_switch_enabled = !p.account_switch_enabled"></span>
    </div>
    <div v-if="p.account_switch_enabled" class="f-row">
      <label class="f-label">账号名<small>已登录账号唯一片段，仅官服/B 服/渠道服生效</small></label>
      <input class="f-text" v-model="p.account_name" placeholder="如 123****4567" />
    </div>
  </div>
</template>
