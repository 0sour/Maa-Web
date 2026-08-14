<script setup lang="ts">
import { useFormParams } from './useFormParams'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p } = useFormParams(props.params)
</script>

<template>
  <div class="params">
    <div class="f-title">▸ 领取奖励参数</div>
    <div class="f-row">
      <label class="f-label">每日/每周任务奖励</label>
      <span class="f-switch" :class="{ on: p.award }" @click="p.award = !p.award"></span>
    </div>
    <div class="f-row">
      <label class="f-label">邮件奖励</label>
      <span class="f-switch" :class="{ on: p.mail }" @click="p.mail = !p.mail"></span>
    </div>
    <div class="f-row">
      <label class="f-label">免费单抽<small>限定池每日赠送</small></label>
      <span class="f-switch" :class="{ on: p.recruit }" @click="p.recruit = !p.recruit"></span>
    </div>
    <div class="f-row">
      <label class="f-label">合成玉奖励<small>幸运墙</small></label>
      <span class="f-switch" :class="{ on: p.orundum }" @click="p.orundum = !p.orundum"></span>
    </div>
    <div class="f-row">
      <label class="f-label">合成玉奖励<small>限时开采许可</small></label>
      <span class="f-switch" :class="{ on: p.mining }" @click="p.mining = !p.mining"></span>
    </div>
    <div class="f-row">
      <label class="f-label">月卡奖励<small>周年赠送</small></label>
      <span class="f-switch" :class="{ on: p.specialaccess }" @click="p.specialaccess = !p.specialaccess"></span>
    </div>
  </div>
</template>
