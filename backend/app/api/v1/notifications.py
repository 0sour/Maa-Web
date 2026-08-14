"""外部通知 API (M6) — 发送记录 + 测试发送 + 重发。

Routes:
    GET  /notifications/logs         发送记录（最近 N 条，倒序）
    POST /notifications/test         测试发送（按当前 notify.* 配置逐渠道发一条）
    POST /notifications/logs/{id}/resend  重发某条记录（按当前配置渠道重发）
"""
from __future__ import annotations

import logging
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.engine import notify
from app.models.notify import NotifyLog

log = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotifyLogRead(BaseModel):
    id: int
    channel: str
    event: str
    title: str
    content: str
    ok: bool
    error: str | None
    ts: str


def _to_read(row: NotifyLog) -> NotifyLogRead:
    ts = row.ts
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return NotifyLogRead(
        id=row.id, channel=row.channel, event=row.event,
        title=row.title, content=row.content, ok=row.ok,
        error=row.error, ts=ts.isoformat(),
    )


class TestSendResult(BaseModel):
    """测试发送：逐渠道结果。"""

    results: list[dict] = Field(default_factory=list)


@router.get("/logs", response_model=list[NotifyLogRead])
async def list_logs(
    limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[NotifyLogRead]:
    limit = max(1, min(limit, 200))
    rows = (
        (
            await session.execute(
                select(NotifyLog).order_by(NotifyLog.id.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_to_read(r) for r in rows]


@router.post("/test", response_model=TestSendResult)
async def test_send() -> TestSendResult:
    """按当前 notify.* 配置逐渠道发送一条测试消息（event=test，不依赖触发开关）。"""
    results = await notify.send(
        "test",
        "Maa-Web · 通知测试",
        "这是一条测试消息：如果你收到它，说明通知配置生效。",
    )
    return TestSendResult(results=results)


@router.post("/logs/{log_id}/resend", response_model=TestSendResult)
async def resend(
    log_id: int, session: AsyncSession = Depends(get_session)
) -> TestSendResult:
    """按当前配置渠道重发某条记录（内容取记录，事件记为 test）。"""
    row = await session.get(NotifyLog, log_id)
    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"通知记录 {log_id} 不存在",
        )
    results = await notify.send("test", row.title, row.content)
    return TestSendResult(results=results)
