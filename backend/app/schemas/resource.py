"""Pydantic DTOs for the MAA resource pack API (S-07)."""
from __future__ import annotations

from pydantic import BaseModel


class ResourceStatus(BaseModel):
    """Resource pack state: local + remote + background update task."""

    # 本地
    installed: bool
    local_version: str | None = None
    pipelines: int = 0
    ready: bool = False
    dir: str = ""
    source: str = ""
    # 更新任务
    updating: bool = False
    progress: float = 0.0
    stage: str = "idle"  # idle | fetch | download | extract | swap | done | error
    update_error: str | None = None
    # 远端
    remote_latest: str | None = None
    remote_url: str | None = None
    remote_size: int = 0
    update_available: bool = False
    source_hint: str = ""
    # 动态资源（MaaResource 增量同步）
    dynamic_syncing: bool = False
    dynamic_stage: str = "idle"  # idle | diff | download | merge | done | error
    dynamic_error: str | None = None
    dynamic_synced_at: str | None = None
    dynamic_commit: str | None = None
    dynamic_pending: int = 0
    dynamic_done: int = 0
    dynamic_mode: str = ""  # diff | full


class ResourceUpdateResult(BaseModel):
    """Response of POST /resources/update."""

    updating: bool
    progress: float = 0.0
    stage: str = "idle"
    message: str


class ResourceItem(BaseModel):
    """One entry of the engine pack item table (item_index.json)."""

    id: str
    name: str
    classify_type: str = ""


class ActivityStage(BaseModel):
    """活动内关卡（名称 + 掉落物）。

    对应 MAA 客户端 GetStageTips 的 `关卡名: 掉落材料名` 行。
    """

    stage: str
    drop: str


class ActivityInfo(BaseModel):
    """今日开放中的 SideStory 活动。"""

    name: str
    days_left: int | None = None
    stages: list[ActivityStage] = []


class ResourceCollectionInfo(BaseModel):
    """资源全开放活动（龙门市区等，含剩余天数）。"""

    name: str
    days_left: int | None = None


class PermanentStageInfo(BaseModel):
    """常驻资源/芯片关卡（今日开放）：掉落或掉落组（芯片本多组合）。"""

    stage: str
    label: str
    drops: list[list[str]] = []


class MiniGameInfo(BaseModel):
    """小游戏（牛杂）条目：value 为引擎任务名（Custom 下发用）。"""

    value: str
    display: str
    tip: str = ""
    days_left: int | None = None
    source: str  # activity | permanent


class TodayStages(BaseModel):
    """GET /resources/stages/today — 今日开放关卡（对齐 MAA 客户端主界面提示）。"""

    game_day: dict[str, str]  # {date, weekday}
    source: str  # web | cache | local
    fetched_at: str
    resource_collection: ResourceCollectionInfo | None = None
    activities: list[ActivityInfo] = []
    open_stages: list[PermanentStageInfo] = []
    minigames: list[MiniGameInfo] = []
