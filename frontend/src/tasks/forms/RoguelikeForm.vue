<script setup lang="ts">
/**
 * 肉鸽刷分参数表单 —— 对齐 MAA 客户端 RoguelikeSettingsUserControl。
 * 主题联动：难度上限 / 模式 / 开局分队（含主题×模式特例）/ 开局职业组 均随主题变化，
 * 数据对齐客户端 _squadDictionary / _commonSquads / GetMaxDifficultyForTheme / Update*List。
 * 模式枚举：0 刷分 / 1 刷源石锭 / 4 凹开局 / 5 刷坍缩范式(萨米) / 6 月度小队 /
 * 7 深入调查 / 20001 刷常乐节点(界园) / 30001 刷襁褓动物(黑流树海)；2、3 已从客户端移除。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useFormParams } from './useFormParams'
import DropSelect, { type DropOption } from './DropSelect.vue'
import NumberField from './NumberField.vue'
import SearchSelect, { type SearchOption } from './SearchSelect.vue'
import { resourcesApi } from '@/api/resources'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p, toggleObj, hasObj, tagRef } = useFormParams(props.params)
const startFoldartal = tagRef('start_foldartal_list')
const expectedParadigms = tagRef('expected_collapsal_paradigms')

// ── 主题（中文名，对齐客户端 RoguelikeTheme） ──
const THEME_LABELS: Record<string, string> = {
  Phantom: '傀影', Mizuki: '水月', Sami: '萨米', Sarkaz: '萨卡兹', JieGarden: '界园', BlackFlow: '黑流树海',
}
const themeOpts = computed<DropOption[]>(() =>
  Object.entries(THEME_LABELS).map(([value, label]) => ({ value, label })),
)

// ── 难度上限（客户端 GetMaxDifficultyForTheme） ──
const DIFF_MAX = 2147483647
const DIFF_LIMITS: Record<string, number> = { Phantom: 15, Mizuki: 18, Sami: 15, Sarkaz: 18, JieGarden: 18, BlackFlow: 15 }
const diffOptions = computed<DropOption[]>(() => {
  const limit = DIFF_LIMITS[String(p.value.theme)] ?? 18
  const list: DropOption[] = [
    { value: '-1', label: '-1 不切换' },
    { value: String(DIFF_MAX), label: `MAX 跟随游戏内（上限 ${limit}）` },
  ]
  for (let i = limit; i >= 0; i--) list.push({ value: String(i), label: i === 0 ? '0（最低）' : String(i) })
  return list
})

// ── 模式（按主题动态，客户端 UpdateRoguelikeModeList） ──
const BASE_MODES: [number, string][] = [
  [0, '0 刷分/奖励点数'], [1, '1 刷源石锭'], [4, '4 凹开局'], [6, '6 月度小队'], [7, '7 深入调查'],
]
// 黑流树海专属模式（客户端 RoguelikeStrategyBlackFlow*：刷等级/投资/襁褓动物）
const BLACKFLOW_MODES: [number, string][] = [
  [0, '0 刷等级，快速飞三层'], [1, '1 刷源石锭，投资完退出'], [30001, '30001 刷襁褓动物'],
]
const THEME_MODES: Record<string, [number, string][]> = {
  Sami: [...BASE_MODES, [5, '5 刷坍缩范式']],
  JieGarden: [...BASE_MODES, [20001, '20001 刷常乐节点']],
  BlackFlow: BLACKFLOW_MODES,
}
const currentModes = computed<DropOption[]>(() =>
  (THEME_MODES[String(p.value.theme)] ?? BASE_MODES).map(([value, label]) => ({ value: String(value), label })),
)

// ── 开局分队（客户端 _squadDictionary + _commonSquads；主题×模式特例 Sarkaz_1） ──
const THEME_SQUADS: Record<string, string[]> = {
  Phantom_Default: ['集群分队', '矛头分队', '研究分队'],
  Mizuki_Default: ['集群分队', '矛头分队', '心胜于物分队', '物尽其用分队', '以人为本分队', '研究分队'],
  Sami_Default: ['集群分队', '矛头分队', '永恒狩猎分队', '生活至上分队', '科学主义分队', '特训分队'],
  Sarkaz_1: ['集群分队', '矛头分队', '博闻广记分队', '蓝图测绘分队', '点刺成锭分队', '拟态学者分队'],
  Sarkaz_Default: [
    '集群分队', '矛头分队', '魂灵护送分队', '博闻广记分队', '蓝图测绘分队',
    '因地制宜分队', '异想天开分队', '点刺成锭分队', '拟态学者分队', '专业人士分队',
  ],
  JieGarden_Default: [
    '特勤分队', '高台突破分队', '地面突破分队', '游客分队', '司岁台分队', '天师府分队',
    '花团锦簇分队', '棋行险着分队', '岁影回音分队', '代理人分队', '知学分队', '商贾分队',
  ],
  BlackFlow_Default: [
    '特勤分队', '矛头分队', '高台突破分队', '地面突破分队',
    '本源研修分队', '文明开化分队', '开拓者分队', '多边贸易分队', '地质调查分队',
  ],
}
// 通用分队（客户端 _commonSquads）；高规格分队仅下列主题可选（客户端显式排除 BlackFlow）
const COMMON_SQUADS = [
  '指挥分队', '后勤分队', '突击战术分队', '堡垒战术分队', '远程战术分队', '破坏战术分队',
]
const COMMON_SQUADS_HIGH_SPEC_THEMES = ['Phantom', 'Mizuki', 'Sami', 'Sarkaz', 'JieGarden']
const squadOptions = computed<DropOption[]>(() => {
  const theme = String(p.value.theme)
  const mode = Number(p.value.mode)
  const key = `${theme}_${mode}`
  const themeSquads = THEME_SQUADS[key] ?? THEME_SQUADS[`${theme}_Default`] ?? []
  const common = COMMON_SQUADS_HIGH_SPEC_THEMES.includes(theme)
    ? [...COMMON_SQUADS, '高规格分队']
    : COMMON_SQUADS
  return [...themeSquads, ...common].map((label) => ({ value: label, label }))
})

// ── 开局职业组（客户端 UpdateRoguelikeRolesList；界园/黑流树海多两项） ──
// 职业构成来自游戏内「选择招募组合」（prts.wiki），随主题版本可能略有差异
const THEME_ROLES: Record<string, DropOption[]> = {
  JieGarden: [
    { value: '先手必胜', label: '先手必胜', desc: '先锋·狙击·特种' },
    { value: '稳扎稳打', label: '稳扎稳打', desc: '重装·狙击·术师' },
    { value: '取长补短', label: '取长补短', desc: '近卫·医疗·辅助' },
    { value: '灵活部署', label: '灵活部署', desc: '先锋·辅助·特种' },
    { value: '坚不可摧', label: '坚不可摧', desc: '重装·术师·医疗' },
    { value: '随心所欲', label: '随心所欲', desc: '随机组合' },
  ],
  BlackFlow: [
    { value: '先手必胜', label: '先手必胜', desc: '先锋·狙击·特种' },
    { value: '稳扎稳打', label: '稳扎稳打', desc: '重装·狙击·术师' },
    { value: '取长补短', label: '取长补短', desc: '近卫·医疗·辅助' },
    { value: '灵活部署', label: '灵活部署', desc: '先锋·辅助·特种' },
    { value: '坚不可摧', label: '坚不可摧', desc: '重装·术师·医疗' },
    { value: '随心所欲', label: '随心所欲', desc: '随机组合' },
  ],
}
const BASE_ROLES: DropOption[] = [
  { value: '先手必胜', label: '先手必胜', desc: '先锋·狙击·特种' },
  { value: '稳扎稳打', label: '稳扎稳打', desc: '重装·狙击·术师' },
  { value: '取长补短', label: '取长补短', desc: '近卫·医疗·辅助' },
  { value: '随心所欲', label: '随心所欲', desc: '随机组合' },
]
const rolesOptions = computed<DropOption[]>(() => THEME_ROLES[String(p.value.theme)] ?? BASE_ROLES)

// ── 黑流树海目标襁褓动物（客户端 RoguelikeBlackFlowCultivationTargetList） ──
// 引擎值对齐客户端序列化：blackflow_cultivation_target（swaddled_xxx 四种）
const CULTIVATION_TARGETS: { value: string; label: string }[] = [
  { value: 'swaddled_cat', label: '襁褓中的猫' },
  { value: 'swaddled_feathered_serpent', label: '襁褓羽蛇' },
  { value: 'swaddled_dog', label: '襁褓中的狗' },
  { value: 'swaddled_cerberus', label: '襁褓三头犬' },
]
const cultivationTargetModel = computed({
  get: () => String(p.value.blackflow_cultivation_target ?? 'swaddled_cat'),
  set: (v: string) => {
    p.value.blackflow_cultivation_target = v
  },
})

// ── 联动归一（客户端切主题/模式后校验当前值，失效回落默认） ──
function inList(list: DropOption[], v: unknown): boolean {
  return list.some((o) => o.value === String(v))
}
watch(
  () => p.value.theme,
  () => {
    if (!inList(currentModes.value, p.value.mode)) p.value.mode = 0
    if (!inList(diffOptions.value, p.value.difficulty)) p.value.difficulty = -1
    if (!inList(squadOptions.value, p.value.squad)) p.value.squad = '指挥分队'
    if (!inList(rolesOptions.value, p.value.roles)) p.value.roles = '稳扎稳打'
  },
)
watch(
  () => p.value.mode,
  () => {
    if (!inList(squadOptions.value, p.value.squad)) p.value.squad = '指挥分队'
  },
)

// v-model 转换（number 字段）
function numModel(key: string, fallback = 0) {
  return computed({
    get: () => String(Number(p.value[key]) || fallback),
    set: (v: string) => {
      p.value[key] = Number(v)
    },
  })
}
const difficultyModel = numModel('difficulty', -1)
const modeModel = numModel('mode')
const findPlaytimeModel = numModel('find_playTime_target', 1)

// v-model 转换（string 字段）
function strModel(key: string, fallback = '') {
  return computed({
    get: () => String(p.value[key] ?? fallback),
    set: (v: string) => {
      p.value[key] = v
    },
  })
}
const squadModel = strModel('squad', '指挥分队')
const rolesModel = strModel('roles', '稳扎稳打')
const collectibleSquadModel = strModel('collectible_mode_squad')
const themeModel = strModel('theme', 'JieGarden')
const coreCharModel = strModel('core_char')

// ── 开局干员（可搜索下拉，随主题联动，对齐客户端 UpdateRoguelikeCoreCharList） ──
// 数据源：resource/roguelike/{主题}/recruitment.json 中 is_start=true 的干员
const coreOptions = ref<SearchOption[]>([])
let corePromise: Promise<void> | null = null

async function loadCoreChars() {
  const theme = String(p.value.theme)
  corePromise = resourcesApi
    .roguelikeCoreChars(theme)
    .then((list) => {
      coreOptions.value = list.map((n) => ({ id: n, name: n }))
    })
    .catch(() => {
      corePromise = null // 允许重试
    })
  return corePromise
}
onMounted(loadCoreChars)
watch(
  () => p.value.theme,
  () => {
    coreOptions.value = []
    corePromise = null
    loadCoreChars()
  },
)
// 清空开局干员时自动关闭助战开局（助战依赖指定核心干员）
watch(
  () => p.value.core_char,
  (v) => {
    if (!v && p.value.use_support) p.value.use_support = false
  },
)

// ── 种子（引擎键为字符串；旧数据布尔 → 重置） ──
if (typeof p.value.start_with_seed !== 'string') p.value.start_with_seed = ''
if (p.value.start_with_seed_enabled === undefined) p.value.start_with_seed_enabled = false

const START_LIST: [string, string][] = [
  ['hot_water', '热水壶'], ['shield', '护盾'], ['ingot', '源石锭'], ['hope', '希望'],
  ['random', '随机收藏品'], ['key', '钥匙'], ['dice', '骰子'], ['ideas', '构想'], ['ticket', '票券'],
]
</script>

<template>
  <div class="params">
    <div class="f-title">▸ 肉鸽刷分参数</div>
    <div class="f-row">
      <label class="f-label">主题<small>切换后难度/模式/分队/职业组联动</small></label>
      <DropSelect v-model="themeModel" :options="themeOpts" />
    </div>
    <div class="f-row">
      <label class="f-label">难度<small>跟随所选主题上限</small></label>
      <DropSelect v-model="difficultyModel" :options="diffOptions" />
    </div>
    <div class="f-row">
      <label class="f-label">模式<small>部分模式仅特定主题可用</small></label>
      <DropSelect v-model="modeModel" :options="currentModes" />
    </div>
    <div class="f-row">
      <label class="f-label">开局分队</label>
      <DropSelect v-model="squadModel" :options="squadOptions" placeholder="指挥分队" />
    </div>
    <div class="f-row">
      <label class="f-label">开局职业组</label>
      <DropSelect v-model="rolesModel" :options="rolesOptions" placeholder="稳扎稳打" />
    </div>
    <div class="f-row" v-if="p.mode === 4">
      <label class="f-label">刷开局使用分队<small>留空跟随开局分队</small></label>
      <DropSelect v-model="collectibleSquadModel" :options="squadOptions" placeholder="跟随开局分队" />
    </div>
    <div class="f-row">
      <label class="f-label">开局干员<small>该主题开局可选干员，留空自动选择</small></label>
      <SearchSelect v-model="coreCharModel" :options="coreOptions" placeholder="搜索该主题开局干员…" empty-text="无匹配干员" />
    </div>
    <div class="f-row" v-if="Number(p.mode) === 20001 && p.theme === 'JieGarden'">
      <label class="f-label">常乐目标节点</label>
      <DropSelect v-model="findPlaytimeModel" :options="[
        { value: '1', label: '1 令' },
        { value: '2', label: '2 黍' },
        { value: '3', label: '3 年' },
      ]" />
    </div>
    <div class="f-row" v-if="Number(p.mode) === 30001 && p.theme === 'BlackFlow'">
      <label class="f-label">目标襁褓动物<small>黑流树海刷襁褓动物模式</small></label>
      <DropSelect v-model="cultivationTargetModel" :options="CULTIVATION_TARGETS.map((t) => ({ value: t.value, label: t.label }))" />
    </div>

    <div class="f-sec">高级</div>
    <div class="f-row">
      <label class="f-label">开始探索次数<small>达到自动停止</small></label>
      <NumberField v-model="p.starts_count" :min="0" />
    </div>

    <div class="f-row">
      <label class="f-label">投资源石锭</label>
      <span class="f-switch" :class="{ on: p.investment_enabled }" @click="p.mode !== 1 && (p.investment_enabled = !p.investment_enabled)"></span>
    </div>
    <div v-if="p.mode === 1" class="f-tip warn">⚠ 刷源石锭模式强制开启投资</div>
    <template v-if="p.mode === 1">
      <div class="f-row">
        <label class="f-label">投资次数<small>达到自动停止</small></label>
        <NumberField v-model="p.investments_count" :min="0" />
      </div>
      <div class="f-row">
        <label class="f-label">投资满自动停止</label>
        <span class="f-switch" :class="{ on: p.stop_when_investment_full }" @click="p.stop_when_investment_full = !p.stop_when_investment_full"></span>
      </div>
      <div class="f-row">
        <label class="f-label">投资后购物<small>刷更多分</small></label>
        <span class="f-switch" :class="{ on: p.investment_with_more_score }" @click="p.investment_with_more_score = !p.investment_with_more_score"></span>
      </div>
    </template>
    <div class="f-row" v-if="p.mode === 4">
      <label class="f-label">刷开局模式启用购物</label>
      <span class="f-switch" :class="{ on: p.collectible_mode_shopping }" @click="p.collectible_mode_shopping = !p.collectible_mode_shopping"></span>
    </div>

    <template v-if="p.mode === 4 && (p.theme === 'Mizuki' || p.theme === 'Sami')">
      <div class="f-row">
        <label class="f-label">凹干员精二直升</label>
        <span class="f-switch" :class="{ on: p.start_with_elite_two }" @click="p.start_with_elite_two = !p.start_with_elite_two"></span>
      </div>
      <div class="f-row" v-if="p.start_with_elite_two">
        <label class="f-label">只凹精二直升<small>不打关</small></label>
        <span class="f-switch" :class="{ on: p.only_start_with_elite_two }" @click="p.only_start_with_elite_two = !p.only_start_with_elite_two"></span>
      </div>
      <div class="f-row" v-if="!p.only_start_with_elite_two">
        <label class="f-label">刷开局期望奖励</label>
        <div class="f-checks">
          <span
            v-for="[k, label] in START_LIST" :key="k" class="f-check"
            :class="{ on: hasObj('collectible_mode_start_list', k) }"
            @click="toggleObj('collectible_mode_start_list', k)"
          >{{ label }}</span>
        </div>
      </div>
    </template>

    <template v-if="p.mode === 4 && p.theme === 'Sami'">
      <div class="f-row">
        <label class="f-label">第一层密文板<small>板子名</small></label>
        <input class="f-text" v-model="p.first_floor_foldartal" />
      </div>
      <div class="f-row">
        <label class="f-label">开局密文板列表<small>生活至上分队专用，逗号分隔，最多 3 个</small></label>
        <input class="f-text" v-model="startFoldartal" />
      </div>
    </template>
    <div class="f-row" v-if="p.mode === 5 && p.theme === 'Sami'">
      <label class="f-label">期望坍缩范式<small>逗号分隔</small></label>
      <input class="f-text" v-model="expectedParadigms" />
    </div>

    <div class="f-row" :class="{ disabled: !coreCharModel }">
      <label class="f-label">助战干员开局<small v-if="!coreCharModel">先选择开局干员后才可启用</small></label>
      <span class="f-switch" :class="{ on: p.use_support }" @click="coreCharModel && (p.use_support = !p.use_support)"></span>
    </div>
    <div class="f-row" v-if="p.use_support">
      <label class="f-label">可非好友助战</label>
      <span class="f-switch" :class="{ on: p.use_nonfriend_support }" @click="p.use_nonfriend_support = !p.use_nonfriend_support"></span>
    </div>

    <div class="f-row" v-if="p.mode === 0 && p.theme !== 'Phantom'">
      <label class="f-label">第 5 层险路恶敌前停止</label>
      <span class="f-switch" :class="{ on: p.stop_at_final_boss }" @click="p.stop_at_final_boss = !p.stop_at_final_boss"></span>
    </div>
    <div class="f-row" v-if="p.mode === 0">
      <label class="f-label">肉鸽等级刷满后停止</label>
      <span class="f-switch" :class="{ on: p.stop_at_max_level }" @click="p.stop_at_max_level = !p.stop_at_max_level"></span>
    </div>

    <template v-if="p.mode === 6">
      <div class="f-row">
        <label class="f-label">月度小队自动切换</label>
        <span class="f-switch" :class="{ on: p.monthly_squad_auto_iterate }" @click="p.monthly_squad_auto_iterate = !p.monthly_squad_auto_iterate"></span>
      </div>
      <div class="f-row" v-if="p.monthly_squad_auto_iterate">
        <label class="f-label">小队通信作为切换依据</label>
        <span class="f-switch" :class="{ on: p.monthly_squad_check_comms }" @click="p.monthly_squad_check_comms = !p.monthly_squad_check_comms"></span>
      </div>
    </template>
    <div class="f-row" v-if="p.mode === 7">
      <label class="f-label">深入调查自动切换</label>
      <span class="f-switch" :class="{ on: p.deep_exploration_auto_iterate }" @click="p.deep_exploration_auto_iterate = !p.deep_exploration_auto_iterate"></span>
    </div>
    <div class="f-row" v-if="p.theme === 'Mizuki'">
      <label class="f-label">用骰子刷新商店<small>指路鳞</small></label>
      <span class="f-switch" :class="{ on: p.refresh_trader_with_dice }" @click="p.refresh_trader_with_dice = !p.refresh_trader_with_dice"></span>
    </div>
    <div class="f-row" v-if="p.theme === 'JieGarden'">
      <label class="f-label">使用种子刷钱</label>
      <span class="f-switch" :class="{ on: p.start_with_seed_enabled }" @click="p.start_with_seed_enabled = !p.start_with_seed_enabled"></span>
    </div>
    <div class="f-row" v-if="p.theme === 'JieGarden' && p.start_with_seed_enabled">
      <label class="f-label">种子内容<small>格式：种子,rogue_主题,难度</small></label>
      <input class="f-text" v-model="p.start_with_seed" placeholder="abc,rogue_6,3" />
    </div>
  </div>
</template>

<style scoped>
.f-tip { font-size: var(--font-size-xs); color: var(--color-text-tertiary); padding: 2px 0 8px; }
.f-tip.warn { color: var(--color-brand, #d8b16a); }
</style>
