"""Pydantic DTOs for the auto-tasks API (自动任务 · M6+).

结构：AutoTask（任务组）→ AutoSlot（时间槽）→ AutoSlotAccount（账号 × 方案快照）。
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.task import TaskItem

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# 到点冲突策略（设备忙时的处理方式）
CONFLICT_CHOICES = ("queue", "skip", "force")
# 客户端类型（对齐 MAA 客户端 StartUpTask 下拉；中文服为主）
CLIENT_TYPE_CHOICES = ("Official", "Bilibili", "txwy", "YoStarEN", "YoStarKR", "YoStarJP", "YoStarTW")


class AutoSlotAccountIn(BaseModel):
    """时间槽的账号绑定（创建/更新时输入）。"""

    # 账号名（引用设置·账号组 accounts.list 的 name；引擎侧 = StartUp.account_name）
    account_name: str = Field(min_length=1, max_length=64)
    client_type: str = "Official"
    # 勾选启用（取消勾选 = 停用但保留配置）
    enabled: bool = True
    # 来源方案名（展示用）
    plan_name: str = Field(default="", max_length=128)
    # 方案内容快照（含参数微调后的结果；空 = 未配置，执行时跳过）
    tasks: list[TaskItem] = Field(default_factory=list)


class AutoSlotIn(BaseModel):
    """时间槽（创建/更新时输入）。

    name 允许为空（与组名一致：未命名槽显示「未命名时间点」，
    2026-08-16 起不允许因空名导致整组保存失败）。
    """

    name: str = Field(default="", max_length=64)
    enabled: bool = True
    weekdays: list[str] = Field(default_factory=list)
    time: str = Field(pattern=_TIME_RE.pattern)
    conflict: str = "queue"
    accounts: list[AutoSlotAccountIn] = Field(default_factory=list)


class AutoTaskCreate(BaseModel):
    """自动任务（组）创建/整体保存：slots 全量替换。

    name 允许为空（新建组立即落库，未命名组显示「未命名」；
    2026-08-16 起无 localStorage 草稿，组一旦创建即存在于后端）。
    """

    name: str = Field(default="", max_length=64)
    device_id: int
    enabled: bool = True
    slots: list[AutoSlotIn] = Field(default_factory=list)


class AutoSlotAccountRead(BaseModel):
    """时间槽的账号绑定（读取）。"""

    id: int
    account_name: str
    client_type: str
    enabled: bool
    plan_name: str = ""
    tasks: list[TaskItem] = Field(default_factory=list)
    position: int = 0
    last_run_at: datetime | None = None
    last_ok: bool | None = None


class AutoSlotRead(BaseModel):
    """时间槽（读取）。"""

    id: int
    name: str
    enabled: bool
    weekdays: list[str] = Field(default_factory=list)
    time: str
    conflict: str
    accounts: list[AutoSlotAccountRead] = Field(default_factory=list)
    last_run_at: datetime | None = None


class AutoTaskRead(BaseModel):
    """自动任务（组）（读取）。"""

    id: int
    name: str
    enabled: bool
    device_id: int
    slots: list[AutoSlotRead] = Field(default_factory=list)
    created_at: datetime


class AutoRunTestPayload(BaseModel):
    """POST /auto-tasks/{id}/run-test 请求体 — 测试运行目标时间槽。"""

    slot_id: int
