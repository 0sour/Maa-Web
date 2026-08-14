"""MAA resource pack management API (S-07) — active download & update.

Routes:
    GET  /resources/status  本地资源状态 + 远端最新版本（可更新判断）
    POST /resources/update  后台下载官方 release 资源包并原子替换

下载源：MAA 官方 GitHub Releases（MAA-v{tag}-{platform}.zip 内 resource/ 目录），
支持镜像前缀（MAAWEB_RESOURCE_MIRROR）与平台选择（MAAWEB_RESOURCE_PLATFORM）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.engine import resource_mgr
from app.schemas.resource import ResourceItem, ResourceStatus, ResourceUpdateResult

log = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("/status", response_model=ResourceStatus)
async def resource_status() -> ResourceStatus:
    """资源包状态：本地就绪/版本 + 是否可更新 + 后台更新进度。"""
    data = await resource_mgr.status()
    return ResourceStatus(**data)


@router.post("/update", response_model=ResourceUpdateResult)
async def resource_update() -> ResourceUpdateResult:
    """触发后台资源包下载/更新（幂等，重复调用返回当前进度）。"""
    data = await resource_mgr.update()
    if data.get("error"):
        return ResourceUpdateResult(
            updating=False,
            stage=data.get("stage", "error"),
            message=data["error"],
        )
    if data.get("running"):
        return ResourceUpdateResult(
            updating=True,
            progress=data.get("progress", 0.0),
            stage=data.get("stage", "download"),
            message="资源包下载/更新已开始",
        )
    return ResourceUpdateResult(
        updating=False,
        progress=data.get("progress", 0.0),
        stage=data.get("stage", "idle"),
        message="资源包已是最新，无需更新",
    )


@router.post("/sync", response_model=ResourceUpdateResult)
async def resource_sync() -> ResourceUpdateResult:
    """触发动态资源增量同步（MaaResource 活动/模板热更新，幂等）。"""
    data = await resource_mgr.sync_dynamic()
    if data.get("error"):
        return ResourceUpdateResult(
            updating=False,
            stage=data.get("stage", "error"),
            message=data["error"],
        )
    if data.get("running"):
        return ResourceUpdateResult(
            updating=True,
            progress=data.get("progress", 0.0),
            stage=data.get("stage", "download"),
            message=(
                f"动态资源同步中（{data.get('mode', 'diff')} 模式，"
                f"待处理 {data.get('pending', 0)} 项）"
            ),
        )
    return ResourceUpdateResult(
        updating=False,
        stage=data.get("stage", "idle"),
        message="动态资源已是最新",
    )


@router.get("/stages", response_model=list[str])
async def resource_stages() -> list[str]:
    """引擎包关卡代号列表（供「目标关卡」搜索下拉选择）。"""
    return resource_mgr.stage_codes()


@router.get("/items", response_model=list[ResourceItem])
async def resource_items() -> list[ResourceItem]:
    """引擎包材料/物品表（item_index.json，供「指定掉落」搜索下拉选择）。"""
    return [ResourceItem(**it) for it in resource_mgr.item_list()]


@router.get("/operators", response_model=list[ResourceItem])
async def resource_operators() -> list[ResourceItem]:
    """引擎包干员表（battle_data.json，供 Copilot「追加干员」搜索下拉选择）。"""
    return [ResourceItem(**it) for it in resource_mgr.operator_list()]


@router.get("/recruit-tags", response_model=list[str])
async def resource_recruit_tags() -> list[str]:
    """引擎包公招 Tag 列表（recruitment.json，供「首选/保留 Tags」多选）。"""
    return resource_mgr.recruit_tags()


@router.get("/roguelike-core-chars", response_model=list[str])
async def resource_roguelike_core_chars(theme: str) -> list[str]:
    """指定肉鸽主题的开局核心干员（roguelike/{theme}/recruitment.json 的 is_start）。

    供「开局干员」可搜索下拉；随主题联动（对齐 MAA 客户端 UpdateRoguelikeCoreCharList）。
    """
    return resource_mgr.roguelike_core_chars(theme)
