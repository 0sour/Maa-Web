# MAA Web 控制台

基于 [maa-cli](https://github.com/MaaAssistantArknights/maa-cli) 的明日方舟自动化 Web 控制台。
手机 / 桌面浏览器远程管理 MAA：编排每日任务、定时执行、识别信息、远程控制设备。

纯轮询架构（无 SSE 长连接），弱网/移动网络稳定；纯原生前端（无构建步骤），服务端 Node.js + Express。

## 功能

- **任务队列**：17 类任务编排（唤醒 / 作战 / 公招 / 基建 / 信用 / 奖励 / 抄作业 / 肉鸽 / 生息演算 / 保全派驻 / 悖论模拟 / 自定义 / 单步 / 识别类 / 关闭游戏），拖拽排序、右键菜单、启用/停用、参数编辑、**实时自动保存**（防抖 500ms）、状态指示（✓/✗/·/●）、参数摘要、运行历史一键重跑
- **定时任务**：每周多时间点调度、错过补偿（3 小时内补执行）、下次执行预览、关联连接配置
- **快速任务**：卡片式任务选择（日常 / 作战 / 抄作业 / 集成战略 / 其他），基础/进阶参数折叠，抄作业作业站代码直达（`12345` / `maa://12345` / `prts://s12345`），视频识别
- **信息识别**：公招识别、仓库识别、干员识别 + 识别结果历史（筛选 / 详情 / 删除，存 200 条）
- **主界面今日关卡**：当天开放的资源关（按星期轮换，含理智与掉落材料）、当期活动关卡（`maa activity`），点击智能填入队列或快速任务
- **设备连接**：adb 扫描 / 连接 / 手动配置、分辨率调整、实时画面（帧率可选 + 自适应循环）
- **远程控制**：ws-scrcpy 集成（4 种解码器含 wasm 软解，手机全兼容，多点触控 / 键盘 / 方向 / 画质调节），UI 风格与主题跟随主站
- **日志面板**：右侧实时日志（可折叠、任务自动展开、吸底跟随、复制/清空）
- **设置**：主题（亮/暗/跟随系统）+ 强调色、访问令牌、自动检查更新（GitHub Releases + 更新代理 + 测试代理）、config.toml 编辑、连接配置、profiles 选择
- **PWA**：可添加到主屏幕全屏使用（manifest + 图标 + service worker）

## 功能边界

- **依赖 maa-cli / MaaCore 能力**：任务执行、识别、游戏内操作全部由 maa-cli 与 MaaCore 完成，本控制台只负责编排与展示；maa-cli 不支持的功能（如部分活动特殊机制）不可用
- **单设备**：当前为单实例模式（全局设备配置）；多设备并行（P2 规划中）
- **网络**：默认监听 `0.0.0.0:3100` 供局域网访问；**默认无鉴权**——建议部署后立即在设置页启用「访问令牌」；不要直接暴露到公网
- **外部通知**（Bark/Telegram 等推送）未实现（需额外部署，规划中）
- **更新无实时进度**：`maa update/install` 在后台运行时不输出进度（CLI 特性），完成后在日志显示结果；可配置更新代理加速下载
- **远程控制**：需要浏览器支持 WebCodecs 或 wasm（Broadway/TinyH264 软解兜底）；依赖 ws-scrcpy 独立服务（见部署）

## 部署

### 环境要求

- Node.js ≥ 20
- [maa-cli](https://github.com/MaaAssistantArknights/maa-cli) 已安装，`MAA_BIN` 或 `bin/maa`（本仓库附带）可用
- MaaCore 与资源已安装（设置页「安装 MaaCore 与资源」或 `maa install`）
- adb 可用（MaaCore 附带 platform-tools）

### 启动

```bash
cd maa-web
npm install          # 安装依赖（@yume-chan 相关保留、ws 等）
PORT=3100 node server/index.js
```

- 服务监听 `http://0.0.0.0:3100`
- 数据目录：`~/.config/maa/maa-web/`（queue.json / token.json / results.json / schedules.json / update.json）
- 手机访问：`http://<服务器IP>:3100/`，可在浏览器「添加到主屏幕」PWA 使用

### 远程控制（ws-scrcpy）部署

远程控制为独立服务（默认端口 8000），详见 [docs/WSCRCPY.md](docs/WSCRCPY.md)：

```bash
cd /tmp/opencode/ws-scrcpy
npm install
npx webpack --config webpack/ws-scrcpy.prod.ts
PATH=/vol1/1000/maa-web/bin/platform-tools:$PATH node ./index.js
```

页面侧边栏「远程控制」按钮会自动携带当前设备与主题跳转。

### 更新

```bash
git pull && npm install
# 前端改动后更新 public/index.html 中的资源版本号（app.js?v=x / style.css?v=x）
PORT=3100 node server/index.js
```

## Docker 部署

项目自带 `Dockerfile` 与 `docker-compose.yml`，支持容器化部署（适合 NAS / 服务器长期运行）。

### 方式一：docker compose（推荐）

```bash
cd maa-web
docker compose up -d --build
```

- 服务监听 `http://<服务器IP>:3100`
- 三个命名卷自动创建：
  - `maa-config` → `/config`：maa-cli / MaaCore 配置（`~/.config/maa` 的容器内位置）
  - `maa-data` → `/data`：MaaCore 及资源（`maa install` 安装到此）
  - `maa-state` → `/state`：状态与日志
- 常用命令：
  ```bash
  docker compose logs -f maa-web        # 查看日志
  docker compose restart maa-web        # 重启
  docker compose down                   # 停止（卷保留）
  docker compose down -v                # 停止并删除数据（慎用）
  ```

### 方式二：docker build + run

```bash
docker build -t maa-web .
docker run -d --name maa-web --init \
  -p 3100:3100 \
  -v maa-config:/config \
  -v maa-data:/data \
  -v maa-state:/state \
  --restart unless-stopped \
  maa-web
```

### 首次使用（容器内）

首次运行后进入 Web 设置页，或在容器内执行：

```bash
docker exec -it maa-web maa install        # 安装 MaaCore 与资源（数据写入 /data 卷）
```

### 连接设备（模拟器 / 真机）

容器默认使用**独立网络**，需让容器能访问宿主上的 adb 设备：

1. **模拟器**：确保模拟器的 adb 端口（如 `127.0.0.1:5555`）监听在宿主机上，并在 Web「设备连接」页填写 `host.docker.internal:5555` 或宿主局域网 IP；Linux 下可在 compose 中加：
   ```yaml
   extra_hosts:
     - "host.docker.internal:host-gateway"
   ```
2. **真机（无线 adb）**：手机通过 `adb tcpip 5555` 开启无线调试后，直接填手机局域网 IP，容器与手机需在同一网段（或网络可达）
3. **需要时**：将 compose 改为 `network_mode: host`（Linux 下最简单，容器直接使用宿主网络与 adb server）

### 更新容器

```bash
git pull
docker compose up -d --build    # 重新构建并滚动更新
```

### 注意事项

- 镜像内已安装 `adb` 与 `curl`（curl 用于「更新代理」测试功能）
- `maa-cli` 二进制（`bin/maa`）为 Linux x86_64 构建；其他架构（ARM 等）需自行替换 `bin/maa`
- 更新检查（GitHub Releases）需要容器能访问外网；大陆网络可在设置页配置更新代理
- **远程控制（ws-scrcpy）不在容器内**，为独立服务（见上文 ws-scrcpy 部署），两者通过 HTTP 跳转协作

## 项目架构

```
maa-web/
├── server/                 # Node.js + Express 后端
│   ├── index.js            # 路由、队列执行、连接管理、聚合接口
│   ├── taskRunner.js       # 任务执行器（子进程管理、输出、历史）
│   ├── dailyTaskTypes.js   # 队列任务类型定义（17 类，MaaCore 任务文件格式）
│   ├── taskSchemas.js      # 快速任务 schema（CLI 子命令参数 + 中文标签）
│   ├── schedules.js        # 定时调度器（周/时间点、错过补偿）
│   ├── results.js          # 识别结果存储
│   ├── stages.js           # 关卡数据（stages.json 加载 + mtime 自动重载 + 搜索）
│   ├── update.js           # 版本检查（GitHub Releases + 缓存）
│   ├── auth.js             # 访问令牌
│   └── maa.js              # maa-cli 二进制封装
├── public/                 # 纯原生前端（无构建）
│   ├── index.html          # 单页应用（视图 + 右侧日志面板 + PWA）
│   ├── app.js              # 全部前端逻辑
│   ├── style.css
│   ├── manifest.json / sw.js / icons/   # PWA
├── docs/
│   ├── WSCRCPY.md          # 远程控制部署与定制文档
├── Dockerfile              # Docker 镜像（node:20-slim，含 adb/curl）
├── docker-compose.yml      # compose 编排（端口 3100、三个数据卷）
├── ROADMAP.md              # 任务规划（已完成 / 待办 / 改动痕迹）
└── TESTING.md              # 测试文档（自动化 + 手动清单）
```

- **依赖**：仅 `express` 与 `ws` 两个运行时依赖（npm），纯原生前端无构建
- **数据流**：前端 5s 轮询 `/api/status`（无 SSE），任务事件由轮询 diff 驱动；识别结果由 MaaCore 日志回调解析后写入 `results.json`
- **任务执行**：队列 → `maa run daily`（任务文件模式，一次执行全部）；快速任务 → `maa <subcommand>` 单跑
- **主题**：亮/暗/跟随系统（CSS 变量），强调色动态注入；远程控制页通过 URL `?theme=` 同步

### 测试

详见 [TESTING.md](TESTING.md)。自动化测试位于 `/tmp/opencode/`（jsdom 前端 + 隔离环境服务端集成），改动后需全量回归。

```bash
cd /tmp/opencode && for t in ui-device ui-runner ui-screen ui-queue-checkbox ui-new-fields ui-results ui-schedule ui-queue-v2 ui-poll ui-mxu ui-scrcpy ui-token ui-quick ui-autosave ui-update ui-stages; do timeout 90 node $t-test.js 2>&1 | tail -1; done && timeout 90 node server-api-test.js 2>&1 | tail -1
```

## 未来任务

完整规划见 [ROADMAP.md](ROADMAP.md)。当前重点：

- **掉落统计页**：解析日志 Drops 回调，按次/按日汇总素材掉落
- **多配置 / 任务后置动作**：多套配置切换、完成后退出模拟器/休眠/关机
- **库存维持**：目标库存达标自动停止
- **抄作业作业列表展示**：作业集导入后显示作业清单（关卡/作者）
- **输入选项化**：肉鸽分队/核心干员/招募组合等下拉选择（第二波）
- **外部通知**（搁置，需额外部署）：Bark/ServerChan/Telegram/Discord/Webhook 推送
- **多设备支持**、新手引导、ws-scrcpy 同源嵌入等

## 许可与致谢

- 核心能力来自 [MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights) 与 [maa-cli](https://github.com/MaaAssistantArknights/maa-cli)
- 远程控制基于 [ws-scrcpy](https://github.com/NetrisTV/ws-scrcpy)
- UI 参考 [MXU](https://github.com/MistEO/MXU) 与 maa-cli-webui
