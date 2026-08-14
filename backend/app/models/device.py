"""SQLAlchemy ORM models (M2: Device; M3+ adds TaskConfig/Schedule/TaskRun/…)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Device(Base):
    """ADB device record (C-01)."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    adb_host: Mapped[str] = mapped_column(String(128), nullable=False)
    adb_port: Mapped[int] = mapped_column(Integer, nullable=False, default=5555)
    touch_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="Minitouch"
    )  # Minitouch | MaaTouch | Adb
    client_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Official"
    )
    # online | offline | connecting | error
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="offline")
    # Last connect failure / degradation reason (null when healthy).
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_online_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
