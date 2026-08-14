# Maa-Web · 技术架构文档

> 版本：v0.3.0 ｜ 更新日期：2026-08-14
> 与 [PRD](./PRD.md) 功能表一一对应（源码核对版），描述承载全部 MAA 功能的工程架构。
> 前端组件实现契约见 [UI 设计规范](../ui-design/design-system-arknights.md)（Token 命名与 §3.9 控件类型契约对应）。

---

## 1. 总体架构

```
浏览器（Web 控制台，Vue3 + TS）
   │  HTTPS/HTTP :8080
   ▼
┌──────────────────────────────────────────────┐
│                Nginx 反代网关                 │
│  静态资源 → /usr/share/nginx/html             │
│  /api/*    → maaweb-api:8000 (REST)          │
│  /ws/*     → maaweb-api:8000 (WebSocket)     │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│              FastAPI 应用层 (Python)          │
│                                              │
│  REST 路由  ◄───►  Services 业务层            │
│  /api/v1/*        ├─ DeviceService   (C-01~04)│
│                   ├─ TaskService     (D-*)    │
│                   ├─ ToolboxService  (T-*)    │
│                   ├─ ScheduleService (S-02)   │
│                   └─ ConfigService   (S-04)   │
│                                              │
│  WebSocket Hub  ◄─── 事件总线 (AsstMsg)       │
│                                              │
│  ┌─────────────────────────────────────────┐  │
│  │           AsstProxy 引擎代理层           │  │
│  │  实例池 · 任务队列 · 状态机 · 回调分发     │  │
│  └────────────────┬────────────────────────┘  │
└───────────────────┼───────────────────────────┘
                    ▼
┌──────────────────────────────────────────────┐
│          MAA Asst 核心（MaaCore）              │
│    ctypes 直调官方发布包动态库                 │
│  (win: MaaCore.dll / linux: libMaaCore.so)   │
│                                              │
│  AsstConnect → ADB  ──► 模拟器 / 真机         │
│  AsstAppendTask (15 任务类型)                 │
│  AsstCallback (AsstMsg 回调)                  │
└──────────────────────────────────────────────┘
```

## 2. 技术栈

| 层 | 技术 | 职责 |
|----|------|------|
| 前端 | Vue3 + TypeScript + Vite + Pinia + Vue Router | 控制台 UI、任务编排、实时日志/画面 |
| 网关 | Nginx | 静态托管 + API/WS 反向代理 |
| 后端 | FastAPI + Uvicorn | REST + WebSocket + 业务编排 |
| 引擎 | MAA Asst 核心（`MaaCore.dll` / `libMaaCore.so`，官方发布包） | 图像识别 + 自动化执行 |
| 存储 | SQLite | 设备、配置、任务历史、日志（文件卷） |
| 调度 | APScheduler | 定时执行（S-02） |
| 通知 | 9 通道适配层（ServerChan/Telegram/Discord/钉钉/SMTP/Bark/Qmsg/Gotify/Webhook） | 事件通知（S-06） |

## 3. 核心模块设计

### 3.1 AsstProxy（引擎代理层）

连接 MAA 引擎（Asst 核心）与业务层，屏蔽底层细节：

```
┌──────────────────────────────────────────┐
│ AsstProxy                                │
│  ├─ InstancePool: 设备 ↔ Asst 实例        │
│  ├─ TaskQueue:    任务串行队列            │
│  ├─ StateMachine: idle/running/stopping/ │
│  │                finished/error         │
│  └─ CallbackBus:  AsstMsg → 事件总线     │
└──────────────────────────────────────────┘
```

> M2 已落地 `app/engine/`（`adb.py` + `asstproxy.py` + `manager.py`）：
> - `adb.py` — 真实 platform-tools 封装（`adb devices -l` 扫描 / connect / disconnect），纯解析函数可单测
> - `asstproxy.py` — MAA Asst 核心（MaaCore 动态库）ctypes 适配器：`AsstCreateEx / AsstConnect / AsstAppendTask / AsstStart / AsstStop` + `AsstMsg` 回调解析；设备 ↔ 会话池，懒加载 + 优雅降级（引擎包未下载不阻断，仅 ADB 可用）
> - `manager.py` — 连接状态机编排：`offline → online | error`，失败原因持久化到 `Device.last_error`
> - 状态语义：ADB 握手指向真实可达性；引擎会话失败只降级不降状态（在线但提示引擎不可用）
>
> M2 任务执行已落地 `taskrunner.py` + `eventbus.py`：
> - `taskrunner.py` — 每设备一个串行 `TaskRunner`：状态机 `idle → running → finished | error | stopped`；真实调用 `AsstAppendTask(type, params) × N` + `AsstStart()`（非阻塞，引擎后台线程执行），`AsstMsg` 回调（TaskChainStart/Completed/Error/Stopped、AllTasksCompleted）经 `call_soon_threadsafe` 线程安全投递到日志队列驱动状态机；日志持久化 `LogEntry` + 广播 eventbus；Copilot 多作业（`params.jobs` 勾选项）展开为逐作业执行；stop 幂等 + 5s 兜底强制收尾（避免 stopping 卡死）
> - **分辨率预检**：`_ensure_resolution_supported()` 启动前检查设备 16:9 / 9:16（容差 0.02），非支持比例给出明确引导（USB 真机提示 1080x1920、模拟器提示 1920x1080），预检失败不阻塞（交给 AsstConnect 终判）
> - `eventbus.py` — 进程内 pub/sub：WS 处理器按 device_id 订阅，runner 发布日志行
> - **客户端本地语义模拟**：Fight 周计划按星期跳过（`_weekly_schedule_enabled`）、战斗次数 -1/0=不限（asstproxy 剥离不下发，引擎默认 INT_MAX）、Mall「一日只执行一次」（`_apply_mall_once_a_day`，游戏日 last_time 存 Setting 表，对齐 MallTask.cs IsCreditFightAvailable）、停滞检测（`_stall_watch_loop`/`_check_stall`，对齐 RunningState StallTimer：卡死超时无进展 → 日志警告 + 停滞通知）
> - 前置校验：设备在线 / 引擎可用 / 引擎包就绪 / 分辨率支持，任一不满足 → `TaskQueueError` → API 409 + 人话 detail；`AsstConnect` 失败（如触控模式不可用）→ `EngineCreateError` → API 502
> - `TaskRun` 表记录每次运行（status/summary/error/started_at/finished_at），`LogEntry` 表持久化日志行
> - **外部通知**（`engine/notify.py`，M6）：完成/出错/停滞事件 → 按 notify.* 配置逐渠道推送（Server酱/钉钉加签/自定义 Webhook），发送记录落 `notify_logs`；taskrunner 收尾时先广播 run_finished 再发送
> - **定时调度**（`engine/scheduler.py`，M6）：分钟级 tick（整点对齐），星期 × 时间匹配 `schedule_jobs` → 执行方案快照；90s 防重窗口、last_run_at 落库、触发日志进实时流
>
> 引擎切换背景（2026-08）：MaaFw 5.x 的 `Resource.post_pipeline` 只接受 Pipeline v2 格式，
> 而 MAA 官方资源是自研旧格式（`algorithm`/`action` 字符串），且战斗/公招/基建依赖 MaaCore
> 内部私有识别器 —— 纯 MaaFw 无法加载官方资源。故引擎切换为 MAA 官方 Asst 核心（与桌面
> 客户端同引擎），资源包管理器（S-07）直接下载完整官方发布包。

关键约束：

- 每个设备对应一个 Asst 实例，任务串行执行（MAA 引擎不支持同设备并发）。
- 任务启动/停止均为异步操作，状态机保证幂等。
- 回调统一 `AsstMsg` → 结构化事件 → WS 广播 + 通知触发。

### 3.2 任务模型（对应 MAA 全部任务类型）

| 前端任务类型 | 引擎 task_type（AsstAppendTask） | 参数来源（源码） |
|-------------|---------------|---------|
| 开始唤醒 | `StartUp` | `StartUpTask.cs`：account_name / account_switch_enabled |
| 关闭游戏 | `CloseDown` | `MaaService.cs` |
| 刷理智 | `Fight` | `FightTask.cs`：stage_plan[] / medicine / stone / times / drops / series / DrGrandet / weekly_schedule / inventory_target |
| 公开招募 | `Recruit` | `RecruitTask.cs`：refresh / select / confirm / first_tags / expedite / preserve_tags / 星级时限 |
| 基建换班 | `Infrast` | `InfrastTask.cs`：mode / facility[] / drones / threshold / dorm / reception / continue_training |
| 信用购物 | `Mall` | `MallTask.cs`：visit_friends / buy_first / blacklist / only_buy_discount / credit_fight |
| 领取奖励 | `Award` | `AwardTask.cs`：award / mail / free_gacha / orundum / mining / special_access |
| 肉鸽 | `Roguelike` | `RoguelikeTask.cs`：theme / mode(含 20001 常乐) / squad / core_char / seed / investments_count… |
| 自动战斗 | `Copilot` / `SSSCopilot` / `ParadoxCopilot` | `MaaService.cs` + `CopilotView.xaml`：stage_name / filename(作业) / copilot_mode(场景，4 页签) / auto_squad / use_formation / ignore_requirements / support_unit_usage / add_trust / add_user_additional[] / copilot_list[] / loop_times |
| 生息演算 | `Reclamation` | `ReclamationTask.cs`：theme(Fire/Tales/RelaunchAnchor) / mode / tool_to_craft |
| 自定义 | `Custom` | `CustomTask.cs`：custom_task_name |
| 数据更新 | `UserDataUpdate` | `UserDataUpdateTask.cs`：update_operbox / update_depot / trigger_interval |
| 仓库保持 | `DepotMaintain` | `DepotMaintainTask.cs`：plan_list[] / skip_during_activity / use_expiring_medicine |
| 单步任务 | `SingleStep` | `MaaService.cs` |
| 小游戏 | `MiniGame` | `AsstProxy.cs TaskType` |

> 每个任务类型的全部参数字段以**客户端源码模型为准**（参考 `参考/MaaAssistantArknights/src/MaaWpfGui/Configuration/Single/MaaTask/`），前端参数面板与后端 Pydantic Schema 同步维护，避免字段漂移。

**已实现任务类型（2026-08-14 核对）**：StartUp / CloseDown / Fight / Recruit / Infrast / Mall / Award / Roguelike / Copilot 九类 —— 前端参数表单（`frontend/src/tasks/forms/`）+ 后端 `asstproxy.to_asst_task()` 映射（默认参数补齐、旧字段兼容 `recruit_max_times→times`、`auto_squad→formation`、Copilot `add_user_additional→user_additional`、Recruit 标签启用开关门控、Roguelike 种子门控、StartUp/CloseDown 自动注入设备 `client_type`）均已落地，可入队下发执行（StartUp 已真机实测）。

**Copilot 作业站集成**（`app/engine/copilot_mgr.py`，M4 前置落地）：
- prts.plus 作业站代码解析（对齐 MAA 客户端 `TryParseCopilotCode`）：`prts://99359` 单作业 / `prts://s51251` 作业集 / `maa://99359` 旧格式 / `s51251` 简写 / 纯数字
- `fetch_from_prts(id)` / `fetch_set_from_prts(id)`：拉取 → 校验 `opers/groups` → 保存到 `resource/copilot/{stage}_{id}.json`；作业集逐作业下载、失败跳过记录
- `stage_display_name()`：作业内部 stageId（如 `act53side_ex01`）→ 可读关卡编号/名称（读 `Arknights-Tile-Pos/overview.json`，与 MAA 客户端 `DataHelper.FindMap` 同源）
- 任务参数面板支持单任务多作业勾选（`params.jobs`），队列层 `taskrunner._expand_copilot_jobs()` 逐个入队执行

### 3.3 引擎包管理（S-07 主动下载/更新）

MAA 引擎与识别资源（pipeline / template / model）随官方 release 完整发布包分发，`app/engine/resource_mgr.py` 负责主动获取。**更新源可配置（对齐 MAA 客户端 UpdateSource）**：`github`（官方 GitHub Releases + ghproxy 镜像）或 `mirrorchyan`（Mirror酱高速源，需 CDK），设置页切换，`update()`/`status()`/`sync_dynamic()` 按源分发。

**更新源 1：GitHub Releases**
- 数据源：`MaaAssistantArknights/MaaAssistantArknights` GitHub Releases 最新版完整包 —— `MAA-{tag}-{platform}.zip`（win-x64 / win-arm64）或 `MAA-{tag}-linux-{arch}.tar.gz`（linux-x86_64 / linux-aarch64，NAS 用），资产名与 `MAAWEB_RESOURCE_PLATFORM`（默认 `win-x64`）匹配
- 包内布局（win zip 平铺 / linux tar 带根目录）：顶层 `MaaCore.dll` / `libMaaCore.so` 引擎库 + `resource/`（任务/模板/OCR 模型/global 客户端资源）+ `Python/`、`MAA.exe` 等
- 镜像：`MAAWEB_RESOURCE_MIRROR`（或设置页「ghproxy 镜像前缀」）逗号/换行分隔多前缀，对每个原始 URL 生成候选列表 `[镜像×n..., 直连]`，并发 HEAD 测速择优（60s 缓存）+ 下载失败自动切换下一源（对齐 MAA 客户端更新机制）

**更新源 2：Mirror酱（MirrorChyan）**
- 引擎包 API：`mirrorchyan.com/api/resources/MAA/latest`（对齐 MAA 客户端 `MaaUrls.MirrorChyanAppUpdate`），带 `current_version` + `cdk` + `os/arch`（`win-x64→os=win,arch=x64`；`linux-aarch64→os=linux,arch=aarch64`）+ `channel=Stable` + `sp_id`；响应 `{version_name, url, filesize, update_type}`；同版本/无 url → `up_to_date`
- **OTA 增量包**（`update_type=incremental`，如 v6.16.6→v6.16.8 实测 4.4MB patch）：`_apply_incremental()` 对齐 MAA 客户端增量更新 —— `changes.json` 的 `deleted` 数组删除文件 + 其余条目覆盖，防路径穿越校验；全量包走整包解压原子替换
- 版本名形如 `2026-08-14 08:00:00.000`（含空格冒号），`_safe_fs_name()` 安全化后用作临时目录名；无 `filesize` 时下载进度取响应头 `content-length`
- CDK 有效期：`check_mirrorchyan_cdk()` 调 `MaaResource/latest` 获取 `data.cdk_expired_time`（unix 秒）持久化，设置页展示剩余天数；错误码对齐 MAA 客户端 MirrorChyanErrorCode（1001/7001 过期/7002 无效/7003 限次/7004 不匹配/7005 封禁/8001 资源不存在）

**通用流程**
- 安装：httpx 流式下载（进度上报）→ 解压（zip / tar.gz，tar 安全过滤）→ 定位含 `resource/` 的包根目录 → 校验（resource/ + 引擎库）→ 原子替换 `maa_resource_dir` → 写 `version.json`（含 source 标记）；Windows 下引擎 DLL 已加载导致目录被占用时退化为逐文件同步（跳过锁定文件）
- 引擎加载：`asstproxy` 懒加载 MaaCore 动态库 → `AsstLoadResource(包根目录)`（引擎自行加载全部资源）；`version.json` tag 变化时自动重载；更新完成后 `asstproxy.release()` 提示重载
- 更新判断：`status()` 按更新源比对本地 `version.json` 与远端最新版本；远端查询带 60s 缓存，失败不阻断本地状态（降级报告）
- 动态资源同步：活动地图格子（`Arknights-Tile-Pos/`）、活动模板（`template/`）、关卡/公招/基建数据 JSON 来自 MAA 官方动态资源仓库 `MaaAssistantArknights/MaaResource`（随活动热更新，与包内 `resource/` 路径同构），同样按更新源分发：
  - GitHub 源：`POST /resources/sync` 拉取 git tree（path→blob sha，120s 缓存）与本地 manifest（`.maaweb_dynamic.json`）对比：差异 ≤ 阈值（1200 文件）按文件并发增量下载（raw 走镜像候选测速），差异过大或无 manifest 时一次 codeload tarball 全量合并（同名覆盖+新增，不删引擎包自有资源）
  - MirrorChyan 源：`MaaResource/latest?current_version={resource/version.json.last_updated}` 检查 → 下载增量包解压合并 → manifest 记录 `version` + `source=mirrorchyan`
  - 完成后 `asstproxy.release()` 提示引擎重载，避免整包（~267MB）重下
- 与 maa-cli 关系：maa-cli 的 `maa install/update` 从同一官方源下载 MaaCore+资源；本实现用纯 Python 等价复刻，避免容器内额外依赖 Rust 二进制

### 3.3.1 运行时设置（runtime_settings.json，UI 可写热更新）

`get_settings()` 是进程内 lru_cache 单例（启动时读 .env），设置页保存无法写回环境，故引入独立 JSON 配置 `app/core/runtime_settings.py`：

- 文件位置：与 SQLite 同目录 `data/config/runtime_settings.json`，**优先级高于 .env**（UI 保存即标记 `_configured`，运行期读取立即生效，无需重启）
- 字段：`update_source`（github | mirrorchyan）、`maa_resource_mirror`（ghproxy 前缀）、`mirrorchyan_cdk`、`mirrorchyan_cdk_expired_time`（unix 秒）、`mirrorchyan_sp_id`（首次启动自动生成并持久化的本机唯一标识，供 MirrorChyan API 使用）、`adb_path`（连接设置保存的 ADB 路径，`adb.resolve_adb_path()` 优先读取，热更新生效）
- 接口：`GET/PUT /api/v1/settings/mirror`（读取/保存，CDK 脱敏 `_mask_cdk` 回显；CDK 未变更时保留旧有效期，变更/清空才清除）、`POST /api/v1/settings/mirror/check`（实时检查有效期）
- 测试隔离：conftest 将 `data_dir` 指向临时目录，`runtime_settings.json` 随之一同隔离

### 3.4 实时通道（日志 + 画面）

| 通道 | 协议 | 内容 |
|------|------|------|
| `/ws/logs` | WebSocket | 任务执行日志（分级）、状态事件、回调消息 |
| `/ws/screen` | WebSocket | 窥屏帧（T-06，JPEG 压缩，帧率自适应） |

### 3.4 工具箱识别流（T-01~T-06）

```
前端上传/触发识别 → REST → ToolboxService
  → MAA 识别接口（截图 → OCR/模板匹配）
  → 结构化结果 JSON → 前端渲染
  → 导出适配器（企鹅物流 / 工具箱 / ARK-NIGHTS 格式）
```

覆盖：公招识别（T-01）、干员识别（T-02）、仓库识别（T-03）、抽卡（T-05）、窥屏（T-06）、小游戏（D-15，像素画/隐秘战线）。T-04 视频识别源码中已注释弃用，不实现。

### 3.5 定时执行（S-02）

- APScheduler 管理 cron/间隔任务。
- 每个定时任务 = 配置快照（S-04）+ 任务组合 + 执行计划。
- 触发后投递到对应设备的 TaskQueue，沿用任务状态机。

### 3.6 通知适配层（S-06）

```
事件源: 任务完成(可带详情) / 任务错误 / 任务卡死
   → 通知中心（分级 + 节流 + 失败重试）
   → 9 Channel: ServerChan | Telegram | Discord | DingTalk | SMTP | Bark | Qmsg | Gotify | CustomWebhook
```

通道类型与源码 `ExternalNotificationSettings` 一致，支持发送测试消息。

### 3.7 配置管理（S-04）

- SQLite 存多配置快照（等价 MAA `gui.json` 的多配置）。
- 配置字段与 MAA 任务参数 JSON 一一映射。
- 支持「启动时自动切换配置」与定时任务绑定配置。

### 3.8 远程控制协议（S-10）

实现 MAA 客户端内置的轮询控制协议（对应源码 `RemoteControlService.cs`），Maa-Web 后端作为该协议的服务端，Web 控制台与引擎之间天然打通：

```
GET 任务:  POST /api/v1/remote/get-task
   请求体 {user, device}   ← 用户身份 + 设备身份
   响应   {tasks: [{type, id, params}]}

执行: 顺序任务队列（LinkStart 系列/工具箱/截图/设置）
      + 即时任务队列（CaptureImageNow/HeartBeat/StopTask）

上报状态: POST /api/v1/remote/report-status
   请求体 {user, device, status, task, payload}
   状态 SUCCESS/FAILED；截图 payload 为 Base64
```

任务类型清单：`LinkStart`（一键长草）/ `LinkStart-Base` / `-WakeUp` / `-Combat` / `-Recruiting` / `-Mall` / `-Mission` / `-AutoRoguelike` / `-Reclamation` / `Toolbox-GachaOnce` / `Toolbox-GachaTenTimes` / `CaptureImage` / `Settings-ConnectAddress` / `Settings-Stage1` / `CaptureImageNow` / `HeartBeat` / `StopTask`。

### 3.9 任务参数面板与设置中心（对应 PRD §4.3 / §4.4）

**任务参数面板**：每个任务的前端参数表单字段与源码 ViewModel 属性一一映射（PRD §4.3 表）。后端 Pydantic Schema 同名透传至 `AsstAppendTask` 的 params JSON，字段名以源码 `SerializeTask` 序列化结果为准，避免前端/后端/引擎三处漂移。

**控件类型契约**：前端参数组件需还原 MAA XAML 控件语义（PRD §4.3 控件类型速查）：

| MAA 控件语义 | 前端组件约定 |
|-------------|-------------|
| 复选框（可半选「仅一次」） | 三态开关（空 = 未保存/半选） |
| 数字微调 | 数字输入 + 步进，含 min/max |
| 下拉单选 | Select 组件 |
| 可搜索下拉 | Select 带远程/本地过滤 + 可输入 |
| 多选下拉 | Select multiple / 勾选面板 |
| 文本填空（含占位符） | Input + placeholder |
| 拖拽列表（增删排序） | 可排序列表组件 |
| 单选组 | Radio group |
| 滑块（带百分比） | Slider + 数值显示 |
| 文件/进程选择 | 输入框 + 浏览按钮 |
| 拆分按钮（主操作+下拉） | DropdownButton |
| 密文输入 | Password Input（可见性切换） |

**设置中心**：8 组设置（已裁剪配置切换/桌面专属/远程控制/成就，原因见「关于我们」）+ 其他界面（工具箱/Copilot/主界面/托盘）映射（PRD §4.4）：

| 设置组 | 源码来源 | 存储 |
|--------|---------|------|
| 配置管理 | `ConfigurationMgrUserControl` | SQLite Config 表（多配置切换） |
| 定时设置 | `TimerSettingsUserControlModel` | Schedule 表 |
| 性能设置 | `PerformanceUserControlModel` | Setting 表（GPU 开关） |
| 游戏设置 | `GameSettingsUserControlModel` | SQLite Setting 表 |
| 连接设置 | `ConnectSettingsUserControlModel` | Device 表 + Setting 表 |
| 启动设置 | `StartSettingsUserControlModel` | Setting 表 |
| 远程控制 | `RemoteControlUserControlModel` | Setting 表（加密存储） |
| GUI 设置 | `GuiSettingsUserControlModel` | Setting 表（语言/主题/日志样式/标题栏内容等） |
| 背景设置 | `BackgroundSettingsUserControlModel` | Setting 表（背景图/不透明度/模糊/Monet） |
| 外部通知 | `ExternalNotificationSettingsUserControlModel` | Setting 表（9 通道配置） |
| 热键设置 | `HotKeySettingsUserControlModel` | Setting 表（全局热键） |
| 成就 | `AchievementSettingsUserControlModel` | 派生数据展示 |
| 更新设置 | `VersionUpdateSettingsUserControlModel` | Setting 表 |
| 问题反馈 | `IssueReportUserControlModel` | 日志导出动作 |
| 关于我们 | `AboutUserControl` | 静态链接 + 公告下载 |

**其他界面映射**：

| 界面 | 源码来源 | 说明 |
|------|---------|------|
| 引导页 | `GuideUserControl` | 7 步首次运行向导（UI/游戏/连接/任务/性能/更新/用户指南） |
| 主界面 | `TaskQueueView` | 任务列表（拖拽/右键菜单/全选反选）、操作区（LinkStart/Stop/WaitAndStop/AutoReload）、今日关卡提示、悬浮窗开关、后置动作面板入口 |
| 工具箱 | `ToolboxView` | 6 页签：公招识别/干员识别/仓库识别/抽卡/窥屏/小游戏 |
| Copilot | `CopilotView` | 4 场景页签 + 高级选项（自动编队/使用编队/忽略要求/助战/追加干员）+ 战斗列表 |
| 托盘 | `NotifyIcon` | 8 项托盘菜单（开始/停止/切换语言/强制显示/隐藏托盘/悬浮窗/重启/退出） |
| 悬浮窗 | `OverlayWindow` | 半透明日志悬浮窗（进程选择器指定目标窗口） |
| 主窗口 | `RootView` | 标题栏（置顶/滚动标题/彩虹更新提示）、背景图、GIF 彩蛋 |

**实例选项透传**：`DeploymentWithPause` / `AdbLiteEnabled` / `KillAdbOnExit` / `TouchMode` 通过 `AsstSetInstanceOption` 下发，后端需维护实例选项同步。

## 4. 数据模型

```
Device        (C-01)   id, name, adb_host, adb_port, touch_mode, client_type,
                       status, last_online_at, last_error
TaskConfig    (S-04)   id, name, is_default, items: JSON[](任务组合)
Schedule      (S-02)   id, name, config_id, cron, enabled, last_run_at
TaskRun       (S-05)   id, device_id, config_id, type, status, started_at,
                       finished_at, result: JSON
LogEntry      (S-05)   id, run_id, ts, level, source, message
Setting       (S-06/09) key, value  (通知通道 / GPU 加速 / 上传 ID 等)
```

> 另有一个非 SQLite 的运行时配置：`data/config/runtime_settings.json`（§3.3.1，UI 可写、热更新、优先级高于 .env，存更新源 / ghproxy 前缀 / MirrorChyan CDK 与有效期 / sp_id）。

## 5. API 概览

> 标注「规划」的行为未实现（M5/M6 排期）；「已裁掉」为 2026-08-14 用户决定移除。

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/devices` | 设备列表 |
| POST | `/api/v1/devices` | 添加设备 |
| POST | `/api/v1/devices/detect` | 扫描 ADB 设备（`adb devices -l`）+ 环境状态 |
| GET | `/api/v1/devices/{id}` | 设备详情 |
| PUT | `/api/v1/devices/{id}` | 更新设备（部分字段） |
| DELETE | `/api/v1/devices/{id}` | 删除设备 |
| POST | `/api/v1/devices/{id}/connect` | 连接设备（真实 ADB 握手 + 可选 MAA 引擎会话） |
| POST | `/api/v1/devices/{id}/disconnect` | 断开设备 |
| GET | `/api/v1/devices/{id}/resolution` | 查询设备分辨率（`wm size`） |
| POST | `/api/v1/devices/{id}/resolution` | 设置分辨率（MAA 16:9 / 9:16，真机临时调整） |
| POST | `/api/v1/devices/{id}/resolution/reset` | 重置分辨率（`wm size reset`） |
| POST | `/api/v1/tasks/{device_id}/run` | 启动任务组合（串行队列，前置失败→409，引擎连接失败→502） |
| POST | `/api/v1/tasks/{device_id}/stop` | 停止任务（幂等） |
| GET | `/api/v1/tasks/{device_id}/status` | 任务状态（idle/running/stopping/finished/error/stopped + 引擎/资源就绪） |
| GET | `/api/v1/tasks/runs/{run_id}/logs` | 任务历史日志（S-05 持久化） |
| GET | `/api/v1/tasks/logs?days=N&device_id=` | 历史日志按天分组（仅今天之前，本地时区归档倒序；当天日志由 /logs/today 提供） |
| GET | `/api/v1/tasks/logs/today?device_id=` | 当天日志（本地时区，时间正序）——实时面板回填，跨页面保留 |
| WS | `/api/v1/tasks/ws/logs?device_id=N` | 实时日志流（S-05，eventbus 推送；日志行携带 DB `id` 供前端去重） |
| GET | `/api/v1/resources/status` | MAA 资源包状态（本地就绪/版本 + 远端最新 + 更新进度 + 动态资源状态 + 更新源） |
| POST | `/api/v1/resources/update` | 后台下载/更新引擎包（按更新源分发：GitHub release 或 MirrorChyan 增量包） |
| POST | `/api/v1/resources/sync` | 动态资源增量同步（MaaResource，按更新源分发 diff/full/mirrorchyan） |
| GET | `/api/v1/resources/stages` | 引擎包关卡代号列表（任务参数「目标关卡」搜索） |
| GET | `/api/v1/resources/items` | 引擎包材料/物品表（item_index.json，任务参数「指定掉落」搜索选择） |
| GET | `/api/v1/settings/mirror` | 镜像源设置读取（更新源 / ghproxy 前缀 / CDK 脱敏状态 / 有效期诊断） |
| PUT | `/api/v1/settings/mirror` | 镜像源设置保存（热更新立即生效；CDK 未变更保留有效期） |
| POST | `/api/v1/settings/mirror/check` | MirrorChyan CDK 有效期检查（对齐 cdk_expired_time 机制） |
| GET | `/api/v1/settings` | 通用设置分组读取（game/connection/ui，SQLite Setting 表） |
| PUT | `/api/v1/settings/{group}` | 通用设置分组保存（key 前缀 upsert，传 None 删除） |
| GET | `/api/v1/settings` | 通用设置分组读取（game/connection/ui/notify，SQLite Setting 表） |
| PUT | `/api/v1/settings/{group}` | 通用设置分组保存（key 前缀 upsert，传 None 删除） |
| GET | `/api/v1/settings/logs-export` | 打包日志目录为 zip 下载（问题反馈导出） |
| GET | `/api/v1/settings/geoip` | IP 定位（ip-api.com，NAS 出口 IP → 经纬度/城市，主题「按日出日落」兜底） |
| GET | `/api/v1/notifications/logs` | 外部通知发送记录（notify_logs，倒序） |
| POST | `/api/v1/notifications/test` | 测试发送（按当前 notify 配置逐渠道发一条） |
| POST | `/api/v1/notifications/logs/{id}/resend` | 重发某条记录（待真实渠道验证后启用） |
| GET | `/api/v1/copilot/list` | 本地作业 JSON 列表（含可读关卡名） |
| POST | `/api/v1/copilot/prts/code` | 解析作业站代码（`prts://99359` / `prts://s51251` / `s51251` / `maa://`）拉取作业/作业集 |
| POST | `/api/v1/copilot/prts/{id}` | 按作业 ID 从 prts.plus 拉取并保存 |
| GET | `/api/v1/schedules` | 定时任务列表（schedule_jobs） |
| POST | `/api/v1/schedules` | 新建定时任务（星期 × 时间 → 方案快照） |
| PUT | `/api/v1/schedules/{id}` | 更新定时任务（部分字段） |
| DELETE | `/api/v1/schedules/{id}` | 删除定时任务 |
| POST | `/api/v1/schedules/{id}/run` | 立即触发一次（试跑，不走时间匹配） |
| ~~POST~~ | ~~`/api/v1/configs`~~ | ~~配置管理（S-04）~~（已裁掉） |
| ~~POST~~ | ~~`/api/v1/remote/get-task`~~ | ~~远程控制·GET 任务（S-10）~~（已裁掉） |
| ~~POST~~ | ~~`/api/v1/remote/report-status`~~ | ~~远程控制·上报状态（S-10）~~（已裁掉） |
| POST | `/api/v1/toolbox/recruit` | 公招识别（T-01，规划 M5） |
| POST | `/api/v1/toolbox/depot` | 仓库识别（T-03，规划 M5） |
| POST | `/api/v1/toolbox/operbox` | 干员识别（T-02，规划 M5） |
| POST | `/api/v1/toolbox/gacha` | 抽卡（T-05，规划 M5） |
| WS | `/ws/logs` | 日志流 |
| WS | `/ws/screen` | 画面流 |
| GET | `/healthz/startup` `/ready` `/live` | 容器探针 |

## 6. 安全

| 面 | 措施 |
|----|------|
| 鉴权 | 首期基础 Token（`MAAWEB_SECRET_KEY` 派生）；二期用户系统 |
| 容器 | 非 root 运行、cap drop、资源 limit |
| 网络 | 仅暴露 Nginx 端口；内部 API 服务不暴露 |
| 数据 | 配置含企鹅/一图流 ID 属敏感信息，SQLite 卷权限收紧 |

## 7. 部署

### 7.1 本地开发模式（当前阶段）

> **决策**：开发阶段不依赖 Docker，直接在宿主机本地运行；Docker 部署保留为发布阶段目标（见 7.2）。

```
浏览器 ──:5173──► Vite Dev Server (前端)
                    │  /api、/healthz → http://127.0.0.1:8000 (代理)
                    └  /ws            → ws://127.0.0.1:8000  (代理)

uvicorn app.main:app --reload --port 8000 (后端 FastAPI)
  └─ AsstProxy ──► MAA Asst 核心（ctypes 直调 MaaCore，S-07 下载引擎包）
```

| 端 | 命令 | 地址 |
|----|------|------|
| 后端 | `pip install -e "backend[dev]"` → 在 `backend/` 下 `uvicorn app.main:app --reload --port 8000` | http://127.0.0.1:8000 |
| 前端 | `cd frontend && npm install && npm run dev` | http://127.0.0.1:5173 |

本地模式下：
- 网关层由 Vite dev 代理替代（Nginx 仅用于 Docker 拓扑）。
- 数据目录为本地默认路径（`config_file` / `database_url` 默认值），无需挂载卷。
- 未下载 MAA 引擎包时后端处于「状态降级」，属预期（通过页面「MAA 引擎包」或 `POST /api/v1/resources/update` 下载后自动就绪）；前端探针用 `httpRoot`（`/`）+ `validateStatus` 兼容非 2xx 响应。
- 设置页保存的镜像源 / MirrorChyan CDK 写入 `data/config/runtime_settings.json`（§3.3.1），与 SQLite 同目录，热更新生效；测试环境由 conftest 指向临时目录隔离。

### 7.2 Docker Compose 部署（发布阶段目标）

| 服务 | 镜像 | 端口 | 卷 |
|------|------|------|-----|
| nginx | 前端多阶段构建 | 8080 | — |
| api | 后端多阶段构建 | 8000（内部） | config / logs / cache / media |

多架构：buildx CI 构建 `linux/amd64` + `linux/arm64`；引擎为 MAA 官方发布包（`MAAWEB_RESOURCE_PLATFORM` 选 `linux-x86_64` / `linux-aarch64`），运行时下载安装，无需在镜像内编译。
