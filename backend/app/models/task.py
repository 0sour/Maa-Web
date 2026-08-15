"""SQLAlchemy ORM models for task runs & logs (S-05).

TaskRun: one execution of a task queue against a device.
LogEntry: one log line produced during a run (also persisted for history).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.device import Base


class TaskRun(Base):
    """A single task-queue execution (device-scoped, serial queue)."""

    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # running | finished | error | stopped
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    # Human-readable task summary, e.g. "刷理智 CE-6 ×3 · 公开招募 ×1"
    summary: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # Failure / stop reason (null while healthy).
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskScheme(Base):
    """已保存的任务方案（任务编排「保存为方案」，2026-08-16 起存后端）。

    此前方案存浏览器 localStorage（换浏览器/设备丢失），现迁移为数据库表；
    tasks 为 PersistedTask JSON 数组（type/entry/label/params/checked/once）。
    """

    __tablename__ = "task_schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 方案名（用户可辨识，如「每日日常」）；同名保存 = 覆盖
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tasks: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class LogEntry(Base):
    """One log line of a task run (level: info | ok | warn | error)."""

    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 日志来源：normal（普通执行）| auto（定时自动任务）| manual_auto（RUN TEST 手动运行）
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
