"""SQLAlchemy ORM model — ToolboxRecord 工具箱识别记录（M5）。

公招/仓库/干员识别结果自动保存，供历史调用展示与后续联动。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.device import Base


class ToolboxRecord(Base):
    """一次工具箱识别/操作的结果记录。"""

    __tablename__ = "toolbox_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 工具类型：recruit | depot | operbox（抽卡/窥屏后续扩展）
    tool: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 识别结果 JSON（结构随工具而异，见 engine/toolbox.py 解析器）
    result: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
