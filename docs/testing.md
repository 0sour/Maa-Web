# Maa-Web · 测试流程规范（Testing & Quality Gates）

> 版本：v1.1 ｜ 更新日期：2026-08-14
> 本规范定义 Maa-Web 的测试策略、检查门禁与回归流程。原则：**每个测试对应一个已命名的风险；每个阻塞检查都有明确的失败响应**。
> 当前为本地开发阶段（无 Docker / 无 CI），门禁以本地命令形式落地；M7 发布阶段迁移到 CI 时，本规范中的命令直接映射为 CI job。

---

## 1. 测试分层（Test Pyramid）

按「越快、越确定、越前置」原则放置检查，从下到上：

| 层 | 内容 | 速度 | 确定性 | 位置 |
|----|------|------|--------|------|
| L0 静态检查 | 后端 `compileall` + ruff；前端 `vue-tsc -b`（类型门禁） | 秒级 | 高 | 每次改动立即跑 |
| L1 单元/组件 | 后端 pytest：路由/服务/状态机纯逻辑（不连真机/真引擎） | 秒~分钟 | 高（无外部依赖） | 每次改动 |
| L2 契约/集成 | pytest + ASGI 测试客户端：API 端点、健康探针、设备 CRUD | 分钟级 | 中（依赖 SQLite 临时库） | 每次改动 |
| L3 端到端 | 前端构建产物 + 浏览器渲染检查 + 真后端探针 | 分钟级 | 中 | 每里程碑 / 涉及前端布局改动 |
| L4 真机联调 | MAA Asst 引擎 + ADB 模拟器/真机实连 | 分钟级 | 依赖环境 | 每里程碑验收（M2+） |

> **门禁预算**：L0+L1 全程 ≤ 2 分钟；L2 ≤ 3 分钟。超时视为检查异常，先排查慢因，不允许静默跳过。

---

## 2. 风险 → 检查映射（Risk → Check Matrix）

每个关键风险必须有一个检查、测试或显式豁免：

| # | 风险 | 对应检查 | 层 | 失败响应 |
|----|------|---------|----|---------|
| R1 | 后端语法/导入错误导致启动失败 | `python -m compileall app` + `python -c "import app.main"` | L0 | 修复报错文件后重跑；无法修复则回退该改动 |
| R2 | ORJSONResponse 依赖缺失 → 全接口 500 | `requirements.txt` 含 `orjson>=3.10,<4.0`；`/healthz/live` 探针返回 JSON | L0/L2 | 补依赖后重装 |
| R3 | 健康探针返回非 JSON / 状态码错误 | `tests/test_health.py`（断言 200/503 与 body 结构） | L2 | 修复探针逻辑；探针变更必须先改测试 |
| R4 | 设备 CRUD 破坏其他端点（回归） | 全量 pytest + 启动回归清单（§5） | L2/L3 | 定位破坏点，修复后全量重跑 |
| R5 | 前端 TS 类型错误 → 构建失败 | `npm run build`（含 `vue-tsc -b`） | L0 | 修复类型；禁止 `any` 逃生舱绕过 |
| R6 | 前端布局改动破坏既有交互 | 浏览器预览 + 手动检查清单（§5.3） | L3 | 修复布局/交互回归 |
| R7 | 路由/导航改动导致死链或 404 | 浏览器点击全部侧栏导航 | L3 | 修复路由表 |
| R8 | SQLite 数据路径在本地/容器不一致 | conftest 用临时目录注入；config 默认值单点维护 | L2 | 统一配置源，禁止硬编码路径 |
| R9 | MAA 引擎包缺失/加载失败导致后端崩溃 | 启动降级（`engine_ready=False` 不阻断启动）+ 探针 503 | L2 | 维持降级语义，不得 raise |
| R10 | 数据目录不可写 → 设备 CRUD 500 | 后端启动日志含 `Data directories ensured`；`GET /api/v1/devices` 返回 200 | L3 | 检查进程对数据目录的写权限；本地开发用 `backend/.env` 指向工作区内路径（TRAE 沙箱无法写盘根 `/data`） |
| R11 | ADB 缺失/连接失败 → 设备 connect 崩溃 | `tests/test_adb.py` + `tests/test_manager.py`：adb 缺失→`AdbUnavailableError`→status=error + `last_error` 持久化；connect 失败→status=error 不 500 | L1/L2 | 状态机如实报告（error+原因），前端卡片展示原因 |
| R12 | MAA 引擎会话创建失败导致连接中断 | `tests/test_asstproxy.py`（fake Asst 引擎）+ manager：引擎失败仅降级（online + 提示），不阻断 ADB 连接 | L1 | 降级语义：设备在线但引擎不可用 |
| R13 | 任务队列启动前置失败崩溃（设备离线/引擎缺失/资源包缺失/重复启动） | `tests/test_taskrunner.py` + `tests/test_tasks_api.py`：前置失败→`TaskQueueError`→API 409 + 人话 detail；成功路径状态机 `idle→running→finished` + run/logs 落库 | L1/L2 | 前置校验显式报告，不产生 500 |
| R14 | 停止语义：任务中止后状态错乱 / 重复 stop | `tests/test_taskrunner.py`：stop→`stopping`→worker 退出→`stopped`；idle 时 stop 为 no-op | L1 | 停止幂等，状态机终态正确 |
| R15 | 资源包主动下载/更新失败（网络/解压/校验） | `tests/test_resource_mgr.py` + `tests/test_resources_api.py`：mock httpx 全流程（下载→解压→原子替换→version.json）；远端失败降级（status 不抛错）；更新任务幂等 | L1/L2 | 失败原因结构化上报（update_error），本地旧资源不受影响（备份+原子替换） |
| R16 | MirrorChyan 双更新源 / CDK 有效期：保存后有效期丢失、CDK 回显掩码、增量包损坏 | `tests/test_settings_api.py`（9 用例：CDK 保存/清空/未变更保留有效期/检查接口/脱敏）+ `tests/test_resource_mgr.py` MirrorChyan 用例（增量包 changes.json deleted + 覆盖、路径穿越防御、os/arch 映射、up_to_date、content-length 进度） | L1/L2 | CDK 未变更时保留旧有效期；增量包逐条容错（占用跳过、越界跳过）；检查失败结构化提示，不抛 5xx |
| R17 | MAA 分辨率限制：非 16:9/9:16 设备启动任务崩溃 | `tests/test_taskrunner.py` 分辨率预检（拒绝/提示文案/放行/纯函数）+ `tests/test_devices.py` / `tests/test_adb.py`（`wm size` 解析/设置/重置，Override 优先） | L1/L2 | 启动前预检给出明确引导（USB 真机 1080x1920 / 模拟器 1920x1080），预检失败不阻塞（AsstConnect 终判）；设备页提供查询/设置/重置 |
| R18 | 作业站（prts.plus）代码解析/拉取破坏任务流程 | `tests/test_copilot_mgr.py`（21 用例：代码格式解析、作业/作业集拉取校验、文件名安全、关卡名映射） | L1/L2 | 解析/拉取失败 → `CopilotFetchError` → API 400 人话提示；单个作业失败跳过不影响作业集其余作业 |

---

## 3. 检查门禁（Check Gates）

### 3.1 每次改动必跑（Pre-change Gates）

```powershell
# 后端（backend/ 下）
python -m compileall app           # L0: 语法
ruff check app tests               # L0: lint
pytest -q                          # L1+L2: 全部单元/集成测试

# 前端（frontend/ 下）
npm run build                      # L0: vue-tsc 类型门禁 + 产物构建
```

**失败响应**：任一命令失败 → 立即修复；修复后**重跑同一条命令**直至通过，再继续下一步。禁止「失败但继续」。

### 3.2 涉及布局/路由改动追加（+ Browser Check）

```powershell
# 前端（frontend/ 下），需后端 8000 + 前端 dev server 均在运行
npm run verify                      # L3: 无头浏览器自动化回归（脚本 frontend/scripts/verify-ui.mjs）
```

- 自动检查：首页 KPI/LINK START、设备管理 CRUD 冒烟（增/连/编/删）、占位页渲染、控制台无 JS 错误、无 ≥500 异常响应。
- 仍建议人工打开 http://127.0.0.1:5173/ 执行 §5.3 手动检查清单（视觉确认）。

### 3.3 每里程碑门禁（Milestone Gates）

- L4 真机联调（MAA Asst 引擎 + ADB）通过
- 全部 `pytest` 通过 + `npm run build` 通过
- 后端 3 个探针返回符合预期（`/healthz/live`=200, `/healthz/ready|startup`=200 或 503 取决于引擎包是否就绪）

---

## 4. Flake 策略（Flake Policy）

| 项 | 策略 |
|----|------|
| 判定阈值 | 同一测试连续 3 次运行出现不一致（rerun-disagreement）即判定 flaky |
| 处置时限 | 24 小时内修复；无法修复则 **quarantine（跳过 + 标注）**，禁止无限重试 |
| 隔离原则 | L1 测试必须 hermetic：不访问外网、不依赖真实时钟、不共享可变状态（每个测试独立临时目录） |
| 降级规则 | 被隔离的 flaky 测试必须带 `@pytest.mark.skip` 注明原因与恢复日期 |

---

## 5. 整体回归清单（Full Regression）

每次改动在「Pre-change Gates」基础上，按改动类型追加：

### 5.1 后端改动 → 追加

```powershell
# 启动回归（如服务未运行则先启动）
python -m uvicorn app.main:app --port 8000
Invoke-RestMethod http://127.0.0.1:8000/healthz/live   # 期望 200 + JSON
Invoke-RestMethod http://127.0.0.1:8000/healthz/ready  # 200 或 503（取决于引擎包是否就绪）
Invoke-RestMethod http://127.0.0.1:8000/api            # 期望 JSON 元信息
```

### 5.2 前端改动 → 追加

- `npm run build` 通过
- 浏览器访问首页：KPI 区渲染、双栏面板、LINK START 横栏**始终悬浮底部**
- 点击侧栏全部导航项：无死链、面包屑正确、占位页正常

### 5.3 手动检查清单（Browser Manual Checklist）

| # | 检查项 | 期望 |
|----|--------|------|
| 1 | 首页加载 | 无控制台报错；方舟主题（金属底/金色/直角）正常 |
| 2 | LINK START 横栏 | 无论内容多长始终悬浮视口底部 |
| 3 | KPI 卡 | 4 格展示，数值衬线字体，右上角金色角标 |
| 4 | 作战部署任务列表 | 勾选/选中交互正常，状态标签着色正确 |
| 5 | 参数面板 | 下拉/开关/数字输入可交互 |
| 6 | 作战记录日志 | 等宽字体，级别颜色（INFO/OK/WARN/ERROR）正确 |
| 7 | 侧栏导航 | 全部可点击，激活态金色斜切指示条 |
| 8 | 顶栏状态芯片 | 与后端探针状态一致（降级时显示「状态降级」） |

---

## 6. 覆盖策略（Coverage Policy）

- **不设全量覆盖率门槛**（避免 vanity coverage）。采用**变更代码覆盖**原则：新增/修改的代码路径必须被测试触达。
- 高价值路径强制覆盖：健康探针三端点、设备 CRUD 全生命周期、任务状态机（M2+）。
- 覆盖度量：`pytest --cov=app` 结果只作参考，以「每个关键风险有测试」为准（§2）。

---

## 7. 测试数据策略（Test Data）

- L1/L2 一律使用**合成数据**（构造 ADB 地址/设备名），不得触碰真实用户配置。
- 测试隔离：`conftest.py` 为每个测试注入独立临时目录作为 `data_dir` / SQLite 路径，测试间零共享。
- 含敏感字段（企鹅物流 ID / Token）的 fixture 禁止入库与打印。

---

## 8. 当前测试清单（Test Inventory）

| 文件 | 覆盖风险 | 状态 |
|------|---------|------|
| `backend/tests/test_health.py` | R2/R3：三探针 JSON 结构 + 状态码 | ✅ 已落地（4 用例） |
| `backend/tests/test_devices.py` | R4/R9/R11/R17：设备 CRUD 全生命周期 + connect 降级 + detect 端点 + 分辨率路由 + 重复设备查重 + 列表探活降级（保持在线/扫描失败不阻塞）+ 隔离 | ✅ 已落地（11 用例） |
| `backend/tests/conftest.py` | R8：临时目录隔离 + ASGI 客户端 + 表级隔离（含 runtime_settings.json 隔离） | ✅ 已落地 |
| `backend/tests/test_adb.py` | R11/R17：adb 输出解析（devices -l / connect）+ 路径解析 + 命令封装 + `wm size` 解析/设置/重置 + resolve_adb_path 优先级（设置页热更新 > env > PATH）+ USB connect serial 在线校验 | ✅ 已落地（39 用例） |
| `backend/tests/test_asstproxy.py` | R12：fake Asst 引擎（MaaCore 动态库）→ 会话创建/池/回调解析/任务映射/降级（含 copilot_mode 场景分发、OfflineConfirm 事件、Fight times≤0 剥离不限） | ✅ 已落地（40 用例） |
| `backend/tests/test_manager.py` | R11/R12：连接状态机（成功/拒绝/缺失/引擎降级）+ 环境状态 | ✅ 已落地（11 用例） |
| `backend/tests/test_taskrunner.py` | R13/R14/R17：任务队列状态机（前置校验/成功/失败/停止/快照/Copilot 系多作业展开）+ 日志持久化 + 分辨率预检 + 残留事件不串线 + 周计划按星期跳过 + OfflineConfirm 停止/续刷 + Mall 一日只执行一次 + 停滞检测（超时触发/提醒间隔/重置/开关） | ✅ 已落地（38 用例） |
| `backend/tests/test_tasks_api.py` | R13/R14：run/stop/status/logs 路由 + 409/422/404 语义 + 历史日志按天分组（仅今天之前/时区序列化）+ 当天日志接口（/logs/today） | ✅ 已落地（10 用例） |
| `backend/tests/test_resource_mgr.py` | R15/R16：引擎包状态/远端查询/下载-解压-原子替换全流程（zip + linux tar.gz）+ GitHub 镜像候选测速 + MirrorChyan（CDK 检查/增量包/os-arch/up_to_date）+ 动态资源同步（diff/full）+ item_index 材料表（可刷过滤）+ battle_data 干员表 + recruitment Tags + 肉鸽开局干员 + stage_codes 可导航过滤（导航任务/主线格式/活动缺失排除） | ✅ 已落地（58 用例） |
| `backend/tests/test_resources_api.py` | R15：resources status/update/sync/items/operators/recruit-tags/roguelike-core-chars 路由 + 失败上报 | ✅ 已落地（7 用例） |
| `backend/tests/test_settings_api.py` | R16：镜像源设置 GET/PUT（update_source / CDK 保存-回显-脱敏）/ 有效期检查 / CDK 未变更保留有效期回归 + 通用设置分组（GET/PUT/upsert/删除/422）+ logs-export zip + geoip（IP 定位成功/服务失败 502）+ proxy-test（代理连通成功/失败） | ✅ 已落地（18 用例） |
| `backend/tests/test_copilot_mgr.py` | R18：作业站代码解析（prts:// / maa:// / 简写 / 纯数字）+ 作业/作业集拉取 + 文件名安全 + 关卡名映射 + SSS 作业（type=SSS 免 opers 校验 + stage_name/strategy 细分校验）+ job_type | ✅ 已落地（24 用例） |
| `backend/tests/test_schedules_api.py` | M6 定时执行：CRUD 全流程 + 校验（空星期/空方案/坏时间/设备 404）+ 立即试跑（在线成功/离线 409/不存在 404） | ✅ 已落地（4 用例） |
| `backend/tests/test_scheduler.py` | M6 调度器：星期×时间匹配触发 + 时间/星期/禁用不匹配跳过 + 同分钟防重 + last_run_at 落库 + 触发日志持久化 | ✅ 已落地（5 用例） |
| `backend/tests/test_notify.py` | M6 外部通知：渠道消息构造（Server酱 URL/钉钉加签/自定义模板与默认 JSON）+ 发送主流程（无配置空返回/事件开关/多渠道+禁用过滤/HTTP 错误与异常落库）+ API（测试发送/记录/重发 404） | ✅ 已落地（11 用例） |
| `frontend/scripts/verify-ui.mjs` | R4/R6/R7/R11：L3 浏览器自动化回归（首页/设备 CRUD+连接终态/检测面板/占位页/控制台错误） | ✅ 已落地（27 断言） |

> 全量 pytest 实测：**285 passed**（2026-08-15）。用例数含参数化展开；新增模块已登记本表。

---

## 9. 命令速查（Quick Reference）

```powershell
# 后端全量测试
cd backend
python -m compileall app
ruff check app tests
pytest -q

# 前端类型门禁 + 构建
cd frontend
npm run build

# L3 浏览器自动化回归（需后端 8000 + dev server 运行中）
npm run verify

# 手动回归
#   启动后端 + 前端，浏览器打开 http://127.0.0.1:5173/
```
