# 🚀 Maa-Web · 面向 NAS 的 MAA Web 控制平台

[![MAA v6.16.8](https://img.shields.io/badge/MAA-v6.16.8-%237c5cff)](https://github.com/MaaAssistantArknights/MaaAssistantArknights)
[![Docker 3-Container](https://img.shields.io/badge/Compose-3%20Services-%2322c55e)](#)
[![ARM64 + AMD64](https://img.shields.io/badge/Arch-ARM64%20%7C%20AMD64-orange)](#)

> 在 NAS 上通过 Docker 部署 MAA（MaaAssistantArknights 官方 Asst 核心），用浏览器随时随地控制明日方舟自动任务。

---

## ✨ 特性

- **🐳 一键 Docker 部署**：`docker compose up -d`，3 容器（nginx 静态+反代 / FastAPI / 内置 adb），ARM64 与 AMD64 NAS 通吃
- **📱 纯 Web 控制**：桌面/手机浏览器通用，无需桌面客户端
- **🔌 ADB over TCP**：连接局域网内任何 Android 模拟器/真机（容器内置 adb，网络 ADB 接入）
- **📋 任务编排 + 方案**：九类任务参数面板（对齐 MAA 客户端源码）+ 拖拽队列 + 方案保存调出 + 左列表右参数双栏布局；方案与队列草稿**存后端**（换浏览器/设备数据一致，旧本地数据自动迁移）
- **⏰ 自动任务（多账号轮换）**：任务组 × 多个执行时间点（各自星期/时间/冲突策略：排队·跳过·强制），每时间点绑定多个账号（设置·账号组维护），逐个执行、账号切换由引擎完成、失败自动跳过并记日志；RUN TEST 一键测试
- **💾 全量配置备份**：一键导出全部配置（设备/方案/自动任务/账号组/设置/镜像源与代理）为 zip；导入覆盖恢复，导入前自动备份
- **🔔 外部通知**：任务完成/出错/停滞推送（Server酱 / 钉钉 / 自定义 Webhook，多渠道并行）
- **📊 作战日志**：当天实时流（跨页保留）+ 历史按天归档（本地时区），按来源区分（普通任务 / 自动任务 / 手动运行），级别过滤 + 关键字搜索
- **🎨 主题自动切换**：深色 / 浅色 / 自动（按当地日出日落或手动时间，IP 定位兜底）
- **🛡 停滞检测**：任务卡死超时提醒 + 通知（对齐 MAA RunningState）
- **🔄 双更新源**：引擎包与动态资源支持 GitHub 官方源 / Mirror酱（MirrorChyan）高速源（CDK 有效期检查 + OTA 增量包）
- **🧊 ARM64 原生支持**：引擎为 MAA 官方发布包（`linux-aarch64` / `linux-x86_64`），运行时下载，无需镜像内编译 C++ 依赖
- **💾 NAS 友好持久化**：4 个命名 Volume 分层（配置/日志/缓存/媒体），容器重启/重建数据不丢，群晖/极空间/Unraid 兼容，非 root 运行

---

## 🏗️ 架构速览（3 容器）

```
浏览器 ──:8080──► maaweb-nginx
                    │
                    ├─ 静态资源 ──► /usr/share/nginx/html  (前端 dist)
                    ├─ /api/*   ──► maaweb-api:8000        (FastAPI)
                    └─ /ws/*    ──► maaweb-api:8000        (WebSocket 日志流)

maaweb-api:8000
  ├─ FastAPI 路由层
  ├─ AsstProxy ──► MAA Asst 核心（ctypes 直调 MaaCore，S-07 下载引擎包）
  └─ SQLite (maaweb-config volume)
        │
        └──► ADB over TCP ──► 局域网模拟器/真机
```

---

## 🚀 快速开始

> **开发阶段**：直接本地运行（不依赖 Docker）；Docker 部署为发布阶段目标，见下方「Docker 部署」。

### 🖥️ 本地开发（当前推荐）

```bash
# 1. 后端 FastAPI（在 backend/ 下）
pip install -e "backend[dev]"
cd backend
uvicorn app.main:app --reload --port 8000

# 2. 前端 Vite（另开终端，在 frontend/ 下）
cd frontend
npm install
npm run dev
```

浏览器访问 **http://127.0.0.1:5173**（前端 dev 代理已把 `/api`、`/healthz`、`/ws` 转发到 `:8000`）。
后端 API 直连：http://127.0.0.1:8000 （探针 `/healthz/live` `/ready` `/startup`）。

> 未下载 MAA 引擎包时 UI 显示「状态降级」，属预期（通过页面「MAA 引擎包」下载官方发布包后自动就绪）。「设置」页可选择更新源（GitHub 官方 / Mirror酱）并配置 ghproxy 镜像前缀与 MirrorChyan CDK（含有效期检查）。更多说明见 [docs/README.md 本地开发](./docs/README.md#本地开发当前阶段优先)。

### 🐳 Docker 部署（发布阶段）

#### 前置条件
- NAS / Linux 主机已安装 Docker Engine ≥ 24 和 Docker Compose Plugin ≥ 2.20
- 至少 **2GB 可用内存**（重度任务推荐 4GB+）
- 局域网内已有可被 ADB 连接的 Android 模拟器（推荐 MuMu 12 / 雷电 9），开启「ADB 调试」

#### 三步启动

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env：至少修改 MAAWEB_SECRET_KEY 为你自己的强随机串
#    注：当前版本密钥仅启动检查、不强制校验；公网暴露需自行加反代（见 docs/DEPLOY.md §8）
#    Windows PowerShell 用：copy .env.example .env

# 3. 一键构建 + 启动
docker compose up -d --build
```

启动后访问：**http://<你的 NAS IP>:8080**

> ⚙️ **架构与时区**：ARM NAS 用默认 `linux-aarch64`；x86 NAS 在 `.env` 设 `MAAWEB_RESOURCE_PLATFORM=linux-x86_64`（引擎包按架构下载）；时区用 `TZ=Asia/Shanghai`（日志按天归档/定时执行依赖）。设备接入用**网络 ADB**（容器已内置 adb）。完整指南见 **[docs/DEPLOY.md](./docs/DEPLOY.md)**。

检查日志：
```bash
docker compose logs -f api       # 看 MAA 后端日志
docker compose logs -f nginx     # 看反代 / 静态服务日志
```

停止：
```bash
docker compose down              # 保留 volume 数据
docker compose down -v           # ⚠️ 删除所有 volume（清配置用）
```

---

## 📦 目录结构

```
Maa-Web/
├── backend/              # FastAPI + MAA Asst 引擎后端
│   ├── app/
│   │   ├── main.py
│   │   ├── api/          # 路由（v1：devices/tasks/resources/settings/copilot）
│   │   ├── core/         # config, runtime_settings（JSON 热更新）, events
│   │   ├── engine/       # ADB / MaaCore 代理 / 任务队列 / 资源包管理
│   │   ├── models/       # Device / TaskRun / LogEntry
│   │   └── schemas/      # Pydantic models
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/             # Vue 3 + Vite + TS 前端
│   ├── src/
│   ├── Dockerfile
│   └── package.json
├── nginx/                # 反代 + 静态托管
│   ├── Dockerfile
│   └── default.conf
├── ui-design/            # UI 设计资产（设计稿 + 组件画廊 + 设计规范）
│   ├── 03-arknights.html
│   ├── 07-component-gallery.html
│   └── design-system-arknights.md
├── docs/                 # 规划文档（PRD / 路线图 / 架构）
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🧪 健康检查端点（供 NAS 监控面板配置）

| 端点 | 用途 | 容器 |
|------|------|------|
| `GET http://<ip>:8080/healthz` | Nginx 存活 | nginx |
| `GET http://localhost:8000/healthz/startup` | API 启动完成（SQLite OK + MAA 引擎包就绪） | api（仅内部） |
| `GET http://localhost:8000/healthz/ready` | API 就绪，可接受请求 | api（仅内部） |
| `GET http://localhost:8000/healthz/live` | API 存活（liveness：不查外部依赖） | api（仅内部） |

> NAS 用户建议在群晖「资源监控」/ Container Manager 中直接依赖容器自带 healthcheck 状态即可。

---

## 🎨 UI 设计

界面采用**明日方舟主题**风格（灰蓝金属 + 金色点缀 + 锐利几何），设计稿与规范位于 [ui-design/](./ui-design/)：

| 资产 | 说明 |
|------|------|
| [03-arknights.html](./ui-design/03-arknights.html) | 总览仪表盘设计稿（浏览器直接打开预览） |
| [07-component-gallery.html](./ui-design/07-component-gallery.html) | 全控件组件画廊：按钮/输入/下拉/表单/列表/日志等全部交互控件 |
| [design-system-arknights.md](./ui-design/design-system-arknights.md) | 设计规范：Token 体系、组件 Props/States 契约、模板页面、无障碍 |

> 设计规范为前端实现契约，正式开发时组件引用其中的 CSS 变量 Token，参数控件语义对齐 PRD §4.3「控件类型速查」。

---

## 🗺️ 路线图

开发规划文档（覆盖 MAA 桌面端全部功能）：[docs/](./docs/README.md)

| 阶段 | 内容 | 状态 |
|------|------|------|
| **M1** | 项目脚手架 + 3 容器 Docker 化 + healthz 打通 | ✅ 已完成 |
| **M2** | 引擎接入 + 设备管理：ADB 设备/模拟器检测/触控模式 + 任务队列 + WS 日志 + 引擎包管理（GitHub/Mirror酱 双源） | ✅ 已完成 |
| **M3** | 日常任务模块：刷理智/公招/基建换班/信用购物/领奖 + 任务编排 | 🚧 进行中（9 类任务参数面板与队列编排已就绪，真机逐项验收中） |
| **M4** | 高级玩法模块：自动战斗(抄作业)/肉鸽/生息演算/自定义任务 | 🚧 进行中（作业站 prts.plus 集成已完成，执行验收待排期） |
| **M5** | 工具箱模块：公招/干员/仓库识别 + 抽卡/窥屏/小游戏 | ⏳ 待排期 |
| **M6** | 调度与系统功能：定时执行/通知/配置管理/日志中心/自动更新/外服/GPU | ⏳ 待排期 |
| **M7** | NAS 优化 + 发布 v1.0：双架构镜像/中断恢复/安全加固/压测 | ⏳ 待排期 |

> 每阶段的详细功能交付与验收标准见 [docs/roadmap.md](./docs/roadmap.md)。

---

## 📚 感谢参考

- [MaaXYZ/MaaFramework](https://github.com/MaaXYZ/MaaFramework) — 官方核心引擎（Apache-2.0）
- [ravizhan/MWU](https://github.com/ravizhan/MWU) — Vue+FastAPI WebUI 架构参考（MIT）
- [MistEO/MXU](https://github.com/MistEO/MXU) — Tauri GUI 的 PI 协议解析思路
- [overflow65537/MFW-PyQt6](https://github.com/overflow65537/MFW-PyQt6) — Runner 状态机参考

---

## ⚠️ 免责声明

本项目仅供学习交流使用。明日方舟为鹰角网络的注册商标，本项目与鹰角网络无任何关联。使用本项目进行游戏操作请遵守游戏用户协议，造成的任何后果由使用者自行承担。
