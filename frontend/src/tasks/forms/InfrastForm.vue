<script setup lang="ts">
/**
 * 基建换班参数表单 —— 对齐 MAA 客户端 InfrastSettingsUserControl。
 * 基础区：换班模式 / 设施 / 无人机 / 工作心情阈值 / 自定义排班（10000）；
 * 高级区：制造站搓玉自动补货、宿舍两项（20000 轮换模式隐藏）、训练室连续专精、会客室三项。
 */
import { computed } from 'vue'
import { DRONE_USES, DRONE_USES_LABELS, INFRAST_FACILITIES } from '../taskTypes'
import { useFormParams } from './useFormParams'
import DropSelect, { type DropOption } from './DropSelect.vue'
import NumberField from './NumberField.vue'
import './field.css'

const props = defineProps<{ params: Record<string, unknown> }>()
const { p, toggle, has } = useFormParams(props.params)

const FACILITY_LABEL: Record<string, string> = {
  Mfg: '制造站', Trade: '贸易站', Control: '控制中枢', Power: '发电站',
  Reception: '会客室', Office: '办公室', Dorm: '宿舍', Processing: '加工站', Training: '训练室',
}

// ── 换班模式（对齐 MAA InfrastTask mode；自定义排班暂未开放） ──
const modeOpts = computed<DropOption[]>(() => [
  { value: '0', label: '0 默认换班' },
  { value: '10000', label: '10000 自定义排班（暂不可用）', disabled: true },
  { value: '20000', label: '20000 一键轮换' },
])
const modeModel = computed({
  get: () => String(p.value.mode ?? 0),
  set: (v: string) => {
    p.value.mode = Number(v)
  },
})

// ── 无人机用途（对齐 MAA UsesOfDrones ComboBox） ──────────
const droneOpts = computed<DropOption[]>(() =>
  DRONE_USES.map((d) => ({ value: d, label: DRONE_USES_LABELS[d] ?? d })),
)
const dronesModel = computed({
  get: () => String(p.value.drones ?? '_NotUse'),
  set: (v: string) => {
    p.value.drones = v
  },
})

// ── 菲亚梅塔恢复目标（v6.17 宿舍换班调整新增，对齐客户端 _fiammettaTargetEntries） ──
const FIAMMETTA_TARGETS = ['清流', '可露希尔', '但书', '巫恋', '龙舌兰', '歌蕾蒂娅']
if (!Array.isArray(p.value.fiammetta_targets) || !p.value.fiammetta_targets.length) {
  p.value.fiammetta_targets = ['清流', '可露希尔', '但书']
}
function setFiammettaTarget(i: number, op: string) {
  const list = Array.isArray(p.value.fiammetta_targets) ? [...p.value.fiammetta_targets] : []
  list[i] = op
  p.value.fiammetta_targets = list
}
</script>

<template>
  <div class="params">
    <div class="f-title">▸ 基建换班参数</div>
    <div class="f-row">
      <label class="f-label">换班模式<small>自定义排班（MAA 排班协议 JSON）暂未开放</small></label>
      <DropSelect v-model="modeModel" :options="modeOpts" />
    </div>
    <div class="f-row">
      <label class="f-label">换班设施<small>顺序即换班顺序；新号未解锁的设施（会客室/训练室等）会导致卡住，请只勾选已解锁的</small></label>
      <div class="f-checks">
        <span
          v-for="f in INFRAST_FACILITIES" :key="f" class="f-check"
          :class="{ on: has('facility', f) }"
          @click="toggle('facility', f)"
        >{{ FACILITY_LABEL[f] }}</span>
      </div>
    </div>
    <div class="f-row" :class="{ disabled: p.mode === 10000 }">
      <label class="f-label">无人机用途<small>自定义排班时不可用</small></label>
      <DropSelect v-model="dronesModel" :options="droneOpts" :disabled="p.mode === 10000" />
    </div>
    <div class="f-row" v-if="p.mode !== 20000">
      <label class="f-label">工作心情阈值<small>0 ~ 1.0</small></label>
      <NumberField v-model="p.threshold" :min="0" :max="1" :step="0.05" />
    </div>

    <div class="f-sec" v-if="p.mode === 10000">自定义排班</div>
    <div class="f-row" v-if="p.mode === 10000">
      <label class="f-label">配置文件路径</label>
      <input class="f-text" v-model="p.filename" placeholder="schedules/base.json" />
    </div>
    <div class="f-row" v-if="p.mode === 10000">
      <label class="f-label">方案序号<small>-1 按时间轮换，0~n 按索引轮换</small></label>
      <NumberField v-model="p.plan_index" :min="-1" />
    </div>

    <div class="f-sec">高级</div>
    <div class="f-row">
      <label class="f-label">制造站搓玉自动补货<small>源石碎片</small></label>
      <span class="f-switch" :class="{ on: p.replenish }" @click="p.replenish = !p.replenish"></span>
    </div>
    <div class="f-row" v-if="p.mode !== 20000">
      <label class="f-label">不将已进驻干员放入宿舍<small>换班时不在训练室/加工站等在岗干员中挑人，避免打扰其工作（代价：加工站干员不会进宿舍休息）</small></label>
      <span class="f-switch" :class="{ on: p.dorm_notstationed_enabled }" @click="p.dorm_notstationed_enabled = !p.dorm_notstationed_enabled"></span>
    </div>
    <div class="f-row" v-if="p.mode !== 20000">
      <label class="f-label">宿舍填入信赖未满干员</label>
      <span class="f-switch" :class="{ on: p.dorm_trust_enabled }" @click="p.dorm_trust_enabled = !p.dorm_trust_enabled"></span>
    </div>
    <div class="f-row" v-if="p.mode !== 20000">
      <label class="f-label">启用菲亚梅塔心情恢复<small>换班开始时将恢复目标与满心情菲亚梅塔放入宿舍互换心情，菲亚梅塔随后留在宿舍恢复（v6.17+）</small></label>
      <span class="f-switch" :class="{ on: p.fiammetta_recovery_enabled }" @click="p.fiammetta_recovery_enabled = !p.fiammetta_recovery_enabled"></span>
    </div>
    <template v-if="p.fiammetta_recovery_enabled && p.mode !== 20000">
      <div class="f-row" v-for="i in 3" :key="i">
        <label class="f-label">菲亚梅塔恢复目标 {{ i }}<small v-if="i === 1">不推荐巫恋/龙舌兰（007 难实现）</small></label>
        <select class="f-text" :value="String((p.fiammetta_targets as string[])?.[i - 1] ?? '清流')" @change="setFiammettaTarget(i - 1, ($event.target as HTMLSelectElement).value)">
          <option v-for="op in FIAMMETTA_TARGETS" :key="op" :value="op">{{ op }}</option>
        </select>
      </div>
    </template>
    <div class="f-row" v-if="p.mode === 0">
      <label class="f-label">使用红松骑士团跨设施组合<small>焰尾(精二)、薇薇安娜(精二)、野鬃/灰毫/远牙(精二)至少一个参与计算：砾</small></label>
      <span class="f-switch" :class="{ on: p.use_pinus_sylvestris }" @click="p.use_pinus_sylvestris = !p.use_pinus_sylvestris"></span>
    </div>
    <div class="f-row" v-if="p.mode === 0">
      <label class="f-label">使用感知信息跨设施组合<small>絮雨(精二)、迷迭香(精二)、黑键(精二)；优先度高于人间烟火</small></label>
      <span class="f-switch" :class="{ on: p.use_perception_information }" @click="p.use_perception_information = !p.use_perception_information"></span>
    </div>
    <div class="f-row" v-if="p.mode === 0">
      <label class="f-label">使用人间烟火跨设施组合<small>巫恋(精二)或龙舌兰(精二)</small></label>
      <span class="f-switch" :class="{ on: p.use_worldly_plight }" @click="p.use_worldly_plight = !p.use_worldly_plight"></span>
    </div>
    <div class="f-row" v-if="p.mode === 0">
      <label class="f-label">使用深海猎人跨设施组合<small>斯卡蒂(精二)、歌蕾蒂娅(精二)</small></label>
      <span class="f-switch" :class="{ on: p.use_abyssal_hunter }" @click="p.use_abyssal_hunter = !p.use_abyssal_hunter"></span>
    </div>
    <div class="f-row">
      <label class="f-label">训练室连续专精</label>
      <span class="f-switch" :class="{ on: p.continue_training }" @click="p.continue_training = !p.continue_training"></span>
    </div>
    <div class="f-row">
      <label class="f-label">会客室 · 领取信息板信用</label>
      <span class="f-switch" :class="{ on: p.reception_message_board }" @click="p.reception_message_board = !p.reception_message_board"></span>
    </div>
    <div class="f-row">
      <label class="f-label">会客室 · 线索交流</label>
      <span class="f-switch" :class="{ on: p.reception_clue_exchange }" @click="p.reception_clue_exchange = !p.reception_clue_exchange"></span>
    </div>
    <div class="f-row">
      <label class="f-label">会客室 · 赠送线索</label>
      <span class="f-switch" :class="{ on: p.reception_send_clue }" @click="p.reception_send_clue = !p.reception_send_clue"></span>
    </div>
  </div>
</template>

<style scoped>
.f-row.disabled { opacity: 0.45; }
</style>
