'use strict';

const CLIENTS = [['Official', '官服'], ['Bilibili', 'B服'], ['Txwy', '渠道服'], ['YoStarEN', '国际服'], ['YoStarJP', '日服'], ['YoStarKR', '韩服']];
const ROGUELIKE_THEMES = [['Phantom', '傀影'], ['Mizuki', '水月'], ['Sami', '萨米'], ['Sarkaz', '萨卡兹'], ['JieGarden', '界园']];
const RECLAMATION_THEMES = [['Tales', '沙洲遗闻']];

const COMMON_FIELDS = [
  {
    name: 'addr',
    label: '连接地址',
    type: 'text',
    placeholder: 'emulator-5554 / 127.0.0.1:5555',
    cli: { flag: '-a' },
    group: 'connection',
  },
  {
    name: 'profile',
    label: '配置档 (profile)',
    type: 'text',
    placeholder: 'default',
    cli: { flag: '-p' },
    group: 'connection',
  },
  {
    name: 'userResource',
    label: '加载自定义资源',
    type: 'checkbox',
    desc: '从 $MAA_CONFIG_DIR/resource 加载用户资源',
    cli: { flag: '--user-resource', boolean: true },
    group: 'connection',
  },
];

// field: { name, label, type, options?, placeholder?, defaultValue?, description?, cli }
// cli: { position } positional | { flag } value option | { flag, boolean } flag option
const TASK_SCHEMAS = {
  startup: {
    category: '日常',
    advancedFields: ['accountName'],
    label: '开始唤醒',
    desc: '启动游戏并进入主界面',
    fields: [
      {
        name: 'client',
        label: '客户端',
        type: 'select',
        options: ['', ...CLIENTS],
        defaultValue: '',
        cli: { position: 0 },
      },
      {
        name: 'accountName',
        label: '账号名',
        type: 'text',
        cli: { flag: '--account-name' },
      },
      ...COMMON_FIELDS,
    ],
  },
  closedown: {
    category: '日常',
    advancedFields: [],
    label: '关闭游戏',
    desc: '关闭游戏客户端',
    fields: [
      {
        name: 'client',
        label: '客户端',
        type: 'select',
        options: [...CLIENTS],
        defaultValue: 'Official',
        cli: { position: 0 },
      },
      ...COMMON_FIELDS,
    ],
  },
  fight: {
    category: '作战',
    advancedFields: ['medicine', 'expiringMedicine', 'stone', 'times', 'drops', 'series', 'clientType', 'drGrandet', 'reportToPenguin', 'penguinId', 'reportToYituliu', 'yituliuId'],
    label: '理智作战',
    desc: '刷取指定关卡',
    fields: [
      {
        name: 'stage',
        label: '关卡',
        type: 'text',
        placeholder: '如 1-7，留空为当前/上次关卡',
        cli: { position: 0 },
      },
      {
        name: 'medicine',
        label: '理智药数量',
        type: 'number',
        cli: { flag: '-m' },
      },
      {
        name: 'expiringMedicine',
        label: '过期的理智药数量',
        type: 'number',
        cli: { flag: '--expiring-medicine' },
      },
      {
        name: 'stone',
        label: '源石数量',
        type: 'number',
        cli: { flag: '--stone' },
      },
      {
        name: 'times',
        label: '战斗次数上限',
        type: 'number',
        cli: { flag: '--times' },
      },
      {
        name: 'drops',
        label: '掉落数停止条件',
        type: 'text',
        placeholder: '如 30012=100，多个用逗号分隔',
        description: '收集到指定掉落物数量后停止，如 30012=100,30011=100',
        cli: { flag: '-D', multiple: ',' },
      },
      {
        name: 'series',
        label: '代理次数 (-1~6)',
        type: 'number',
        cli: { flag: '--series' },
      },
      {
        name: 'clientType',
        label: '客户端类型',
        type: 'select',
        options: ['', ...CLIENTS],
        defaultValue: '',
        description: '游戏崩溃时用于重启客户端',
        cli: { flag: '--client-type' },
      },
      {
        name: 'drGrandet',
        label: '碎石计划通模式',
        type: 'checkbox',
        cli: { flag: '--dr-grandet', boolean: true },
      },
      {
        name: 'reportToPenguin',
        label: '上报企鹅物流',
        type: 'checkbox',
        cli: { flag: '--report-to-penguin', boolean: true },
      },
      {
        name: 'penguinId',
        label: '企鹅物流 ID',
        type: 'text',
        cli: { flag: '--penguin-id' },
      },
      {
        name: 'reportToYituliu',
        label: '上报一图流',
        type: 'checkbox',
        cli: { flag: '--report-to-yituliu', boolean: true },
      },
      {
        name: 'yituliuId',
        label: '一图流 ID',
        type: 'text',
        cli: { flag: '--yituliu-id' },
      },
      ...COMMON_FIELDS,
    ],
  },
  copilot: {
    category: '抄作业',
    advancedFields: ['raid', 'formation', 'formationIndex', 'addTrust', 'ignoreRequirements', 'useSanityPotion', 'supportUnitUsage', 'supportUnitName', 'loopTimes'],
    label: '自动抄作业',
    desc: '运行作业 URI 或本地文件',
    fields: [
      {
        name: 'uris',
        label: '作业 URI',
        type: 'textarea',
        placeholder: 'maa://1234 或 ./1234.json，每行一个',
        description: '支持 maa://code、maa://codes、file://path，可填写多个',
        cli: { flag: null, positional_list: 0 },
      },
      {
        name: 'raid',
        label: '突袭模式',
        type: 'select',
        options: [['', '普通'], ['normal', '普通'], ['raid', '突袭'], ['both', '普通+突袭']],
        defaultValue: '',
        cli: { flag: '--raid' },
      },
      {
        name: 'formation',
        label: '自动编队',
        type: 'checkbox',
        cli: { flag: '--formation', boolean: true },
      },
      {
        name: 'formationIndex',
        label: '编队序号 (1-4)',
        type: 'number',
        cli: { flag: '--formation-index' },
      },
      {
        name: 'addTrust',
        label: '补信任位',
        type: 'checkbox',
        cli: { flag: '--add-trust', boolean: true },
      },
      {
        name: 'ignoreRequirements',
        label: '忽略干员需求',
        type: 'checkbox',
        cli: { flag: '--ignore-requirements', boolean: true },
      },
      {
        name: 'useSanityPotion',
        label: '使用理智药',
        type: 'checkbox',
        cli: { flag: '--use-sanity-potion', boolean: true },
      },
      {
        name: 'supportUnitUsage',
        label: '助战使用模式',
        type: 'select',
        options: [['', '不使用'], ['0', '不使用'], ['1', '仅补必要'], ['2', '随机加一个'], ['3', '随机加两个']],
        defaultValue: '',
        cli: { flag: '--support-unit-usage' },
      },
      {
        name: 'supportUnitName',
        label: '指定助战干员',
        type: 'text',
        cli: { flag: '--support-unit-name' },
      },
      {
        name: 'loopTimes',
        label: '循环次数',
        type: 'number',
        cli: { flag: '--loop-times' },
      },
      ...COMMON_FIELDS,
    ],
  },
  roguelike: {
    category: '集成战略',
    advancedFields: ['roles', 'startsCount', 'investmentsCount', 'disableInvestment', 'investmentWithMoreScore', 'noStopWhenInvestmentFull', 'useSupport', 'useNonfriendSupport', 'startWithEliteTwo', 'onlyStartWithEliteTwo', 'stopAtFinalBoss', 'refreshTraderWithDice', 'useFoldartal', 'startFoldartals', 'expectedCollapsalParadigms', 'startWithSeed'],
    label: '自动集成战略',
    desc: '自动肉鸽',
    fields: [
      {
        name: 'theme',
        label: '主题',
        type: 'select',
        options: ROGUELIKE_THEMES,
        defaultValue: 'Phantom',
        cli: { position: 0 },
      },
      {
        name: 'mode',
        label: '模式',
        type: 'select',
        options: [['0', '刷经验'], ['1', '刷源石锭'], ['2', '兼顾 0 和 1（已弃用）'], ['3', '通关'], ['4', '凹开局'], ['5', '刷坍缩范式']],
        defaultValue: '0',
        cli: { flag: '--mode' },
      },
      {
        name: 'squad',
        label: '开局分队',
        type: 'text',
        placeholder: '如 指挥分队',
        cli: { flag: '--squad' },
      },
      {
        name: 'coreChar',
        label: '核心干员',
        type: 'text',
        placeholder: '如 维什戴尔',
        cli: { flag: '--core-char' },
      },
      {
        name: 'roles',
        label: '开局招募组合',
        type: 'text',
        placeholder: '如 取长补短',
        cli: { flag: '--roles' },
      },
      {
        name: 'startsCount',
        label: '探索次数上限',
        type: 'number',
        cli: { flag: '--starts-count' },
      },
      {
        name: 'difficulty',
        label: '难度',
        type: 'number',
        cli: { flag: '--difficulty' },
      },
      {
        name: 'investmentsCount',
        label: '投资次数上限',
        type: 'number',
        cli: { flag: '--investments-count' },
      },
      {
        name: 'disableInvestment',
        label: '关闭投资',
        type: 'checkbox',
        cli: { flag: '--disable-investment', boolean: true },
      },
      {
        name: 'investmentWithMoreScore',
        label: '投资模式获取更多分数',
        type: 'checkbox',
        cli: { flag: '--investment-with-more-score', boolean: true },
      },
      {
        name: 'noStopWhenInvestmentFull',
        label: '投资满后不停止',
        type: 'checkbox',
        cli: { flag: '--no-stop-when-investment-full', boolean: true },
      },
      {
        name: 'useSupport',
        label: '使用助战',
        type: 'checkbox',
        cli: { flag: '--use-support', boolean: true },
      },
      {
        name: 'useNonfriendSupport',
        label: '使用非好友助战',
        type: 'checkbox',
        cli: { flag: '--use-nonfriend-support', boolean: true },
      },
      {
        name: 'startWithEliteTwo',
        label: '开局精二',
        type: 'checkbox',
        cli: { flag: '--start-with-elite-two', boolean: true },
      },
      {
        name: 'onlyStartWithEliteTwo',
        label: '仅开局精二',
        type: 'checkbox',
        cli: { flag: '--only-start-with-elite-two', boolean: true },
      },
      {
        name: 'stopAtFinalBoss',
        label: '最终 BOSS 前停止',
        type: 'checkbox',
        cli: { flag: '--stop-at-final-boss', boolean: true },
      },
      {
        name: 'refreshTraderWithDice',
        label: '掷骰刷新商店 (Mizuki)',
        type: 'checkbox',
        cli: { flag: '--refresh-trader-with-dice', boolean: true },
      },
      {
        name: 'useFoldartal',
        label: '使用密文板 (Sami)',
        type: 'checkbox',
        cli: { flag: '--use-foldartal', boolean: true },
      },
      {
        name: 'startFoldartals',
        label: '开局密文板',
        type: 'text',
        cli: { flag: '-F' },
      },
      {
        name: 'expectedCollapsalParadigms',
        label: '坍缩范式列表',
        type: 'text',
        cli: { flag: '-P' },
      },
      {
        name: 'startWithSeed',
        label: '种子开局 (Sarkaz)',
        type: 'checkbox',
        cli: { flag: '--start-with-seed', boolean: true },
      },
      ...COMMON_FIELDS,
    ],
  },
  reclamation: {
    category: '集成战略',
    advancedFields: ['increaseMode', 'numCraftBatches'],
    label: '自动生息演算',
    desc: '自动生息演算',
    fields: [
      {
        name: 'theme',
        label: '主题',
        type: 'select',
        options: RECLAMATION_THEMES,
        defaultValue: 'Tales',
        cli: { position: 0 },
      },
      {
        name: 'mode',
        label: '模式',
        type: 'select',
        options: ['0', '1'],
        defaultValue: '1',
        cli: { flag: '-m' },
      },
      {
        name: 'toolsToCraft',
        label: '制造的工具',
        type: 'text',
        defaultValue: '荧光棒',
        cli: { flag: '-C' },
      },
      {
        name: 'increaseMode',
        label: '数量增加方式',
        type: 'select',
        options: ['0', '1'],
        defaultValue: '0',
        cli: { flag: '--increase-mode' },
      },
      {
        name: 'numCraftBatches',
        label: '每局制造批次',
        type: 'number',
        defaultValue: '16',
        cli: { flag: '--num-craft-batches' },
      },
      ...COMMON_FIELDS,
    ],
  },
  ssscopilot: {
    category: '抄作业',
    advancedFields: ['loopTimes'],
    label: '自动抄保全作业',
    desc: '运行保全派驻作业',
    fields: [
      {
        name: 'uri',
        label: '作业路径',
        type: 'text',
        placeholder: 'sss/plan.json 或绝对路径',
        cli: { position: 0 },
      },
      {
        name: 'loopTimes',
        label: '循环次数',
        type: 'number',
        defaultValue: '1',
        cli: { flag: '--loop-times' },
      },
      ...COMMON_FIELDS,
    ],
  },
  paradoxcopilot: {
    category: '抄作业',
    advancedFields: [],
    label: '自动抄悖论模拟作业',
    desc: '运行悖论模拟作业',
    fields: [
      {
        name: 'uri',
        label: '作业路径',
        type: 'text',
        placeholder: 'paradox/exusiai.json 或绝对路径',
        cli: { position: 0 },
      },
      ...COMMON_FIELDS,
    ],
  },
  run: {
    category: '其他',
    advancedFields: [],
    label: '自定义任务',
    desc: '运行自定义任务文件',
    fields: [
      {
        name: 'task',
        label: '任务',
        type: 'customTasks',
        placeholder: '选择任务',
        cli: { position: 0 },
      },
      ...COMMON_FIELDS,
    ],
  },
  video: {
    category: '其他',
    advancedFields: [],
    label: '视频识别',
    desc: '识别作业视频，生成作业 JSON',
    viaTool: true,
    fields: [
      {
        name: 'filename',
        label: '视频文件路径',
        type: 'text',
        placeholder: '服务器上的视频文件路径',
      },
      ...COMMON_FIELDS,
    ],
  },
};

const COMMON_OPTIONS = {
  batch: { flag: '--batch', label: '批量模式', desc: '跳过交互输入，使用默认值' },
  dryRun: { flag: '--dry-run', label: '试运行', desc: '只解析配置，不连接游戏' },
  noSummary: { flag: '--no-summary', label: '关闭总结', desc: '不显示任务总结' },
  noAutoReconnect: { flag: '--no-auto-reconnect', label: '不自动重连', desc: '游戏断线时不自动重连' },
};

function buildArgs(type, params = {}, common = {}) {
  const schema = TASK_SCHEMAS[type];
  if (!schema) throw new Error(`Unknown task type: ${type}`);

  const positional = new Map();
  const args = [];
  const pushList = [];

  for (const field of schema.fields) {
    const value = params[field.name];
    if (value === undefined || value === null || value === '') continue;

    const cli = field.cli;
    if (cli.position !== undefined) {
      positional.set(cli.position, String(value));
      continue;
    }
    if (cli.flag === null && cli.positional_list !== undefined) {
      pushList.push(...String(value).split(/\r?\n/).map((s) => s.trim()).filter(Boolean));
      continue;
    }
    if (cli.boolean) {
      if (value === true || value === 'true' || value === 'on') args.push(cli.flag);
      continue;
    }
    if (cli.multiple) {
      for (const part of String(value).split(cli.multiple).map((s) => s.trim()).filter(Boolean)) {
        args.push(cli.flag, part);
      }
      continue;
    }
    args.push(cli.flag, String(value));
  }

  for (const [idx, flag] of Object.entries(COMMON_OPTIONS)) {
    if (common[idx] === true) args.push(flag.flag);
  }

  const orderedPositional = [...positional.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, v]) => v);

  const cmd = [type, ...orderedPositional, ...pushList, ...args];
  return cmd;
}

function schemaOf(type) {
  return TASK_SCHEMAS[type];
}

module.exports = { TASK_SCHEMAS, buildArgs, schemaOf, COMMON_OPTIONS, CLIENTS };
