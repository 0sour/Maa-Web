"""任务方案 API (2026-08-16) — task_schemes 表（原 localStorage → 后端化）。

Routes:
    GET    /task-schemes            方案列表（updated_at 倒序）
    POST   /task-schemes            保存方案（同名覆盖，upsert by name）
    PUT    /task-schemes/{id}       更新（改名/换任务）
    DELETE /task-schemes/{id}       删除

背景：方案此前存浏览器 localStorage（maaweb.task.schemes），换浏览器/设备
数据丢失 → 迁移为数据库表，任意客户端访问一致。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.task import TaskScheme

log = logging.getLogger(__name__)

router = APIRouter(prefix="/task-schemes", tags=["task-schemes"])


class TaskSchemePayload(BaseModel):
    """创建/更新载荷：name + tasks（PersistedTask 形状的宽松对象）。"""

    name: str = Field(min_length=1, max_length=64)
    tasks: list[dict] = Field(default_factory=list)


class TaskSchemeRead(BaseModel):
    id: int
    name: str
    tasks: list[dict]
    updated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


def _to_read(scheme: TaskScheme) -> TaskSchemeRead:
    try:
        tasks = json.loads(scheme.tasks)
    except (TypeError, json.JSONDecodeError):
        tasks = []
    return TaskSchemeRead(
        id=scheme.id,
        name=scheme.name,
        tasks=tasks if isinstance(tasks, list) else [],
        updated_at=_utc(scheme.updated_at),
        created_at=_utc(scheme.created_at),
    )


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _get_or_404(session: AsyncSession, scheme_id: int) -> TaskScheme:
    scheme = await session.get(TaskScheme, scheme_id)
    if scheme is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"任务方案 {scheme_id} 不存在",
        )
    return scheme


@router.get("", response_model=list[TaskSchemeRead])
async def list_schemes(
    session: AsyncSession = Depends(get_session),
) -> list[TaskSchemeRead]:
    rows = (
        (
            await session.execute(
                select(TaskScheme).order_by(TaskScheme.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_read(s) for s in rows]


@router.post("", response_model=TaskSchemeRead)
async def save_scheme(
    payload: TaskSchemePayload,
    session: AsyncSession = Depends(get_session),
) -> TaskSchemeRead:
    """保存方案：同名覆盖（upsert by name，与前端 saveScheme 语义一致）。"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="方案名不能为空",
        )
    existing = (
        await session.execute(
            select(TaskScheme).where(TaskScheme.name == name)
        )
    ).scalar_one_or_none()
    if existing is None:
        scheme = TaskScheme(name=name, tasks=json.dumps(payload.tasks, ensure_ascii=False))
        session.add(scheme)
        await session.commit()
        await session.refresh(scheme)
    else:
        existing.tasks = json.dumps(payload.tasks, ensure_ascii=False)
        await session.commit()
        await session.refresh(existing)
        scheme = existing
    log.info("task scheme saved: %s", scheme.name)
    return _to_read(scheme)


@router.put("/{scheme_id}", response_model=TaskSchemeRead)
async def update_scheme(
    scheme_id: int,
    payload: TaskSchemePayload,
    session: AsyncSession = Depends(get_session),
) -> TaskSchemeRead:
    """更新方案（改名或换任务；改名冲突 409）。"""
    scheme = await _get_or_404(session, scheme_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="方案名不能为空",
        )
    if name != scheme.name:
        clash = (
            await session.execute(
                select(TaskScheme).where(
                    TaskScheme.name == name, TaskScheme.id != scheme_id
                )
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=f"方案名「{name}」已存在",
            )
        scheme.name = name
    scheme.tasks = json.dumps(payload.tasks, ensure_ascii=False)
    await session.commit()
    await session.refresh(scheme)
    return _to_read(scheme)


@router.delete("/{scheme_id}")
async def delete_scheme(
    scheme_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    scheme = await _get_or_404(session, scheme_id)
    await session.delete(scheme)
    await session.commit()
    return {"ok": True}
