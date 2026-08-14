"""SQLAlchemy ORM models — Setting 通用设置表（S-04 配置管理的基础存储）。

设置页各分组（运行/连接/界面等）以 `key` 扁平存储（前缀 `game.*` / `connection.*`
/ `ui.*`），value 为 JSON 序列化文本（bool/str/number/list 均可）。
镜像源等运行时热更新设置仍走 `runtime_settings.json`（见 core/runtime_settings.py）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.device import Base


class Setting(Base):
    """通用 key-value 设置（S-04/§4.4 设置中心存储）。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
