# Maa-Web · 产品需求文档（PRD）

> 版本：v0.3.0 ｜ 更新日期：2026-08-14 ｜ 状态：规划中（M2 已实现，M3/M4 部分实现，见 §4.5 实现进度总览）
> 本 PRD 依据 MAA 客户端**源码**（`参考/MaaAssistantArknights`）逐项核对功能，保证桌面客户端全部能力进入 Web 控制台开发规划。
> 界面实现契约见 [UI 设计规范](../ui-design/design-system-arknights.md)（明日方舟主题）与 [组件画廊](../ui-design/07-component-gallery.html)。

---

## 1. 需求背景

MAA（MaaAssistantArknights）是基于图像识别的明日方舟游戏小助手，可一键完成全部日常任务。桌面版（WPF）功能完整，但存在两个痛点：

1. **无法无人值守**：需要 Windows 桌面常驻运行，模拟器与 MAA 必须同机。
2. **无法远程控制**：用户离开电脑就无法查看进度、调整任务、接收通知。

Maa-Web 将 MAA 引擎（MaaCore / Asst 核心）封装进 Docker 容器，部署在 NAS 上 7×24 小时运行，通过浏览器（Web 控制台）远程完成全部任务配置、调度与监控。本项目本质是「MAA 桌面客户端的 Web 化重实现」，因此**功能覆盖以桌面客户端为基准，不缩减**。

## 2. 目标与成功标准

| 维度 | 目标 |
|------|------|
| 功能覆盖 | Web 控制台功能与 MAA 桌面客户端逐项对齐，无缺失（见 §4 功能映射表） |
| 部署体验 | `docker compose up -d` 后 5 分钟内可连接模拟器开始任务 |
| 远程可用 | 浏览器（桌面/手机）均可用，局域网内延迟 < 500ms 指令反馈 |
| 无人值守 | 支持定时执行 + 任务失败自动重试 + 通知推送，连续运行 7×24 |
| 多架构 | ARM64（NAS 常见）+ AMD64 双架构镜像 |

## 3. 用户与场景

**核心用户**：拥有 NAS 的明日方舟玩家，日常需要长时间挂机刷理智、基建换班、肉鸽刷分。

**典型场景**：

1. 周一早高峰前，手机上打开控制台勾选「日常六件套」，NAS 自动执行到下班。
2. 出差在外，收到「高级资深干员」公招通知，打开手机查看并手动确认。
3. 新活动上线，导入作业站神秘代码，远程启动自动战斗抄作业。
4. 周末在家，用控制台的「窥屏」功能实时查看模拟器画面。

## 4. 功能需求（与 MAA 桌面端逐项对齐）

> 功能编号规则：`D-日常 / T-工具箱 / C-连接 / S-系统`。来源标注对应 MAA 官方文档章节。

### 4.1 功能总览表

#### A. 核心任务模块（对应 AsstAppendTask 任务类型）

| # | 功能 | 说明 | MAA 来源 |
|---|------|------|---------|
| D-01 | 开始唤醒 StartUp | 启动模拟器、启动客户端、进入游戏、账号切换（`AccountName` + `AccountSwitchEnabled`） | 源码 `StartUpTask.cs` |
| D-02 | 关闭游戏 CloseDown | 关闭游戏客户端 | 源码 `MaaService.cs` |
| D-03 | 理智作战 Fight | 关卡导航、吃理智药、碎石、指定次数/材料、**库存目标模式**、代理倍率、掉落识别上传、崩溃重启、博朗台碎石、**关卡计划列表/备选关卡/周计划** | 源码 `FightTask.cs` |
| D-04 | 公开招募 Recruit | 自动公招、加急许可、3/4/5/6 星选择与时限、首选标签、保留标签、三星刷新策略 | 源码 `RecruitTask.cs` |
| D-05 | 基建换班 Infrast | 默认/自定义排班/一键轮换三模式、9 设施房间开关、无人机用途、心情阈值、源石碎片补货、宿舍、会客室线索、**继续专精** | 源码 `InfrastTask.cs` |
| D-06 | 信用购物 Mall | 访问好友基建、优先购买、黑名单、信用溢出强购、仅购折扣、OF-1 信用战、**「一天仅一次」限制** | 源码 `MallTask.cs` |
| D-07 | 领取奖励 Award | 每日/每周任务、邮件、免费单抽、幸运墙、开采许可、月卡奖励 | 源码 `AwardTask.cs` |
| D-08 | 肉鸽刷分 Roguelike | 5 主题（傀影/水月/萨米/萨卡兹/界园）、**9 模式（刷分/刷锭/凹开局/坍缩范式/月度小队/深入调查/常乐节点等）**、种子刷钱 | 源码 `RoguelikeTask.cs` |
| D-09 | 自动战斗 Copilot | 抄作业（主线/故事集/SS、保全派驻、悖论模拟、其他活动**4 个场景页签**）、作业 JSON 导入、神秘代码、自动编队（含使用编队/忽略要求/助战/追加干员）、战斗列表、循环次数 | 源码 `MaaService.cs` + `CopilotView.xaml` |
| D-10 | 生息演算 Reclamation | **3 主题（沙中之火/沙洲遗闻/重启锚点）+ 4 模式（无存档刷点/存档制造/RA-1/RA-4/RA-15）+ 制造工具/清空商店** | 源码 `ReclamationTask.cs` |
| D-11 | 自定义任务 Custom | 指定任务名执行自定义 JSON 流程 | 源码 `CustomTask.cs` |
| D-12 | 数据更新 UserDataUpdate | 定时更新干员盒/仓库数据（**触发间隔**：每次/固定周期） | 源码 `UserDataUpdateTask.cs` |
| D-13 | 仓库保持 DepotMaintain | 库存保持：**多 Plan（关卡+材料+数量+药/石）+ 活动期间跳过 + 临期药** | 源码 `DepotMaintainTask.cs` |
| D-14 | 单步任务 SingleStep | 单步执行（当前仅支持战斗） | 源码 `MaaService.cs` |
| D-15 | 小游戏 MiniGame | 识别并完成游戏内小游戏（**像素画 PixelPaint：图片导入/适配/抖动/色彩滑块/涂白/滑动；隐秘战线：结局+事件选择**） | 源码 `AsstProxy.cs TaskType` + `ToolboxView.xaml` |

#### B. 工具箱模块（对应 MAA 工具箱 Tools）

| # | 功能 | 说明 | MAA 来源 |
|---|------|------|---------|
| T-01 | 公招识别 | 手动识别公招界面，高星标签展示、结果确认、自动设时、显示潜能、自动选择 3/4/5/6 星标签 | 源码 `ToolboxViewModel` |
| T-02 | 干员识别 | 识别已有/未有干员及潜能，供公招识别参考、导出 | 源码 `ToolboxViewModel` |
| T-03 | 仓库识别 | 识别养成材料，导出至企鹅物流/工具箱/ARK-NIGHTS | 源码 `ToolboxViewModel` |
| T-04 | 任务视频识别 | 拖入战斗视频自动生成作业 JSON（源码中已注释，标注为不可用） | 源码 `MaaService.cs` |
| T-05 | 抽卡 | 单抽/十连、截图展示、免责声明 | 源码 `ToolboxViewModel` |
| T-06 | 窥屏 | 按目标帧率实时展示模拟器画面（FPS 检测与提示） | 源码 `AsstProxy.cs` |

#### C. 连接与设备模块（对应连接设置）

| # | 功能 | 说明 | MAA 来源 |
|---|------|------|---------|
| C-01 | 设备管理 | ADB 设备增删改查、地址端口配置、连接状态监控 | 源码 `ConnectSettingsUserControlModel` |
| C-02 | 模拟器检测 | 自动/常驻检测局域网模拟器（BlueStacks/MuMu12/雷电/夜神/逍遥/WSA 等 13 种连接预设） | 源码 `ConnectConfigList` |
| C-03 | 触控模式 | Minitouch / MaaTouch / MuMu 增强 / 兼容等模式切换 | 源码 `TouchModeList` |
| C-04 | 自动启动模拟器 | ADB 连接失败时尝试启动模拟器 | 源码 `AsstProxy.cs` |

#### D. 系统功能模块（对应 GUI 层能力）

| # | 功能 | 说明 | MAA 来源 |
|---|------|------|---------|
| S-01 | 任务编排 | 拖拽排序任务、勾选启用、右侧半选「仅一次」、一键长草 LinkStart、Stop/WaitAndStop、自动重载资源、任务右键菜单（运行一次/复制/重命名/删除）、全选/反选、悬浮窗、托盘菜单、主窗口置顶/标题滚动 | 源码 `TaskQueueViewModel` |
| S-02 | 定时执行 | 按时间点/周期自动执行任务组合，支持强制启动/显示窗口/自定义配置 | 源码 `TimerSettingsUserControlModel` |
| S-03 | 脚本钩子 | 任务开始前/结束后执行自定义脚本（Copilot 单独开关） | 源码 `ConfigConverter.cs` |
| S-04 | ~~配置管理~~（已裁掉） | ~~多配置保存/切换（对应 gui.json 多配置）、启动时自动切换配置~~——2026-08-14 用户决定：多用户需求走数据分离，不做配置切换 | 源码 `ConfigFactory` |
| S-05 | 日志中心 | 实时日志流（分级/卡片式）+ 日志压缩包导出（问题反馈） | 源码 `AsstProxy` + `IssueReport` |
| S-06 | 通知推送 | 9 种通道：**ServerChan/Telegram/Discord/钉钉/SMTP/Bark/Qmsg/Gotify/自定义Webhook**；完成/错误/卡死触发 | 源码 `ExternalNotificationSettings` |
| S-07 | 自动更新 | 资源包与版本 OTA 更新、拖入压缩包更新 | 源码 `MaaUpdater` |
| S-08 | 外服支持 | 客户端类型：官方/B服/taptap/美/日/韩/繁中 | 源码 `ClientType` |
| S-09 | GPU 加速 | DirectML 推理加速开关（含 GPU 黑名单） | 源码 `GpuOption.cs` |
| S-10 | ~~远程控制协议~~（已裁掉） | ~~轮询远端获取任务 + 上报状态~~——2026-08-14 用户决定：NAS 端口访问即远程控制，客户端协议（手机端控制 PC）场景不适用 | 源码 `RemoteControlService.cs` |
| S-12 | ~~桌面专属设置~~ | 启动设置/GUI 窗口类/背景壁纸/全局热键/GPU 加速（DirectML 仅 Windows）——NAS/Web 部署不适用，**不实现** | 源码对应 UserControl |
| S-11 | ~~成就系统~~（已裁掉） | ~~任务使用成就跟踪~~——2026-08-14 用户决定：客户端成就多为 UI 交互类，与 WebUI 交互不一致 | 源码 `AchievementTrackerHelper.cs` |

### 4.2 核心模块详细需求

#### 4.2.1 D-03 理智作战（P0）

**业务逻辑**（字段对应源码 `FightTask.cs`）：

- 支持关卡导航：主线（`-NORMAL/-HARD` 切换难度）、资源本（CE-6/LS-6/CA-5/AP-5/SK-5）、芯片本（PR-A-1）、剿灭（Annihilation 系列，支持自定剿灭关卡 `UseCustomAnnihilation`）、别传（OF-1/OF-F3）、当期 SS 后三关、复刻 SS（SSReopen-前缀）。
- **关卡计划列表 `StagePlan`**：从上往下选择第一个可用关卡，支持备选关卡 `UseOptionalStage`；手动输入关卡 `IsStageManually`；隐藏不可用关卡 `HideUnavailableStage`。
- **周计划 `UseWeeklySchedule`**：按星期几开关每日执行（Dictionary<DayOfWeek, bool>）。
- 四个停止条件（短路开关，任一达到即完成）：吃理智药次数 / 碎石次数 / 指定作战次数 / 指定材料数量。
- **库存目标模式 `IsInventoryTarget`**：指定材料按仓库库存目标计算（配合 D-13 仓库保持）。
- 理智耗尽处理：可吃理智药（`UseExpiringMedicine` 临期药 + `MedicineExpireDays` 指定过期天数）、可碎石（`UseStoneAllowSave` 允许保存碎石状态）、可启用「博朗台模式」`IsDrGrandet`（碎石前等待自然恢复 1 点）。
- 代理倍率 `Series`：-1 禁用切换 / 0 自动最大 / 1~10 指定（国服新列表）；可隐藏 `HideSeries`；外服上限受资源版本限制。
- 掉落识别：自动识别掉落并上传企鹅物流 / 一图流（需配置报告 ID）。
- 崩溃恢复：配置 `client_type` 后，游戏崩溃自动重启客户端并续刷。
- 支持未勾选「代理指挥」时自动勾选。

**交互逻辑**：任务编排页 → 展开「刷理智」卡片 → 关卡列表（可多选备选）→ 理智药/石头/次数/材料 → 周计划开关 → 保存到当前配置 → 一键启动。

**边界与异常**：

- 理智药不足、石头不足、现有理智也不足 → 不刷图自动结束。
- 第六关无法代理 → 自动切换第五关（仅 CE/LS）。
- 复刻 SS 一次性刷完 XX-1~XX-9。
- 指定材料与关卡选择互相独立（指定材料只是完成依据，不导航关卡）。

#### 4.2.2 D-04 公开招募（P0）

**业务逻辑**：

- 自动公招：自动选择/确认标签（`select`/`confirm` 按星级数组）、支持刷新三星标签、支持加急许可（无限或指定次数）。
- 首选标签 `first_tags`：3 星时强制多选指定标签。
- 保留标签 `preserve_tags`：识别到指定标签（如「支援机械」）保留槽位跳过本次。
- 招募时限 `recruitment_time`：按星级设置希望时限（默认 540 分钟）。
- 公招数据自动上传企鹅物流 / 一图流。
- 出现 1/5/6 星标签 → 触发通知（S-06）。

**交互逻辑**：任务编排页 → 「公开招募」卡片 → 标签策略设置 → 自动确认/手动确认切换 → 启动。

**边界与异常**：

- 仅计算不招募：`times=0` + `confirm=[]`。
- 加急许可用尽后按普通流程继续。

#### 4.2.3 D-05 基建换班（P0）

**业务逻辑**：

- 三种模式：默认（单设施最优解）/ 自定义（读取用户排班 JSON，`mode=10000`）/ 一键轮换（`mode=20000`，跳过中枢/发电站/宿舍/办公室）。
- 设施有序数组：`Mfg` 制造 / `Trade` 贸易 / `Power` 发电 / `Control` 控制中枢 / `Reception` 会客室 / `Office` 办公室 / `Dorm` 宿舍 / `Processing` 加工站 / `Training` 训练室。
- 无人机用途：Money/SyntheticJade/CombatRecord/PureGold/OriginStone/Chip。
- 心情阈值 `threshold`（0~1.0，默认 0.3）。
- 贸易站「源石碎片」自动补货；宿舍「未进驻」选项；宿舍剩余位置填入信赖未满干员。
- 会客室：领取信息板信用、线索交流、赠送线索（三个独立开关）。
- 自定义排班需支持 MAA「基建排班协议」JSON 格式导入（`filename` + `plan_index`）。

**交互逻辑**：任务编排页 → 「基建换班」卡片 → 设施排序（拖拽）→ 模式选择 → 参数配置 → 保存。

#### 4.2.4 D-06 信用购物（P0）

**业务逻辑**：

- 三轮购买逻辑：按 `buy_first` 顺序购买 → 从左到右避开 `blacklist` 购买 → 信用溢出时无视黑名单继续购买。
- `visit_friends`：访问好友基建获取信用。
- `only_buy_discount`：第二轮仅购买折扣物品。
- `reserve_max_credit`：信用 < 300 停止购买（第二轮）。
- `credit_fight`：借助战打一局 OF-1 获取次日信用，可指定编队栏位（0-4）。

#### 4.2.5 D-07 领取奖励（P0）

**业务逻辑**：每日/每周任务奖励、全部邮件、限定池免费单抽、幸运墙合成玉、限时开采许可合成玉、五周年月卡奖励 —— 六个独立开关组合。

#### 4.2.6 D-08 肉鸽刷分（P1）

**业务逻辑**（字段对应源码 `RoguelikeTask.cs`）：

- 主题：Phantom（傀影）/ Mizuki（水月）/ Sami（萨米）/ Sarkaz（萨卡兹）/ JieGarden（界园）。
- **9 模式**：0 刷分（稳定高层）/ 1 刷源石锭（一层投资即退）/ 4 凹开局（指定难度+期望奖励）/ 5 刷坍缩范式（萨米，期望列表命中即停）/ 6 月度小队 / 7 深入调查 / **20001 常乐节点（界园，第一层进洞找指定节点，找不到重开，目标节点子类型：令/黍/年）**。
- 开局配置：分队、烧水分队 `SquadCollectible`、职业组、核心干员（中文名）、助战开关（含非好友助战）。
- 停止条件：探索次数上限 / 刷满等级 / 投资次数上限 / 投资满 / 指定坍缩范式 / 期望开局奖励命中 / 最终 Boss 前停。
- 主题特有：萨米密文板（一层远见板子/生活队凹板子）、坍缩范式、水月骰子刷商店、烧水购物、**种子刷钱 `StartWithSeed`+`Seed`**。
- 其他：月度小队自动切换、深入调查自动切换、难度指定（未解锁取最高）、凹开局精二直升 `StartWithEliteTwo`。

**交互逻辑**：任务编排页 → 「肉鸽」卡片 → 主题 Tab → 模式选择 → 开局配置 → 停止条件 → 启动。

#### 4.2.7 D-09 自动战斗 Copilot（P1）

**业务逻辑**（场景对应源码 `AsstTaskType` 三种任务类型 + CopilotView 四个场景页签）：

- 场景页签：`MainStageStoryCollectionSideStory`（主线/故事集/SS，当前章节内导航）、`SSS`（保全派驻，可循环次数）、`ParadoxSimulation`（悖论模拟，单次/多干员连续、按职业找人、跳过未拥有干员）、`OtherActivityStage`（其他活动关卡）。
- 作业导入：本地 JSON 文件 / 作业站神秘代码（prts.plus）。
- 自动编队：清空当前编队按作业需求自动编队；可追加自定干员（干员名/技能等级/模组，DataGrid 编辑）、补充低信赖干员；悖论模拟必须关闭自动编队手动选技能。
- 高级选项：使用编队方案（UseFormation + 编队下拉）、忽略作业要求（IgnoreRequirements）、助战使用（SupportUnitUsage + 下拉）、战斗列表（UseCopilotList）、理智药（UseSanityPotion）。
- 战斗列表：批量导入、添加关卡、清空关卡、拖拽排序、勾选执行；理智不足/战斗失败/非三星结算时停止队列。
- 循环次数设置（Loop/LoopTimes 0-9999）。
- 演习模式支持。

**交互逻辑**：作业页 → 导入/粘贴代码 → 场景选择 → 战斗列表配置 → 启动。

#### 4.2.8 D-10 生息演算（P2）

**业务逻辑**（字段对应源码 `ReclamationTask.cs`）：

- **3 主题**：`Fire`（沙中之火）/ `Tales`（沙洲遗闻）/ `RelaunchAnchor`（重启锚点）。
- **4 模式**（Flags 组合）：`ProsperityNoSave` 无存档刷点数（进出关卡）/ `ProsperityInSave` 存档制造刷点数（默认制造荧光棒，可指定道具 `ToolToCraft`）/ `RA1` / `RA4` / `RA15` 重启锚点循环（需前置通关与配队）。
- `MaxCraftCountPerRound` 单次最大制造轮数、`ClearStore` 商店购物开关。
- 当前为早期支持，暂不推荐无人值守。

#### 4.2.9 D-11 自定义任务（P2）

**业务逻辑**：允许用户指定任务名 `CustomTaskName` 执行自定义 JSON 流程（对应 Custom 任务类型），高级用户使用。

#### 4.2.10 D-12 数据更新（P1）

**业务逻辑**（源码 `UserDataUpdateTask.cs`）：更新干员盒 `UpdateOperBox` + 仓库 `UpdateDepot` 数据，触发间隔 `TriggerInterval`（每次/固定周期），为干员识别/仓库识别/库存保持提供数据基础。

#### 4.2.11 D-13 仓库保持（P1）

**业务逻辑**（源码 `DepotMaintainTask.cs`）：库存保持任务，维护目标材料库存数量。

- 多 Plan：每个 Plan 指定 关卡+材料+目标数量+用药/用石数量。
- 选项：`SkipDuringActivity` 活动期间跳过、`SkipDuringResourceCollection` 资源全开放期间跳过、`UseAutoSeries` AUTO 代理倍率、`UseMedicine/UseStone` 开关、`UseExpiringMedicine` 使用 48h 临期药（固定 2 天阈值）。
- 依赖 T-03 仓库识别结果判断当前库存。

#### 4.2.12 T-01~T-06 工具箱（P1/P2）

- 公招识别：进入公招标签界面 → 一键识别 → 展示高星标签与推荐 → 支持结果确认、自动设时。
- 干员识别：识别干员列表（含潜能），数据供公招识别联动展示，支持导出。
- 仓库识别：自动进入仓库（升级材料页）→ 滚动识别 → 导出企鹅物流/工具箱/ARK-NIGHTS。
- 视频识别：源码中已注释（官方弃用），**标注为不可用，不进入开发规划**。
- 抽卡：单抽/十连（限时寻访）→ 截图展示 → 免责声明确认。
- 窥屏：按目标帧率实时展示模拟器画面，FPS 检测与提示，帧率不足自动降频。

#### 4.2.13 S-02 定时执行（P1）

**业务逻辑**：任务组合 + 执行计划（每天 N 点 / 每周某日 / 间隔），到点自动启动任务队列，支持「启动时自动切换配置」、`ForceScheduledStart` 强制启动、`ShowWindowBeforeForceScheduledStart`、`CustomConfig`。

#### 4.2.14 S-06 通知推送（P1）

**业务逻辑**：事件 → 通知通道。触发事件：任务完成（可带详情）、任务错误、任务卡死。**9 种通道**（与源码一致）：ServerChan / Telegram / Discord / 钉钉 / SMTP / Bark / Qmsg / Gotify / 自定义 Webhook。支持发送测试消息。

#### 4.2.15 S-10 远程控制协议（P1）

**业务逻辑**（源码 `RemoteControlService.cs`，**内置协议，Maa-Web 后端天然实现服务端**）：

- 轮询 GET 任务：POST `{user, device}` → 远端返回 `tasks` 数组，每条含 `type/id/params`。
- 任务类型：`LinkStart` 系列（一键长草/基建/唤醒/战斗/公招/信用/任务/肉鸽/生息）、`Toolbox-GachaOnce/GachaTenTimes`、`CaptureImage`、`HeartBeat`、`StopTask`、`Settings-ConnectAddress`、`Settings-Stage1`。
- 顺序任务队列 + 即时任务队列分离。
- 上报状态：POST `{user, device, status, task, payload}`，`SUCCESS/FAILED`，截图以 Base64 返回。
- Maa-Web 可将 Web 控制台直接映射为该协议的服务端，实现「Web 下发任务 → 引擎执行 → 回传截图/状态」。

#### 4.2.16 S-05 日志中心（P1）

**业务逻辑**：WebSocket 实时推送任务执行日志（对应 MAA 回调消息协议），支持日志分级过滤、搜索、卡片式展示、导出压缩包（问题反馈用）。

### 4.3 任务用户可调整选项（源码 `TaskQueue` ViewModel + XAML 提取）

> 以下为 MAA 桌面端每个任务在 UI 上暴露的全部可调项，并标注**控件类型**（还原客户端操作逻辑）。Web 控制台参数面板必须逐一覆盖同样的控件语义。

#### 控件类型速查（MAA XAML → Web 控件映射）

| MAA 控件 | 操作逻辑 | Web 控件 |
|----------|---------|---------|
| `CheckBox`（支持右键半选「仅一次」） | 勾选/取消；右键 → 临时生效一次 | 开关 / 复选框 |
| `hc:NumericUpDown` | 数字微调（带上下箭头，有最小/最大值） | 数字输入框 |
| `ComboBox / hc:ComboBox` | 下拉单选 | 下拉选择栏 |
| `hc:ComboBox + MakeComboBoxSearchable` | 下拉 + 可输入过滤 | 可搜索下拉选择栏 |
| `hc:CheckComboBox`（多选下拉） | 下拉展开勾选多项 | 多选下拉 |
| `TextBox / hc:TextBox`（含 Placeholder） | 自由文本填空 | 输入框（带占位符） |
| `ListBox`（可拖拽 + 删除按钮） | 列表项拖拽排序 / 增删 | 拖拽列表 |
| `hc:ButtonGroup + RadioButton` | 单选按钮组（互斥） | 单选组 |
| `Slider` | 滑动条选值（带百分比显示） | 滑块 |
| `Button` | 触发动作（如文件选择） | 按钮 |
| `hc:SplitButton` | 主按钮 + 下拉附加动作 | 拆分按钮 |
| `TabControl / TabItem` | 页签切换 | 页签 |
| `hc:TextBox + ShowEyeButton` | 密文输入 + 可见性切换 | 密码输入框 |

#### 4.3.1 开始唤醒（`StartUpSettingsUserControlModel` / `StartUpTaskUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| AccountSwitchEnabled | CheckBox | 启用账号切换 |
| AccountName | TextBox | 切换账号名（官方/B服支持片段匹配），启用开关后可用 |
| 手动切换账号 | Button | 单独执行一次账号切换（不跑完整唤醒） |

#### 4.3.2 理智作战（`FightSettingsUserControlModel` / `FightSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| StagePlan | ListBox（拖拽+删除） | 关卡计划列表，多关卡从上到下选第一个可用；每项关卡选择用 ComboBox（可选搜索）或 TextBox（手动输入）二选一 |
| CustomStageCode | CheckBox | 切换关卡输入方式：下拉选择 ↔ 手动输入 |
| UseMedicine / MedicineNumber | CheckBox + NumericUpDown | 使用理智药 / 数量（0-999） |
| UseStone / StoneNumber / AllowUseStoneSave | CheckBox + NumericUpDown + CheckBox | 碎石 / 数量（0-999）/ 允许保存碎石状态 |
| HasTimesLimited / MaxTimes | CheckBox + NumericUpDown | 启用次数限制 / 最大次数（0-999） |
| Series | ComboBox（运行中禁用） | 代理倍率下拉（-1 禁用切换 / 0 自动 / 1-10 指定） |
| HideSeries | CheckBox | 隐藏代理倍率下拉 |
| IsSpecifiedDrops / DropsItemId / DropsQuantity | CheckBox + 可搜索 ComboBox + NumericUpDown | 指定掉落材料（可搜索选择）/ 数量 |
| UseDropQuantityMode / UseTargetInventoryMode | RadioButton 组（ButtonGroup） | 指定数量模式 / 目标库存模式切换 |
| UseInventoryTarget | 状态显示 | 库存目标模式（显示当前库存/有效数量文本，运行时锁定） |
| UseCustomAnnihilation / AnnihilationStage | CheckBox + ComboBox | 自定剿灭关卡 |
| IsDrGrandet | CheckBox | 博朗台碎石模式 |
| UseAlternateStage | CheckBox | 使用备选关卡（开启后 StagePlan 支持多关卡） |
| UseExpiringMedicine / MedicineExpireDays | CheckBox + ComboBox | 临期药 / 过期天数下拉（2/3/5/7） |
| UseExpireMedicineForActivity | CheckBox | 活动也用临期药 |
| HideUnavailableStage | CheckBox | 隐藏不可用关卡 |
| UseWeeklySchedule | CheckBox + ListBox | 周计划（展开 7 天 CheckBox 列表） |
| StageResetMode | ComboBox | 关卡重置模式下拉 |
| AutoRestartOnDrop | CheckBox | 掉落异常自动重启 |

#### 4.3.3 公开招募（`RecruitSettingsUserControlModel` / `RecruitSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| RecruitMaxTimes | NumericUpDown | 单轮最大公招次数（默认 4） |
| UseExpeditedWithNull | CheckBox | 使用加急许可 |
| SelectExtraTags | ComboBox | 多 Tag 策略下拉：0 默认 / 1 选 3 个 / 2 只选稀有 |
| AutoRecruitFirstList / UseLevel3PreferTags | CheckBox + CheckComboBox | 3 星首选 Tag 多选下拉 / 启用 |
| AutoRecruitPreserveTagList / PreserveTagEnabled | CheckBox + CheckComboBox | 保留并跳过 Tag 多选下拉 / 启用 |
| RefreshLevel3 | CheckBox | 无倾向 Tag 时刷新 3 星 |
| ForceRefresh | CheckBox | 无招聘许可仍刷新 |
| ChooseLevel3 / Level3Time | CheckBox + NumericUpDown | 自动确认 3 星 / 时长 |
| ChooseLevel4 / Level4Time | CheckBox + NumericUpDown | 自动确认 4 星 / 时长 |
| ChooseLevel5 | CheckBox | 自动确认 5 星（固定 9:00 展示） |
| ChooseLevel6 | CheckBox | 自动确认 6 星（界面不可改，仅配置） |

#### 4.3.4 基建换班（`InfrastSettingsUserControlModel` / `InfrastSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| InfrastRoomModels | ListBox（CheckBox 项） | 设施房间列表（勾选启用 + 拖拽排序） |
| UsesOfDrones | ComboBox | 无人机用途下拉 |
| DormThreshold | Slider（百分比显示） | 心情阈值滑块（30 = 0.3） |
| DormFilterNotStationedEnabled | CheckBox | 不将已进驻干员放入宿舍 |
| DormTrustEnabled | CheckBox | 宿舍空位补信赖未满干员 |
| OriginiumShardAutoReplenishment | CheckBox | 制造站搓玉自动补货 |
| ReceptionMessageBoardReceive | CheckBox | 会客室板子领取信用 |
| ReceptionClueExchange | CheckBox | 会客室线索交换 |
| ReceptionSendClue | CheckBox | 赠送线索 |
| ContinueTraining | CheckBox | 继续专精训练 |
| DefaultInfrast / CustomInfrastFile | ComboBox + 文件选择 | 默认排班 / 自定义 JSON 文件路径（ComboBox 选择 UserDefined 后启用文件选择） |
| CustomInfrastPlanSelect / CustomPlanListDisplay | ComboBox | 自定义方案序号（A/B/C…） |

#### 4.3.5 信用购物（`MallSettingsUserControlModel` / `MallSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| CreditShopping | CheckBox | 是否购物 |
| CreditFirstList | TextBox | 优先购买列表（逗号分隔） |
| CreditBlackList | TextBox | 黑名单列表（逗号分隔） |
| CreditForceShoppingIfCreditFull | CheckBox | 信用溢出时无视黑名单 |
| CreditOnlyBuyDiscount | CheckBox | 只买折扣物品 |
| CreditReserveMaxCredit | CheckBox | 信用 <300 停止购物 |
| CreditVisitFriendsEnabled / CreditVisitOnceADay | CheckBox + CheckBox | 访问好友 / 一天仅一次 |
| CreditFightTaskEnabled / CreditFightOnceADay / CreditFightSelectFormation | CheckBox + CheckBox + ComboBox | OF-1 信用战 / 一天仅一次 / 编队选择 |

#### 4.3.6 肉鸽刷分（`RoguelikeSettingsUserControlModel` / `RoguelikeSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| RoguelikeTheme | ComboBox | 主题下拉（5 项） |
| RoguelikeMode | ComboBox | 模式下拉（7 项） |
| RoguelikeDifficulty | ComboBox | 难度下拉 |
| RoguelikeSquad | 可搜索 ComboBox | 开局分队（可搜索过滤） |
| RoguelikeCollectibleModeSquad | 可搜索 ComboBox | 烧水分队 |
| RoguelikeRoles | 可搜索 ComboBox | 开局职业组 |
| RoguelikeCoreChar | 可搜索 ComboBox | 核心干员（可搜索选择） |
| RoguelikeStartsCount | NumericUpDown | 开始探索次数 |
| RoguelikeInvestmentEnabled / RoguelikeInvestsCount | CheckBox + NumericUpDown | 投资开关 / 次数 |
| RoguelikeInvestmentWithMoreScore | CheckBox | 投资后购物刷分（仅投资模式显示） |
| RoguelikeCollectibleModeShopping | CheckBox | 烧水购物 |
| RoguelikeRefreshTraderWithDice | CheckBox | 骰子刷新商店（水月） |
| RoguelikeStartWithEliteTwo / OnlyStartWithEliteTwo | CheckBox + CheckBox | 凹精二直升（职业分队才显示） |
| RoguelikeExpectedCollapsalParadigms | TextBox | 期望坍缩范式（萨米模式 5） |
| Roguelike3FirstFloorFoldartal / ...Foldartals | CheckBox + TextBox | 萨米刷一层远见板子 |
| Roguelike3NewSquad2StartingFoldartal / ...Foldartals | CheckBox + TextBox | 萨米生活队凹开局板子 |
| RoguelikeUseSupportUnit / RoguelikeEnableNonfriendSupport | CheckBox + CheckBox | 助战 / 非好友助战 |
| RoguelikeStopWhenInvestmentFull | CheckBox | 投资满停止 |
| RoguelikeStopAtFinalBoss | CheckBox | 最终 Boss 前停止 |
| RoguelikeStopAtMaxLevel | CheckBox | 等级刷满停止 |
| RoguelikeMonthlySquadAutoIterate / CheckComms | CheckBox + CheckBox | 月度小队自动切换 / 刷通讯 |
| RoguelikeDeepExplorationAutoIterate | CheckBox | 深入调查自动切换 |
| RoguelikeFindPlaytimeTarget | ComboBox | 常乐节点目标（令/黍/年，仅界园+常乐模式） |
| RoguelikeDelayAbortUntilCombatComplete | CheckBox | 战斗完成后再中止 |
| RoguelikeStartWithSeed / RoguelikeSeed | CheckBox + TextBox | 种子刷钱 |

#### 4.3.7 生息演算（`ReclamationSettingsUserControlModel` / `ReclamationSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| Theme | ComboBox | 主题下拉（3 项） |
| Mode | ComboBox | 模式下拉（5 项） |
| ReclamationToolToCraft | TextBox | 制造道具（默认荧光棒） |
| ReclamationIncrementMode | ComboBox | 增量模式下拉 |
| ReclamationMaxCraftCountPerRound | NumericUpDown | 单次最大制造轮数（默认 16） |
| ReclamationClearStore | CheckBox | 清空商店购物 |

#### 4.3.8 领取奖励（`AwardSettingsUserControlModel` / `AwardSettingsUserControl.xaml`）

ReceiveAward / ReceiveMail / ReceiveFreeGacha（启用需确认弹窗）/ ReceiveOrundum / ReceiveMining / ReceiveSpecialAccess —— 六个独立 CheckBox。

#### 4.3.9 数据更新（`UserDataUpdateSettingsUserControlModel` / `UserDataUpdateSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| UpdateOperBox | CheckBox | 更新干员盒 |
| UpdateDepot | CheckBox | 更新仓库 |
| TriggerInterval | ComboBox | 触发间隔下拉（每次 / 固定周期） |

#### 4.3.10 仓库保持（`DepotMaintainTaskUserControlModel` / `DepotMaintainTaskUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| PlanList（每条） | ListBox（拖拽+删除）+ 关卡 ComboBox/TextBox + 材料可搜索 ComboBox + NumericUpDown × 4 | 库存保持多 Plan：关卡 + 目标材料 + 数量 + 用药/用石数量 |
| 预设 | SplitButton | 常用刷取预设一键填充 Plan |
| SkipDuringActivity | CheckBox | 活动期间跳过整个任务 |
| SkipDuringResourceCollection | CheckBox | 资源全开放期间跳过 |
| UseAutoSeries | CheckBox | 使用 AUTO 代理倍率 |
| UseMedicine / UseStone | CheckBox + CheckBox | 全局启用用药 / 用石 |
| UseExpiringMedicine | CheckBox | 使用 48h 临期药 |

#### 4.3.11 后置动作（`PostActionSetting` / `PostActionUserControl.xaml`）

> 任务队列完成后执行的收尾动作，位于任务列表下方独立面板。所有动作支持 CheckBox 右键 → 「仅一次」（本次执行后自动复位）。

| 选项 | 控件 | 说明 |
|------|------|------|
| Once | CheckBox | 仅执行一次（后置动作全部临时生效一次） |
| BackToAndroidHome | CheckBox（可仅一次） | 返回 Android 桌面（需 Android 控制动作） |
| ExitArknights | CheckBox（可仅一次，与 ExitEmulator 互斥） | 退出明日方舟游戏 |
| ExitEmulator | CheckBox（可仅一次） | 退出模拟器 |
| ExitSelf | CheckBox（可仅一次，与 IfNoOtherMaa 互斥） | 退出 MAA 自身 |
| IfNoOtherMaa | CheckBox | 无其他 MAA 实例运行时才执行（需启用 Sleep/Hibernate/Shutdown 之一） |
| Sleep | CheckBox（可仅一次） | 系统睡眠 |
| Hibernate | CheckBox（可仅一次） | 系统休眠 |
| Shutdown | CheckBox（可仅一次） | 系统关机 |
| Clear | Button | 清空全部后置动作勾选 |

**交互逻辑**：任务编排页 → 后置动作面板（任务列表下方齿轮按钮进入）→ 勾选收尾动作 → 任务执行完成后依次执行；任一动作右键标记「仅一次」后执行完自动取消勾选。

#### 4.3.12 自动战斗 Copilot 高级选项（`CopilotViewModel` / `CopilotView.xaml`）

> 补充 D-09 界面层可调项。Copilot 页含 4 个场景页签：主线/故事集/SS、SSS（保全派驻）、悖论模拟、其他活动关卡。

| 选项 | 控件 | 说明 |
|------|------|------|
| 场景页签 | ListBox Tab（4 项） | 主线/故事集/SS、SSS、悖论模拟、其他活动 |
| 作业文件 | TextBox + 文件树 Popup + 选择 Button + 粘贴 Button | 作业路径输入（下拉文件树浏览）+ 本地选择 + 剪贴板粘贴 |
| AutoSquad（Form） | CheckBox | 自动编队（主线/其他活动页签可用） |
| UseFormation | CheckBox + ComboBox | 使用编队方案（启用后下拉选编队序号） |
| IgnoreRequirements | CheckBox | 忽略作业要求（等级/技能不足时仍执行） |
| SupportUnitUsage | CheckBox + ComboBox | 助战使用（无好友可用时接取非好友助战） |
| AddTrust | CheckBox | 补充低信赖干员 |
| AddUserAdditional | CheckBox + DataGrid Popup | 追加自定干员：干员名（文本）+ 技能等级（NumericUpDown 0-3）+ 模组（ComboBox）+ 删除按钮 |
| UseCopilotList | CheckBox | 使用战斗列表（多关卡队列） |
| UseSanityPotion | CheckBox | 理智不足时使用理智药 |
| Loop / LoopTimes | CheckBox + NumericUpDown | 循环次数（0-9999） |
| CopilotTaskName | TextBox（带占位符） | 作业任务名（Web 作业展示名） |
| 战斗列表 | ListBox（拖拽+勾选）+ 导入/添加/清空 Button | 批量导入（ImportFiles）、添加关卡（右键反向）、清空（右键清除不可用）、拖拽排序、勾选执行、删除单项 |
| 点赞/地图链接 | Button + Hyperlink | 作业站作业 👍/👎 反馈 + PrtsPlus/地图/视频链接 |

### 4.4 客户端设置中心（源码 `Settings` ViewModel 提取）

> MAA 设置界面全部可配置项。Web 控制台「设置」页需覆盖以下分组。

#### 4.4.1 游戏设置（`GameSettingsUserControlModel` / `GameSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| StartGame | CheckBox | 自动启动客户端 |
| ClientType / ClientTypeList | ComboBox | 官方 / B服 / 美服 / 日服 / 韩服 / taptap（切换时重载资源） |
| DeploymentWithPause | CheckBox | 部署时暂停（二倍速暂停） |
| StartsWithScript / EndsWithScript | TextBox（支持拖拽文件） | 任务开始前 / 结束后脚本路径 |
| CopilotWithScript | CheckBox | Copilot 结束也执行脚本 |
| ManualStopWithScript | CheckBox | 手动停止也执行脚本 |
| BlockSleep / BlockSleepWithScreenOn | CheckBox + CheckBox | 阻止系统休眠 / 亮屏时阻止休眠 |
| EnablePenguin / PenguinId | CheckBox + TextBox | 企鹅物流上报 |
| EnableYituliu | CheckBox | 一图流上报 |
| EnableStallTimeout / StallTimeoutMinutes | CheckBox + NumericUpDown | 卡死检测超时（默认 10 分钟） |
| ReminderIntervalMinutes | NumericUpDown | 卡死提醒间隔（默认 5 分钟） |

#### 4.4.2 连接设置（`ConnectSettingsUserControlModel` / `ConnectSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| AutoDetectConnection / AlwaysAutoDetectConnection | CheckBox + CheckBox | 自动检测 / 常驻检测 |
| ConnectAddress + 历史(5 条) | 可搜索 ComboBox（带删除按钮） | ADB 连接地址（自动规范化端口分隔符，历史记录下拉） |
| AdbPath | TextBox + 文件选择 Button | ADB 路径（校验文件名含 adb） |
| ConnectConfig | ComboBox | 13 种连接预设（General/BlueStacks/MuMu12/LDPlayer/Nox/XYAZ/WSA/PC 等）+ 各自默认端口 |
| ExtraConfig | 展开区（CheckBox + TextBox） | 雷电/MuMu12/PC 额外配置（随预设动态显示） |
| TouchMode | ComboBox（附说明视频链接） | MiniTouch / MaaTouch / Adb / MaaFwAdb / MuMuExtras |
| ScreencapMethod / ScreencapTestCost | 测试 Button + 结果显示 | 截图方式 / 截图耗时测试 |
| RetryOnDisconnected | CheckBox（需配模拟器路径） | ADB 断开重试 |
| AllowAdbRestart / AllowAdbHardRestart | CheckBox + CheckBox | 允许重启 ADB / 允许强杀 ADB |
| AdbLiteEnabled | CheckBox | 启用 ADB Lite |
| KillAdbOnExit | CheckBox | 退出时杀掉 ADB |
| 实例选项 | 透传 | DeploymentWithPause / AdbLiteEnabled / KillAdbOnExit 透传 AsstSetInstanceOption |

#### 4.4.3 启动设置（`StartSettingsUserControlModel` / `StartSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| StartSelf | CheckBox（附风险提示） | 开机自启 |
| RunDirectly | CheckBox | 启动直接运行 |
| SkipStartupAutoRunAfterUpdate | CheckBox | 更新后跳过自动运行 |
| MinimizeDirectly | CheckBox | 启动直接最小化 |
| OpenEmulatorAfterLaunch | CheckBox | 启动后打开模拟器 |
| EmulatorPath | TextBox + 文件选择/选择进程 Button | 模拟器路径 |
| EmulatorAddCommand | TextBox（依赖路径非空启用） | 附加命令 |
| EmulatorWaitSeconds | TextBox | 等待秒数 |
| RetryOnDisconnected | CheckBox | ADB 断开重试（此页复现） |

#### 4.4.4 GUI 设置（`GuiSettingsUserControlModel` / `GuiSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| UseTray / MinimizeToTray | CheckBox + CheckBox | 使用托盘 / 最小化到托盘 |
| WindowTitleScrollable | CheckBox | 窗口标题可滚动 |
| HideCloseButton | CheckBox | 隐藏关闭按钮 |
| UseNotify | CheckBox | 使用系统通知 |
| UseCardLog / MaxNumberOfLogThumbnails | CheckBox + NumericUpDown | 卡片式日志 / 最大缩略图数（0-1000） |
| LogItemDateFormatString | ComboBox | 日志时间格式 |
| MainTasksInvertNullFunction | CheckBox | 主任务勾选框空值语义反转（`勾选=本次不执行` 与 `不勾选=本次执行` 互换） |
| Language | ComboBox | 界面语言（简繁英日韩） |
| OperNameLanguage | ComboBox | 干员名语言 |
| DarkMode | ComboBox | 界面主题（跟随系统/浅色/深色） |
| InverseClearMode | ComboBox | 主界面反选按钮功能（反选模式切换） |
| WindowTitleSelectShowList | 多选下拉（CheckComboBox） | 标题栏显示内容（组合） |
| RestartGuide | Button | 重新开始引导页 |
| IgnoreBadModulesAndUseSoftwareRendering | CheckBox | 忽略坏模块用软件渲染 |

#### 4.4.5 定时设置（`TimerSettingsUserControlModel` / `TimerSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| ForceScheduledStart | CheckBox | 强制启动 |
| ShowWindowBeforeForceScheduledStart | CheckBox | 强制启动前显示窗口 |
| CustomConfig | CheckBox | 定时使用自定义配置 |
| TimerList（每条） | CheckBox + 两个 NumericUpDown(时/分) + ComboBox(绑定配置) | 定时器列表：启用 + 时间点 + 配置选择 |

#### 4.4.6 远程控制（`RemoteControlUserControlModel` / `RemoteControlUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| RemoteControlGetTaskEndpointUri | TextBox | 获取任务端点 |
| RemoteControlReportStatusUri | TextBox | 上报状态端点 |
| RemoteControlUserIdentity | TextBox | 用户身份 |
| RemoteControlDeviceIdentity | TextBox | 设备身份 |
| RemoteControlPollIntervalMs | NumericUpDown | 轮询间隔（毫秒） |

#### 4.4.7 外部通知（`ExternalNotificationSettingsUserControlModel` / `ExternalNotificationSettingsUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| 通道添加 | SplitButton | 下拉选择 9 种通道（Smtp/ServerChan/Discord/DingTalk/Telegram/Bark/Qmsg/Gotify/CustomWebhook） |
| 通道配置（每条） | 动态表单（TextBox + CheckBox + 密码框 ShowEyeButton） | 各通道字段（Webhook URL / Token / 收件人等） |
| 触发开关 | CheckBox × 4 | SendWhenComplete / ShowWhenCompleteWithDetails / SendWhenError / SendWhenStalled |
| 测试发送 | Button | 发送测试消息 |

#### 4.4.8 性能设置（`PerformanceUserControlModel` / `PerformanceUserControl.xaml`）

AllowDeprecatedGpu —— CheckBox（允许使用旧 GPU，DirectML 推理加速相关）。

#### 4.4.9 版本更新（`VersionUpdateSettingsUserControlModel` / `VersionUpdateSettingsUserControl.xaml`）

资源信息更新 Button / 检查更新 Button（对应 S-07 OTA）。

> **已落地（2026-08-14）**：设置页「镜像下载源」模块实现更新源二选一（GitHub 官方 / Mirror酱）+ ghproxy 镜像前缀（多候选测速择优）+ MirrorChyan CDK 配置（掩码输入 + 眼睛按钮、保存保留、有效期检查 `cdk_expired_time`、错误码 7001/7002 等对齐 MAA 客户端）；引导页第 6 步「更新设置」所列能力与之一致。

#### 4.4.10 问题反馈（`IssueReportUserControlModel` / `IssueReportUserControl.xaml`）

生成日志压缩包 Button（导出便于共享排障）。

#### 4.4.11 成就（`AchievementSettingsUserControlModel` / `AchievementSettingsUserControl.xaml`）

成就列表 ListBox 展示（时间管理大师 / 全频道广播 / 肉鸽 N4/N8/N12/N15 等）。

#### 4.4.12 背景设置（`BackgroundSettingsUserControlModel` / `BackgroundSettings.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| BackgroundImagePath | TextBox + 文件树 Popup + 选择 Button | 背景图路径（下拉树状浏览内置壁纸/自定义） |
| BackgroundOpacity | Slider（0-100%，α 实时预览） | 背景不透明度 |
| BackgroundBlurEffectRadius | Slider（0-50px） | 背景模糊半径 |
| BackgroundImageStretchMode | ComboBox | 背景拉伸模式 |
| BackgroundMonetEnabled | CheckBox | Monet 动态取色（从背景图提取主题色） |
| BackgroundMonetMode | ComboBox | 取色模式（自动 / 自定义） |
| BackgroundMonetCustomColor | 色块预览 + Button | 自定义主题色选择 |

#### 4.4.13 全局热键（`HotKeySettingsUserControl` / `HotKeyEditorUserControl`）

| 选项 | 控件 | 说明 |
|------|------|------|
| HotKeyShowGui | 快捷键编辑器（HotKeyEditor） | 显示/隐藏主界面全局热键 |
| HotKeyLinkStart | 快捷键编辑器（HotKeyEditor） | 开始任务全局热键 |
| HotKeyChangingTip | TooltipBlock | 热键修改提示 |

#### 4.4.14 配置管理（`ConfigurationMgrUserControl` / `ConfigurationMgrUserControl.xaml`）

| 选项 | 控件 | 说明 |
|------|------|------|
| 配置列表 | 可编辑 ComboBox（带删除按钮） | 切换当前配置（对应 gui.json 多配置） |
| 新增配置 | TextBox（Enter 提交）+ Button | 新建配置命名 |

#### 4.4.15 关于我们（`AboutUserControl` / `AboutUserControl.xaml`）

官网 / B 站 / GitHub / QQ 群 / QQ 频道 / Telegram / Discord 链接 + 公告下载 Button（`CheckAndDownloadAnnouncement`）。

#### 4.4.16 引导页（`GuideUserControl` / `GuideUserControl.xaml`）

首次运行 7 步配置向导（`StepBar` 步骤条，含上一步/下一步/完成按钮）：

| 步骤 | 内容 |
|------|------|
| 1 UI 设置 | 界面语言 + 主题 |
| 2 游戏设置 | 客户端类型 |
| 3 连接设置 | 自动检测开关、连接预设、ADB 路径、连接地址、触控模式、模拟器额外配置（MuMu12/雷电/PC）、截图测试 |
| 4 任务设置 | 任务列表操作教学（勾选/仅一次/右键菜单/设置入口） |
| 5 性能设置 | GPU 推理选项 |
| 6 更新设置 | 更新类型 / 更新源 / MirrorChyan CDK |
| 7 用户指南 | 文档链接、问题反馈、GitHub 规范、开源参与、用户协议 |

#### 4.4.17 其他界面（工具箱 / Copilot / 主界面 / 托盘 / 主窗口）

| 区域 | 控件 | 说明 |
|------|------|------|
| 工具箱 | TabControl + TabItem | 公招识别 / 干员识别 / 仓库识别 / 抽卡 / 窥屏 / **小游戏**页签 |
| 公招识别 | CheckBox × 星级 + NumericUpDown × 时长 + 识别 Button | 手动识别界面（对应 T-01）：自动设时开关 + 显示潜能 + 自动选择 3/4/5/6 星标签（3/4 星可调时分，5/6 星固定 9:00） |
| 干员识别 | TabControl（已有/未有）+ ListBox | 干员卡片网格展示（对应 T-02）：名称/星级/精英/等级/潜能图标 + 导出（企鹅物流等） |
| 仓库识别 | 导出 ComboBox + Button | 材料导出（对应 T-03）+ 上次同步时间 |
| 抽卡 | Button × 2（单抽/十连）+ 免责声明 | GachaOnce / GachaTenTimes + 免责声明确认（含「不再显示」）+ 抽卡截图 + FPS 显示（对应 T-05） |
| 窥屏 | Button + NumericUpDown（目标帧率 1-600） | Peep! 启停 + 目标帧率设置 + FPS 实时显示（对应 T-06） |
| 小游戏 | 分类 ListBox + 像素画编辑器 + 隐秘战线配置 | 像素画（PixelPaint）：拖入图片/选择图片/适配模式/抖动模式/对比度/亮度/饱和度滑块/涂白/滑动；隐秘战线（SecretFront）：结局 + 事件选择；右侧实时日志（对应 D-15） |
| Copilot 作业 | 神秘代码 TextBox + 导入 Button + 场景 ComboBox | 抄作业（对应 D-09，详见 §4.3.12） |
| 主界面·任务列表 | ListBox（拖拽）+ CheckBox + 复制/重命名/删除 Button + 右键菜单 | 任务列表：勾选启用、拖拽排序、悬停显示复制/重命名/删除；设置齿轮右键菜单（运行一次/复制/重命名/删除）；添加任务下拉（11 类任务，含调试任务）；全选 / 反选（SplitButton 可切反选模式） |
| 主界面·操作区 | LinkStart / Stop / WaitAndStop Button + AutoReload CheckBox | 一键长草（深睡眠状态显示图标）、停止、等待并停止（肉鸽战斗中）、自动重载资源 |
| 主界面·信息区 | 今日关卡提示 + 仓库同步时间 | 左下角今日可刷关卡列表 + 右上角仓库上次同步时间提示 |
| 主界面·悬浮窗 | Overlay 开关 Button（右键选目标窗口） | 半透明悬浮窗实时显示任务日志（进程选择器指定目标窗口） |
| 托盘菜单 | ContextMenu（8 项） | 开始长草 / 停止 / 切换语言 / 强制显示 / 隐藏托盘 / 切换悬浮窗 / 重启 / 退出 |
| 主窗口标题栏 | 置顶 Button + 滚动标题 + 彩虹更新提示 | 窗口置顶（📌）、标题可滚动、版本/资源更新彩虹文字（点击手动更新） |
| 主窗口背景 | 背景图（含模糊/透明度） | 应用背景设置（§4.4.12） |
| 主窗口彩蛋 | 右下角 GIF（可拖动，右键更换） | 彩蛋动画展示 |

## 4.5 实现进度总览（2026-08-16 核对）

> 与代码逐项核对后的真实进度，供开发排期与验收对照；细节见 [roadmap.md](./roadmap.md) 里程碑状态表与 [architecture.md](./architecture.md) 已落地标注。

| 范围 | 状态 | 说明 |
|------|------|------|
| C-01 设备管理 | ✅ 已实现 | CRUD + 连接/断开 + 状态监控 + 环境检测（ADB/引擎芯片）+ **分辨率查询/设置/重置** + USB connect serial 在线校验 + 列表探活降级（拔线自动离线） |
| C-02 模拟器检测 | ✅ 已实现 | `adb devices -l` 扫描（含 USB serial 设备识别，port=0 直接以 serial 连接） |
| C-03 触控模式 | ✅ 已实现 | Minitouch / MaaTouch / Adb 切换（MaaTouch 真机实测可用） |
| D-01 StartUp / D-02 CloseDown | ✅ 已实现 | 参数透传 + 设备 client_type 注入；StartUp 真机实测执行成功 |
| D-03~D-07 日常任务 | 🚧 面板已就绪 | Fight/Recruit/Infrast/Mall/Award 表单 + 后端映射 + 队列下发通道全部实现（对齐源码模型）；**Mall 补齐「访问好友 + 一日只执行一次」**（客户端本地语义后端模拟）；真机逐项验收中（新号部分功能未解锁） |
| D-08 肉鸽 | 🚧 面板已就绪 | RoguelikeForm（5 主题 + 全联动 + 种子门控等），执行验收待排期 |
| D-09 Copilot | 🚧 后端已完成 | prts.plus 作业站集成 + 场景分发（普通/SS 合并、悖论模拟 ParadoxCopilot、保全 SSS）+ SSS 作业导入校验细分；实际抄作业执行待真机验收 |
| D-11 Custom | 🚧 通道已就绪 | 映射与入队通道已实现，待实机验证 |
| S-01 任务编排 | ✅ 已实现 | 纯编辑页（左列表右参数双栏）+ 拖拽排序/勾选启用/方案保存调出；**方案与草稿存后端**（换浏览器一致，旧本地数据自动迁移）；LINK START 已移至自动任务页 |
| S-02 定时执行 | ✅ 已升级为自动任务 | **自动任务（2026-08-16）**：任务组×多时间点（星期/时间/冲突策略排队·跳过·强制）+ 每时间点多账号轮换（账号组来源，AccountSwitchTask 切换，失败跳过）+ 每账号方案快照与参数微调 + RUN TEST + 独立日志（source=auto/manual_auto）；旧 schedule_jobs 启动自动迁移 |
| S-03 脚本钩子 | ⏳ 未做 | 运行设置仅存储字段，执行待排期 |
| S-05 日志中心 | ✅ 已实现 | WS 实时日志流 + **当天实时/历史按天归档**（本地时区，时区修复）+ /logs 页（级别过滤/关键字/按天展开）+ 日志导出压缩包 |
| S-06 通知推送 | 🚧 3 通道落地 | Server酱/钉钉（加签）/自定义 Webhook + 完成/出错/停滞触发 + 发送记录页；**真实渠道验证待以后版本**（重发暂禁用，两处「未测试」提示） |
| S-07 自动更新 | ✅ 已实现 | 引擎包双更新源（GitHub release + MirrorChyan，CDK 有效期检查/OTA 增量包）+ 动态资源同步 + 更新设置页 |
| S-12 桌面专属 | ✅ 已裁掉 | 启动/GUI 窗口/背景/热键/GPU（DirectML 仅 Windows）——WebUI 不适用；**性能/启动/背景/热键 4 组已从设置中心移除**，原因见「关于我们」 |
| 设置中心 §4.4 | ✅ 8 组落地 | 定时（独立页）/运行/连接/界面（**主题深色/浅色/自动**：日出日落 + 手动时间 + IP 定位兜底）/外部通知/更新/问题反馈（日志导出）/关于（含已裁剪清单）；15 组裁剪为 8 组 |
| C-04 / S-08 外服（部分）/ T-01~T-06 / D-12~D-15 | ⏳ 未排期 | 见 roadmap M5/M6 |
| C-04 / S-02/S-03/S-04/S-06/S-08~S-11 / T-01~T-06 / D-12~D-15 | ⏳ 未排期 | 见 roadmap M3~M6 |

## 5. 数据与指标

| 指标 | 目标 | 采集方式 |
|------|------|---------|
| 功能覆盖率 | 100% 对齐 §4 功能表 | 每里程碑验收时逐项核对 |
| 任务执行成功率 | ≥ 95%（正常网络/设备） | 日志中心统计 |
| 指令反馈延迟 | < 500ms（局域网） | 前端埋点 |
| 定时任务准时率 | ≥ 99% | 调度器日志 |
| 连续运行稳定性 | 7×24 无重启 | 容器监控 |

## 6. 依赖、风险与里程碑

### 6.1 技术依赖

- **MAA Asst 核心**（官方发布包 `MaaCore.dll` / `libMaaCore.so`，ctypes 直调 Asst C API，`MAAWEB_RESOURCE_PLATFORM` 支持 win-x64 / linux-x86_64 / linux-aarch64）→ 核心引擎（与桌面客户端同引擎，原生加载官方资源）。
- **AsstCaller C 接口** → 已实现：`asstproxy.py` 封装 AsstCreate/AsstAppendTask/AsstStart/AsstStop/AsstMsg 回调。
- **作业站 prts.plus API** → 神秘代码解析与作业搜索。
- **企鹅物流 / 一图流 API** → 掉落与公招数据上传。
- **ADB**（模拟器/真机连接）。
- **SQLite**（配置持久化，等价 gui.json 角色）。

### 6.2 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Python 绑定缺少部分回调字段 | 中 | 中 | 保留 AsstCaller C 接口备选方案；文档标注支持范围 |
| 生息演算早期功能不稳定 | 中 | 低 | 标注「实验性」，不做无人值守承诺 |
| 作业站 API 变动 | 低 | 中 | 抽象解析层，独立测试 |
| NAS 无 GPU 时识别慢 | 中 | 低 | 纯 CPU 模式优化 + 可插拔 GPU 加速开关 |
| 游戏更新导致识别失效 | 高 | 中 | 资源包 OTA 更新机制（S-07） |

### 6.3 里程碑

见 [roadmap.md](./roadmap.md) 完整分阶段规划。

---

## 7. 附录：功能对齐自查表

开发过程中每个里程碑结束，对照下表逐项勾选（来源为 MAA 官方文档，可在 [docs.maa.plus](https://docs.maa.plus/zh-cn/) 复核）：

- [ ] D-01 开始唤醒（账号切换、自动启动客户端）
- [ ] D-02 关闭游戏
- [ ] D-03 理智作战（全部导航关卡 + 四停止条件 + 博朗台 + 崩溃重启 + 掉落上传）
- [ ] D-04 公开招募（加急许可、首选/保留标签、时限、数据上传）
- [ ] D-05 基建换班（三模式 + 9 设施 + 无人机 + 宿舍 + 会客室 + 自定义排班协议）
- [ ] D-06 信用购物（三轮购买 + 好友访问 + 折扣 + OF-1）
- [ ] D-07 领取奖励（六种奖励开关）
- [ ] D-08 肉鸽刷分（5 主题 × 9 模式含常乐节点 + 全部主题特有参数 + 种子）
- [ ] D-09 自动战斗（Copilot/SSS/悖论模拟三场景 + 自动编队 + 战斗列表 + 循环）
- [ ] D-10 生息演算（3 主题 + 4 模式 + 制造/清空商店）
- [ ] D-11 自定义任务
- [ ] D-12 数据更新（干员盒/仓库 + 触发间隔）
- [ ] D-13 仓库保持（多 Plan + 活动跳过 + 临期药）
- [ ] D-14 单步任务 / D-15 小游戏
- [ ] T-01 公招识别（自动设时/显示潜能/自动选星）/ T-02 干员识别 / T-03 仓库识别 / T-05 抽卡（免责声明）/ T-06 窥屏（目标帧率）（T-04 视频识别官方已弃用，不规划）
- [ ] D-15 小游戏：像素画（PixelPaint 编辑器）+ 隐秘战线（结局/事件）+ 分类列表
- [ ] C-01~C-04 设备与连接（13 种连接预设 + 触控模式 + 自动启动模拟器）
- [ ] S-01 任务编排（含主界面操作区：LinkStart/Stop/WaitAndStop/AutoReload、任务列表右键菜单、全选/反选、悬浮窗、托盘菜单、主窗口置顶/标题滚动）
- [ ] S-02 定时执行 / S-03 脚本钩子 / S-04 配置管理 / S-05 日志中心 / S-06 通知（9 通道）/ S-07 自动更新 / S-08 外服支持 / S-09 GPU 加速 / S-10 远程控制协议 / S-11 成就系统
- [ ] 任务可调项全覆盖（§4.3）：每个任务的用户可调整选项逐一在 Web 参数面板实现（含 §4.3.11 后置动作、§4.3.12 Copilot 高级选项）
- [ ] 设置中心全覆盖（§4.4）：游戏/连接/启动/GUI/定时/远程控制/通知/性能/更新/反馈/成就 + **背景/热键/配置管理/关于** + 引导页（7 步）+ 工具箱/Copilot/主界面/托盘界面

> 自 v0.2.0 起，功能来源已从官方文档改为**客户端源码逐项核对**（参考仓库：`参考/MaaAssistantArknights`），源码为最高优先级基准。
