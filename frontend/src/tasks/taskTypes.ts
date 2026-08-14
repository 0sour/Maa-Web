/**
 * 共享任务类型注册表与序列化（作战总览 / 任务编排 两页复用，保持一致）。
 *
 * entry 即 MAA AsstAppendTask 类型，params 为该任务的**独立参数**（表单直接编辑），
 * 字段与默认值以 MAA 官方集成文档为准（docs.maa.plus/protocol/integration.html），
 * 后端 asstproxy.to_asst_task() 补齐必填字段（如 StartUp 的 client_type 取设备配置）。
 */
import type { TaskItemPayload } from '@/api/tasks'

export interface TaskTypeDef {
  type: string
  entry: string
  label: string
  params: Record<string, unknown>
}

/** 客户端版本选项（StartUp/CloseDown/Fight 崩溃重启共用） */
export const CLIENT_TYPES = ['Official', 'Bilibili', 'txwy', 'YoStarEN', 'YoStarJP', 'YoStarKR']
/** 自动战斗作业列表项：一个 Copilot 任务可承载多个作业（作业集），勾选 = 启用执行 */
export interface CopilotJob {
  filename: string
  stage_name: string  // 内部 stageId（执行用）
  stage_display: string  // 用户可读关卡名（展示用，如 TO-EX-1）
  enabled: boolean
  is_raid?: boolean  // 突袭难度（多作业导航标记）
}
/** 客户端版本中文标签（与 MAA 客户端一致） */
export const CLIENT_TYPE_LABELS: Record<string, string> = {
  Official: '官服',
  Bilibili: 'B 服',
  txwy: '渠道服',
  YoStarEN: '国际服',
  YoStarJP: '日服',
  YoStarKR: '韩服',
}
/** 服务器选项（掉落识别与上传） */
export const SERVERS = ['CN', 'US', 'JP', 'KR']
/** 基建设施（有序，顺序即换班顺序，对齐 MAA 客户端 InfrastRoomType 枚举） */
export const INFRAST_FACILITIES = [
  'Mfg', 'Trade', 'Control', 'Power', 'Reception', 'Office', 'Dorm', 'Processing', 'Training',
]
/** 无人机用途 */
export const DRONE_USES = ['_NotUse', 'Money', 'SyntheticJade', 'CombatRecord', 'PureGold', 'OriginStone', 'Chip']
/** 无人机用途中文标签（与 MAA 客户端一致） */
export const DRONE_USES_LABELS: Record<string, string> = {
  _NotUse: '不使用无人机',
  Money: '贸易站-龙门币',
  SyntheticJade: '贸易站-合成玉',
  CombatRecord: '制造站-经验书',
  PureGold: '制造站-赤金',
  OriginStone: '制造站-源石碎片',
  Chip: '制造站-芯片组',
}
/** 肉鸽主题 */
export const ROGUE_THEMES = ['Phantom', 'Mizuki', 'Sami', 'Sarkaz', 'JieGarden']
/** 剿灭关卡（对齐 MAA 客户端 FightSettingsUserControlModel.AnnihilationModeList） */
export const ANNIHILATION_STAGES: { value: string; label: string }[] = [
  { value: 'Annihilation', label: '当期剿灭' },
  { value: 'Chernobog@Annihilation', label: '切尔诺伯格' },
  { value: 'LungmenOutskirts@Annihilation', label: '龙门外环' },
  { value: 'LungmenDowntown@Annihilation', label: '龙门市区' },
]

export const TASK_TYPES: TaskTypeDef[] = [
  {
    type: '唤醒', entry: 'StartUp', label: '开始唤醒 StartUp',
    params: { client_type: '', start_game_enabled: true, account_name: '', account_switch_enabled: false },
  },
  {
    type: '关闭游戏', entry: 'CloseDown', label: '关闭游戏 CloseDown',
    params: { client_type: '' },
  },
  {
    type: '刷理智', entry: 'Fight', label: '刷理智 Fight',
    params: {
      stage: 'CE-6', medicine: 0, medicine_expire_days: 0, stone: 0,
      times: -1, series: 0, report_to_penguin: false, penguin_id: '',
      report_to_yituliu: false, yituliu_id: '', server: 'CN',
      client_type: '', DrGrandet: false,
      use_expiring_medicine: false,  // 使用临期药（旧数据兼容：medicine_expire_days>0 视为开启）
      use_custom_annihilation: false, annihilation_stage: 'Annihilation',  // 自定义剿灭
      auto_restart_on_drop: true,  // 游戏掉线自动重启续刷（对齐 MAA 客户端默认 true）
      weekly_schedule: { Mon: true, Tue: true, Wed: true, Thu: true, Fri: true, Sat: true, Sun: true },  // 周计划（客户端本地行为）
    },
  },
  {
    type: '公招', entry: 'Recruit', label: '公开招募 Recruit',
    params: {
      // 星级选择（3 星仅确认，4-6 星点击+确认，对齐 MAA 客户端 ChooseLevel3~6）
      select: [4], confirm: [3, 4],
      refresh: true, force_refresh: true,  // 刷新三星 Tags + 无许可也刷新
      first_tags: [], prefer_tags_enabled: true,  // 3 星 Tag 倾向
      extra_tags_mode: 0, times: 4, set_time: true,
      expedite: false,
      preserve_tags: [], preserve_tags_enabled: false,  // 保留 Tag
      recruitment_time: { 3: 540, 4: 540 },  // 3/4 星时限（分钟），5/6 星固定 9:00
      report_to_penguin: false, penguin_id: '', report_to_yituliu: false,
      yituliu_id: '', server: 'CN',
    },
  },
  {
    type: '基建', entry: 'Infrast', label: '基建换班 Infrast',
    params: {
      mode: 0, facility: [...INFRAST_FACILITIES], drones: 'Money',
      threshold: 0.3, replenish: true, dorm_notstationed_enabled: true,
      dorm_trust_enabled: true, continue_training: false,  // 训练室连续专精
      reception_message_board: true,
      reception_clue_exchange: true, reception_send_clue: true,
      filename: '', plan_index: 0,
    },
  },
  {
    type: '信用', entry: 'Mall', label: '信用购物 Mall',
    params: {
      visit_friends: true, visit_friends_once_a_day: false,
      shopping: true, buy_first: [], blacklist: [],
      force_shopping_if_credit_full: false, only_buy_discount: false,
      reserve_max_credit: false,
      credit_fight: false, credit_fight_once_a_day: true, formation_index: 0,
    },
  },
  {
    type: '领奖', entry: 'Award', label: '领取奖励 Award',
    params: { award: true, mail: false, recruit: false, orundum: false, mining: false, specialaccess: false },
  },
  {
    type: '肉鸽', entry: 'Roguelike', label: '肉鸽刷分 Roguelike',
    params: {
      theme: 'JieGarden', mode: 0, squad: '指挥分队', roles: '取长补短',
      core_char: '', use_support: false, use_nonfriend_support: false,
      starts_count: 2147483647, difficulty: 2147483647,  // 难度 MAX（跟随游戏内）
      stop_at_final_boss: false,
      stop_at_max_level: false, investment_enabled: true, investments_count: 2147483647,
      stop_when_investment_full: false, investment_with_more_score: false,
      start_with_elite_two: false, only_start_with_elite_two: false,
      refresh_trader_with_dice: false, first_floor_foldartal: '',
      start_foldartal_list: [], collectible_mode_start_list: {},
      expected_collapsal_paradigms: ['目空一些', '睁眼瞎', '图像损坏', '一抹黑'],
      use_foldartal: true, check_collapsal_paradigms: false,
      double_check_collapsal_paradigms: true,
      monthly_squad_auto_iterate: false, monthly_squad_check_comms: false,
      deep_exploration_auto_iterate: false, collectible_mode_shopping: false,
      collectible_mode_squad: '', start_with_seed: '',  // 种子为字符串键
      start_with_seed_enabled: false,  // 使用种子开关（UI 门控）
      find_playTime_target: 1,  // 界园刷常乐目标节点
    },
  },
  {
    type: '抄作业', entry: 'Copilot', label: '自动战斗 Copilot',
    params: {
      filename: '', stage_name: '', copilot_mode: 0,
      // 编队（键名对齐 MAA 引擎 CopilotTask 参数）
      formation: true,  // 自动编队
      use_formation: false, formation_index: 1,  // 使用编队 + 编队编号
      ignore_requirements: false,
      support_unit_usage: 0, support_unit_name: '',  // 0不加 1需要时 2指定 3随机
      add_trust: false,
      add_user_additional: [],  // [{name, skill}] 追加干员
      use_sanity_potion: false,  // 连战时使用理智药
      loop_times: 1,
      // 作业列表：一个自动战斗任务可承载多个作业（作业集），勾选 = 启用执行
      jobs: [] as CopilotJob[],
    },
  },
]

export function typeDefOf(entry: string): TaskTypeDef | undefined {
  return TASK_TYPES.find((t) => t.entry === entry)
}

/** 队列中的一条任务（id/selected 为编辑期状态，不入库/不入方案） */
export interface QueueTask {
  id: number
  type: string
  entry: string
  label: string
  /** 该任务独立参数（表单直接编辑，序列化原样保存） */
  params: Record<string, unknown>
  checked: boolean
  once: boolean
  selected: boolean
}

/** 持久化/方案文件中的任务形状（不含 id/selected） */
export interface PersistedTask {
  type: string
  entry: string
  label: string
  params: Record<string, unknown>
  checked: boolean
  once: boolean
}

/** 队列 → API 下发载荷（linkStart 用） */
export function queueToPayload(queue: QueueTask[]): TaskItemPayload[] {
  return queue
    .filter((t) => t.checked)
    .map((t) => ({ name: t.label, entry: t.entry, type: t.type, params: { ...t.params } }))
}

/** 队列 → 持久化形状（params 原样，刷新/方案加载后行为一致） */
export function serializeQueue(queue: QueueTask[]): PersistedTask[] {
  return queue.map((t) => ({
    type: t.type,
    entry: t.entry,
    label: t.label,
    params: { ...t.params },
    checked: t.checked,
    once: t.once,
  }))
}

let seq = 0

/** 持久化形状 → 队列（分配新 id；entry 未知时保留原始 label） */
export function deserializeQueue(list: PersistedTask[]): QueueTask[] {
  return list.map((t) => {
    const def = typeDefOf(t.entry)
    return {
      id: ++seq,
      type: t.type || def?.type || t.entry,
      entry: t.entry,
      label: t.label || def?.label || t.entry,
      params: { ...t.params },
      checked: t.checked !== false,
      once: !!t.once,
      selected: false,
    }
  })
}

/** 新任务 id */
export function nextTaskId(): number {
  return ++seq
}

/** 通用工具：逗号分隔文本 ↔ 字符串数组（tags 类字段） */
export function tagsToString(list: unknown): string {
  return Array.isArray(list) ? (list as string[]).join(', ') : ''
}

export function stringToTags(text: string): string[] {
  return text
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean)
}
