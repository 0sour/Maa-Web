<script setup lang="ts">
/**
 * 公开招募参数表单 —— 对齐 MAA 客户端 RecruitSettingsUserControl。
 * 星级选择：3/4/5/6 星开关（3 星仅确认不点击，4-6 星点击+确认，对齐客户端 Serialize 派生规则）；
 * 招募时限：3/4 星可编辑（1:00~9:00，步长 10 分钟），5/6 星固定 9:00。
 * 高级区：更多 Tags 策略 / 3 星 Tag 倾向 / 刷新三星 Tags / 无许可也刷新 / 保留 Tag（均有启用开关）。
 */
import { computed, onMounted, ref } from 'vue'
import { SERVERS } from '../taskTypes'
import { useFormParams } from './useFormParams'
import DropSelect, { type DropOption } from './DropSelect.vue'
import MultiSelect, { type MultiOption } from './MultiSelect.vue'
import NumberField from './NumberField.vue'
import { resourcesApi } from '@/api/resources'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p } = useFormParams(props.params)

// ── 星级选择（对齐客户端 ChooseLevel3~6 → select/confirm 派生） ──
const LEVELS = [3, 4, 5, 6]

function confirmList(): number[] {
  return Array.isArray(p.value.confirm) ? (p.value.confirm as number[]).filter((n) => n >= 3 && n <= 6) : []
}
function selectList(): number[] {
  return Array.isArray(p.value.select) ? (p.value.select as number[]).filter((n) => n >= 4 && n <= 6) : []
}
function levelOn(lv: number): boolean {
  return confirmList().includes(lv)
}
function setLevel(lv: number, on: boolean) {
  const sel = new Set(selectList())
  const cf = new Set(confirmList())
  if (on) {
    cf.add(lv)
    if (lv >= 4) sel.add(lv) // 3 星仅确认，不点击（对齐客户端）
  } else {
    cf.delete(lv)
    sel.delete(lv)
  }
  p.value.select = [...sel].sort((a, b) => a - b)
  p.value.confirm = [...cf].sort((a, b) => a - b)
}

// 旧数据规范化：2 星等非法值剔除；已确认的 4/5/6 星补齐 select
function initLevels() {
  const cf = new Set(confirmList())
  const sel = new Set(selectList())
  for (const lv of [4, 5, 6]) if (cf.has(lv)) sel.add(lv)
  p.value.select = [...sel].sort((a, b) => a - b)
  p.value.confirm = [...cf].sort((a, b) => a - b)
}
initLevels()

// ── 招募时限（分钟，3/4 星可编辑，5/6 星固定 9:00=540） ──
function rtOf(lv: number): number {
  const o = p.value.recruitment_time
  if (o && typeof o === 'object') {
    const n = (o as Record<string, unknown>)[String(lv)]
    if (typeof n === 'number' && !Number.isNaN(n)) return n
  }
  return 540
}
function setRt(lv: number, minutes: number) {
  const o = { ...(p.value.recruitment_time as Record<string, number> | undefined) }
  o[String(lv)] = Math.min(9 * 60, Math.max(60, Math.round(minutes)))
  p.value.recruitment_time = o
}

const rtHour = ref<Record<number, number>>({})
const rtMin = ref<Record<number, number>>({})
function rtPart(lv: number) {
  rtHour.value[lv] = Math.floor(rtOf(lv) / 60)
  rtMin.value[lv] = (rtOf(lv) % 60) / 10 * 10
}
for (const lv of LEVELS) rtPart(lv)
function setRtHour(lv: number, h: number) {
  rtHour.value[lv] = h
  setRt(lv, h * 60 + rtMin.value[lv])
}
function setRtMin(lv: number, m: number) {
  rtMin.value[lv] = m
  setRt(lv, rtHour.value[lv] * 60 + m)
}

// ── 更多 Tags 策略（对齐 MAA 客户端 AutoRecruitSelectExtraTagsList） ──
const tagsModeOpts = computed<DropOption[]>(() => [
  { value: '0', label: '0 默认不选择额外 Tag' },
  { value: '1', label: '1 选择高星时总是选择三个 Tag' },
  { value: '2', label: '2 尽量多选高星 Tag' },
])
const tagsModeModel = computed({
  get: () => String(p.value.extra_tags_mode ?? 0),
  set: (v: string) => {
    p.value.extra_tags_mode = Number(v)
  },
})

// ── 服务器 ──────────────────────────────────────────────
const serverOpts = computed<DropOption[]>(() => SERVERS.map((s) => ({ value: s, label: s })))
const serverModel = computed({
  get: () => String(p.value.server ?? 'CN'),
  set: (v: string) => {
    p.value.server = v
  },
})

// ── 首选 / 保留 Tags（对齐 MAA 客户端 CheckComboBox 多选下拉） ──
// 数据源：引擎包 recruitment.json 的 tags（模块级缓存）
const tagOptions = ref<MultiOption[]>([])
let tagsPromise: Promise<void> | null = null

function loadTags() {
  if (!tagsPromise) {
    tagsPromise = resourcesApi
      .recruitTags()
      .then((list) => {
        tagOptions.value = list.map((t) => ({ value: t, label: t }))
      })
      .catch(() => {
        tagsPromise = null // 允许重试
      })
  }
  return tagsPromise
}
onMounted(loadTags)

function tagsOf(key: string): string[] {
  const v = p.value[key]
  return Array.isArray(v) ? (v as string[]).filter((t) => typeof t === 'string' && t.trim()) : []
}
const firstTags = computed({
  get: () => tagsOf('first_tags'),
  set: (v: string[]) => {
    p.value.first_tags = v
  },
})
const preserveTags = computed({
  get: () => tagsOf('preserve_tags'),
  set: (v: string[]) => {
    p.value.preserve_tags = v
  },
})
</script>

<template>
  <div class="params">
    <div class="f-title">▸ 公开招募参数</div>

    <div class="f-row">
      <label class="f-label">招募次数</label>
      <NumberField v-model="p.times" :min="0" />
    </div>
    <div class="f-row">
      <label class="f-label">使用加急许可<small>加急次数与招募次数一致</small></label>
      <span class="f-switch" :class="{ on: p.expedite }" @click="p.expedite = !p.expedite"></span>
    </div>

    <div class="f-sec">星级选择</div>
    <div class="f-tip">勾选 = 自动确认该星级干员（3 星仅确认不点击，4~6 星点击+确认）；3/4 星可设招募时长</div>
    <div v-for="lv in LEVELS" :key="lv" class="f-row">
      <label class="f-label">自动确认 {{ lv }} 星<small>{{ lv <= 4 ? '招募时长（时:分，1:00~9:00）' : '招募时长固定 9:00' }}</small></label>
      <span class="f-switch" :class="{ on: levelOn(lv) }" @click="setLevel(lv, !levelOn(lv))"></span>
      <template v-if="lv <= 4">
        <NumberField
          class="rt-time"
          :model-value="rtHour[lv]"
          :min="1" :max="9"
          @update:model-value="(h) => setRtHour(lv, h)"
        />
        <span class="rt-colon">:</span>
        <NumberField
          class="rt-time"
          :model-value="rtMin[lv]"
          :min="0" :max="50" :step="10"
          @update:model-value="(m) => setRtMin(lv, m)"
        />
      </template>
      <span v-else class="rt-fixed">9:00</span>
    </div>

    <div class="f-sec">高级设置</div>
    <div class="f-row">
      <label class="f-label">更多 Tags 策略<small>高星组合时额外 Tag 的选择方式（对齐 MAA 客户端）</small></label>
      <DropSelect v-model="tagsModeModel" :options="tagsModeOpts" />
    </div>
    <div class="f-row">
      <label class="f-label">3 星 Tag 倾向<small>倾向选择下方首选 Tags</small></label>
      <span class="f-switch" :class="{ on: p.prefer_tags_enabled }" @click="p.prefer_tags_enabled = !p.prefer_tags_enabled"></span>
    </div>
    <div v-if="p.prefer_tags_enabled" class="f-row">
      <label class="f-label">首选 Tags<small>3 星时优先勾选以下标签（多选）</small></label>
      <MultiSelect v-model="firstTags" :options="tagOptions" placeholder="首选 Tags" />
    </div>
    <div class="f-row">
      <label class="f-label">刷新三星 Tags<small>无倾向 Tag 时刷新 3 星</small></label>
      <span class="f-switch" :class="{ on: p.refresh }" @click="p.refresh = !p.refresh"></span>
    </div>
    <div class="f-row" :class="{ disabled: !p.refresh }">
      <label class="f-label">无许可也刷新<small>无招募许可时仍尝试刷新 Tags</small></label>
      <span class="f-switch" :class="{ on: p.force_refresh }" @click="p.refresh && (p.force_refresh = !p.force_refresh)"></span>
    </div>
    <div class="f-row">
      <label class="f-label">保留 Tag<small>识别到则跳过该槽位</small></label>
      <span class="f-switch" :class="{ on: p.preserve_tags_enabled }" @click="p.preserve_tags_enabled = !p.preserve_tags_enabled"></span>
    </div>
    <div v-if="p.preserve_tags_enabled" class="f-row">
      <label class="f-label">保留 Tags<small>识别到则跳过该槽位（多选）</small></label>
      <MultiSelect v-model="preserveTags" :options="tagOptions" placeholder="保留 Tags" />
    </div>

    <div class="f-sec">数据上报</div>
    <div class="f-row">
      <label class="f-label">服务器</label>
      <DropSelect v-model="serverModel" :options="serverOpts" />
    </div>
    <div class="f-row">
      <label class="f-label">汇报企鹅物流</label>
      <span class="f-switch" :class="{ on: p.report_to_penguin }" @click="p.report_to_penguin = !p.report_to_penguin"></span>
    </div>
    <div class="f-row" v-if="p.report_to_penguin">
      <label class="f-label">企鹅 ID</label>
      <input class="f-text" v-model="p.penguin_id" placeholder="123456" />
    </div>
    <div class="f-row">
      <label class="f-label">汇报一图流</label>
      <span class="f-switch" :class="{ on: p.report_to_yituliu }" @click="p.report_to_yituliu = !p.report_to_yituliu"></span>
    </div>
    <div class="f-row" v-if="p.report_to_yituliu">
      <label class="f-label">一图流 ID</label>
      <input class="f-text" v-model="p.yituliu_id" placeholder="123456" />
    </div>
  </div>
</template>

<style scoped>
.rt-time { width: 60px !important; }
.rt-time :deep(.nf-input) { width: 60px; }
.rt-colon { color: var(--color-text-tertiary); }
.rt-fixed { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.f-tip { font-size: var(--font-size-xs); color: var(--color-text-tertiary); line-height: 1.6; padding: 2px 0 6px; }
.f-row.disabled { opacity: 0.45; }
.f-row.disabled .f-label small { color: var(--color-text-tertiary); }
</style>
