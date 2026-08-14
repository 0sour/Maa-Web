"""SQLAlchemy ORM model — ScheduleJob 定时执行任务（M6 调度）。

一条记录 = 一个定时触发点：星期 × 时间（分钟级），到点自动在目标设备上
执行一份任务方案（tasks 为方案内容的 JSON 快照——方案在任务编排页保存于
localStorage，定时触发由后端完成，故保存时快照）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.device import Base


class ScheduleJob(Base):
    """定时执行任务（星期 + 时间 → 自动跑任务方案）。"""

    __tablename__ = "schedule_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 定时任务名称（用户可辨识，如「每日长草」）
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # JSON 数组：["Mon","Tue",...]（与周计划同用 %a 缩略，对齐客户端星期缩写）
    weekdays: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 触发时间 "HH:MM"（本地时区，分钟级）
    time: Mapped[str] = mapped_column(String(5), nullable=False, default="06:00")
    # 来源方案名（展示用；tasks 为保存时的快照，方案后续改动不影响已定时任务）
    plan_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # 任务方案内容快照（TaskItemPayload JSON 数组，同 POST /tasks/{id}/run 的 tasks）
    tasks: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 上次触发时间（防同分钟重复触发 + 展示）
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
