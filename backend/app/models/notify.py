"""SQLAlchemy ORM model — NotifyLog 外部通知发送记录（M6 外部通知）。

每次推送（完成/出错/测试/重发）逐渠道记录一条：渠道、事件、标题内容、
发送结果（ok/error），供「通知」页查看与重发。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.device import Base


class NotifyLog(Base):
    """外部通知发送记录。"""

    __tablename__ = "notify_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # serverchan | dingtalk | custom
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    # complete | error | test
    event: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
