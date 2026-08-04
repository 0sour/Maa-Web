# MAA Web 控制台 — 任务规划

基于 maa-cli 的 Web 控制台，参考 MXU、maa-cli-webui、ws-scrcpy 与 MaaAssistantArknights 原版客户端持续完善。

## 已完成

- **任务队列**：多任务编排、参数编辑、拖拽排序、右键菜单、状态指示（✓/✗/·/●）、参数摘要、运行历史「重新运行」、侧栏面板排队任务列表、**队列状态实时自动保存**（防抖 500ms）
- **定时任务**：周几+时间点调度、错过补偿（3h）、下次执行预览
- **快速任务页重构**：卡片式任务选择（日常/作战/抄作业/集成战略/其他 5 分类）、基础/进阶参数折叠、运行设置独立、最近使用标记、抄作业 maa:// 代码直达、**视频识别**（走工具通道）
- **信息识别页**（原工具箱+识别结果合并）：公招/仓库/干员识别卡片 + 识别结果历史（筛选/详情/删除）同页展示
- **设备连接**：adb 扫描/连接/手动配置、分辨率调整、实时画面（帧率可选+自适应循环）、ws-scrcpy 远程控制（风格/主题/自适应/精简已对齐）
- **配置管理**：config.toml 编辑、连接配置、profiles 选择
- **日志面板**：时间戳/级别着色/吸底跟随/显示更多/复制/下载
- **外观**：深/浅/跟随系统主题 + 强调色
- **安全与 PWA**：访问令牌（Bearer 校验）、manifest + 图标 + service worker
- **更新管理**（2026-08-05 完成）：自动检查更新（GitHub Releases API + 6h 缓存）、设置页更新状态提示、「更新代理」配置 + 测试代理按钮（curl 实测连通/延迟/速度）、安装按钮 --force 重装语义、runMaintenance 路径修复（/api/ 前缀）
- **主界面活动与今日关卡**（2026-08-05 完成）：任务队列页顶部「今日开放」（资源关按星期轮换 + 理智 + 掉落材料中文名）+「当期活动」（`maa activity` 解析）；点击关卡智能路由——队列有「理智作战」直接填入并自动保存，否则跳快速任务填入
- **右侧实时日志面板**（2026-08-05 完成）：右侧固定栏（320px，手机端抽屉），实时更新 + 吸底跟随 + 复制/清空/收起；侧栏「实时日志」按钮主动展开；任务开始自动展开；原「日志」页删除（switchView('logs') 全部改为展开侧栏面板）
- **关卡信息自动刷新**（2026-08-05 完成）：队列页停留时每 10 分钟轮询 `/api/stages/today`，跨天自动切换；init 首次加载立即显示（无需切换标签页）
- **B 已撤销**（2026-08-05）：调研确认队列「添加任务」原生支持全部 17 类（含 Copilot/Roguelike/Reclamation/SSSCopilot/ParadoxCopilot/Custom，走 daily.json 任务文件一次执行）；此前拟加的「子命令队列化」与之重复已回退（loadQueueTypes/executeQueue/onDone 全部还原）；快速任务页为 CLI 直跑方式（URI/maa:// 代码），与队列 MaaCore 任务文件方式并存互补
- **README + 关于页**（2026-08-05 完成）：完整 README（功能/功能边界/部署/Docker 教程/架构/未来任务）+ 侧边栏「关于」页（极简 markdown 渲染，实时读根目录 README.md）
- **Docker 部署**（2026-08-05 完成）：Dockerfile（node:20-slim + adb/curl/libatomic1 + COPY README/bin/maa）、compose（代理环境变量化、宿主目录挂载 ~/.config、~/.local/share、~/.local/state、~/.cache/maa，数据无缝迁移）；已实际部署运行
- **GitHub 同步**（2026-08-05）：仓库 0sour/Maa-Web，git 凭据 store + 项目代理固定；敏感信息（内网 IP/本地路径）已清理；作者身份修正为 0sour
- **架构**：纯轮询（5s）无 SSE、静态资源版本号缓存策略、HTML 标签完整性校验（严格解析器）、jsdom + 服务端集成测试（17 个文件全绿）

## 下一步优化清单（按优先级）

### P1 功能完善（对应原版 MAA 差距）

- [x] **A 主界面活动与今日关卡**（2026-08-05 完成）
- [x] **B 快速任务队列化**（2026-08-05 撤销——队列原生已支持全部类型，无需子命令队列化）
- [ ] **C 掉落统计页**：解析日志 Drops 回调，按次/按日汇总素材掉落
- [x] **D 多配置/后置动作**（2026-08-06 完成）：队列配置快照（保存当前队列为命名配置/一键切换/删除，`config/maa-web/configs/*.json`，含关联连接 profile）；定时任务可关联队列配置（触发先 applyConfig 再执行）与后置动作；运行设置加「完成后动作」（关闭游戏 maa closedown / 休眠 / 关机，systemd 动作在容器内自动检测并提示不可用）
- [ ] **E 库存维持**：目标库存达标自动停止（`maa fight -D`）
- [x] **F 自动检查更新**（2026-08-05 完成）
- [ ] **O 抄作业作业列表展示（记录于 2026-08-05）**：
  - 需求：maa 的作业导入（maa:// 代码 / 作业集 maa://xxx s / 本地 JSON）后**可能包含多个作业任务**（作业集=多关、多作业文件），当前 web 只把 URI 填入输入框直接运行，**没有导入后作业列表的展示**（各作业关卡/说明/数量）
  - 现状：快速任务 copilot 只有「作业 URI」输入框；运行后只能在日志里看到逐关输出
  - 参考原版：CopilotViewModel 有作业列表 Tab（主线/SS/保全/悖论）+ 作业集批量拉取后逐项显示（关卡名/作者/说明），支持勾选运行
  - 实施：服务端解析作业源（maa:// 代码 → 请求作业站 PRTS 获取作业 JSON，作业集展开为列表；本地文件读取 tasks 数组）→ 前端展示作业列表（关卡/名称/作者），支持勾选后运行；与现有 URI 输入并存
  - 成本：中；价值：中（抄作业是高频功能，导入预览提升信任度）
- [ ] **Q 抄作业上传作业文件（记录于 2026-08-06）**：
  - 需求：三个自动抄作业入口（快速任务「自动抄作业」「自动抄保全作业」「自动抄悖论模拟作业」，以及任务队列的 Copilot 任务）都添加上传作业文件功能——手机/浏览器直接选择本地作业 JSON 上传到服务器（保存到 `config/copilot/`），上传后自动解析并加入作业列表（与代码导入/文件选择同等地位），无需手动把文件放到服务器路径
  - 现状：抄作业只能输入作业代码（maa:///prts://）或填写服务器上的文件路径，手机端无法直接上传本地作业文件
  - 实施：`POST /api/copilot/upload`（multipart 或 base64 JSON 上传 → 校验作业 JSON（stage_name/actions）→ 保存 `config/copilot/upload-<时间戳>.json` → 返回路径 + 解析信息）；前端三个抄作业入口加「上传作业文件」按钮（文件选择 → 上传 → 自动填入/加入列表）；队列 Copilot 上传后加入作业列表（勾选即生效）
  - 成本：低；价值：中（手机端导入本地作业的刚需路径）
- [ ] **R 修复定时任务不可用（记录于 2026-08-06）**：
  - 需求：定时任务（schedules 定时执行队列）目前处于不可用状态，需要单独找时间排查修复
  - 现状：待排查——可能原因：容器重启后 schedules 未持久化/加载、tick 补偿窗口（COMPENSATE_MS=3h）过期不触发、Docker 容器内时间/时钟问题、或 fire 时队列读取失败
  - 排查建议：查看容器日志 `[scheduler]` 输出、检查 `config/maa-web/schedules.json` 是否在容器内正确落盘、手动触发验证（接口手动 fire 或临时缩短 tick 间隔）、确认 applyConfig/runDailyQueue 链路无异常
- [ ] **S 修复公招识别不可用（记录于 2026-08-06）**：
  - 需求：公招识别（Recruit 识别任务）目前处于不可用状态，需排查修复
  - 现状：待排查——可能原因：tool 任务文件写入/读取失败、`maa run tool` 输出解析（extractRecruitResult 依赖日志格式）、词条页面判定条件（需已进入公招词条选择页且有空闲槽位）、Docker 容器内截图/OCR 环境（libatomic/资源缺失）
  - 排查建议：手动在容器内跑一次公招识别（`maa run tool` + tool.json Recruit 任务）观察输出与退出码；检查 `state/maa/logs` 中本次运行的识别日志结构是否被 `extractRecruitResult` 正确解析；确认快速任务页「公招识别」入口的提交参数
- [ ] **P 外部通知**（搁置，需额外 docker 部署，后续评估）：任务完成/失败推送（Bark/ServerChan/Telegram/Discord/Webhook）

### P1 UI/UX

- [x] **H 右侧实时日志面板**（2026-08-05 完成，见已完成）
- [x] **N 选项中文汉化（第一批）**（2026-08-05 完成，见已完成；剩余 boolMap 类选项后续补）
- [ ] **J 输入选项化（专项，大工程）**：
  - 进度：
    - [x] **第一波：作战关卡选择**（2026-08-05 完成）：快速任务/队列的「关卡」字段改为自定义搜索下拉（点击展开/输入过滤/显示理智+掉落）；数据 `/api/stages/list` 全量 532 关（limit 放宽 1000），字母开头资源关优先排序；**stages.json 来自 MaaCore 资源，服务端 mtime 检测自动重载（随 `maa update` 更新生效，无需重启）**
    - [x] **第二波：肉鸽参数选择**（2026-08-05 完成）：`/api/roguelike` 接口（分队表按主题 + 核心干员 is_start 过滤 + 难度/模式按主题动态）；快速任务「自动集成战略」的**分队/核心干员/难度/模式**全部改为搜索下拉（显示中文标签、值存 data-raw 提交、**切换主题自动清空已选**）；核心干员对齐官方逻辑（仅 is_start=true 的开局干员，排除组名/职业杂项）
    - [ ] 第三波：**队列侧 Roguelike 字段**（dailyTaskTypes 的 squad/core_char/roles 接入同一 picker）；roles（开局招募组合）数据源待定
    - [ ] 第四波：编队/客户端等其余字段
  - 回退指引：关卡选择涉及 `server/stages.js`、`server/index.js`（/api/stages/list）、`public/app.js`（buildStagePicker/loadStageOptions 及 buildQuickInput/fieldInput 的 stage 分支）；肉鸽选择涉及 `server/roguelike.js`（/api/roguelike）、`public/app.js`（buildPicker 通用组件 + squad/coreChar/difficulty/mode 分支 + theme 联动清空）
- [ ] **N 选项中文汉化（专项）**：界面英文/标识符选项替换为中文（客户端类型/肉鸽主题/无人机用途/设施/代理倍率等），值不变、显示层映射中文标签，参考 MAA 原版 zh-cn.json 词表；与 J 配合
- [x] **N 选项中文汉化（第一批）**（2026-08-05 完成）：
  - 范围：客户端类型（官服/B服/渠道服/国际服/日服/韩服）、代理倍率（不切换/AUTO/N倍）、服务器（国服/美服/日服/韩服）、额外选 Tag 模式、基建设施（制造站/贸易站/…）、无人机用途（龙门币/合成玉/…）、编队序号（默认/编队1-4）、助战使用模式、肉鸽主题（傀影/水月/萨米/萨卡兹/界园）与模式、生息演算主题/模式/连点长按、抄作业突袭模式——**值不变，显示层映射中文标签**（`[值, 标签]` 对）
  - 改动文件（**回退指引**：`git checkout` 或撤销以下文件即可部分回退）：
    1. `server/taskSchemas.js`：CLIENTS/ROGUELIKE_THEMES/RECLAMATION_THEMES 常量与 raid/supportUnitUsage/roguelike mode/reclamation 字段 options → 标签对
    2. `server/dailyTaskTypes.js`：CLIENTS 常量与 series/server/extra_tags_mode/facility/drones/formation_index/support_unit_usage/theme 字段 options → 标签对
    3. `public/app.js`：buildQuickInput select 分支 + fieldInput chips 分支支持 `[值, 标签]` 对（**回退需同时还原这两处渲染逻辑**）
  - 未覆盖：boolMap 类（凹开局期望等，hint 已有中文对照）留待后续
- [x] **K 设备状态页整合**（2026-08-06 完成）：设备页新增「实例状态」卡片——连接状态（点/设备名/序列号/触控/adb）+ 实时截图缩略（5s 轮询刷新）+ 任务运行状态 + 操作（远程控制/全屏画面/连接配置），openScrcpyWindow 抽为公共函数
- [x] **L 快速任务扩展**（2026-08-06 判定不可行）：maa-cli 0.7.5 tool 任务不支持 `Gacha`/`MiniGame` 类型（`unknown variant`），无法实现抽卡十连/小游戏刷取；等 maa-cli 后续版本支持后再评估
- [x] **M ws-scrcpy 集成优化**（2026-08-06 完成）：见专项

### P1 ws-scrcpy 远程控制优化（专项）

- 进度：
  - [x] **① 风格统一**（完成）：亮/暗/跟随系统三态对齐 maa-web 色板，URL `?theme=` 驱动；按钮/morebox/设备卡片/分隔符样式对齐
  - [x] **② 画面自适应**（完成）：fitToScreen 强制自适应；画面/触摸层等比缩放不超视口
  - [x] **③ 体验衔接**（完成）：设备列表精简、流页面隐藏列表覆盖层、.video 容器透明化
  - [x] **④ 集成方式**（完成，保持现状）：维持新标签页跳转；iframe 嵌入需反代 8000 端口且与现有 `#!/` hash 路由冲突，收益低不采用
  - [x] **⑤ 移动端细节**（完成）：流连接**断线自动重连**（3s 退避、用户主动停止不重连、重连失败持续重试）；断开/等待/就绪等状态文案汉化（`已断开连接，3 秒后自动重连…`/`连接中…`/`就绪`/`等待设备信息…`）；标题汉化（设备名 - 远程控制）；移动端工具栏布局优化（main.css 追加 media query：控件网格/按钮列/弹层适配 ≤768px）；界面主文案汉化（iOS 专有难度等保留英文，安卓主场景不涉及）
- 注意：ws-scrcpy 源码改动（断线重连/汉化）需 `npm run dist:prod` 重新构建；构建会重置 `dist/public/main.css` 移动端 patch，需重新追加（见本文件附注）；部署见 `docs/WSCRCPY.md`

### P2

- [ ] **多设备支持**：多实例并行（连接/截图/任务独立），需重构 server 连接管理
- [ ] **新手引导**：首次使用分步引导

### P3 细节

- [ ] 日志按级别过滤
- [ ] 侧栏常驻 adb 连接状态
- [ ] 截图失败自动重试与降级提示
- [ ] 队列运行错误自动重试策略
- [ ] 掉落/仓库趋势图（canvas 折线）

## 参考项目

- MaaAssistantArknights 原版客户端源码（差距分析依据）
- MXU 与 maa-cli-webui：UI/交互参考
- ws-scrcpy：远程控制（独立服务 8000 端口，maa-web 集成跳转）

## 测试与部署

- 回归（开发环境）：`for t in ui-device ui-runner ui-screen ui-queue-checkbox ui-new-fields ui-results ui-schedule ui-queue-v2 ui-poll ui-mxu ui-scrcpy ui-token ui-quick ui-autosave; do timeout 90 node $t-test.js 2>ui-token ui-quick ui-autosave; do echo "== $t =="; timeout 90 node $t-test.js 2>&1 | tail -1; done && timeout 90 node server-api-test.js 2>&1 | tail -1`1 | tail -1; done; timeout 90 node server-api-test.js 2>ui-token ui-quick ui-autosave; do echo "== $t =="; timeout 90 node $t-test.js 2>&1 | tail -1; done && timeout 90 node server-api-test.js 2>&1 | tail -1`1 | tail -1`
- 前端改动后更新 `public/index.html` 资源版本号并重启：`PORT=3100 node server/index.js`（paseo 终端 2b6b9f2f）
- HTML 改动后跑标签完整性校验（Python 严格解析器）
- ws-scrcpy 服务：`<ws-scrcpy 目录>/dist`，`PATH=<项目目录>/bin/platform-tools:$PATH node ./index.js`
