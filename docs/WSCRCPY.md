# ws-scrcpy 部署与定制文档

ws-scrcpy（https://github.com/NetrisTV/ws-scrcpy）— Web 版 scrcpy 远程控制服务，作为 maa-web 的远程控制后端独立运行。

## 部署位置

- 源码/构建目录：`/tmp/opencode/ws-scrcpy`
- 运行目录：`/tmp/opencode/ws-scrcpy/dist`
- 服务端口：**8000**（HTTP）
- 依赖 adb：`/vol1/1000/maa-web/bin/platform-tools/`（启动时加入 PATH）

## 安装（首次）

```bash
cd /tmp/opencode
git clone https://github.com/NetrisTV/ws-scrcpy.git   # 国内网络可用代理：-c http.proxy=http://192.168.10.110:7890
cd ws-scrcpy
npm install --no-audit --no-fund
# 构建生产包
npx webpack --config webpack/ws-scrcpy.prod.ts        # 约 19 秒
```

## 配置

- 端口配置：`config.yaml`（`server: [{ secure: false, port: 8000 }]`）；实际生效以 dist 内 index.js 读取为准，默认 8000
- adb 发现：服务启动时 `adb` 必须在 PATH（含 platform-tools）

## 启动 / 停止

paseo 终端（当前终端 id：c689cbcc）：

```bash
PATH=/vol1/1000/maa-web/bin/platform-tools:$PATH node ./index.js
```

- 停止：`Ctrl+C`
- 注意：paseo 终端 Ctrl+C 后可能卡住（命令无法再输入），此时 kill 终端并新建，再执行上述启动命令（先发命令文本，再单独发 Enter）

## 已做的本地定制（勿被升级覆盖）

| 改动 | 文件 | 说明 |
|---|---|---|
| 画质提升 | `src/app/player/{BasePlayer,BroadwayPlayer,TinyH264Player,MsePlayer,MsePlayerForQVHack,WebCodecsPlayer}.ts` | 默认 bitrate 524288→**8000000**、maxFps 24→**30**、bounds 480→**1920**（wasm 软解也不再糊） |
| 主题跟随 maa-web | `src/style/app.css`、`src/style/devicelist.css`、`src/app/index.ts` | 亮/暗/跟随系统三态与 maa-web 对齐：亮=#f3f5f9/#ffffff/#d8dee9/#232a36，暗=#12151b/#1f2530/#2b3342/#e6eaf2；URL `?theme=`（query 或 hash）强制指定，未指定跟随系统；列表页与流页均生效 |
| 控件风格对齐 | `src/style/app.css`、`morebox.css`、`devicelist.css` | 控制按钮列圆角卡片+阴影、按钮 hover 高亮；morebox 圆角边框+毛玻璃+输入控件圆角；设备列表改圆角卡片（12px）+ 边框 + hover 高亮 + 虚线分隔条；按钮/下拉圆角 |
| fitToScreen 强制自适应 | `src/app/player/BasePlayer.ts` | `getFitToScreenFromStorage` 始终返回 true（忽略 localStorage 历史值），画面始终按窗口自适应 |
| 精简设备列表 | `build.config.override.json` | `INCLUDE_DEV_TOOLS/FILE_LISTING/ADB_SHELL: false`，仅保留流入口 |

每次改动后需重建：`npx webpack --config webpack/ws-scrcpy.prod.ts` 并重启服务。

## maa-web 集成

- 入口：maa-web 侧边栏「远程控制」按钮（`#wsscrcpy-btn`）→ 新标签页打开 `http://<host>:8000/#!/?action=stream&udid=<设备地址>`
- 设备地址从 maa-web `GET /api/connection` 的 `address` 字段获取

## 常见问题

- **设备上 server 启动失败（BindException: Address already in use）**：设备上残留 scrcpy server 进程，点设备行的「Kill server」或 adb 重启设备后重试
- **jar 路径冲突**：maa-web 曾用 `/data/local/tmp/scrcpy-server.jar`（3.3.2）；ws-scrcpy 用同一路径 push 自己的 1.19-ws7 fork 版——各自会话开始时都会重新 push 自己的 jar，不同时使用无冲突
- **画面模糊**：已默认 8Mbps/1920；仍糊可在流页「Configure stream」调码率，或手机端选 Broadway 播放器
