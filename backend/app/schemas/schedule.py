"""Pydantic schemas — 定时执行（schedule_jobs，M6 调度）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScheduleJobBase(BaseModel):
    """创建/更新定时任务。weekdays 为 %a 缩略（Mon..Sun）；tasks 为方案内容快照。"""

    device_id: int
    name: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    weekdays: list[str] = Field(default_factory=list)
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    plan_name: str = ""
    tasks: list[dict] = Field(default_factory=list)


class ScheduleJobCreate(ScheduleJobBase):
    pass


class ScheduleJobUpdate(BaseModel):
    """部分更新（均为可选）。"""

    device_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None
    weekdays: list[str] | None = None
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    plan_name: str | None = None
    tasks: list[dict] | None = None


class ScheduleJobRead(BaseModel):
    """定时任务读取模型（tasks 反序列化回列表）。"""

    id: int
    device_id: int
    name: str
    enabled: bool
    weekdays: list[str]
    time: str
    plan_name: str
    tasks: list[dict]
    last_run_at: datetime | None
    created_at: datetime
