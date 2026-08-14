<script setup lang="ts">
/** 自动战斗（抄作业）参数表单 —— 对齐 MAA 客户端 CopilotView。
 *  作业文件：任务内维护作业列表（作业集），勾选 = 启用执行，按勾选顺序执行；
 *  编队选项仅「自动编队」开启时显示（MAA 客户端 Form 联动），键名对齐引擎。 */
import { computed, onMounted, ref, watch } from 'vue'
import { useFormParams } from './useFormParams'
import DropSelect, { type DropOption } from './DropSelect.vue'
import NumberField from './NumberField.vue'
import SearchSelect, { type SearchOption } from './SearchSelect.vue'
import CopilotFilePicker from './CopilotFilePicker.vue'
import { copilotApi } from '@/api/copilot'
import { resourcesApi } from '@/api/resources'
import type { CopilotJob } from '@/tasks/taskTypes'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p } = useFormParams(props.params)

// ── 作业场景（对齐客户端 CopilotView 场景页签 → AsstTaskType 分发） ──
const copilotModeOpts = computed<DropOption[]>(() => [
  { value: '0', label: '0 普通/SS 作战' },
  { value: '2', label: '2 悖论模拟（ParadoxCopilot）' },
  { value: '3', label: '3 保全作战（SSSCopilot）' },
])
const copilotModeModel = computed({
  get: () => {
    const v = Number(p.value.copilot_mode ?? 0)
    return String(v === 1 ? 0 : v)  // 旧数据 1（SS 作战）归一为 0
  },
  set: (v: string) => {
    p.value.copilot_mode = Number(v)
  },
})
const copilotModeHint = computed(() => {
  const mode = Number(p.value.copilot_mode ?? 0)
  if (mode === 2) return '悖论模拟：使用标准作业格式，后端按 ParadoxCopilot 任务类型下发'
  if (mode === 3) return '保全作战：需 SSS 专用作业格式（Stage 关卡 + 部署循环），后端按 SSSCopilot 下发'
  return '普通/SS 由引擎按作业关卡自动识别导航'
})

// ── 旧数据键迁移（auto_squad → formation；追加干员字符串 → 结构化） ──
if (p.value.auto_squad !== undefined && p.value.formation === undefined) {
  p.value.formation = p.value.auto_squad
}
if (p.value.formation === undefined) p.value.formation = true

// 作业列表：兼容旧数据（只有 filename 的单作业任务 → 派生为列表一项）
if (!Array.isArray(p.value.jobs)) {
  p.value.jobs = p.value.filename
    ? [{
        filename: String(p.value.filename),
        stage_name: String(p.value.stage_name ?? ''),
        stage_display: String(p.value.stage_display ?? p.value.stage_name ?? ''),
        enabled: true,
      }]
    : []
}
const jobs = p.value.jobs as CopilotJob[]

function addJobs(list: CopilotJob[]) {
  for (const job of list) {
    if (!job?.filename) continue
    if (jobs.some((j) => j.filename === job.filename)) continue
    jobs.push({
      filename: job.filename,
      stage_name: job.stage_name ?? '',
      stage_display: job.stage_display || job.stage_name || '',
      enabled: true,
      is_raid: !!job.is_raid,
    })
  }
}

function removeJob(i: number) {
  jobs.splice(i, 1)
}

// 旧作业项缺失关卡名时，从后端本地作业列表补全
async function backfillStageNames() {
  if (!jobs.some((j) => !j.stage_display && j.filename)) return
  try {
    const list = await copilotApi.list()
    const map = new Map(list.map((f) => [f.filename, { s: f.stage_name, d: f.stage_display }]))
    for (const job of jobs) {
      if (job.stage_display) continue
      const hit = map.get(job.filename)
      if (!hit) continue
      job.stage_name = job.stage_name || hit.s
      job.stage_display = hit.d || hit.s
    }
  } catch {
    /* 后端不可用则保持现状 */
  }
}
onMounted(backfillStageNames)

// ── 追加干员（引擎要求 [{name, skill}]） ────────────────────
// UI：干员搜索下拉 + 技能下拉 + 「＋ 添加」+ 可删列表（对齐 MAA 客户端 DataGrid 追加干员）
function normalizeAdditional(raw: unknown): { name: string; skill: number }[] {
  if (Array.isArray(raw)) {
    const out: { name: string; skill: number }[] = []
    for (const x of raw) {
      if (typeof x === 'string' && x.trim()) out.push({ name: x.trim(), skill: 0 })
      else if (x && typeof x === 'object') {
        const o = x as Record<string, unknown>
        if (o.name) out.push({ name: String(o.name), skill: Number(o.skill) || 0 })
      }
    }
    return out
  }
  if (typeof raw === 'string') {
    return raw.split(/[,，]/).map((s) => s.trim()).filter(Boolean).map((name) => ({ name, skill: 0 }))
  }
  return []
}
const additionalList = ref(normalizeAdditional(p.value.add_user_additional))
p.value.add_user_additional = additionalList.value
watch(
  additionalList,
  () => {
    p.value.add_user_additional = additionalList.value
  },
  { deep: true },
)

// 干员数据源：引擎包 battle_data.json（模块级缓存，本地过滤搜索）
const operOptions = ref<SearchOption[]>([])
let operPromise: Promise<void> | null = null

function loadOperators() {
  if (!operPromise) {
    operPromise = resourcesApi
      .operators()
      .then((list) => {
        operOptions.value = list.map((o) => ({ id: o.id, name: o.name }))
      })
      .catch(() => {
        operPromise = null // 允许重试
      })
  }
  return operPromise
}
onMounted(loadOperators)

const uaOperId = ref('')
const uaSkill = ref(1)
// 干员技能只有 1/2/3（0 为引擎内部「不指定」，UI 不暴露）
const skillOpts = computed<DropOption[]>(() =>
  [1, 2, 3].map((i) => ({ value: String(i), label: `技能 ${i}` })),
)
const uaSkillModel = computed({
  get: () => String(uaSkill.value),
  set: (v: string) => {
    uaSkill.value = Number(v)
  },
})

function addOper() {
  const name = operOptions.value.find((o) => o.id === uaOperId.value)?.name
  if (!name) return
  additionalList.value.push({ name, skill: uaSkill.value })
  uaOperId.value = ''
}

function removeOper(i: number) {
  additionalList.value.splice(i, 1)
}

// ── 助战使用（对齐引擎 BattleFormationTask::SupportUnitUsage） ──
const supportOpts = computed<DropOption[]>(() => [
  { value: '0', label: '0 不借用助战' },
  { value: '1', label: '1 仅缺一人时补漏' },
  { value: '2', label: '2 补漏，或使用指定干员' },
  { value: '3', label: '3 补漏，或随机一个' },
])
const supportModel = computed({
  get: () => String(Number(p.value.support_unit_usage) || 0),
  set: (v: string) => {
    p.value.support_unit_usage = Number(v)
  },
})

// ── 使用编队（序号 1~4） ──────────────────────────────
const formationOpts = computed<DropOption[]>(() =>
  [1, 2, 3, 4].map((i) => ({ value: String(i), label: `编队 ${i}` })),
)
const formationModel = computed({
  get: () => String(Number(p.value.formation_index) || 1),
  set: (v: string) => {
    p.value.formation_index = Number(v)
  },
})
</script>

<template>
  <div class="params">
    <div class="f-title">▸ 自动战斗参数（作业）</div>

    <!-- 作业列表：勾选 = 启用执行，按列表顺序执行 -->
    <div class="f-row f-col">
      <label class="f-label">作业文件<small>勾选启用，按顺序执行；可从本地或 prts.plus 作业站导入</small></label>
      <div class="job-list">
        <div v-if="jobs.length === 0" class="job-empty">暂无作业，用下方搜索框或作业站导入添加</div>
        <label v-for="(job, i) in jobs" :key="job.filename + i" class="job-item">
          <input type="checkbox" v-model="job.enabled" title="启用该作业" />
          <span class="stage">{{ job.stage_display || job.stage_name || '—' }}</span>
          <span class="fn">{{ job.filename }}</span>
          <label class="raid" title="突袭难度标记（多作业导航用）">
            <input type="checkbox" v-model="job.is_raid" />突袭
          </label>
          <button type="button" class="job-del" title="移除" @click.prevent="removeJob(i)">✕</button>
        </label>
      </div>
      <CopilotFilePicker @import-jobs="addJobs" />
    </div>

    <div class="f-row">
      <label class="f-label">作业场景<small>{{ copilotModeHint }}</small></label>
      <DropSelect v-model="copilotModeModel" :options="copilotModeOpts" />
    </div>
    <div v-if="Number(p.copilot_mode) >= 2" class="f-tip warn">⚠ 悖论/保全作业需放入 resource/copilot/ 后从作业列表勾选（作业格式与场景匹配）</div>
    <div class="f-row" v-if="Number(p.copilot_mode) !== 2">
      <label class="f-label">循环次数<small>重复执行当前作业列表</small></label>
      <NumberField v-model="p.loop_times" :min="1" />
    </div>
    <div class="f-row" v-if="Number(p.copilot_mode) === 0">
      <label class="f-label">使用理智药<small>连战时自动补充理智（无数量限制，会持续服用直至打完）</small></label>
      <span class="f-switch" :class="{ on: p.use_sanity_potion }" @click="p.use_sanity_potion = !p.use_sanity_potion"></span>
    </div>

    <!-- 编队（仅普通/SS 场景显示；悖论/保全不共用，对齐客户端 CopilotTabIndex 联动） -->
    <template v-if="Number(p.copilot_mode) === 0">
    <div class="f-sec">编队</div>
    <div class="f-row">
      <label class="f-label">自动编队</label>
      <span class="f-switch" :class="{ on: p.formation }" @click="p.formation = !p.formation"></span>
    </div>
    <template v-if="p.formation">
      <div class="f-row">
        <label class="f-label">使用编队<small>从已保存编队中选择</small></label>
        <span class="f-switch" :class="{ on: p.use_formation }" @click="p.use_formation = !p.use_formation"></span>
        <DropSelect v-if="p.use_formation" v-model="formationModel" :options="formationOpts" />
      </div>
      <div class="f-row">
        <label class="f-label">忽略干员要求<small>跳过未满足的干员属性要求</small></label>
        <span class="f-switch" :class="{ on: p.ignore_requirements }" @click="p.ignore_requirements = !p.ignore_requirements"></span>
      </div>
      <div class="f-row">
        <label class="f-label">助战使用<small>编队缺员时自动借用助战干员</small></label>
        <DropSelect v-model="supportModel" :options="supportOpts" />
        <input
          v-if="Number(p.support_unit_usage) === 2"
          class="f-text"
          v-model="p.support_unit_name"
          placeholder="助战干员名"
        />
      </div>
      <div class="f-row">
        <label class="f-label">追加信任干员</label>
        <span class="f-switch" :class="{ on: p.add_trust }" @click="p.add_trust = !p.add_trust"></span>
      </div>
      <div class="f-row f-col">
        <label class="f-label">追加干员<small>搜索选择干员与技能后「＋ 添加」，可添加多个</small></label>
        <div class="add-line">
          <SearchSelect v-model="uaOperId" :options="operOptions" placeholder="搜索干员名…" empty-text="无匹配干员" />
          <DropSelect v-model="uaSkillModel" :options="skillOpts" />
          <button type="button" class="add-btn" :disabled="!uaOperId" @click="addOper">＋ 添加</button>
        </div>
        <div class="oper-list">
          <div v-if="additionalList.length === 0" class="oper-empty">尚未追加干员（可选）</div>
          <div v-for="(op, i) in additionalList" :key="i" class="oper-item">
            <span class="chk-d"></span>
            <span class="nm">{{ op.name }}</span>
            <span class="skill">技能 {{ op.skill || 1 }}</span>
            <button type="button" class="job-del" title="移除" @click="removeOper(i)">✕</button>
          </div>
        </div>
      </div>
    </template>
    </template>
  </div>
</template>

<style scoped>
.f-col { flex-direction: column; align-items: stretch; gap: 6px; }

.job-list {
  display: flex; flex-direction: column; gap: 4px;
  max-height: 200px; overflow-y: auto;
}
.job-empty { font-size: var(--font-size-xs); color: var(--color-text-tertiary); padding: 6px 0; }
.f-tip { font-size: var(--font-size-xs); color: var(--color-text-tertiary); padding: 2px 0 8px; }
.f-tip.warn { color: var(--color-brand, #d8b16a); }
.f-narrow { min-width: 90px !important; }
.f-textarea {
  width: 100%;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 6px 11px; font-size: var(--font-size-md); outline: none;
  font-family: inherit; resize: vertical;
}
.f-textarea:focus { border-color: var(--color-brand); }

/* ── 追加干员：搜索行 + 列表 ────────────── */
.add-line { display: flex; align-items: stretch; gap: 8px; }
.add-line .ss { flex: 1; min-width: 0; }
.add-btn {
  flex-shrink: 0;
  background: rgba(216, 177, 106, 0.14); color: var(--color-brand);
  border: 1px solid var(--color-brand-strong);
  padding: 0 14px; font-size: var(--font-size-sm); cursor: pointer;
  letter-spacing: 0.5px;
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.add-btn:hover:not(:disabled) { background: var(--color-bg-active); box-shadow: var(--shadow-glow-sm); }
.add-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.oper-list { display: flex; flex-direction: column; gap: 4px; }
.oper-empty { font-size: var(--font-size-xs); color: var(--color-text-tertiary); padding: 4px 0; }
.oper-item {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 10px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  font-size: var(--font-size-md);
}
.oper-item .chk-d {
  width: 13px; height: 13px; flex-shrink: 0;
  border: 1px solid var(--color-brand-strong);
  background: var(--color-brand);
  transform: rotate(45deg);
  display: flex; align-items: center; justify-content: center;
}
.oper-item .chk-d::after { content: "✓"; transform: rotate(-45deg); font-size: 8px; font-weight: 700; color: var(--color-text-inverse); }
.oper-item .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oper-item .skill {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  font-family: var(--font-family-mono); letter-spacing: 0.5px;
  border: 1px solid var(--color-border-default); padding: 1px 7px;
}
.oper-item .job-del {
  flex-shrink: 0;
  background: none; border: none; cursor: pointer;
  color: var(--color-text-tertiary); font-size: var(--font-size-md); padding: 0 2px;
}
.oper-item .job-del:hover { color: var(--color-danger); }

.job-item {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 8px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: border-color var(--motion-duration-fast) var(--motion-easing-standard);
}
.job-item:hover { border-color: var(--color-brand); }
.job-item:has(input:checked) { border-color: var(--color-brand-strong); }
.job-item input { accent-color: var(--color-brand); cursor: pointer; }
.job-item .stage { color: var(--color-text-primary); font-weight: 600; flex-shrink: 0; }
.job-item .fn {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--color-text-secondary); font-family: var(--font-family-mono);
}
.job-item .raid {
  display: inline-flex; align-items: center; gap: 2px;
  flex-shrink: 0; font-size: var(--font-size-2xs);
  color: var(--color-text-tertiary); cursor: pointer; user-select: none;
}
.job-item .raid input { accent-color: var(--color-brand); }
.job-item .job-del {
  flex-shrink: 0; border: none; background: transparent;
  color: var(--color-text-tertiary); cursor: pointer; font-size: var(--font-size-sm);
}
.job-item .job-del:hover { color: var(--color-danger); }
</style>
