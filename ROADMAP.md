# MAA Web 控制台 — 任务规划

基于 maa-cli 的 Web 控制台，参考 MXU、maa-cli-webui、ws-scrcpy 与 MaaAssistantArknights 原版客户端持续完善。

## 已完成

- **任务队列**：多任务编排、参数编辑、拖拽排序、右键菜单、状态指示（✓/✗/·/●）、参数摘要、运行历史「重新运行」、侧栏面板排队任务列表、队列状态实时自动保存（防抖 500ms）
- **定时任务**（含 2026-08-06 单任务支持）：周几+时间点调度、错过补偿（3h）、下次执行预览；执行内容可选「任务队列」或「单任务」——单任务配置界面与任务队列完全一致（17 类任务类型、队列同款字段表单：基础/高级分组、肉鸽 theme 联动动态选项、抄作业本地文件+作业代码导入+作业集预览勾选即添加）；触发时生成独立任务文件 `tasks/maa-web-single.json` 执行（不覆盖 daily.json）；支持后置动作；保存校验任务类型；编辑回填
- **快速任务页重构**：卡片式任务选择（日常/作战/抄作业/集成战略/其他 5 分类）、基础/进阶参数折叠、运行设置独立、最近使用标记、抄作业 maa:// 代码直达、视频识别（走工具通道）
- **抄作业作业列表（O，2026-08-06 收尾）**：作业代码/作业集导入后自动预览展开列表（关卡/作者/浏览/难度/说明），支持勾选执行与全选/取消全选——快速任务页、队列 Copilot（勾选即添加/取消即移除，本地作业文件下拉）、定时任务单任务三处一致
- **抄作业上传作业文件（Q，2026-08-06 完成）**：`POST /api/copilot/upload`（JSON body → 校验 stage_name/actions → 保存 `config/copilot/upload-<时间戳>.json` → 返回 path+items）；快速任务加「上传作业文件」按钮；保全/悖论模拟加上传按钮；队列 Copilot 上传后显示在作业列表
- **信息识别页**（原工具箱+识别结果合并）：公招/仓库/干员识别卡片 + 识别结果历史（筛选/详情/删除）同页展示
- **设备连接与实例状态（K，2026-08-06）**：adb 扫描/连接/手动配置、分辨率调整、实时画面（帧率可选+自适应循环）、设备页「实例状态」卡片（连接状态+实时截图缩略 5s 刷新+任务状态+操作按钮）、ws-scrcpy 远程控制（风格/主题/自适应/精简对齐）、openScrcpyWindow 公共函数
- **配置管理**：config.toml 编辑、连接配置、profiles 选择；**多配置快照（D，2026-08-06）**：保存当前队列为命名配置/一键切换/删除（`config/maa-web/configs/*.json`，含关联 profile）；定时任务关联队列配置（触发先 applyConfig 再执行）与后置动作（关闭游戏/休眠/关机，systemd 动作容器内自动检测提示不可用）
- **库存维持（E，2026-08-06 完成）**：`maa fight -D<物品ID>=<数量>` 原生支持（收集到指定掉落数即停止，可多组）；`/api/items`（item_index.json 中文名/ID 搜索）+ 前端材料选择器（搜索+数量+删除，值 `ID=数量,ID=数量`），快速任务「掉落数停止条件」与队列「指定材料」均接入
- **今日关卡按凌晨 4 点切换（T，2026-08-06 完成）**：`getHours() < 4` 按前一天计算星期；容器 TZ=Asia/Shanghai 边界验证 03:59/04:00
- **主界面活动与今日关卡（A/F，2026-08-05 完成）**：队列页顶部「今日开放」（资源关按星期轮换+理智+掉落中文名）+「当期活动」（`maa activity`）；点击关卡智能路由（队列有理智作战直接填入，否则跳快速任务）；每 10 分钟轮询跨天自动切换；**自动检查更新**（GitHub Releases API + 6h 缓存、设置页状态提示、更新代理配置+测试按钮、--force 重装语义）
- **右侧实时日志面板（H，2026-08-05 完成）**：右侧固定栏（320px，手机端抽屉）、实时更新+吸底跟随+复制/清空/收起、侧栏「实时日志」按钮、任务开始自动展开
- **选项中文汉化（N，2026-08-06 收尾）**：客户端类型/代理倍率/服务器/额外选 Tag/设施/无人机用途/编队序号/助战模式/肉鸽与生息演算主题模式/突袭模式等全部 select/chips/boolMap 选项 `[值, 标签]` 中文对（值不变，显示层映射，参考原版 zh-cn.json）
- **输入选项化（J，分批完成）**：第一波作战关卡选择（快速任务+队列「关卡」字段搜索下拉，显示理智+掉落，`/api/stages/list` 全量 532 关，stages.json mtime 自动重载）；第二波肉鸽参数选择（`/api/roguelike` 按主题动态分队/难度/模式/核心干员，is_start 过滤，切换主题清空已选）；第三波队列侧 Roguelike 字段（squad/core_char/roles/difficulty 接入同一 picker，roles 数据源来自 `/api/roguelike`）；**第四波未做：编队/客户端等其余字段**
- **小游戏（牛杂）（X，2026-08-06 完成）**：MiniGame=资源任务链经 core `CustomTask` 执行（Gacha 走 C API 无 cli 入口、Peep=GUI 投屏）；动态扫描 `resource/tasks/tasks.json`（`*@Store@Begin`/`MiniGame@*` 入口含 doc 中文名，mtime 随 `maa update` 自动增删）→ `/api/minigames`；快速任务「小游戏」卡片 + `/api/run` minigame 分支生成 `tasks/maa-web-minigame.json` 执行；当前可用入口：`Store@Begin`（绿票、黄票商店）
- **快速任务扩展（L，2026-08-06 判定不可行）**：maa-cli 0.7.5 tool 任务不支持 `Gacha`/`MiniGame` 类型，等后续版本支持再评估
- **ws-scrcpy 远程控制优化（M，专项完成）**：①风格统一（三态主题对齐色板）②画面自适应（fitToScreen+等比缩放）③体验衔接（列表精简/覆盖层隐藏）④集成方式（保持新标签页，iframe 需反代 8000 端口收益低）⑤移动端细节（断线自动重连 3s 退避、状态文案汉化、≤768px 布局）；源码改动需 `npm run dist:prod` 重建，构建重置移动端 patch 需重新追加
- **日志面板**：时间戳/级别着色/吸底跟随/显示更多/复制/下载
- **外观**：深/浅/跟随系统主题 + 强调色
- **安全与 PWA**：访问令牌（Bearer 校验）、manifest + 图标 + service worker
- **更新管理（F，2026-08-05 完成）**：自动检查更新、设置页更新状态、「更新代理」配置 + 测试代理按钮、安装按钮 --force 重装语义、runMaintenance 路径修复（/api/ 前缀）
- **README + 关于页**（2026-08-05 完成）：完整 README（功能/边界/部署/Docker/架构/未来任务）+ 侧边栏「关于」页（极简 markdown 渲染）
- **Docker 部署**（2026-08-05 完成）：Dockerfile（node:20-slim + adb/curl/libatomic1）、compose（代理环境变量化、~/.config、~/.local/share、~/.local/state、~/.cache/maa 挂载无缝迁移）；已实际部署运行
- **GitHub 同步**（2026-08-05）：仓库 0sour/Maa-Web，敏感信息（内网 IP/本地路径）已清理，作者身份 0sour
- **架构**：纯轮询（5s）无 SSE、静态资源版本号缓存策略、HTML 标签完整性校验（严格解析器）、jsdom + 服务端集成测试

## 待用户验证（已修复，实测后移除）

- [ ] **R 定时任务时区**（2026-08-06 已修复）：根因=容器时区 UTC 与本地差 8 小时；修复=compose 加 `TZ=Asia/Shanghai`（node 自带 ICU 时区数据）。API/落盘/tick 逻辑验证正常，待实测确认
- [ ] **S 公招识别**（2026-08-06 已修复）：链路实测正常（asst.log callback 格式、`maa dir log`=/state/maa/debug、1080x1920 支持）；体验根因=未进入词条页时失败无提示；增强=无结果时读日志最近 `SubTaskError`（taskchain=Recruit）提示具体任务（如 `RecruitBegin 识别不到页面`）。待实测确认

## 待办（按优先级）

### P1 功能完善

- [ ] **C 掉落统计页**：解析日志 Drops 回调，按次/按日汇总素材掉落
- [ ] **P 外部通知**（搁置，需额外 docker 部署，后续评估）：任务完成/失败推送（Bark/ServerChan/Telegram/Discord/Webhook）
- [ ] **U 设备页实时画面闪烁**（待决策，用户倾向移除）：K 实例卡片截图缩略 5s 轮询导致一闪一闪。方案：1.直接移除缩略图（推荐）2.低频刷新（治标不治本）3.双缓冲 onload 替换 4.仅设备页可见时刷新+保留旧图（最稳改动最大）

### P1 UI/UX

- [ ] **J 第四波（剩余）**：编队/客户端等其余字段选项化（第一~三波已完成，见上）
- [ ] 队列/快速任务运行错误自动重试策略

### P2

- [ ] **多设备支持**：多实例并行（连接/截图/任务独立），需重构 server 连接管理
- [ ] **新手引导**：首次使用分步引导

### P3 细节

- [ ] 日志按级别过滤
- [ ] 侧栏常驻 adb 连接状态
- [ ] 截图失败自动重试与降级提示
- [ ] 掉落/仓库趋势图（canvas 折线）

## 回退指引

- 关卡选择（J 第一波）：`server/stages.js`、`server/index.js`（/api/stages/list）、`public/app.js`（buildStagePicker/loadStageOptions 及 buildQuickInput/fieldInput 的 stage 分支）
- 肉鸽选择（J 第二/三波）：`server/roguelike.js`（/api/roguelike）、`public/app.js`（buildPicker 通用组件 + squad/coreChar/difficulty/mode/roles 分支 + theme 联动清空）
- 汉化（N）：`server/taskSchemas.js`（CLIENTS/ROGUELIKE_THEMES/RECLAMATION_THEMES 及 raid/supportUnitUsage/roguelike mode/reclamation options）、`server/dailyTaskTypes.js`（CLIENTS 及 series/server/extra_tags_mode/facility/drones/formation_index/support_unit_usage/theme options）、`public/app.js`（buildQuickInput select 分支 + fieldInput chips 分支的 `[值, 标签]` 渲染）
- 定时任务单任务：`server/schedules.js`（task 字段/runSingleTask）、`server/index.js`（scheduler.init runSingleTask、BY_TYPE 校验）、`public/app.js`（renderScheduleTaskType/Fields 队列式渲染）、`public/index.html`（schedule-mode/schedule-task-* 弹窗区）

## 参考项目

- MaaAssistantArknights 原版客户端源码（差距分析依据）
- MXU 与 maa-cli-webui：UI/交互参考
- ws-scrcpy：远程控制（独立服务 8000 端口，maa-web 集成跳转）

## 测试与部署

- 回归（开发环境，脚本在 /tmp/opencode/）：`for t in ui-device ui-runner ui-screen ui-queue-checkbox ui-new-fields ui-results ui-schedule ui-queue-v2 ui-poll ui-mxu ui-scrcpy ui-token ui-quick ui-autosave ui-copilot ui-drops ui-stages ui-minigame ui-schedule-queue ui-upload ui-about ui-configs; do echo "== $t =="; timeout 90 node /tmp/opencode/$t-test.js 2>&1 | tail -1; done && timeout 90 node /tmp/opencode/server-api-test.js 2>&1 | tail -1`
- 前端改动后更新 `public/index.html` 资源版本号并重建容器：`export BUILD_HTTP_PROXY=http://192.168.10.110:7890 BUILD_HTTPS_PROXY=http://192.168.10.110:7890 && sg docker -c "docker compose up -d --build"`
- HTML 改动后跑标签完整性校验（Python 严格解析器）
- ws-scrcpy 服务：`<ws-scrcpy 目录>/dist`，`PATH=<项目目录>/bin/platform-tools:$PATH node ./index.js`；源码改动需 `npm run dist:prod` 重建（见 `docs/WSCRCPY.md`）
