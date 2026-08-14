"""Task queue API (S-01) + WebSocket log streaming (S-05) — wired to the real engine.

Routes:
    POST   /tasks/{device_id}/run       启动一个串行任务队列
    POST   /tasks/{device_id}/stop      停止运行中的队列
    GET    /tasks/{device_id}/status    当前队列状态（idle/running/…）
    GET    /tasks/runs/{run_id}/logs    某次运行的历史日志
    WS     /ws/logs?device_id=N         实时日志流（S-05）
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.engine import asstproxy, eventbus, taskrunner
from app.engine.taskrunner import TaskQueueError, TaskRunner
from app.models.device import Device
from app.models.task import LogEntry
from app.schemas.task import (
    LogDayGroup,
    LogEntryRead,
    LogsByDayRead,
    TaskRunCreate,
    TaskRunResult,
    TaskStatusRead,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _get_device_or_404(session: AsyncSession, device_id: int) -> Device:
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"device {device_id} not found",
        )
    return device


@router.post("/{device_id}/run", response_model=TaskRunResult)
async def run_tasks(
    device_id: int,
    payload: TaskRunCreate,
    session: AsyncSession = Depends(get_session),
) -> TaskRunResult:
    """Start a serial task queue against a device (real MAA Asst execution)."""
    device = await _get_device_or_404(session, device_id)
    try:
        run = await TaskRunner.get(device_id).start(device, payload.tasks)
    except TaskQueueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except asstproxy.EngineCreateError as exc:
        # 引擎连接/初始化失败（如 AsstConnect 失败）→ 502，向前端透出具体原因
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return TaskRunResult(
        run_id=run.id,
        device_id=device.id,
        status=run.status,
        message="任务队列已启动",
    )


@router.post("/{device_id}/stop", response_model=TaskRunResult)
async def stop_tasks(
    device_id: int, session: AsyncSession = Depends(get_session)
) -> TaskRunResult:
    """Request a graceful stop of the running queue."""
    await _get_device_or_404(session, device_id)
    runner = TaskRunner.get(device_id)
    await runner.stop()
    return TaskRunResult(
        run_id=runner.run_id or 0,
        device_id=device_id,
        status=runner.status,
        message="停止指令已下发" if runner.status != taskrunner.IDLE else "当前无运行任务",
    )


@router.get("/{device_id}/status", response_model=TaskStatusRead)
async def task_status(
    device_id: int, session: AsyncSession = Depends(get_session)
) -> TaskStatusRead:
    device = await _get_device_or_404(session, device_id)
    return TaskRunner.get(device_id).snapshot(
        device_online=device.status == "online",
        engine_available=asstproxy.is_available(),
    )


def _entry_read(e: LogEntry) -> LogEntryRead:
    """LogEntry → 读取模型：DB 存 UTC naive，输出带 +00:00 供前端转本地时区。"""
    ts = e.ts
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return LogEntryRead(
        id=e.id, run_id=e.run_id, device_id=e.device_id,
        level=e.level, message=e.message, ts=ts,
    )


@router.get("/runs/{run_id}/logs", response_model=list[LogEntryRead])
async def run_logs(
    run_id: int, session: AsyncSession = Depends(get_session)
) -> list[LogEntryRead]:
    result = await session.execute(
        select(LogEntry).where(LogEntry.run_id == run_id).order_by(LogEntry.id)
    )
    return [_entry_read(e) for e in result.scalars().all()]


def _local_day_start(dt: datetime) -> datetime:
    """本地时区当天 00:00（aware）。"""
    return dt.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)


def _utc_naive(dt: datetime) -> datetime:
    """aware → UTC 墙钟 naive（与 SQLite CURRENT_TIMESTAMP 的存储形式一致）。"""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/logs", response_model=LogsByDayRead)
async def logs_by_day(
    days: int = 7,
    device_id: int | None = None,
    limit: int = 2000,
    session: AsyncSession = Depends(get_session),
) -> LogsByDayRead:
    """历史日志：今天之前的 N 天（本地时区），按天分组倒序，天内时间正序。

    当天日志由 GET /tasks/logs/today 提供（实时面板）；当天过了才归档到这里。
    """
    days = max(1, min(days, 30))
    limit = max(100, min(limit, 5000))
    local_today = _local_day_start(datetime.now())
    utc_since = _utc_naive(local_today - timedelta(days=days))
    utc_before = _utc_naive(local_today)
    q = select(LogEntry).where(LogEntry.ts >= utc_since, LogEntry.ts < utc_before)
    if device_id is not None:
        q = q.where(LogEntry.device_id == device_id)
    rows = (
        (await session.execute(q.order_by(LogEntry.ts.desc()).limit(limit)))
        .scalars()
        .all()
    )
    groups: dict[str, list[LogEntry]] = {}
    for row in rows:
        # DB 存 UTC，按本地时区日期归档
        date = row.ts.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d")
        groups.setdefault(date, []).append(row)
    day_groups = [
        LogDayGroup(
            date=date,
            count=len(entries),
            entries=[_entry_read(e) for e in reversed(entries)],
        )
        for date, entries in sorted(groups.items(), reverse=True)
    ]
    return LogsByDayRead(days=day_groups)


@router.get("/logs/today", response_model=LogDayGroup)
async def logs_today(
    device_id: int | None = None,
    limit: int = 2000,
    session: AsyncSession = Depends(get_session),
) -> LogDayGroup:
    """当天日志（本地时区，时间正序）——实时面板回填用，跨页面保留。"""
    limit = max(100, min(limit, 5000))
    local_today = _local_day_start(datetime.now())
    utc_since = _utc_naive(local_today)
    q = select(LogEntry).where(LogEntry.ts >= utc_since)
    if device_id is not None:
        q = q.where(LogEntry.device_id == device_id)
    rows = (
        (await session.execute(q.order_by(LogEntry.id).limit(limit)))
        .scalars()
        .all()
    )
    return LogDayGroup(
        date=local_today.strftime("%Y-%m-%d"),
        count=len(rows),
        entries=[_entry_read(e) for e in rows],
    )


# ── WebSocket log stream (S-05) ─────────────────────────────────────────

@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket, device_id: int) -> None:
    """Live log stream for one device. Query: /api/v1/tasks/ws/logs?device_id=N"""
    await websocket.accept()
    q = eventbus.subscribe(device_id)
    try:
        while True:
            payload = await q.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        eventbus.unsubscribe(device_id, q)
