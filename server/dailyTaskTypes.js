'use strict';

const CLIENTS = [['Official', '官服'], ['Bilibili', 'B服'], ['Txwy', '渠道服'], ['YoStarEN', '国际服'], ['YoStarJP', '日服'], ['YoStarKR', '韩服']];

// 字段类型：
//   select    下拉，空值忽略
//   checkbox  布尔，false 忽略
//   number    数字，空值忽略
//   text      文本，空值忽略
//   multi     逗号分隔 -> 字符串数组
//   multiNum  逗号分隔 -> 数字数组
//   chips     多选（checkbox 组）-> 字符串数组
//   drops     材料掉落 "id=数量,id=数量" -> {id: 数量}
//   strNumMap  "k=v,k=v" -> {k: 数量}
//   boolMap    chips 多选 -> {key: true}
//   lines      textarea 每行 -> 字符串数组
//   rows       textarea 每行逗号分隔列 -> 对象数组（field.cols 列名、field.numCols 数字列）
const TASK_TYPES = [
  {
    type: 'StartUp',
    label: '开始唤醒',
    desc: '启动客户端并进入主界面',
    defaultEnabled: true,
    fields: [
      { name: 'client_type', label: '客户端', type: 'select', options: CLIENTS, default: 'Official', group: 'basic' },
      { name: 'start_game_enabled', label: '自动启动客户端', type: 'checkbox', group: 'basic' },
      { name: 'account_name', label: '切换账号', type: 'text', placeholder: '如 123、张三', hint: '仅支持切换至已登录账号，请保证输入在所有已登录账号中唯一', group: 'advanced' },
    ],
  },
  {
    type: 'Fight',
    label: '理智作战',
    desc: '刷取指定关卡，掉落识别',
    defaultEnabled: true,
    fields: [
      { name: 'stage', label: '关卡', type: 'text', placeholder: '如 1-7，留空为当前/上次', hint: '支持主线、CE-6/LS-6、剿灭 Annihilation、活动关卡等', group: 'basic' },
      { name: 'medicine', label: '使用理智药数量', type: 'number', group: 'basic' },
      { name: 'medicine_expire_days', label: '使用N天内过期理智药', type: 'number', group: 'basic' },
      { name: 'stone', label: '使用源石数量', type: 'number', group: 'basic' },
      { name: 'times', label: '指定次数', type: 'number', group: 'basic' },
      { name: 'series', label: '代理倍率', type: 'select', valueType: 'int', options: [['', '默认'], ['-1', '不切换'], ['0', 'AUTO'], ['1', '1倍'], ['2', '2倍'], ['3', '3倍'], ['4', '4倍'], ['5', '5倍'], ['6', '6倍']], hint: '-1 禁用 / 0 AUTO / 1-6 指定', group: 'advanced' },
      { name: 'drops', label: '指定材料', type: 'drops', placeholder: '如 30011=10,30062=5', hint: '任一材料达到数量即停止，材料 ID 见 item_index.json', group: 'advanced' },
      { name: 'DrGrandet', label: '碎石计划通模式', type: 'checkbox', hint: '在碎石确认界面等待理智恢复后再碎石', group: 'advanced' },
      { name: 'report_to_penguin', label: '上报企鹅物流', type: 'checkbox', group: 'advanced' },
      { name: 'penguin_id', label: '企鹅物流 ID', type: 'text', group: 'advanced' },
      { name: 'report_to_yituliu', label: '上报一图流', type: 'checkbox', group: 'advanced' },
      { name: 'yituliu_id', label: '一图流 ID', type: 'text', group: 'advanced' },
      { name: 'server', label: '服务器', type: 'select', options: [['', '默认'], ['CN', '国服'], ['US', '美服'], ['JP', '日服'], ['KR', '韩服']], hint: '影响掉落识别及上传', group: 'advanced' },
      { name: 'client_type', label: '崩溃重启客户端', type: 'select', options: ['', ...CLIENTS], hint: '游戏崩溃时自动重启并继续', group: 'advanced' },
    ],
  },
  {
    type: 'Recruit',
    label: '公开招募',
    desc: '自动公招，可仅识别',
    defaultEnabled: true,
    fields: [
      { name: 'refresh', label: '刷新三星 Tags', type: 'checkbox', group: 'basic' },
      { name: 'select', label: '点击选中的 Tag 等级', type: 'multiNum', placeholder: '如 5,4', group: 'basic' },
      { name: 'confirm', label: '点击确认的 Tag 等级', type: 'multiNum', placeholder: '如 4,3，留空则仅公招识别', group: 'basic' },
      { name: 'times', label: '招募次数', type: 'number', hint: '0 表示仅公招计算', group: 'basic' },
      { name: 'set_time', label: '设置招募时限', type: 'checkbox', default: true, group: 'basic' },
      { name: 'expedite', label: '使用加急许可', type: 'checkbox', group: 'advanced' },
      { name: 'expedite_times', label: '加急次数', type: 'number', hint: '留空为无限使用', group: 'advanced' },
      { name: 'extra_tags_mode', label: '额外选 Tag 模式', type: 'select', valueType: 'int', options: [['', '不加'], ['0', '不加'], ['1', '尽量选3个'], ['2', '只选有稀有度的']], hint: '1 选3个Tag / 2 同时选更多高星组合', group: 'advanced' },
      { name: 'first_tags', label: '首选 Tags', type: 'multi', placeholder: '如 高级资深干员', hint: '仅 Tag 等级为 3 时生效，强制选择', group: 'advanced' },
      { name: 'preserve_tags', label: '保留并跳过的 Tags', type: 'multi', placeholder: '如 支援机械', hint: '识别到指定 Tag 时保留槽位并跳过本次招募', group: 'advanced' },
      { name: 'recruitment_time', label: '各等级招募时限(分钟)', type: 'strNumMap', placeholder: '如 3=540,4=540', hint: 'Tag 等级 >=3 对应的希望招募时限，默认 540 分钟', group: 'advanced' },
      { name: 'report_to_penguin', label: '上报企鹅物流', type: 'checkbox', group: 'advanced' },
      { name: 'penguin_id', label: '企鹅物流 ID', type: 'text', group: 'advanced' },
      { name: 'report_to_yituliu', label: '上报一图流', type: 'checkbox', group: 'advanced' },
      { name: 'yituliu_id', label: '一图流 ID', type: 'text', group: 'advanced' },
      { name: 'server', label: '服务器', type: 'select', options: [['', '默认'], ['CN', '国服'], ['US', '美服'], ['JP', '日服'], ['KR', '韩服']], hint: '影响识别结果上传', group: 'advanced' },
    ],
  },
  {
    type: 'Infrast',
    label: '基建换班',
    desc: '自动换班与无人机',
    defaultEnabled: true,
    fields: [
      { name: 'mode', label: '换班模式', type: 'select', valueType: 'int', options: [['0', '默认换班'], ['10000', '自定义排班'], ['20000', '一键轮换']], group: 'basic' },
      { name: 'facility', label: '设施', type: 'chips', options: [['Mfg', '制造站'], ['Trade', '贸易站'], ['Power', '发电站'], ['Control', '控制中枢'], ['Reception', '会客室'], ['Office', '办公室'], ['Dorm', '宿舍'], ['Processing', '加工站'], ['Training', '训练室']], group: 'basic' },
      { name: 'drones', label: '无人机用途', type: 'select', options: [['', '不使用'], ['_NotUse', '不使用'], ['Money', '龙门币'], ['SyntheticJade', '合成玉'], ['CombatRecord', '战斗记录'], ['PureGold', '赤金'], ['OriginStone', '源石碎片'], ['Chip', '芯片']], group: 'basic' },
      { name: 'threshold', label: '心情阈值', type: 'number', step: '0.1', default: '0.3', group: 'advanced' },
      { name: 'replenish', label: '源石碎片自动补货', type: 'checkbox', group: 'advanced' },
      { name: 'dorm_trust_enabled', label: '宿舍填入信赖未满干员', type: 'checkbox', group: 'advanced' },
      { name: 'dorm_notstationed_enabled', label: '宿舍启用未进驻', type: 'checkbox', group: 'advanced' },
      { name: 'reception_message_board', label: '领取会客室信用', type: 'checkbox', default: true, group: 'advanced' },
      { name: 'reception_clue_exchange', label: '线索交流', type: 'checkbox', default: true, group: 'advanced' },
      { name: 'reception_send_clue', label: '赠送线索', type: 'checkbox', default: true, group: 'advanced' },
      { name: 'filename', label: '自定义排班文件', type: 'text', placeholder: '如 schedules/base.json', hint: '仅自定义换班模式生效，相对路径位于配置目录 infrast/ 下', group: 'advanced' },
      { name: 'plan_index', label: '排班方案序号', type: 'number', group: 'advanced' },
    ],
  },
  {
    type: 'Mall',
    label: '信用收支',
    desc: '访问好友、领取信用、购物',
    defaultEnabled: true,
    fields: [
      { name: 'visit_friends', label: '访问好友', type: 'checkbox', default: true, group: 'basic' },
      { name: 'shopping', label: '购物', type: 'checkbox', default: true, group: 'basic' },
      { name: 'buy_first', label: '优先购买', type: 'multi', placeholder: '如 招聘许可,龙门币', group: 'advanced' },
      { name: 'blacklist', label: '购物黑名单', type: 'multi', placeholder: '如 家具零件', group: 'advanced' },
      { name: 'force_shopping_if_credit_full', label: '信用溢出时无视黑名单', type: 'checkbox', group: 'advanced' },
      { name: 'only_buy_discount', label: '只购买折扣物品', type: 'checkbox', group: 'advanced' },
      { name: 'reserve_max_credit', label: '信用低于300停止购买', type: 'checkbox', group: 'advanced' },
      { name: 'credit_fight', label: '借助战打 OF-1 赚信用', type: 'checkbox', group: 'advanced' },
      { name: 'formation_index', label: '编队序号', type: 'select', valueType: 'int', options: ['0', '1', '2', '3', '4'], group: 'advanced' },
    ],
  },
  {
    type: 'Award',
    label: '领取奖励',
    desc: '领取每日/邮件等奖励',
    defaultEnabled: true,
    fields: [
      { name: 'award', label: '每日/每周任务奖励', type: 'checkbox', default: true, group: 'basic' },
      { name: 'mail', label: '邮件奖励', type: 'checkbox', group: 'basic' },
      { name: 'recruit', label: '每日免费单抽', type: 'checkbox', group: 'basic' },
      { name: 'orundum', label: '幸运墙合成玉', type: 'checkbox', group: 'basic' },
      { name: 'mining', label: '限时开采许可合成玉', type: 'checkbox', group: 'basic' },
      { name: 'specialaccess', label: '月卡奖励', type: 'checkbox', group: 'basic' },
    ],
  },
  {
    type: 'Roguelike',
    label: '自动肉鸽',
    desc: '集成战略全自动',
    defaultEnabled: true,
    fields: [
      { name: 'theme', label: '主题', type: 'select', options: [['Phantom', '傀影'], ['Mizuki', '水月'], ['Sami', '萨米'], ['Sarkaz', '萨卡兹'], ['JieGarden', '界园']], default: 'Phantom', group: 'basic' },
      { name: 'mode', label: '模式', type: 'select', valueType: 'int', options: [['0', '刷分'], ['1', '刷源石锭'], ['4', '凹开局'], ['5', '刷坍缩范式(Sami)'], ['6', '刷月度小队'], ['7', '刷深入调查']], default: '0', group: 'basic' },
      { name: 'squad', label: '开局分队', type: 'text', placeholder: '如 指挥分队', group: 'basic' },
      { name: 'roles', label: '开局职业组', type: 'text', placeholder: '如 取长补短', group: 'basic' },
      { name: 'core_char', label: '核心干员(中文)', type: 'text', placeholder: '如 维什戴尔', group: 'basic' },
      { name: 'starts_count', label: '探索次数上限', type: 'number', group: 'advanced' },
      { name: 'difficulty', label: '难度', type: 'number', group: 'advanced' },
      { name: 'use_support', label: '使用助战', type: 'checkbox', group: 'advanced' },
      { name: 'use_nonfriend_support', label: '允许非好友助战', type: 'checkbox', group: 'advanced' },
      { name: 'investment_enabled', label: '投资源石锭', type: 'checkbox', default: true, group: 'advanced' },
      { name: 'investments_count', label: '投资次数上限', type: 'number', group: 'advanced' },
      { name: 'stop_when_investment_full', label: '投资满后停止', type: 'checkbox', group: 'advanced' },
      { name: 'investment_with_more_score', label: '投资后购物(模式1)', type: 'checkbox', group: 'advanced' },
      { name: 'stop_at_final_boss', label: '最终BOSS前停止', type: 'checkbox', group: 'advanced' },
      { name: 'stop_at_max_level', label: '肉鸽等级刷满停止', type: 'checkbox', group: 'advanced' },
      { name: 'start_with_elite_two', label: '凹精二直升(模式4)', type: 'checkbox', group: 'advanced' },
      { name: 'only_start_with_elite_two', label: '只凹精二直升(模式4)', type: 'checkbox', group: 'advanced' },
      { name: 'refresh_trader_with_dice', label: '掷骰刷新商店(Mizuki)', type: 'checkbox', group: 'advanced' },
      { name: 'use_foldartal', label: '使用密文板(Sami)', type: 'checkbox', group: 'advanced' },
      { name: 'expected_collapsal_paradigms', label: '期望坍缩范式(模式5)', type: 'multi', placeholder: '如 目空一些,睁眼瞎', group: 'advanced' },
      { name: 'first_floor_foldartal', label: '第一层密文板(Sami)', type: 'text', placeholder: '如 大地的手术台', hint: '希望在第一层远见阶段得到的密文板，凹到则停止', group: 'advanced' },
      { name: 'start_foldartal_list', label: '开局密文板列表(模式4)', type: 'multi', placeholder: '如 蜜水,诸王', hint: 'Sami 模式 4 凹开局，需配合「生活至上分队」', group: 'advanced' },
      { name: 'collectible_mode_start_list', label: '凹开局期望奖励(模式4)', type: 'boolMap', options: [['hot_water', '热水壶'], ['shield', '护盾'], ['ingot', '源石锭'], ['hope', '希望'], ['random', '随机'], ['key', '钥匙'], ['dice', '骰子'], ['ideas', '构想'], ['ticket', '票券']], hint: '热水壶/护盾/源石锭/希望/随机/钥匙/骰子/构想/票券', group: 'advanced' },
      { name: 'check_collapsal_paradigms', label: '检测坍缩范式', type: 'checkbox', hint: '模式 5 下默认开启', group: 'advanced' },
      { name: 'double_check_collapsal_paradigms', label: '坍缩检测防漏', type: 'checkbox', group: 'advanced' },
      { name: 'monthly_squad_auto_iterate', label: '月度小队自动切换', type: 'checkbox', group: 'advanced' },
      { name: 'monthly_squad_check_comms', label: '月度小队通信作切换依据', type: 'checkbox', group: 'advanced' },
      { name: 'deep_exploration_auto_iterate', label: '深入调查自动切换', type: 'checkbox', group: 'advanced' },
      { name: 'collectible_mode_shopping', label: '烧水时购物', type: 'checkbox', group: 'advanced' },
      { name: 'collectible_mode_squad', label: '烧水分队', type: 'text', placeholder: '留空与 squad 同步', group: 'advanced' },
      { name: 'start_with_seed', label: '种子开局(Sarkaz)', type: 'checkbox', group: 'advanced' },
    ],
  },
  {
    type: 'Reclamation',
    label: '生息演算',
    desc: '生息演算自动化',
    defaultEnabled: true,
    fields: [
      { name: 'theme', label: '主题', type: 'select', options: [['Fire', '沙中之火（已关闭）'], ['Tales', '沙洲遗闻'], ['RelaunchAnchor', '重启锚点']], default: 'Tales', group: 'basic' },
      { name: 'mode', label: '模式', type: 'select', valueType: 'int', options: [['0', '无存档刷点数'], ['1', '有存档制工具(Tales)'], ['16', 'RA-1 精耕细作'], ['32', 'RA-15 60杀'], ['48', 'RA-4 击杀BOSS']], default: '1', group: 'basic' },
      { name: 'tools_to_craft', label: '制造工具', type: 'multi', placeholder: '如 荧光棒,发电机', group: 'advanced' },
      { name: 'increment_mode', label: '数量增加方式', type: 'select', valueType: 'int', options: [['0', '连点'], ['1', '长按']], group: 'advanced' },
      { name: 'num_craft_batches', label: '单次最大制造轮数', type: 'number', default: '16', group: 'advanced' },
    ],
  },
  {
    type: 'Copilot',
    label: '自动抄作业',
    desc: '运行作业 JSON',
    defaultEnabled: true,
    fields: [
      { name: 'filename', label: '作业文件路径', type: 'text', placeholder: '如 copilot/1-7.json 或绝对路径', hint: '与作业列表二选一', group: 'basic' },
      { name: 'copilot_list', label: '作业列表', type: 'rows', cols: ['filename', 'stage_name', 'is_raid'], numCols: [], placeholder: '每行一个作业：文件名,关卡名,is_raid(可选)', hint: '与单个作业文件二选一，可批量', group: 'basic' },
      { name: 'loop_times', label: '循环次数', type: 'number', default: '1', hint: '仅单个作业模式下有效', group: 'basic' },
      { name: 'use_sanity_potion', label: '理智不足时用药', type: 'checkbox', group: 'basic' },
      { name: 'formation', label: '自动编队', type: 'checkbox', group: 'advanced' },
      { name: 'formation_index', label: '编队序号', type: 'select', valueType: 'int', options: ['0', '1', '2', '3', '4'], group: 'advanced' },
      { name: 'user_additional', label: '自定义追加干员', type: 'rows', cols: ['name', 'skill'], numCols: ['skill'], placeholder: '每行一个：干员名,技能序号(1-3)', hint: '仅在自动编队时生效', group: 'advanced' },
      { name: 'add_trust', label: '按信赖升序补位', type: 'checkbox', group: 'advanced' },
      { name: 'ignore_requirements', label: '忽视干员属性要求', type: 'checkbox', group: 'advanced' },
      { name: 'support_unit_usage', label: '助战使用模式', type: 'select', valueType: 'int', options: ['', '0', '1', '2', '3'], group: 'advanced' },
      { name: 'support_unit_name', label: '指定助战干员', type: 'text', hint: '助战模式为 2 时生效', group: 'advanced' },
    ],
  },
  {
    type: 'SSSCopilot',
    label: '保全派驻',
    desc: '自动抄保全作业',
    defaultEnabled: false,
    fields: [
      { name: 'filename', label: '作业文件路径', type: 'text', placeholder: '如 sss/plan.json 或绝对路径', group: 'basic' },
      { name: 'loop_times', label: '循环次数', type: 'number', group: 'basic' },
    ],
  },
  {
    type: 'ParadoxCopilot',
    label: '悖论模拟',
    desc: '自动抄悖论模拟作业',
    defaultEnabled: false,
    fields: [
      { name: 'filename', label: '单个作业文件路径', type: 'text', placeholder: '如 paradox/exusiai.json', hint: '与作业列表二选一', group: 'basic' },
      { name: 'list', label: '作业列表', type: 'lines', placeholder: '每行一个作业文件路径', hint: '与单个作业文件二选一', group: 'basic' },
    ],
  },
  {
    type: 'Depot',
    label: '仓库识别',
    desc: '识别仓库材料并统计',
    defaultEnabled: false,
    fields: [],
  },
  {
    type: 'OperBox',
    label: '干员识别',
    desc: '识别干员 Box，统计已有与潜能',
    defaultEnabled: false,
    fields: [],
  },
  {
    type: 'VideoRecognition',
    label: '视频识别',
    desc: '识别作业视频并生成作业 JSON',
    defaultEnabled: false,
    fields: [
      { name: 'filename', label: '视频文件路径', type: 'text', placeholder: '如 videos/copilot.mp4', group: 'basic' },
    ],
  },
  {
    type: 'Custom',
    label: '自定义任务',
    desc: '执行任意内置任务名（按顺序匹配执行）',
    defaultEnabled: false,
    fields: [
      { name: 'task_names', label: '任务名列表', type: 'multi', placeholder: '如 StartUp,Infrast,Fight', group: 'basic' },
    ],
  },
  {
    type: 'SingleStep',
    label: '单步任务',
    desc: '单步执行战斗任务（目前仅支持 copilot）',
    defaultEnabled: false,
    fields: [
      { name: 'subtask', label: '子任务类型', type: 'select', options: [['stage', '设置关卡'], ['start', '开始作战'], ['action', '单步作战操作']], default: 'stage', group: 'basic' },
      { name: 'stage', label: '关卡名', type: 'text', placeholder: '如 1-7', hint: '仅 subtask=stage 时生效', group: 'basic' },
      { name: 'details', label: '操作详情 JSON', type: 'json', placeholder: '如 {"name":"史尔特尔","location":[4,5],"direction":"左"}', hint: '仅 subtask=action 时生效，为战斗协议中的单个 action', group: 'advanced' },
    ],
  },
  {
    type: 'CloseDown',
    label: '关闭游戏',
    desc: '关闭客户端',
    defaultEnabled: true,
    fields: [
      { name: 'client_type', label: '客户端', type: 'select', options: ['', ...CLIENTS], group: 'basic' },
    ],
  },
];

const BY_TYPE = Object.fromEntries(TASK_TYPES.map((t) => [t.type, t]));

function typeMeta(type) {
  return BY_TYPE[type];
}

function valueToParam(field, raw) {
  if (raw === undefined || raw === null || raw === '') return undefined;
  switch (field.type) {
    case 'checkbox':
      return !!raw;
    case 'number':
      return Number.isFinite(raw) ? raw : Number(raw);
    case 'select':
      if (field.valueType === 'int') {
        const n = Number(raw);
        return Number.isNaN(n) ? undefined : n;
      }
      return String(raw);
    case 'multi':
    case 'multiNum':
    case 'lines':
    case 'chips':
    case 'rows':
      if (Array.isArray(raw)) {
        if (field.type === 'multi') return raw.map((s) => String(s)).filter(Boolean);
        if (field.type === 'multiNum') return raw.map((s) => Number(s)).filter((n) => !Number.isNaN(n));
        if (field.type === 'chips') return raw.map((s) => String(s)).filter(Boolean);
        return raw;
      }
      break;
    case 'drops':
    case 'strNumMap':
    case 'boolMap':
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) return raw;
      break;
    case 'json':
      if (raw && typeof raw === 'object') return raw;
      try {
        const parsed = JSON.parse(String(raw));
        return parsed && typeof parsed === 'object' ? parsed : undefined;
      } catch {
        return undefined;
      }
    default:
      return String(raw);
  }
  switch (field.type) {
    case 'multi':
      return String(raw).split(',').map((s) => s.trim()).filter(Boolean);
    case 'multiNum':
      return String(raw).split(',').map((s) => Number(s.trim())).filter((n) => !Number.isNaN(n));
    case 'chips': {
      const arr = Array.isArray(raw) ? raw : String(raw).split(',');
      return arr.map((s) => String(s).trim()).filter(Boolean);
    }
    case 'drops': {
      const out = {};
      for (const part of String(raw).split(',').map((s) => s.trim()).filter(Boolean)) {
        const [id, count] = part.split('=');
        if (id && count !== undefined) out[id.trim()] = Number(count.trim());
      }
      return Object.keys(out).length ? out : undefined;
    }
    case 'strNumMap': {
      const out = {};
      for (const part of String(raw).split(',').map((s) => s.trim()).filter(Boolean)) {
        const [k, v] = part.split('=');
        if (k && v !== undefined && !Number.isNaN(Number(v))) out[k.trim()] = Number(v.trim());
      }
      return Object.keys(out).length ? out : undefined;
    }
    case 'boolMap': {
      const arr = Array.isArray(raw) ? raw : String(raw).split(',');
      const keys = arr.map((s) => String(s).trim()).filter(Boolean);
      if (!keys.length) return undefined;
      return Object.fromEntries(keys.map((k) => [k, true]));
    }
    case 'lines': {
      const arr = String(raw).split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
      return arr.length ? arr : undefined;
    }
    case 'rows': {
      const cols = field.cols || [];
      const numCols = new Set(field.numCols || []);
      const out = [];
      for (const line of String(raw).split(/\r?\n/).map((s) => s.trim()).filter(Boolean)) {
        const parts = line.split(',').map((s) => s.trim());
        const obj = {};
        cols.forEach((c, i) => {
          const v = parts[i];
          if (v === undefined || v === '') return;
          if (numCols.has(c)) obj[c] = Number(v);
          else if (v === 'true') obj[c] = true;
          else if (v === 'false') obj[c] = false;
          else obj[c] = v;
        });
        if (Object.keys(obj).length) out.push(obj);
      }
      return out.length ? out : undefined;
    }
    default:
      return String(raw);
  }
}

function buildParams(fields, values) {
  const params = {};
  for (const field of fields) {
    const v = valueToParam(field, values[field.name]);
    if (v === undefined) continue;
    if (field.type === 'checkbox' && !v) continue;
    params[field.name] = v;
  }
  return params;
}

// 生成 maa-cli 每日任务文件内容（v0.7+ 格式：{ client_type, tasks: [...] }）
function generateTaskFile(tasks) {
  const list = [];
  let clientType = 'Official';
  for (const t of tasks) {
    if (t && t.enabled === false) continue;
    const meta = BY_TYPE[t.type];
    if (!meta) continue;
    const params = buildParams(meta.fields, t.params || {});
    if (t.type === 'StartUp' && params.client_type && typeof params.client_type === 'string') {
      clientType = params.client_type;
      delete params.client_type;
    }
    if (t.type === 'SingleStep' && params.subtask && typeof params.subtask === 'string') {
      params.type = 'copilot';
      if (params.subtask !== 'stage') delete params.stage;
      if (params.subtask !== 'action') delete params.details;
    }
    const entry = { type: t.type };
    if (t.name && t.name.trim()) entry.name = String(t.name).trim();
    if (Object.keys(params).length) entry.params = params;
    list.push(entry);
  }
  return JSON.stringify({ client_type: clientType, tasks: list }, null, 2) + '\n';
}

module.exports = { TASK_TYPES, BY_TYPE, typeMeta, generateTaskFile, buildParams, CLIENTS };
