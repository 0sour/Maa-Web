"""Pydantic DTOs for the Copilot (作业) API — prts.plus 集成。"""
from __future__ import annotations

from pydantic import BaseModel


class CopilotFile(BaseModel):
    """本地作业列表项：文件名 + 关卡名（从作业内容读取）。"""

    filename: str  # 相对 resource/ 的路径（含 copilot/ 前缀）
    stage_name: str = ""  # 内部 stageId（执行用）
    stage_display: str = ""  # 用户可读关卡名（展示用，如 TO-EX-1）
    job_type: str = "copilot"  # copilot（普通/悖论标准格式）| sss（保全专用格式）


class CopilotFetchResult(BaseModel):
    """prts.plus 单个作业获取结果：已保存到本地 + 展示元信息。"""

    id: int
    filename: str  # 相对 resource/ 的路径（含 copilot/ 前缀）
    stage_name: str
    stage_display: str = ""
    job_type: str = "copilot"  # copilot | sss
    uploader: str = ""
    views: int = 0
    rating: int = 0
    upload_time: str = ""


class CopilotCodeResult(BaseModel):
    """作业站代码解析结果：单个作业（type=copilot）或作业集（type=set）。"""

    type: str  # copilot | set
    # ── copilot ──
    id: int | None = None
    filename: str | None = None
    stage_name: str | None = None
    uploader: str = ""
    views: int = 0
    rating: int = 0
    upload_time: str = ""
    # ── set ──
    name: str | None = None
    description: str = ""
    jobs: list[CopilotFetchResult] = []
    skipped: list[int] = []
