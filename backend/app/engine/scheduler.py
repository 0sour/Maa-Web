"""Minute-level scheduler — auto_slots → AutoSessionRunner 触发（M6+）。

每分钟检查一次启用的自动任务时间槽：本地时区 星期 × HH:MM 匹配即触发，
按槽的账号列表逐个执行（账号轮换，StartUp 注入 account_name 由引擎
AccountSwitchTask 切换）。设备忙时按槽的冲突策略处理：排队等待 / 跳过本次 /
强制结束上一任务。结果写入 LogEntry（source=auto）并广播 eventbus
（自动任务页实时日志可见）；同分钟窗口内不重复触发（slot.last_run_at 防重）。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.engine import eventbus
from app.engine.taskrunner import (
    FINISHED,
    RUNNING,
    STOPPING,
    TaskQueueError,
    TaskRunner,
)
from app.models.auto_task import AutoSlot, AutoSlotAccount, AutoTask
from app.models.device import Device
from app.models.task import LogEntry
from app.schemas.task import TaskItem

log = logging.getLogger(__name__)

# 同一触发点 90 秒内只执行一次（整分钟 tick 的防重窗口）
_DEDUP_SECONDS = 90
# 设备空闲轮询间隔（账号轮换等待上一个 run 完成）
_POLL_SECONDS = 5


async def _log(
    device_id: int, level: str, message: str, *, source: str = "auto"
) -> None:
    """持久化 + 广播（与 taskrunner._consume_logs 同款，实时日志可见）。"""
    try:
        entry = LogEntry(
            run_id=0,
            device_id=device_id,
            source=source,
            level=level,
            message=message,
        )
        async with get_sessionmaker()() as s:
            s.add(entry)
            await s.commit()
        eventbus.publish(
            device_id,
            {
                "id": entry.id,
                "source": source,
                "level": level,
                "message": message,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:  # noqa: BLE001 - 日志失败不阻塞调度
        log.warning("scheduler log persist failed device=%s", device_id)


class AutoSessionRunner:
    """自动任务会话执行器：每设备一个队列，串行执行槽的账号轮换。

    槽触发（source=auto）与 RUN TEST（source=manual_auto）共用此执行器；
    进程内队列，重启即清（丢失排队中的触发可接受）。
    """

    def __init__(self) -> None:
        self._queues: dict[int, asyncio.Queue] = {}
        self._workers: dict[int, asyncio.Task] = {}

    async def submit(
        self,
        *,
        device_id: int,
        slot_name: str,
        conflict: str,
        accounts: list[dict[str, Any]],
        source: str,
    ) -> None:
        """提交一个槽执行。队列容量 1（已有排队中的槽 → 本次跳过记日志）。"""
        q = self._queues.setdefault(device_id, asyncio.Queue(maxsize=1))
        job = (slot_name, conflict, accounts, source)
        try:
            q.put_nowait(job)
        except asyncio.QueueFull:
            await _log(device_id, "warn", f"⏰ 自动任务「{slot_name}」已排队中，本次跳过")
            return
        worker = self._workers.get(device_id)
        if worker is None or worker.done():
            self._workers[device_id] = asyncio.create_task(self._worker_loop(device_id))

    async def _worker_loop(self, device_id: int) -> None:
        q = self._queues.get(device_id)
        assert q is not None
        while True:
            slot_name, conflict, accounts, source = await q.get()
            try:
                await self._execute(device_id, slot_name, conflict, accounts, source)
            except Exception:  # noqa: BLE001 - 单槽失败不影响调度
                log.exception("auto session crashed device=%s slot=%s", device_id, slot_name)
                await _log(device_id, "error", f"⏰ 自动任务「{slot_name}」执行异常")

    async def _execute(
        self,
        device_id: int,
        slot_name: str,
        conflict: str,
        accounts: list[dict[str, Any]],
        source: str,
    ) -> None:
        """执行一个槽：冲突处理 → 逐账号串行执行（失败跳过继续）。"""
        runner = TaskRunner.get(device_id)
        if runner.status in (RUNNING, STOPPING):
            if source != "auto" or conflict == "skip":
                await _log(device_id, "warn", f"⏰ 自动任务「{slot_name}」触发时设备忙，跳过本次")
                return
            if conflict == "force":
                await _log(
                    device_id, "warn", f"⏰ 自动任务「{slot_name}」触发时设备忙，强制结束上一任务"
                )
                await runner.stop()
            else:
                await _log(device_id, "info", f"⏰ 自动任务「{slot_name}」触发时设备忙，排队等待…")
            await self._wait_free(device_id)

        async with get_sessionmaker()() as s:
            device = await s.get(Device, device_id)
        if device is None:
            await _log(device_id, "warn", f"⏰ 自动任务「{slot_name}」失败：设备不存在")
            return

        done = 0
        for acc in accounts:
            try:
                items = [
                    TaskItem(**t) for t in json.loads(acc["tasks"]) if isinstance(t, dict)
                ]
            except (TypeError, json.JSONDecodeError):
                items = []
            if not items:
                await _log(
                    device_id,
                    "warn",
                    f"⏭ 「{slot_name}」· 账号 {acc['account_name']} 方案为空，跳过",
                )
                await self._mark_account(acc["id"], ok=False)
                continue
            try:
                run = await runner.start(
                    device,
                    items,
                    client_type=acc["client_type"],
                    account_name=acc["account_name"],
                    source=source,
                )
            except TaskQueueError as exc:
                await _log(
                    device_id,
                    "warn",
                    f"⏭ 「{slot_name}」· 账号 {acc['account_name']} 启动失败：{exc}",
                )
                await self._mark_account(acc["id"], ok=False)
                continue
            await _log(
                device_id,
                "info",
                f"⏰ 「{slot_name}」· 账号 {acc['account_name']} 开始（run {run.id}）",
            )
            ok = await self._wait_free(device_id)
            await self._mark_account(acc["id"], ok=ok)
            if ok:
                await _log(device_id, "ok", f"✔ 「{slot_name}」· 账号 {acc['account_name']} 完成")
            else:
                await _log(
                    device_id,
                    "warn",
                    f"⏭ 「{slot_name}」· 账号 {acc['account_name']} 执行失败，跳过",
                )
            done += 1
        if done:
            await _log(
                device_id, "info", f"⏰ 自动任务「{slot_name}」本轮执行完毕（{len(accounts)} 个账号）"
            )

    async def _wait_free(self, device_id: int) -> bool:
        """轮询设备空闲；返回离开时状态是否 FINISHED（上一 run 正常完成）。"""
        runner = TaskRunner.get(device_id)
        while runner.status in (RUNNING, STOPPING):
            await asyncio.sleep(_POLL_SECONDS)
        return runner.status == FINISHED

    async def _mark_account(self, account_id: int, *, ok: bool) -> None:
        """记录账号上次执行结果（展示 ✓/✗）。"""
        async with get_sessionmaker()() as s:
            acc = await s.get(AutoSlotAccount, account_id)
            if acc is None:
                return
            acc.last_run_at = datetime.now(timezone.utc).replace(tzinfo=None)
            acc.last_ok = ok
            await s.commit()


class Scheduler:
    """单例调度器：应用生命周期内运行，events.py 负责 start/stop。"""

    _task: asyncio.Task | None = None

    def start(self) -> None:
        """启动后台 tick 循环（幂等）。"""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._tick())
        log.info("scheduler started (minute-aligned tick)")

    async def stop(self) -> None:
        """停止 tick 循环（幂等）。"""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log.info("scheduler stopped")

    async def _tick(self) -> None:
        while True:
            try:
                await self._check()
            except Exception:  # noqa: BLE001 - tick 永不崩溃
                log.exception("scheduler tick failed")
            # 对齐到下一整分钟（触发时刻 = HH:MM:00，直观且不漂移）
            now = datetime.now().astimezone()
            await asyncio.sleep(60 - now.second)

    async def _check(self) -> None:
        now = datetime.now().astimezone()
        hhmm = now.strftime("%H:%M")
        abbr = now.strftime("%a")
        async with get_sessionmaker()() as s:
            rows = (
                (
                    await s.execute(
                        select(AutoSlot)
                        .join(AutoTask, AutoSlot.task_id == AutoTask.id)
                        .where(AutoTask.enabled, AutoSlot.enabled)
                    )
                )
                .scalars()
                .all()
            )
        for slot in rows:
            if slot.time != hhmm:
                continue
            try:
                weekdays = json.loads(slot.weekdays)
            except (TypeError, json.JSONDecodeError):
                weekdays = []
            if abbr not in weekdays:
                continue
            if slot.last_run_at is not None:
                last = slot.last_run_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc).astimezone()
                if (now - last).total_seconds() < _DEDUP_SECONDS:
                    continue
            await self._trigger(slot.id, now)

    async def _trigger(self, slot_id: int, now: datetime) -> None:
        """触发时间槽：标记 last_run_at（防重）→ 账号快照 → 提交会话执行器。"""
        async with get_sessionmaker()() as s:
            slot = await s.get(AutoSlot, slot_id)
            if slot is None:
                return
            task = await s.get(AutoTask, slot.task_id)
            device = await s.get(Device, task.device_id) if task is not None else None
            slot.last_run_at = now.replace(tzinfo=None)
            await s.commit()
            rows = (
                (
                    await s.execute(
                        select(AutoSlotAccount)
                        .where(
                            AutoSlotAccount.slot_id == slot_id,
                            AutoSlotAccount.enabled,
                        )
                        .order_by(AutoSlotAccount.position)
                    )
                )
                .scalars()
                .all()
            )
            accounts = [
                {
                    "id": a.id,
                    "account_name": a.account_name,
                    "client_type": a.client_type,
                    "tasks": a.tasks,
                }
                for a in rows
            ]
        if device is None:
            await _log(0, "warn", f"⏰ 自动任务槽「{slot.name}」失败：设备不存在")
            return
        if not accounts:
            await _log(device.id, "warn", f"⏰ 自动任务「{slot.name}」触发：无启用账号，跳过本轮")
            return
        await auto_runner.submit(
            device_id=device.id,
            slot_name=slot.name,
            conflict=slot.conflict,
            accounts=accounts,
            source="auto",
        )


scheduler = Scheduler()
auto_runner = AutoSessionRunner()
