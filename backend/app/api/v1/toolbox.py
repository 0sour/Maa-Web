"""工具箱 API（M5 第一批）— 公招 / 仓库 / 干员识别 + 历史记录 + 招募联动。

Routes:
    POST   /toolbox/recognize              启动识别任务（异步，返回 task_id）
    GET    /toolbox/tasks/{task_id}        识别任务状态与结果（前端轮询）
    GET    /toolbox/records                历史识别记录列表（按工具过滤）
    GET    /toolbox/records/{id}           单条记录详情（历史结果调用展示）
    DELETE /toolbox/records/{id}           删除记录
    POST   /toolbox/recruit/execute        按识别结果执行真实公招（联动，消耗招募许可）
"""
from __future__ import annotations

import json
import logging
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.engine import toolbox
from app.engine.taskrunner import TaskQueueError, TaskRunner
from app.models.device import Device
from app.models.toolbox import ToolboxRecord
from app.schemas.task import TaskItem

log = logging.getLogger(__name__)

router = APIRouter(prefix="/toolbox", tags=["toolbox"])

_TOOLS = ("recruit", "depot", "operbox")


class RecognizePayload(BaseModel):
    device_id: int
    tool: str = Field(pattern="^(recruit|depot|operbox)$")


class RecruitExecutePayload(BaseModel):
    """按识别结果执行真实公招：目标星级（引擎自动挑该星级 Tag 组合）。"""

    device_id: int
    level: int = Field(ge=3, le=6)


def _utc(dt) -> str:
    if dt is None:
        return ""
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return dt.isoformat()


def _record_read(r: ToolboxRecord) -> dict:
    try:
        result = json.loads(r.result)
    except (TypeError, ValueError):
        result = {}
    return {
        "id": r.id,
        "tool": r.tool,
        "device_id": r.device_id,
        "result": result if isinstance(result, dict) else {},
        "summary": toolbox.summary_of(r.tool, result if isinstance(result, dict) else {}),
        "created_at": _utc(r.created_at),
    }


async def _get_device_or_404(session: AsyncSession, device_id: int) -> Device:
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"设备 {device_id} 不存在",
        )
    return device


@router.post("/recognize")
async def start_recognize(
    payload: RecognizePayload,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """启动识别任务（设备在线且空闲）。识别完成自动保存历史记录。"""
    device = await _get_device_or_404(session, payload.device_id)
    if device.status != "online":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"设备 {device.name} 未连接（状态 {device.status}）",
        )
    runner = TaskRunner.get(device.id)
    if runner.status in ("RUNNING", "STOPPING"):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="设备正在执行任务，请先停止再识别",
        )
    task_id = toolbox.start_recognize(device, payload.tool)
    log.info("toolbox recognize started task=%s tool=%s device=%s", task_id, payload.tool, device.id)
    return {"ok": True, "task_id": task_id, "tool": payload.tool}


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> dict:
    """识别任务状态：running | done | error；done 时带 result。"""
    t = toolbox.task_status(task_id)
    if t is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"识别任务 {task_id} 不存在",
        )
    return t


@router.get("/records")
async def list_records(
    tool: str | None = None,
    device_id: int | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """历史识别记录列表（按工具/设备过滤，时间倒序）。"""
    limit = max(1, min(limit, 200))
    q = select(ToolboxRecord)
    if tool in _TOOLS:
        q = q.where(ToolboxRecord.tool == tool)
    if device_id is not None:
        q = q.where(ToolboxRecord.device_id == device_id)
    rows = (
        (
            await session.execute(
                q.order_by(ToolboxRecord.id.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {"records": [_record_read(r) for r in rows]}


@router.get("/records/{record_id}")
async def get_record(
    record_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """单条历史记录（结果调用展示用）。"""
    r = await session.get(ToolboxRecord, record_id)
    if r is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"识别记录 {record_id} 不存在",
        )
    return _record_read(r)


@router.delete("/records/{record_id}")
async def delete_record(
    record_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    r = await session.get(ToolboxRecord, record_id)
    if r is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"识别记录 {record_id} 不存在",
        )
    await session.delete(r)
    await session.commit()
    return {"ok": True}


@router.post("/recruit/execute")
async def execute_recruit(
    payload: RecruitExecutePayload,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """按识别结果执行真实公招（联动）：下发 Recruit 任务（select/confirm=目标星级）。

    注意：会真实消耗招募许可并占用公招栏位（与任务编排 Recruit 任务同通道）。
    """
    device = await _get_device_or_404(session, payload.device_id)
    if device.status != "online":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"设备 {device.name} 未连接（状态 {device.status}）",
        )
    items = [
        TaskItem(
            name=f"公招执行（{payload.level}★）",
            entry="Recruit",
            type="公招",
            # times=1 必须显式（引擎默认 0 时 while 循环不执行，不会招募）
            params={"select": [payload.level], "confirm": [payload.level], "set_time": True, "times": 1},
        )
    ]
    try:
        run = await TaskRunner.get(device.id).start(device, items)
    except TaskQueueError as exc:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {
        "ok": True,
        "run_id": run.id,
        "message": f"已开始执行 {payload.level}★ 公招（识别联动）",
    }
