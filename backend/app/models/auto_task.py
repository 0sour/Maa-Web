"""SQLAlchemy ORM models — 自动任务（AutoTask → AutoSlot → AutoSlotAccount）。

一个自动任务 = 多个时间槽（各自名称/星期/时间/启停/冲突策略）；
每个时间槽有独立账号列表，每个账号绑定自己的方案快照 + 可选参数微调。
账号切换由引擎 AccountSwitchTask 完成（StartUp 注入 account_name）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.device import Base


class AutoTask(Base):
    """自动任务组（如「每日长草」）：一组时间槽的集合。"""

    __tablename__ = "auto_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 自动任务组名称（用户可辨识，如「每日长草」）
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class AutoSlot(Base):
    """时间槽：星期 × 时间 触发点（含冲突策略与防重标记）。"""

    __tablename__ = "auto_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 槽名称（如「早间长草」）
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # JSON 数组：["Mon","Tue",...]（与周计划同用 %a 缩略）
    weekdays: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 触发时间 "HH:MM"（本地时区，分钟级）
    time: Mapped[str] = mapped_column(String(5), nullable=False, default="06:00")
    # 到点冲突策略（设备仍有任务运行时）：queue 排队等待 | skip 跳过本次 | force 强制结束上一任务
    conflict: Mapped[str] = mapped_column(String(8), nullable=False, default="queue")
    # 上次触发时间（防同分钟重复触发 + 展示）
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class AutoSlotAccount(Base):
    """时间槽的账号绑定：账号（来自设置·账号组）+ 方案快照 + 启停勾选。"""

    __tablename__ = "auto_slot_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 槽内执行顺序（升序）
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 账号名（引用设置·账号组 accounts.list 的 name；引擎侧 = StartUp.account_name）
    account_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 客户端类型（官服 Official / B服 Bilibili / txwy / yoestar）
    client_type: Mapped[str] = mapped_column(String(16), nullable=False, default="Official")
    # 勾选启用（取消勾选 = 停用但保留配置）
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 来源方案名（展示用；tasks 为保存时的快照，含参数微调后的结果）
    plan_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # 方案内容快照（TaskItemPayload JSON 数组）
    tasks: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 上次执行结果（展示 ✓/✗）
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
