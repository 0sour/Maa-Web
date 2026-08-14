"""Copilot (作业) API — prts.plus 作业站集成 + 本地作业列表。

Routes:
    GET  /copilot/list             本地 resource/copilot/ 已有作业 JSON 列表
    POST /copilot/prts/{id}        从 prts.plus 按作业 ID 拉取并保存（兼容旧调用）
    POST /copilot/prts/code        解析作业站代码（prts://99359 / prts://s51251
                                   / s51251 / 99359）→ 单个作业或作业集
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.engine import copilot_mgr
from app.schemas.copilot import CopilotCodeResult, CopilotFetchResult, CopilotFile

log = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotCodeIn(BaseModel):
    code: str


def _to_fetch_result(data: dict) -> CopilotFetchResult:
    return CopilotFetchResult(**data)


@router.get("/list", response_model=list[CopilotFile])
async def copilot_list() -> list[dict]:
    """本地已有作业 JSON 列表（含从作业内容读取的关卡名）。"""
    return copilot_mgr.copilot_files()


@router.post("/prts/code", response_model=CopilotCodeResult)
async def copilot_resolve_code(payload: CopilotCodeIn) -> CopilotCodeResult:
    """解析作业站代码 → 单个作业保存 / 作业集逐个下载保存。

    注意：必须声明在 /prts/{copilot_id} 之前，否则 "code" 会被当作
    copilot_id 匹配（FastAPI 按声明顺序匹配路由）。
    """
    try:
        ctype, cid = copilot_mgr.resolve_code(payload.code)
        if ctype == "set":
            data = await copilot_mgr.fetch_set_from_prts(cid)
            return CopilotCodeResult(
                type="set",
                name=data["name"],
                description=data["description"],
                jobs=[_to_fetch_result(j) for j in data["jobs"]],
                skipped=data["skipped"],
            )
        data = await copilot_mgr.fetch_from_prts(cid)
        return CopilotCodeResult(type="copilot", **_to_fetch_result(data).model_dump())
    except copilot_mgr.CopilotFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - keep server alive
        log.exception("copilot resolve code unexpected error")
        raise HTTPException(status_code=502, detail="作业站暂时不可用，请稍后重试") from exc


@router.post("/prts/{copilot_id}", response_model=CopilotFetchResult)
async def copilot_fetch_prts(copilot_id: int) -> CopilotFetchResult:
    """从 prts.plus 按作业 ID 拉取 → 保存到 resource/copilot/ → 返回元信息。"""
    try:
        return _to_fetch_result(await copilot_mgr.fetch_from_prts(copilot_id))
    except copilot_mgr.CopilotFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - keep server alive
        log.exception("copilot fetch unexpected error id=%s", copilot_id)
        raise HTTPException(status_code=502, detail="作业站暂时不可用，请稍后重试") from exc
