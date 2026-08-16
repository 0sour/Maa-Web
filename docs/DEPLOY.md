# NAS 部署指南（Docker）

Maa-Web 以 3 容器部署：`nginx`（前端静态 + 反向代理）→ `api`（FastAPI + MAA Asst 引擎）。
数据全部落在命名卷，升级/重启不丢；非 root 运行（UID 1000，兼容群晖/Unraid 默认用户）。

## 1. 前置条件

- NAS / Linux 主机：Docker Engine ≥ 24 + Compose Plugin ≥ 2.20
- 内存 ≥ 2GB（重度挂机推荐 4GB+）
- 与 NAS 同一局域网内的 Android 设备：
  - 真机：开启「开发者选项 → USB 调试」（网络 ADB 场景）或已 root 的无线调试
  - 模拟器：开启「ADB 调试」（MuMu / 雷电等均支持网络 ADB）

## 2. 架构选择

| NAS 架构 | `MAAWEB_RESOURCE_PLATFORM` |
|----------|---------------------------|
| ARM64（群晖/威联通主流、树莓派） | `linux-aarch64`（默认值） |
| AMD64（x86 NAS、软路由） | `linux-x86_64` |

引擎包（MaaCore 官方发布包）由页面「识别资源包」按此变量下载，**必须与 NAS 架构匹配**，否则引擎加载失败。

## 3. 三步启动

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env，至少确认：
#    MAAWEB_SECRET_KEY    强随机串（当前版本仅启动检查、不强制校验，见 §8）
#    MAAWEB_RESOURCE_PLATFORM  按上表设 linux-x86_64（ARM 可留默认）
#    TZ                   时区（默认 Asia/Shanghai，日志/定时/主题均依赖）
#    MAAWEB_EXPOSE_PORT   对外端口（默认 8080；被占用时改如 18080）

# 3. 构建并启动
docker compose up -d --build
```

启动后访问 **http://<NAS IP>:8080**。

## 4. 设备接入（网络 ADB）

容器内已安装 `adb`（`MAAWEB_ADB_PATH=/usr/bin/adb`），通过**网络 ADB** 连接设备：

**真机（推荐无线调试）**：
```bash
# 在 NAS 上（或本机 adb）先连接一次并授权
adb connect <手机IP>:5555
adb devices          # 确认 device（非 unauthorized）
```

**模拟器**：模拟器设置里开启 ADB 调试，记下端口（MuMu 默认 16384/16416，雷电 5555）。

然后在 WebUI「设备管理 → 添加设备」：
- ADB 主机：设备 IP（或模拟器所在主机 IP）
- ADB 端口：5555（真机无线调试）/ 模拟器端口

> 注意：容器内 `adb connect` 后设备重启或网络变化需重新连接；设备管理页有「连接/断开」按钮可手动重连。

## 5. 首次使用流程

1. 打开 `http://<NAS IP>:8080`，确认后端/引擎状态芯片
2. 「设备管理 → 添加设备」→ 连接成功（引擎就绪状态）
3. 「设置 → 更新设置」或首页「识别资源包」→ 下载 MAA 引擎包（按架构）
4. 「任务编排」编排队列 → 保存为方案 → 「定时执行」设置定时 → LINK START 或等调度触发

## 6. 数据与升级

```bash
docker compose logs -f api      # 后端日志
docker compose down             # 停止（保留数据）
docker compose down -v          # ⚠️ 删除全部数据卷（配置/日志/引擎包全清）
docker compose pull             # 升级镜像
docker compose up -d            # 应用升级
```

数据卷：`maaweb-config`（SQLite + 设置）、`maaweb-logs`（任务日志）、`maaweb-cache`（引擎包/资源）、`maaweb-media`（截图/录像）。

## 7. 常见问题

| 现象 | 处理 |
|------|------|
| 首页引擎「未就绪」 | 未下载引擎包或平台不匹配：检查 `MAAWEB_RESOURCE_PLATFORM` 与 NAS 架构一致，重下引擎包 |
| 首次部署时 `/healthz/startup` 返回 503 | 正常：引擎包未下载属「未完全就绪」；`/healthz/ready` 返回 200 即可访问 UI 下载引擎包 |
| api 容器启动报 `InvalidRequestError: The asyncio extension requires an async driver` | `docker-compose.yml` 的 `DATABASE_URL` 必须以 `sqlite+aiosqlite:///` 开头（缺 `+aiosqlite` 前缀 SQLAlchemy 会走同步驱动） |
| nginx 容器重启循环，报 `"map" directive is not allowed here` | `map` 指令只能出现在 http 上下文（conf.d 文件顶层），不能放在 `server {}` 内 |
| nginx 容器重启循环，报 `open() "/run/nginx.pid" failed (13: Permission denied)` | 镜像内 `/run` 目录必须可写（`/var/run` 是符号链接，`chown -R` 不会到达 `/run` 本身）；用最新镜像 |
| 引擎包已下载但引擎「未就绪」，日志报 `libatomic.so.1: cannot open shared object file` | backend 镜像缺 `libatomic1`（MaaCore 依赖）：用最新镜像重建 api（`docker compose up -d --build api`） |
| 设备检测/接入报 `adb 命令失败 ... Cannot mkdir '/home/appuser/.android': No such file or directory` | 镜像内 `appuser` 无 HOME（`--no-create-home` 且容器默认 HOME=/root）：新镜像已建 `/home/appuser` + `ENV HOME=/home/appuser`（adb server 需要 `~/.android` 存 ADB 密钥）；重建 api 容器 |
| 首页「识别引擎」显示「引擎降级 · 仅 ADB」，但引擎包明明就绪 | `GET /devices/detect` 的 adb 失败分支未带引擎字段导致前端误判（已修复）；同时确认上一条 adb server 是否正常 |
| 更新源选 Mirror酱（MirrorChyan）后引擎包下载失败（code 8001） | Mirror酱的 MAA 资源仅发布 Windows 应用本体，Linux（NAS）无对应包；引擎包请用 GitHub 源（可配 ghproxy 镜像或 HTTP 代理） |
| GitHub 官方直连下载引擎包失败（HEAD 200 但 GET 中断） | 「更新设置 → HTTP 代理」填 clash 等代理地址（如 `http://<NAS IP>:7890`），或配置 ghproxy 镜像前缀 |
| 构建报 `blob ...: operation not permitted`（btrfs 卷） | 构建缓存坏块：删除报错路径的 blob 文件，再 `docker builder prune -af` 重建索引后重试 |
| `adb` 连接 `unauthorized` | 设备弹窗授权；真机需在「开发者选项」里撤销授权后重连 |
| 任务时间/日志日期差 8 小时 | 容器时区未设：`.env` 配 `TZ=Asia/Shanghai` 后重建容器 |
| 端口 8080 被占用 | `.env` 改 `MAAWEB_EXPOSE_PORT` |
| 日志页反复「⚠ 日志流连接异常，尝试重连…」 | 前端 WS 走 `/api/v1/tasks/ws/logs`（`/api/` location）——早期 nginx `/api/` 未转发 Upgrade 头导致握手失败；新镜像已补 `proxy_set_header Upgrade/Connection`（`$connection_upgrade` map 在 http 层），重建 nginx 容器 |
| 连不上 NAS 上模拟器 | 模拟器网络模式需「桥接/NAT 可达」；确认防火墙放行 adb 端口 |
| 更新源走 GitHub 慢 | 「设置 → 更新设置」配置 ghproxy 镜像前缀或 MirrorChyan CDK |

> 以上 api/nginx 报错均已在本项目 Docker 实机验证（Steam Deck / Debian 12 x86_64）中复现并修复，对应 commit 见仓库历史。

## 7.5 数据持久化与备份（2026-08-16 补充）

- **重启不丢**：所有持久数据在 Docker named volume `maaweb-config`（/data/config）——SQLite（maaweb.db，含设备/方案/队列草稿/自动任务/账号组/设置）+ runtime_settings.json（镜像源/CDK/代理/ADB 路径）；引擎包与资源在 `maaweb-cache`、日志在 `maaweb-logs`。容器 `restart` / `up -d --build` 重建 / 删除重建容器均不丢失（已实机验证）。
- **导出/导入**：设置 → 问题反馈 → 「导出配置」（zip，含全部配置与设置）／「导入配置」（覆盖恢复，导入前自动备份当前配置到 `maaweb-logs` 卷 backup/ 目录）。备份只需保存该 zip 或直接备份 `maaweb-config` 卷。

## 8. 架构与安全说明

- `nginx` 容器：仅静态文件 + `/api`、`/ws` 反向代理，非 root（nginx 用户）
- `api` 容器：非 root（UID 1000）、`cap_drop: ALL`、`no-new-privileges`
- 单用户设计：`MAAWEB_SECRET_KEY` 目前仅作启动检查（空值时自动生成并打印到容器日志）；**API 尚未强制校验该密钥**（登录鉴权在 roadmap「安全加固」项，首期为基础 Token）。**如暴露到公网，务必自行加反代 HTTPS + 访问控制，不要依赖密钥**
- 备份：只需备份 `maaweb-config` 卷（SQLite 单文件）+ 需要的 `maaweb-media`
