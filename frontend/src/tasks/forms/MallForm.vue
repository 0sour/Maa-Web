<script setup lang="ts">
/**
 * 信用购物参数表单 —— 对齐 MAA 客户端 MallSettingsUserControl。
 * 基础区：访问好友基建（一日只执行一次）/ 购物 / 借助战打 OF-1 赚信用（一日只执行一次，编队栏位 0-4）；
 * 高级区：优先购买、黑名单等 5 项，需「购物」开启才可用；列表用分号分隔。
 */
import { computed, ref, watch } from 'vue'
import { useFormParams } from './useFormParams'
import DropSelect, { type DropOption } from './DropSelect.vue'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p } = useFormParams(props.params)

// ── 编队栏位（0 当前编队，1-4 编队栏，离散值用下拉） ──────
const formationOpts = computed<DropOption[]>(() => [
  { value: '0', label: '0 当前编队' },
  { value: '1', label: '1 编队栏' },
  { value: '2', label: '2 编队栏' },
  { value: '3', label: '3 编队栏' },
  { value: '4', label: '4 编队栏' },
])
const formationModel = computed({
  get: () => String(Number(p.value.formation_index) || 0),
  set: (v: string) => {
    p.value.formation_index = Number(v)
  },
})

// 分号分隔列表（客户端 buy_first/blacklist 用 ; 分隔）
function semiRef(key: string) {
  const text = ref(Array.isArray(p.value[key]) ? (p.value[key] as string[]).join('; ') : '')
  watch(text, (t) => {
    p.value[key] = t
      .split(/[;；]/)
      .map((s) => s.trim())
      .filter(Boolean)
  })
  watch(
    () => p.value[key],
    (v) => {
      const next = Array.isArray(v) ? (v as string[]).join('; ') : ''
      if (text.value !== next) text.value = next
    },
    { deep: true },
  )
  return text
}
const buyFirst = semiRef('buy_first')
const blacklist = semiRef('blacklist')
</script>

<template>
  <div class="params">
    <div class="f-title">▸ 信用购物参数</div>
    <div class="f-row">
      <label class="f-label">访问好友<small>获取信用</small></label>
      <span class="f-switch" :class="{ on: p.visit_friends }" @click="p.visit_friends = !p.visit_friends"></span>
    </div>
    <div class="f-sub-row" v-if="p.visit_friends">
      <label class="f-label">一日只执行一次<small>当天已访问过则跳过</small></label>
      <span class="f-switch" :class="{ on: p.visit_friends_once_a_day }" @click="p.visit_friends_once_a_day = !p.visit_friends_once_a_day"></span>
    </div>
    <div class="f-row">
      <label class="f-label">购物</label>
      <span class="f-switch" :class="{ on: p.shopping }" @click="p.shopping = !p.shopping"></span>
    </div>
    <div class="f-row">
      <label class="f-label">借助战打 OF-1 赚信用<small>次日获得更多信用</small></label>
      <span class="f-switch" :class="{ on: p.credit_fight }" @click="p.credit_fight = !p.credit_fight"></span>
    </div>
    <div class="f-sub-row" v-if="p.credit_fight">
      <label class="f-label">一日只执行一次<small>当天已打过则跳过（默认开启）</small></label>
      <span class="f-switch" :class="{ on: p.credit_fight_once_a_day }" @click="p.credit_fight_once_a_day = !p.credit_fight_once_a_day"></span>
    </div>
    <div class="f-row" v-if="p.credit_fight">
      <label class="f-label">编队栏位<small>借助战打 OF-1 使用的编队</small></label>
      <DropSelect v-model="formationModel" :options="formationOpts" />
    </div>

    <div class="f-sec">高级</div>
    <div class="f-row" :class="{ disabled: !p.shopping }">
      <label class="f-label">优先购买<small>商品名，分号分隔</small></label>
      <input class="f-text" v-model="buyFirst" :disabled="!p.shopping" placeholder="招聘许可; 龙门币" />
    </div>
    <div class="f-row" :class="{ disabled: !p.shopping }">
      <label class="f-label">购物黑名单<small>商品名，分号分隔</small></label>
      <input class="f-text" v-model="blacklist" :disabled="!p.shopping" placeholder="加急许可; 家具零件" />
    </div>
    <div class="f-row" :class="{ disabled: !p.shopping }">
      <label class="f-label">信用溢出时无视黑名单</label>
      <span class="f-switch" :class="{ on: p.shopping && p.force_shopping_if_credit_full }" @click="p.shopping && (p.force_shopping_if_credit_full = !p.force_shopping_if_credit_full)"></span>
    </div>
    <div class="f-row" :class="{ disabled: !p.shopping }">
      <label class="f-label">只买折扣物品<small>仅第二轮购买</small></label>
      <span class="f-switch" :class="{ on: p.shopping && p.only_buy_discount }" @click="p.shopping && (p.only_buy_discount = !p.only_buy_discount)"></span>
    </div>
    <div class="f-row" :class="{ disabled: !p.shopping }">
      <label class="f-label">信用低于 300 停止购买<small>仅第二轮购买</small></label>
      <span class="f-switch" :class="{ on: p.shopping && p.reserve_max_credit }" @click="p.shopping && (p.reserve_max_credit = !p.reserve_max_credit)"></span>
    </div>
  </div>
</template>

<style scoped>
.f-row.disabled { opacity: 0.45; }
.f-row.disabled input { cursor: not-allowed; }
/* 子开关（对齐客户端缩进树形结构）：一日只执行一次 */
.f-sub-row {
  display: flex; align-items: center; gap: 10px;
  padding-left: 26px;
  border-left: 1px dashed var(--color-border-default);
  margin-left: 13px;
}
.f-sub-row .f-label { font-size: var(--font-size-sm); }
</style>
