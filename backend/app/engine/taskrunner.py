"""Per-device serial task queue (S-01) wired to the real MAA Asst core (M2).

One `TaskRunner` per device — MAA 引擎同设备不并发，任务严格串行。

Runner state machine (docs/roadmap.md M2):
    idle → running → finished | error | stopped
             └─(stop)→ stopping → stopped

Execution model (MAA Asst 核心, 引擎切换版):
    AsstAppendTask(type, params) × N   — 追加整条任务链（StartUp/Fight/Recruit…）
    AsstStart()                        — 非阻塞启动，引擎后台线程执行
    回调消息（AsstMsg）                — C 回调线程 → call_soon_threadsafe → 日志队列
      TaskChainStart/Completed/Error/Stopped → 当前任务与结果
      AllTasksCompleted                → 收尾（done 事件）
    AsstStop()                         — 停止

Logs are persisted to SQLite (LogEntry) and broadcast over eventbus → WS.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.engine import adb, asstproxy, eventbus
from app.models.device import Device
from app.models.setting import Setting
from app.models.task import LogEntry, TaskRun
from app.schemas.task import TaskItem, TaskStatusRead
from sqlalchemy import select

log = logging.getLogger(__name__)

# ── Runner states ─────────────────────────────────────────────
IDLE, RUNNING, STOPPING, FINISHED, ERROR, STOPPED = (
    "idle", "running", "stopping", "finished", "error", "stopped",
)


class TaskQueueError(RuntimeError):
    """Start precondition failed (device offline / engine missing / resources…)."""


def _resource_ready() -> tuple[bool, str]:
    """Check the MAA engine package (resource/ + MaaCore lib) is installed."""
    d = get_settings().maa_resource_dir
    if not (d / "resource").is_dir():
        return False, f"MAA 引擎包缺失：{d} 下未找到 resource/（请先下载资源包）"
    lib = asstproxy.engine_lib_name()
    if not (d / lib).exists():
        return False, f"MAA 引擎包不完整：缺少 {lib}（请重新下载）"
    return True, str(d)


def _summarize(tasks: list[TaskItem]) -> str:
    """Human-readable queue summary, e.g. '刷理智 CE-6 ×3 · 公开招募 ×1'."""
    return " · ".join(t.name for t in tasks[:4]) + (f" 等 {len(tasks)} 项" if len(tasks) > 4 else "")


def _today_abbr() -> str:
    """本地时区星期缩写（Mon/Tue/.../Sun），周计划按此匹配。"""
    return datetime.now().astimezone().strftime("%a")


def _yj_today() -> str:
    """明日方舟游戏日（凌晨 4 点重置，对齐客户端 DateTimeExtension.ToYjDate）。"""
    return (datetime.now().astimezone() - timedelta(hours=4)).strftime("%Y-%m-%d")


async def _load_game_settings() -> dict:
    """读取运行设置组（game.*，key 去前缀，JSON 反序列化）——停滞检测等用。"""
    out: dict = {}
    try:
        async with get_sessionmaker()() as s:
            rows = (
                (await s.execute(select(Setting).where(Setting.key.like("game.%"))))
                .scalars()
                .all()
            )
        for row in rows:
            key = row.key.removeprefix("game.")
            try:
                out[key] = json.loads(row.value)
            except (TypeError, json.JSONDecodeError):
                out[key] = row.value
    except Exception:  # noqa: BLE001 - 读取失败按默认配置
        log.warning("game settings read failed")
    return out


def _weekly_schedule_enabled(params: dict, today: str) -> bool:
    """Fight 周计划（客户端本地行为，引擎不消费）：当天键 False → 跳过。

    `weekly_schedule` 形如 {"Mon": true, "Tue": false, ...}（默认每天执行）。
    """
    ws = params.get("weekly_schedule")
    if not isinstance(ws, dict):
        return True
    return ws.get(today, True) is not False


def _is_maa_aspect_ratio(width: int, height: int) -> bool:
    """MAA 仅支持 16:9 / 9:16 比例（≥720p），其他比例连接阶段会被引擎拒绝。"""
    ratio = width / height
    return any(abs(ratio - r) < 0.02 for r in (16 / 9, 9 / 16))


async def _ensure_resolution_supported(device: Device) -> str | None:
    """MAA 引擎连接前预检设备分辨率；不支持的 16:9/9:16 时返回引导提示，否则 None。

    真机（USB serial）分辨率按「短边×长边」计，对应 9:16（1080x1920）；模拟器为
    横屏 16:9（1920x1080）。预检失败（adb 异常）不阻塞，交给 AsstConnect 最终判定。
    """
    try:
        size = await adb.get_resolution(device.adb_host, device.adb_port)
    except Exception as exc:  # noqa: BLE001 - 预检失败不阻塞
        log.warning("device=%s resolution precheck failed: %s", device.id, exc)
        return None
    if size and not _is_maa_aspect_ratio(*size):
        w, h = size
        tip = "1080x1920（竖屏真机）" if (device.adb_port or 0) <= 0 else "1920x1080（模拟器）"
        return (
            f"设备分辨率 {w}x{h} 不是 MAA 支持的 16:9 / 9:16 比例。"
            f"请先在「设备管理 → 分辨率」中将分辨率调整为 {tip}，再运行任务"
        )
    return None


def _expand_copilot_jobs(ttype: str, params: dict) -> list[tuple[str, dict]] | None:
    """Copilot 多作业展开：`params.jobs` 里 enabled 的作业逐个展开成独立任务。

    返回 None → 非 Copilot 系任务 / 无 jobs 列表（保持原单任务行为）；
    返回空列表 → 有 jobs 但无启用作业（调用方跳过整个任务）；
    否则返回 [(type, params)]，每个 params 剔除 jobs 键并填好 filename/stage_name。

    覆盖三种作业场景（对齐 MAA 客户端作业集）：普通/SS（Copilot）、
    悖论模拟（ParadoxCopilot）、保全作战（SSSCopilot）。
    """
    if ttype not in ("Copilot", "ParadoxCopilot", "SSSCopilot") or not isinstance(params.get("jobs"), list):
        return None
    base = {k: v for k, v in params.items() if k != "jobs"}
    entries: list[tuple[str, dict]] = []
    for job in params["jobs"]:
        if not isinstance(job, dict):
            continue
        fn = job.get("filename")
        if not job.get("enabled") or not fn:
            continue
        entries.append(
            (ttype, {**base, "filename": fn, "stage_name": job.get("stage_name", "")})
        )
    return entries


class TaskRunner:
    """Serial task queue for one device (one run at a time)."""

    _runners: dict[int, TaskRunner] = {}

    def __init__(self, device_id: int) -> None:
        self.device_id = device_id
        self.status: str = IDLE
        self.run_id: int | None = None
        self.current: str = ""
        self.error: str | None = None
        self._stop = asyncio.Event()
        # (level, msg) 日志行 | (None, {event}) 引擎控制事件
        self._log_q: asyncio.Queue[tuple[str | None, str | dict]] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._worker: asyncio.Task | None = None
        self._consumer: asyncio.Task | None = None
        self._done = asyncio.Event()
        self._any_failed = False
        self._current_params: dict = {}  # 当前任务的原始 params（OfflineConfirm 等事件判断用）
        # 停滞检测（对齐 MAA RunningState StallTimer）：卡死超时内无新任务进展 → 提醒
        self._device_name = ""
        self._last_progress: datetime | None = None
        self._stall_last_fire: datetime | None = None
        self._stall_watch: asyncio.Task | None = None

    @classmethod
    def get(cls, device_id: int) -> TaskRunner:
        runner = cls._runners.get(device_id)
        if runner is None:
            runner = cls(device_id)
            cls._runners[device_id] = runner
        return runner

    # ── Public API ────────────────────────────────────────────

    async def start(self, device: Device, tasks: list[TaskItem]) -> TaskRun:
        """Start a serial queue run. Raises TaskQueueError on preconditions."""
        if self.status in (RUNNING, STOPPING):
            raise TaskQueueError("该设备已有任务正在运行，请先停止")
        if device.status != "online":
            raise TaskQueueError(f"设备 {device.name} 未连接（状态 {device.status}）")
        if not asstproxy.is_available():
            raise TaskQueueError("MAA 引擎不可用（请先在「识别资源包」下载 MAA 引擎包）")
        ready, detail = _resource_ready()
        if not ready:
            raise TaskQueueError(detail)
        hint = await _ensure_resolution_supported(device)
        if hint:
            raise TaskQueueError(hint)

        # 丢弃上一 run 的残留回调（如停止时晚到的 TaskChainStopped），避免串线到本次日志
        while not self._log_q.empty():
            self._log_q.get_nowait()

        session = await asstproxy.create_session(device, adb.resolve_adb_path())
        session.set_handler(self._emit_threadsafe, self._on_event_threadsafe)

        self._loop = asyncio.get_running_loop()
        self._stop.clear()
        self._done = asyncio.Event()
        self._any_failed = False
        self.status = RUNNING
        self.error = None
        self.current = tasks[0].name if tasks else ""
        # 停滞检测起点：任务开始计时，新任务链开始时重置
        self._device_name = device.name
        self._last_progress = datetime.now(timezone.utc)
        self._stall_last_fire = None

        run = TaskRun(device_id=device.id, status=RUNNING, summary=_summarize(tasks))
        async with get_sessionmaker()() as s:
            s.add(run)
            await s.commit()
            await s.refresh(run)
        self.run_id = run.id

        self._consumer = asyncio.create_task(self._consume_logs())
        self._worker = asyncio.create_task(self._run_worker(session, tasks, run.id))
        self._stall_watch = asyncio.create_task(self._stall_watch_loop())
        log.info("task run started device=%s run=%s tasks=%d", device.id, run.id, len(tasks))
        return run

    async def stop(self) -> None:
        """Request a graceful stop (idempotent)."""
        if self.status != RUNNING:
            return
        self.status = STOPPING
        self._stop.set()
        session = asstproxy.get_session(self.device_id)
        if session is not None:
            try:
                await asyncio.to_thread(session.stop)
            except Exception as exc:  # noqa: BLE001 - native surface
                log.warning("device=%s AsstStop failed: %s", self.device_id, exc)
        await self._log_q.put(("warn", "■ 收到停止指令，正在停止…"))
        # 兜底：若引擎未在超时内回发 AllTasksCompleted（如进程异常），强制收尾，
        # 避免 runner 永久停留在 stopping 导致无法再次启动。
        asyncio.create_task(self._force_finalize_after(5.0))

    async def _force_finalize_after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if self.status == STOPPING:
            self.status = STOPPED
            self._done.set()

    def snapshot(self, device_online: bool, engine_available: bool) -> TaskStatusRead:
        ready, _ = _resource_ready()
        return TaskStatusRead(
            device_id=self.device_id,
            status=self.status,
            run_id=self.run_id,
            summary=self.current or "",
            device_online=device_online,
            engine_available=engine_available,
            resource_ready=ready,
            error=self.error,
        )

    # ── Internals ─────────────────────────────────────────────

    def _emit_threadsafe(self, level: str, msg: str) -> None:
        """Called from the MaaCore C callback thread — hop onto the loop."""
        assert self._loop is not None
        self._loop.call_soon_threadsafe(self._log_q.put_nowait, (level, msg))

    def _on_event_threadsafe(self, ev: dict) -> None:
        """Called from the MaaCore C callback thread — hop onto the loop."""
        assert self._loop is not None
        self._loop.call_soon_threadsafe(self._log_q.put_nowait, (None, ev))

    async def _run_worker(
        self, session: Any, tasks: list[TaskItem], run_id: int
    ) -> None:
        try:
            appended = 0
            for task in tasks:
                if self._stop.is_set():
                    break
                self._current_params = dict(getattr(task, "params", None) or {})
                # Fight 周计划：客户端本地按星期过滤（引擎不消费），当天未启用则跳过
                if not _weekly_schedule_enabled(self._current_params, _today_abbr()):
                    await self._log_q.put(
                        ("info", f"⏭ {task.name} 今天不在周计划内，跳过")
                    )
                    continue
                # Mall「一日只执行一次」：客户端本地状态（引擎不消费），当天已执行则关子项
                if getattr(task, "entry", "") == "Mall":
                    await self._apply_mall_once_a_day(task)
                ttype, params = asstproxy.to_asst_task(task)
                # Copilot 多作业：jobs 列表内勾选的作业逐个入队（对齐 MAA 客户端作业集）
                sub_tasks = _expand_copilot_jobs(ttype, params)
                if sub_tasks is not None and not sub_tasks:
                    await self._log_q.put(("info", f"⏭ {task.name} 未勾选启用的作业，跳过"))
                    continue
                if sub_tasks is None:
                    sub_tasks = [(ttype, params)]
                for tt, pp in sub_tasks:
                    if self._stop.is_set():
                        break
                    task_id = await asyncio.to_thread(session.append_task, tt, pp)
                    if not task_id:
                        self.status = ERROR
                        self.error = f"{task.name} 任务添加失败（{tt} 参数不被引擎接受）"
                        await self._log_q.put(("error", f"✖ {task.name} 任务添加失败"))
                        break
                    appended += 1
                    await self._log_q.put(("info", f"▶ 入队 {task.name}（{tt}）"))
                if self.status == ERROR:
                    break

            if appended and not self._stop.is_set() and self.status != ERROR:
                started = await asyncio.to_thread(session.start)
                if not started:
                    raise TaskQueueError("AsstStart 启动失败")
                # 等待引擎回调（AllTasksCompleted → _consume_logs 决定终态）
                await self._done.wait()
            elif not appended and not self._stop.is_set() and self.status != ERROR:
                # 无任务入队（如 Copilot 作业全未勾选）→ 引擎不会回调，直接收尾
                self.status = FINISHED
                await self._log_q.put(("info", "── 队列为空，无任务可执行 ──"))
                self._done.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep runner alive, report error
            self.status = ERROR
            self.error = str(exc)
            log.exception("device=%s run %s crashed", self.device_id, run_id)
            await self._log_q.put(("error", f"✖ 执行异常: {exc}"))
        finally:
            try:
                await asyncio.to_thread(session.stop)  # 确保引擎停止、队列清空
            except Exception:  # noqa: BLE001 - teardown must never raise
                pass
            # 让日志消费者先排空剩余队列（含"全部任务完成"等收尾行）再退出
            await self._log_q.put(("__STOP__", None))
            if self._consumer is not None:
                try:
                    await self._consumer
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - consumer is best-effort
                    log.warning("device=%s log consumer crashed", self.device_id)
                self._consumer = None
            await self._finish_run(run_id)
            self._worker = None

    async def _consume_logs(self) -> None:
        """Drain the queue → 控制事件改状态；日志行持久化 + 广播。"""
        while True:
            kind, payload = await self._log_q.get()
            if kind == "__STOP__":
                break
            if kind is None and isinstance(payload, dict):
                await self._handle_event(payload)
                continue
            level, msg = kind, str(payload)
            try:
                entry = LogEntry(
                    run_id=self.run_id or 0,
                    device_id=self.device_id,
                    level=level,
                    message=msg,
                )
                async with get_sessionmaker()() as s:
                    s.add(entry)
                    await s.commit()
            except Exception:  # noqa: BLE001 - log persistence must not kill stream
                log.warning("device=%s log persist failed", self.device_id)
            eventbus.publish(
                self.device_id,
                {
                    "id": entry.id,
                    "level": level,
                    "message": msg,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            )

    async def _stall_watch_loop(self) -> None:
        """停滞检测循环：每 30s 检查一次（RUNNING 且超时无进展 → 提醒 + 通知）。"""
        while True:
            await asyncio.sleep(30)
            try:
                await self._check_stall(datetime.now(timezone.utc))
            except Exception:  # noqa: BLE001 - 检测失败不影响执行
                log.exception("device=%s stall check failed", self.device_id)

    async def _check_stall(self, now: datetime) -> None:
        """停滞判据（对齐 MAA RunningState.StallTimer）：卡死超时内无新任务链进展。

        首次超时立即提醒，之后按提醒间隔重复；新任务链开始（task_start）时重置。
        提醒 = 日志警告（运行设置 enable_stall_timeout 控制）+ 停滞通知
        （notify.enabled_stalled 控制，走外部通知渠道）。
        """
        if self.status != RUNNING or self._last_progress is None:
            return
        cfg = await _load_game_settings()
        if not cfg.get("enable_stall_timeout"):
            return
        timeout_min = int(cfg.get("stall_timeout_minutes") or 10)
        reminder_min = int(cfg.get("reminder_interval_minutes") or 10)
        elapsed = (now - self._last_progress).total_seconds() / 60
        if elapsed < timeout_min:
            return
        if self._stall_last_fire is not None:
            since_fire = (now - self._stall_last_fire).total_seconds() / 60
            if since_fire < reminder_min:
                return
        self._stall_last_fire = now
        msg = f"⚠ 任务可能卡住：{timeout_min} 分钟无进展（{self.current or '当前任务'}）"
        await self._log_q.put(("warn", msg))
        from app.engine import notify

        await notify.send(
            "stalled",
            f"Maa-Web · {self._device_name or self.device_id} 任务停滞",
            f"设备：{self._device_name or self.device_id}\n{msg}",
        )

    async def _apply_mall_once_a_day(self, task: TaskItem) -> None:
        """Mall「一日只执行一次」客户端逻辑（MallTask.cs IsCreditFightAvailable）。

        引擎不消费 once 语义——由 WebUI 侧模拟：启用时若今天（游戏日）已执行过
        对应子项（Setting 表 last_time），本次入队前把该子项强制关闭。
        """
        params = dict(getattr(task, "params", None) or {})
        pairs = (
            ("visit_friends_once_a_day", "mall.visit_friends_last_time", "visit_friends"),
            ("credit_fight_once_a_day", "mall.credit_fight_last_time", "credit_fight"),
        )
        today = _yj_today()
        try:
            async with get_sessionmaker()() as s:
                for once_key, last_key, target_key in pairs:
                    if not params.get(once_key):
                        continue
                    row = await s.get(Setting, last_key)
                    if row is None:
                        continue
                    try:
                        last = json.loads(row.value)
                    except (TypeError, json.JSONDecodeError):
                        last = row.value
                    if last == today:
                        params[target_key] = False
        except Exception:  # noqa: BLE001 - best-effort，读失败不阻塞执行
            log.warning("device=%s mall once_a_day read failed", self.device_id)
        task.params = params

    async def _mark_mall_done(self) -> None:
        """Mall 任务链完成：记录两个「一日只执行一次」的上次执行日期（游戏日）。"""
        today = _yj_today()
        try:
            async with get_sessionmaker()() as s:
                for key in ("mall.visit_friends_last_time", "mall.credit_fight_last_time"):
                    row = await s.get(Setting, key)
                    if row is None:
                        s.add(Setting(key=key, value=json.dumps(today)))
                    else:
                        row.value = json.dumps(today)
                await s.commit()
        except Exception:  # noqa: BLE001 - best-effort persistence
            log.warning("device=%s mall last_time persist failed", self.device_id)

    async def _handle_event(self, ev: dict) -> None:
        """引擎回调事件 → 运行器状态（均在事件循环线程执行）。"""
        kind = ev.get("event")
        if kind == "task_start":
            self.current = str(ev.get("taskchain") or self.current)
            # 新任务链开始 = 有进展：重置停滞计时与提醒状态
            self._last_progress = datetime.now(timezone.utc)
            self._stall_last_fire = None
        elif kind == "task_completed" and str(ev.get("taskchain") or "").lower() == "mall":
            # 客户端在 Mall 完成后写 LastTime（IsCreditFightAvailable 按天比较）
            await self._mark_mall_done()
        elif kind == "task_error":
            self._any_failed = True
            self.error = f"{ev.get('taskchain') or '任务'} 执行失败"
        elif kind == "all_completed":
            if self.status == RUNNING:
                if self._any_failed:
                    self.status = ERROR
                else:
                    self.status = FINISHED
                    # 「全部任务完成」日志由引擎回调层（asstproxy msg=3）统一输出，此处不再重复
            elif self.status == STOPPING:
                self.status = STOPPED
            self._done.set()
        elif kind == "offline_confirm":
            # 游戏掉线/闪退：auto_restart_on_drop=false 时停止任务（默认 true 自动续刷）。
            # 置 STOPPING + _stop，待引擎 all_completed 到达时收尾为 STOPPED。
            if self._current_params and self._current_params.get("auto_restart_on_drop") is False:
                await self._log_q.put(("warn", "■ 游戏掉线，自动重启已关闭，停止任务"))
                self.status = STOPPING
                self._stop.set()

    async def _finish_run(self, run_id: int) -> None:
        # 任务结束：停止停滞检测
        if self._stall_watch is not None:
            self._stall_watch.cancel()
            self._stall_watch = None
        device_name = None
        run = None
        try:
            async with get_sessionmaker()() as s:
                run = await s.get(TaskRun, run_id)
                if run is not None:
                    run.status = self.status
                    run.error = self.error
                    run.finished_at = datetime.now(timezone.utc)
                    await s.commit()
                if self.status in (FINISHED, ERROR):
                    dev = await s.get(Device, self.device_id)
                    device_name = dev.name if dev is not None else f"设备 {self.device_id}"
        except Exception:  # noqa: BLE001 - best-effort persistence
            log.warning("device=%s run %s finish persist failed", self.device_id, run_id)
        eventbus.publish(
            self.device_id,
            {"event": "run_finished", "status": self.status, "run_id": run_id},
        )
        # 外部通知（M6）：完成/出错事件 → 按 notify.* 配置推送（send 内部全捕获，失败不冒泡）
        if self.status in (FINISHED, ERROR) and device_name is not None:
            from app.engine import notify

            if self.status == FINISHED:
                event, label = "complete", "任务完成"
            else:
                event, label = "error", "任务出错"
            summary = run.summary if run is not None else ""
            detail = f"队列：{summary or '（空）'}"
            if self.status == ERROR and self.error:
                detail += f"\n错误：{self.error}"
            await notify.send(
                event,
                f"Maa-Web · {device_name} {label}",
                detail,
            )
