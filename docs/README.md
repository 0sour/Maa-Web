# Maa-Web 开发文档

本项目所有规划文档，功能覆盖以 MAA 客户端**源码**（`参考/MaaAssistantArknights`）逐项核对为最高基准，官方文档（[docs.maa.plus](https://docs.maa.plus/zh-cn/)）作为辅助参考。

| 文档 | 说明 |
|------|------|
| [PRD.md](./PRD.md) | 产品需求文档：MAA 全功能映射（源码核对版）、模块详细需求、验收标准（含 §4.5 实现进度总览） |
| [roadmap.md](./roadmap.md) | 开发路线图：M2~M7 分阶段规划，每阶段含功能交付与验收 |
| [architecture.md](./architecture.md) | 技术架构：引擎集成、任务模型、远程控制协议、API 设计、数据模型 |
| [testing.md](./testing.md) | 测试流程规范：风险→检查矩阵、测试分层、门禁命令、flake 策略、回归清单 |
| [DEPLOY.md](./DEPLOY.md) | NAS 部署指南：架构选择、三步启动、网络 ADB 设备接入、数据卷/升级、常见问题 |
| design-system-arknights.md (../ui-design/design-system-arknights.md) | UI 设计规范：明日方舟主题 Token、组件契约、模板页面（配套设计稿见 [ui-design/](../ui-design/)） |

## 快速索引

- 全部功能清单（含编号）：见 [PRD §4](./PRD.md#4-功能需求与-maa-桌面端逐项对齐)
- 真实实现进度（与代码核对）：见 [PRD §4.5](./PRD.md#45-实现进度总览2026-08-15-核对) 与 [roadmap 里程碑状态表](./roadmap.md#里程碑状态表)
- 引擎任务参数规范：以**客户端源码模型**为准（`参考/MaaAssistantArknights/src/MaaWpfGui/Configuration/Single/MaaTask/`），协议文档见 [MAA 集成文档](https://docs.maa.plus/zh-cn/protocol/integration.html)
- 远程控制协议：~~已裁掉~~（NAS 端口访问即远程控制，2026-08-14 决定），相关代码见 [architecture §3.8](./architecture.md)

## UI 设计资产

| 文件 | 说明 |
|------|------|
| [03-arknights.html](../ui-design/03-arknights.html) | 选用风格设计稿：明日方舟主题总览仪表盘（可独立打开预览） |
| [07-component-gallery.html](../ui-design/07-component-gallery.html) | 全控件组件画廊：按钮/输入/下拉/表单/列表/日志等全部交互控件示例 |
| [design-system-arknights.md](../ui-design/design-system-arknights.md) | 设计规范：Token 体系、组件 Props/States 契约、模板页面、无障碍标准 |

> 设计稿与规范为前端实现契约：正式开发时组件需引用规范中的 Token（CSS 变量），参数控件语义对齐 PRD §4.3「控件类型速查」。

## 本地开发（当前阶段优先）

> **决策**：开发阶段不依赖 Docker，直接在宿主机本地运行（Docker 部署保留为发布阶段目标）。详见 [architecture.md](./architecture.md)。

| 端 | 命令（在项目根目录执行） | 地址 |
|----|-------------------------|------|
| 后端 FastAPI | `pip install -e "backend[dev]"` → `uvicorn app.main:app --reload --port 8000`（在 `backend/` 下） | http://127.0.0.1:8000 |
| 前端 Vite | `cd frontend && npm install && npm run dev` | http://127.0.0.1:5173 |

- 后端已附带 `backend/.env`（git 忽略）：本地开发数据目录指向 `backend/data/`（工作区内，兼容 TRAE 沙箱权限），生产 Docker 仍用 `/data` 卷。
- 前端 dev 代理已配置：`/api`、`/healthz` → `:8000`，`/ws` → WS `:8000`，浏览器直接访问前端即可联调。
- 健康检查探针：`/healthz/live` `/healthz/ready` `/healthz/startup`（本地可直接 curl 验证）。
- 后端首次启动若未下载 MAA 引擎包则 UI 显示「状态降级」，属预期（通过页面「MAA 引擎包」或 `POST /api/v1/resources/update` 下载完整发布包后自动就绪）。
- **更新源配置**：「设置」页（`/settings`）选择更新源（GitHub 官方 / Mirror酱 MirrorChyan）+ ghproxy 镜像前缀 + MirrorChyan CDK（有效期检查）；保存写入 `backend/data/config/runtime_settings.json`，热更新立即生效，无需重启（覆盖 .env 默认值）。
- Docker 相关（compose/镜像）不影响本地开发，可暂不安装。
- 每次改动后请按 [testing.md](./testing.md) 执行门禁回归（编译 + pytest + 前端构建 + 手动检查清单）。
