"""Minute-level scheduler (M6) — schedule_jobs → TaskRunner 定时触发。

每分钟检查一次启用的定时任务：本地时区 星期 × HH:MM 匹配即触发，
在目标设备上执行方案快照（tasks JSON）。触发结果写入 LogEntry 并广播
eventbus（实时日志可见）；同分钟窗口内不重复触发（last_run_at 防重）。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.engine import adb, asstproxy, eventbus
from app.engine.taskrunner import TaskQueueError, TaskRunner
from app.models.device import Device
from app.models.schedule import ScheduleJob
from app.models.task import LogEntry
from app.schemas.task import TaskItem

log = logging.getLogger(__name__)

# 同一触发点 90 秒内只执行一次（整分钟 tick 的防重窗口）
_DEDUP_SECONDS = 90


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
                (await s.execute(select(ScheduleJob).where(ScheduleJob.enabled)))
                .scalars()
                .all()
            )
        for job in rows:
            if job.time != hhmm:
                continue
            try:
                weekdays = json.loads(job.weekdays)
            except (TypeError, json.JSONDecodeError):
                weekdays = []
            if abbr not in weekdays:
                continue
            if job.last_run_at is not None:
                last = job.last_run_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc).astimezone()
                if (now - last).total_seconds() < _DEDUP_SECONDS:
                    continue
            await self._fire(job.id, now)

    async def _fire(self, job_id: int, now: datetime) -> None:
        """触发一个定时任务：标记 last_run_at（防重）→ 前置校验 → 启动队列。"""
        async with get_sessionmaker()() as s:
            job = await s.get(ScheduleJob, job_id)
            if job is None:
                return
            device = await s.get(Device, job.device_id)
            job.last_run_at = now.replace(tzinfo=None)
            await s.commit()
        if device is None:
            await self._log(0, "warn", f"⏰ 定时任务「{job.name}」失败：设备不存在")
            return

        try:
            tasks = json.loads(job.tasks)
            items = [TaskItem(**t) for t in tasks if isinstance(t, dict)]
            if not items:
                await self._log(device.id, "warn", f"⏰ 定时任务「{job.name}」失败：方案为空")
                return
            run = await TaskRunner.get(device.id).start(device, items)
            await self._log(
                device.id,
                "info",
                f"⏰ 定时任务「{job.name}」已触发（{job.plan_name or '方案'}，run {run.id}）",
            )
        except TaskQueueError as exc:
            await self._log(device.id, "warn", f"⏰ 定时任务「{job.name}」触发失败：{exc}")
        except Exception as exc:  # noqa: BLE001 - 单任务失败不影响其他
            log.exception("scheduled job %s crashed", job_id)
            await self._log(device.id, "error", f"⏰ 定时任务「{job.name}」执行异常：{exc}")

    async def _log(self, device_id: int, level: str, message: str) -> None:
        """持久化 + 广播（与 taskrunner._consume_logs 同款，实时日志可见）。"""
        try:
            entry = LogEntry(run_id=0, device_id=device_id, level=level, message=message)
            async with get_sessionmaker()() as s:
                s.add(entry)
                await s.commit()
            eventbus.publish(
                device_id,
                {
                    "id": entry.id,
                    "level": level,
                    "message": message,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:  # noqa: BLE001 - 日志失败不阻塞调度
            log.warning("scheduler log persist failed device=%s", device_id)


scheduler = Scheduler()
