"""自动任务 API (M6+) — auto_tasks → auto_slots → auto_slot_accounts。

Routes:
    GET    /auto-tasks                自动任务列表（含时间槽与账号，嵌套）
    POST   /auto-tasks                新建自动任务（slots 全量嵌套）
    PUT    /auto-tasks/{id}           整体保存（slots 全量替换）
    DELETE /auto-tasks/{id}           删除（级联删槽与账号绑定）
    POST   /auto-tasks/{id}/run-test  测试运行某时间槽（手动，日志 source=manual_auto）

定时触发由 engine/scheduler.py 完成（source=auto）；本 API 只管配置与手动测试。
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
from app.engine.scheduler import auto_runner
from app.engine.taskrunner import TaskRunner
from app.models.auto_task import AutoSlot, AutoSlotAccount, AutoTask
from app.models.device import Device
from app.schemas.auto_task import (
    AutoRunTestPayload,
    AutoSlotIn,
    AutoSlotRead,
    AutoTaskCreate,
    AutoTaskRead,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auto-tasks", tags=["auto-tasks"])


def _utc(dt) -> datetime | None:
    """DB naive UTC → 附 UTC 时区（前端 new Date 转本地）。"""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _slot_account_to_read(acc: AutoSlotAccount) -> dict:
    try:
        tasks = json.loads(acc.tasks)
    except (TypeError, json.JSONDecodeError):
        tasks = []
    return {
        "id": acc.id,
        "account_name": acc.account_name,
        "client_type": acc.client_type,
        "enabled": acc.enabled,
        "plan_name": acc.plan_name,
        "tasks": [t for t in tasks if isinstance(t, dict)],
        "position": acc.position,
        "last_run_at": _utc(acc.last_run_at),
        "last_ok": acc.last_ok,
    }


def _slot_to_read(slot: AutoSlot, accounts: list[AutoSlotAccount]) -> dict:
    try:
        weekdays = json.loads(slot.weekdays)
    except (TypeError, json.JSONDecodeError):
        weekdays = []
    return {
        "id": slot.id,
        "name": slot.name,
        "enabled": slot.enabled,
        "weekdays": weekdays if isinstance(weekdays, list) else [],
        "time": slot.time,
        "conflict": slot.conflict,
        "accounts": [_slot_account_to_read(a) for a in accounts],
        "last_run_at": _utc(slot.last_run_at),
    }


async def _task_to_read(session: AsyncSession, task: AutoTask) -> AutoTaskRead:
    slots = (
        (
            await session.execute(
                select(AutoSlot).where(AutoSlot.task_id == task.id).order_by(AutoSlot.id)
            )
        )
        .scalars()
        .all()
    )
    slot_ids = [s.id for s in slots]
    accounts: dict[int, list[AutoSlotAccount]] = {s.id: [] for s in slots}
    if slot_ids:
        rows = (
            (
                await session.execute(
                    select(AutoSlotAccount)
                    .where(AutoSlotAccount.slot_id.in_(slot_ids))
                    .order_by(AutoSlotAccount.position)
                )
            )
            .scalars()
            .all()
        )
        for a in rows:
            accounts.setdefault(a.slot_id, []).append(a)
    return AutoTaskRead(
        id=task.id,
        name=task.name,
        enabled=task.enabled,
        device_id=task.device_id,
        slots=[AutoSlotRead(**_slot_to_read(s, accounts[s.id])) for s in slots],
        created_at=task.created_at,
    )


async def _get_task_or_404(session: AsyncSession, task_id: int) -> AutoTask:
    task = await session.get(AutoTask, task_id)
    if task is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"自动任务 {task_id} 不存在",
        )
    return task


async def _validate_slots(session: AsyncSession, payload: AutoTaskCreate) -> None:
    """设备存在 + 槽结构校验（星期非空、冲突策略合法）。"""
    device = await session.get(Device, payload.device_id)
    if device is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"设备 {payload.device_id} 不存在",
        )
    for slot in payload.slots:
        if not slot.weekdays:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"时间槽「{slot.name}」请至少选择一个星期",
            )
        if slot.conflict not in ("queue", "skip", "force"):
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"时间槽「{slot.name}」冲突策略不合法：{slot.conflict}",
            )


async def _apply_slots(
    session: AsyncSession,
    task_id: int,
    slots: list[AutoSlotIn],
) -> None:
    """重建时间槽与账号绑定（删除旧记录后按输入全量写入）。"""
    old_slots = (
        (await session.execute(select(AutoSlot).where(AutoSlot.task_id == task_id)))
        .scalars()
        .all()
    )
    for slot in old_slots:
        old_accs = (
            (
                await session.execute(
                    select(AutoSlotAccount).where(AutoSlotAccount.slot_id == slot.id)
                )
            )
            .scalars()
            .all()
        )
        for acc in old_accs:
            await session.delete(acc)
        await session.delete(slot)
    await session.flush()
    for slot_in in slots:
        slot = AutoSlot(
            task_id=task_id,
            name=slot_in.name,
            enabled=slot_in.enabled,
            weekdays=json.dumps(slot_in.weekdays),
            time=slot_in.time,
            conflict=slot_in.conflict,
        )
        session.add(slot)
        await session.flush()
        for position, acc_in in enumerate(slot_in.accounts):
            session.add(
                AutoSlotAccount(
                    slot_id=slot.id,
                    position=position,
                    account_name=acc_in.account_name,
                    client_type=acc_in.client_type,
                    enabled=acc_in.enabled,
                    plan_name=acc_in.plan_name,
                    tasks=json.dumps(
                        [t.model_dump() for t in acc_in.tasks], ensure_ascii=False
                    ),
                )
            )


@router.get("", response_model=list[AutoTaskRead])
async def list_auto_tasks(
    session: AsyncSession = Depends(get_session),
) -> list[AutoTaskRead]:
    rows = (
        (await session.execute(select(AutoTask).order_by(AutoTask.id)))
        .scalars()
        .all()
    )
    return [await _task_to_read(session, t) for t in rows]


@router.post("", response_model=AutoTaskRead)
async def create_auto_task(
    payload: AutoTaskCreate,
    session: AsyncSession = Depends(get_session),
) -> AutoTaskRead:
    await _validate_slots(session, payload)
    task = AutoTask(
        name=payload.name, enabled=payload.enabled, device_id=payload.device_id
    )
    session.add(task)
    await session.flush()
    await _apply_slots(session, task.id, payload.slots)
    await session.commit()
    await session.refresh(task)
    log.info("auto task created id=%s name=%s", task.id, task.name)
    return await _task_to_read(session, task)


@router.put("/{task_id}", response_model=AutoTaskRead)
async def update_auto_task(
    task_id: int,
    payload: AutoTaskCreate,
    session: AsyncSession = Depends(get_session),
) -> AutoTaskRead:
    """整体保存：name/enabled/device_id 更新，slots 全量替换（含账号绑定）。"""
    task = await _get_task_or_404(session, task_id)
    await _validate_slots(session, payload)
    task.name = payload.name
    task.enabled = payload.enabled
    task.device_id = payload.device_id
    await _apply_slots(session, task.id, payload.slots)
    await session.commit()
    await session.refresh(task)
    log.info("auto task updated id=%s name=%s slots=%d", task.id, task.name, len(payload.slots))
    return await _task_to_read(session, task)


@router.delete("/{task_id}")
async def delete_auto_task(
    task_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    task = await _get_task_or_404(session, task_id)
    await _apply_slots(session, task.id, [])
    await session.delete(task)
    await session.commit()
    return {"ok": True}


@router.post("/{task_id}/run-test")
async def run_test_auto_task(
    task_id: int,
    payload: AutoRunTestPayload,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """测试运行：仅执行指定时间槽的启用账号（真实执行走定时触发）。

    设备在线且空闲才接受；执行结果写入自动任务日志（source=manual_auto，
    带「自动任务(手动运行)」标签，与定时触发的 source=auto 区分）。
    """
    task = await _get_task_or_404(session, task_id)
    slot = await session.get(AutoSlot, payload.slot_id)
    if slot is None or slot.task_id != task.id:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"时间槽 {payload.slot_id} 不存在（不属于该自动任务）",
        )
    device = await session.get(Device, task.device_id)
    if device is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"设备 {task.device_id} 不存在",
        )
    if device.status != "online":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"设备 {device.name} 未连接（状态 {device.status}）",
        )
    runner = TaskRunner.get(device.id)
    if runner.status in ("RUNNING", "STOPPING"):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="设备已有任务正在运行，请先停止再测试",
        )
    accounts = (
        (
            await session.execute(
                select(AutoSlotAccount)
                .where(
                    AutoSlotAccount.slot_id == slot.id,
                    AutoSlotAccount.enabled,
                )
                .order_by(AutoSlotAccount.position)
            )
        )
        .scalars()
        .all()
    )
    if not accounts:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"时间槽「{slot.name}」没有启用账号，请先在自动任务页添加",
        )
    acc_dicts = [
        {
            "id": a.id,
            "account_name": a.account_name,
            "client_type": a.client_type,
            "tasks": a.tasks,
        }
        for a in accounts
    ]
    await auto_runner.submit(
        device_id=device.id,
        slot_name=slot.name,
        conflict=slot.conflict,
        accounts=acc_dicts,
        source="manual_auto",
    )
    log.info(
        "auto task %s slot %s run-test submitted (accounts=%d)",
        task_id,
        slot.id,
        len(accounts),
    )
    return {
        "ok": True,
        "message": f"已提交测试运行：{slot.name}（{len(accounts)} 个账号）",
    }
