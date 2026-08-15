"""Pydantic DTOs for the task queue API (S-01 / S-05)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskItem(BaseModel):
    """One task in the queue, as submitted by the frontend.

    `entry` 即 MAA 任务类型（StartUp/Fight/Recruit/Infrast/Mall/Award/Roguelike/
    Copilot…），`params` 为 MAA AsstAppendTask 参数（见 docs/architecture.md §3.2），
    由引擎层 asstproxy.to_asst_task() 补齐 MAA 必填字段。
    """

    name: str = Field(min_length=1, max_length=64)
    # MAA 任务类型（AsstAppendTask type），如 "Fight" / "Recruit" / "StartUp"。
    entry: str = Field(min_length=1, max_length=64)
    # Human-readable task type label, e.g. "刷理智".
    type: str = Field(min_length=1, max_length=32)
    params: dict = Field(default_factory=dict)


class TaskRunCreate(BaseModel):
    """Body of POST /tasks/{device_id}/run — the queue to execute."""

    tasks: list[TaskItem] = Field(min_length=1, max_length=32)


class LogEntryRead(BaseModel):
    """One persisted log line."""

    id: int
    run_id: int
    device_id: int
    # 日志来源：normal（普通任务）| auto（定时自动任务）| manual_auto（自动任务·手动运行）
    source: str = "normal"
    level: str
    message: str
    ts: datetime


class LogDayGroup(BaseModel):
    """一天的任务日志（按天分割，本地时区日期）。"""

    date: str  # YYYY-MM-DD（本地时区）
    count: int
    entries: list[LogEntryRead] = []  # 时间正序


class LogsByDayRead(BaseModel):
    """历史任务日志（跨 run，按天分组倒序）。"""

    days: list[LogDayGroup] = []

    model_config = {"from_attributes": True}


class TaskRunRead(BaseModel):
    """A task run record."""

    id: int
    device_id: int
    status: str
    summary: str
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskStatusRead(BaseModel):
    """Live status of a device's task runner."""

    device_id: int
    # idle | running | stopping | finished | error
    status: str
    run_id: int | None = None
    # 当前/最近一次运行的任务摘要
    summary: str = ""
    # 设备是否已连接（未连接时无法执行）
    device_online: bool = False
    engine_available: bool = False
    resource_ready: bool = False
    error: str | None = None


class TaskRunResult(BaseModel):
    """Response of run / stop actions."""

    run_id: int
    device_id: int
    status: str
    message: str
