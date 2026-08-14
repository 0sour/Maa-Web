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


class LogEntry(Base):
    """One log line of a task run (level: info | ok | warn | error)."""

    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
