<script setup lang="ts">
/**
 * 刷理智参数表单 —— 对齐 MAA 客户端 FightSettingsUserControl。
 * 基础区：关卡 / 理智药 / 源石 / 次数 / 代理倍率 / 指定掉落（材料搜索下拉 + 数量）；
 * 高级区：碎石模式、过期理智药（需开关门控）、自定义剿灭。
 * server / client_type / 数据上报为任务级配置（客户端为全局注入，此处保留任务级）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { resourcesApi, type ResourceItem } from '@/api/resources'
import { ANNIHILATION_STAGES, CLIENT_TYPES, CLIENT_TYPE_LABELS, SERVERS } from '../taskTypes'
import { useFormParams } from './useFormParams'
import DropSelect, { type DropOption } from './DropSelect.vue'
import NumberField from './NumberField.vue'
import SearchSelect, { type SearchOption } from './SearchSelect.vue'
import StagePicker from './StagePicker.vue'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p } = useFormParams(props.params)

// 旧数据兼容：medicine_expire_days 非 0 时视为开启过期药
if (p.value.use_expiring_medicine === undefined) {
  p.value.use_expiring_medicine = Number(p.value.medicine_expire_days ?? 0) > 0
}

// ── 指定掉落：材料搜索下拉 + 数量（对齐 MAA 客户端 DropsItemId/DropsQuantity）──
// 引擎包 item_index.json 全量加载一次（模块级缓存），本地过滤搜索。
const itemOptions = ref<SearchOption[]>([])
const itemLoadErr = ref('')
let itemsPromise: Promise<ResourceItem[]> | null = null

function loadItems() {
  if (!itemsPromise) {
    itemsPromise = resourcesApi
      .items()
      .then((list) => {
        itemOptions.value = list.map((it) => ({ id: it.id, name: it.name }))
        return list
      })
      .catch((e: unknown) => {
        itemLoadErr.value = (e as { message?: string })?.message ?? '材料列表加载失败'
        itemsPromise = null // 允许重试
        return []
      })
  }
  return itemsPromise
}
onMounted(loadItems)

// drops: object {item_id: 数量}。UI 单对编辑（材料 + 数量）；
// 旧数据若含多对（老文本格式），取第一对回显。
const dropsItem = ref('')
const dropsCount = ref(0)

watch(
  () => p.value.drops,
  (v) => {
    if (v && typeof v === 'object') {
      const entries = Object.entries(v as Record<string, unknown>)
      const [id, n] = entries[0] ?? []
      if (id) {
        dropsItem.value = id
        dropsCount.value = Number(n) || 0
      }
    }
  },
  { immediate: true, deep: true },
)

watch([dropsItem, dropsCount], ([id, n]) => {
  if (id && n > 0) {
    p.value.drops = { [id]: n }
  } else {
    p.value.drops = undefined
  }
})

const dropsHint = computed(() =>
  dropsItem.value
    ? `累计掉落该材料 ${dropsCount.value || 0} 个即停止（按结算掉落统计，非仓库存量）`
    : '刷取指定材料达到累计掉落数即停止；留空 = 不使用此条件',
)

// ── 周计划（对齐 MAA 客户端 WeeklySchedule，客户端本地行为） ──
const WEEK_DAYS: Record<string, string> = {
  Mon: '周一', Tue: '周二', Wed: '周三', Thu: '周四', Fri: '周五', Sat: '周六', Sun: '周日',
}
function weeklySchedule(): Record<string, boolean> {
  const ws = p.value.weekly_schedule
  return ws && typeof ws === 'object' ? (ws as Record<string, boolean>) : {}
}
function weeklyOn(key: string): boolean {
  return weeklySchedule()[key] !== false
}
function toggleWeekly(key: string) {
  const ws = { ...weeklySchedule() }
  ws[key] = !weeklyOn(key)
  p.value.weekly_schedule = ws
}

// ── 碎石模式（DrGrandet）：两种模式动态说明 ────────────────
const drGrandetHint = computed(() =>
  p.value.DrGrandet
    ? '葛朗台模式：理智溢出时挂机等待自然恢复后再碎石，省源石但耗时长'
    : '理智不足时直接碎石，省时间但溢出部分浪费',
)

// ── 下拉选项（对齐 MAA 客户端 ComboBox 语义） ─────────────
const seriesOpts = computed<DropOption[]>(() => [
  { value: '-1', label: '-1 禁用切换' },
  { value: '0', label: '0 自动最大' },
  ...Array.from({ length: 10 }, (_, i) => ({ value: String(i + 1), label: `${i + 1} 倍` })),
])
const seriesModel = computed({
  get: () => String(p.value.series ?? 0),
  set: (v: string) => {
    p.value.series = Number(v)
  },
})
const serverOpts = computed<DropOption[]>(() => SERVERS.map((s) => ({ value: s, label: s })))
const clientTypeOpts = computed<DropOption[]>(() => [
  { value: '', label: '不启用' },
  ...CLIENT_TYPES.map((c) => ({ value: c, label: CLIENT_TYPE_LABELS[c] ?? c })),
])

// params 为 Record<string, unknown>，string 字段经 computed 转换后绑定
function strField(key: string, fallback = '') {
  return computed({
    get: () => String(p.value[key] ?? fallback),
    set: (v: string) => {
      p.value[key] = v
    },
  })
}
const annihilationStageModel = strField('annihilation_stage', 'Annihilation')
const serverModel = strField('server', 'CN')
const clientTypeModel = strField('client_type')
</script>

<template>
  <div class="params">
    <div class="f-title">▸ 刷理智参数</div>
    <div class="f-row">
      <label class="f-label">目标关卡<small>候选为常用/活动可导航关卡；可手动输入任意关卡名（如 4-10、AP-5、H10-1-Hard、SSReopen-XX），引擎不支持的会入队失败</small></label>
      <StagePicker v-model="p.stage" />
    </div>
    <div class="f-row">
      <label class="f-label">理智药<small>最大使用数量</small></label>
      <NumberField v-model="p.medicine" :min="0" :max="999" />
    </div>
    <div class="f-row">
      <label class="f-label">源石<small>最大吃石头数量</small></label>
      <NumberField v-model="p.stone" :min="0" :max="999" />
    </div>
    <div class="f-row">
      <label class="f-label">战斗次数<small>最大执行次数：-1 = 不限（刷到理智/掉落条件自然停止，对齐 MAA 默认）</small></label>
      <NumberField v-model="p.times" :min="-1" :max="999" :special-value="-1" special-label="不限" />
    </div>
    <div class="f-row">
      <label class="f-label">代理倍率</label>
      <DropSelect v-model="seriesModel" :options="seriesOpts" />
    </div>
    <div class="f-row">
      <label class="f-label">指定掉落<small>{{ dropsHint }}</small></label>
      <div class="drop-pick">
        <SearchSelect
          v-model="dropsItem"
          :options="itemOptions"
          placeholder="搜索材料名或 ID，如 固源岩"
          empty-text="无匹配材料"
        />
        <NumberField v-model="dropsCount" :min="1" :max="9999" :disabled="!dropsItem" />
      </div>
    </div>
    <div v-if="itemLoadErr" class="f-row"><small class="drop-err">⚠ {{ itemLoadErr }}</small></div>

    <div class="f-sec">高级</div>
    <div class="f-row">
      <label class="f-label">碎石模式<small>{{ drGrandetHint }}</small></label>
      <div class="f-checks">
        <span class="f-check" :class="{ on: !p.DrGrandet }" @click="p.DrGrandet = false">直接碎石</span>
        <span class="f-check" :class="{ on: !!p.DrGrandet }" @click="p.DrGrandet = true">等待恢复后碎石</span>
      </div>
    </div>
    <div class="f-row">
      <label class="f-label">使用过期理智药<small>临期药优先使用</small></label>
      <span class="f-switch" :class="{ on: p.use_expiring_medicine }" @click="p.use_expiring_medicine = !p.use_expiring_medicine"></span>
    </div>
    <div class="f-row" v-if="p.use_expiring_medicine">
      <label class="f-label">过期天数<small>使用 N 天内的临期药</small></label>
      <NumberField v-model="p.medicine_expire_days" :min="1" :max="7" />
    </div>
    <div class="f-row">
      <label class="f-label">游戏掉线自动重启<small>闪退/掉线自动重启客户端续刷（需设置客户端版本）</small></label>
      <span class="f-switch" :class="{ on: p.auto_restart_on_drop }" @click="p.auto_restart_on_drop = !p.auto_restart_on_drop"></span>
    </div>
    <div class="f-row f-col">
      <label class="f-label">周计划<small>当天未勾选则跳过该任务（对齐 MAA 客户端 WeeklySchedule）</small></label>
      <div class="f-checks">
        <span
          v-for="(label, key) in WEEK_DAYS" :key="key" class="f-check"
          :class="{ on: weeklyOn(key) }"
          @click="toggleWeekly(key)"
        >{{ label }}</span>
      </div>
    </div>
    <div class="f-row">
      <label class="f-label">库存目标模式<small>按仓库存量停止（需仓库识别数据，待 D-12/T-03 接入）</small></label>
      <span class="f-tip dim">暂未开放</span>
    </div>
    <div class="f-row">
      <label class="f-label">自定义剿灭</label>
      <span class="f-switch" :class="{ on: p.use_custom_annihilation }" @click="p.use_custom_annihilation = !p.use_custom_annihilation"></span>
    </div>
    <div class="f-row" v-if="p.use_custom_annihilation">
      <label class="f-label">剿灭关卡</label>
      <DropSelect v-model="annihilationStageModel" :options="ANNIHILATION_STAGES" />
    </div>

    <div class="f-sec">连接与上报</div>
    <div class="f-row">
      <label class="f-label">服务器<small>影响掉落识别与上报</small></label>
      <DropSelect v-model="serverModel" :options="serverOpts" />
    </div>
    <div class="f-row">
      <label class="f-label">客户端版本<small>崩溃后重启并继续刷，留空不启用</small></label>
      <DropSelect v-model="clientTypeModel" :options="clientTypeOpts" placeholder="不启用" />
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
