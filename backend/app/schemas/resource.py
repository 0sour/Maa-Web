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
