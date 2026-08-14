"""定时执行 API (M6) — schedule_jobs CRUD + 立即试跑。

Routes:
    GET    /schedules            定时任务列表
    POST   /schedules            新建定时任务（weekdays 星期 × time 触发）
    PUT    /schedules/{id}       更新（部分字段）
    DELETE /schedules/{id}       删除
    POST   /schedules/{id}/run   立即触发一次（试跑，不走时间匹配）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.engine.scheduler import scheduler
from app.engine.taskrunner import TaskQueueError, TaskRunner
from app.models.device import Device
from app.models.schedule import ScheduleJob
from app.schemas.schedule import (
    ScheduleJobCreate,
    ScheduleJobRead,
    ScheduleJobUpdate,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _to_read(job: ScheduleJob) -> ScheduleJobRead:
    """ORM → 读取模型：tasks/weekdays 反序列化；last_run_at 附 UTC 时区（前端转本地）。"""
    try:
        tasks = json.loads(job.tasks)
        weekdays = json.loads(job.weekdays)
    except (TypeError, json.JSONDecodeError):
        tasks, weekdays = [], []
    last = job.last_run_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return ScheduleJobRead(
        id=job.id, device_id=job.device_id, name=job.name, enabled=job.enabled,
        weekdays=weekdays if isinstance(weekdays, list) else [],
        time=job.time, plan_name=job.plan_name,
        tasks=tasks if isinstance(tasks, list) else [],
        last_run_at=last, created_at=job.created_at,
    )


async def _get_job_or_404(session: AsyncSession, job_id: int) -> ScheduleJob:
    job = await session.get(ScheduleJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"定时任务 {job_id} 不存在",
        )
    return job


async def _validate_device(session: AsyncSession, device_id: int) -> None:
    """设备必须存在（在线状态在触发时校验）。"""
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"设备 {device_id} 不存在",
        )


@router.get("", response_model=list[ScheduleJobRead])
async def list_schedules(
    session: AsyncSession = Depends(get_session),
) -> list[ScheduleJobRead]:
    rows = (
        (await session.execute(select(ScheduleJob).order_by(ScheduleJob.id)))
        .scalars()
        .all()
    )
    return [_to_read(j) for j in rows]


@router.post("", response_model=ScheduleJobRead)
async def create_schedule(
    payload: ScheduleJobCreate,
    session: AsyncSession = Depends(get_session),
) -> ScheduleJobRead:
    await _validate_device(session, payload.device_id)
    if not payload.weekdays:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请至少选择一个星期",
        )
    if not payload.tasks:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请选择要执行的任务方案",
        )
    job = ScheduleJob(
        device_id=payload.device_id,
        name=payload.name,
        enabled=payload.enabled,
        weekdays=json.dumps(payload.weekdays),
        time=payload.time,
        plan_name=payload.plan_name,
        tasks=json.dumps(payload.tasks, ensure_ascii=False),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return _to_read(job)


@router.put("/{job_id}", response_model=ScheduleJobRead)
async def update_schedule(
    job_id: int,
    payload: ScheduleJobUpdate,
    session: AsyncSession = Depends(get_session),
) -> ScheduleJobRead:
    job = await _get_job_or_404(session, job_id)
    if payload.device_id is not None:
        await _validate_device(session, payload.device_id)
        job.device_id = payload.device_id
    if payload.name is not None:
        job.name = payload.name
    if payload.enabled is not None:
        job.enabled = payload.enabled
    if payload.weekdays is not None:
        if not payload.weekdays:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="请至少选择一个星期",
            )
        job.weekdays = json.dumps(payload.weekdays)
    if payload.time is not None:
        job.time = payload.time
    if payload.plan_name is not None:
        job.plan_name = payload.plan_name
    if payload.tasks is not None:
        if not payload.tasks:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="请选择要执行的任务方案",
            )
        job.tasks = json.dumps(payload.tasks, ensure_ascii=False)
    await session.commit()
    await session.refresh(job)
    return _to_read(job)


@router.delete("/{job_id}")
async def delete_schedule(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    job = await _get_job_or_404(session, job_id)
    await session.delete(job)
    await session.commit()
    return {"ok": True}


@router.post("/{job_id}/run", response_model=ScheduleJobRead)
async def run_schedule_now(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> ScheduleJobRead:
    """立即触发一次（试跑，不走星期/时间匹配）。"""
    job = await _get_job_or_404(session, job_id)
    device = await session.get(Device, job.device_id)
    if device is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"设备 {job.device_id} 不存在",
        )
    if device.status != "online":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"设备 {device.name} 未连接（状态 {device.status}）",
        )
    try:
        tasks = json.loads(job.tasks)
        from app.schemas.task import TaskItem

        items = [TaskItem(**t) for t in tasks if isinstance(t, dict)]
        if not items:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="方案为空，请先在任务编排页保存方案后重新选择",
            )
        run = await TaskRunner.get(job.device_id).start(device, items)
    except TaskQueueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    job.last_run_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()
    await session.refresh(job)
    log.info("scheduled job %s manually run → run %s", job_id, run.id)
    return _to_read(job)
