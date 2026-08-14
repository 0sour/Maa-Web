"""作业（Copilot）管理 — prts.plus 作业站集成。

prts.plus（Maa 作业分享站）不提供公开搜索 API，客户端（MaaWpfGui）用
`GET /copilot/get/{id}`（单个作业）与 `GET /set/get?id={id}`（作业集）拉取。
作业站代码格式（对齐 MAA 客户端 TryParseCopilotCode）：

    prts://99359     单个作业
    prts://s51251    作业集
    maa://99359      旧格式作业
    s51251           作业集简写
    99359            纯数字 = 单个作业

本模块在 Web 端做同样的事：

    resolve_code(code)        — 解析作业站代码 → (type, id)
    fetch_from_prts(id)       — 拉取单个作业 → 保存到 resource/copilot/
    fetch_set_from_prts(id)   — 拉取作业集 → 逐个下载作业保存 → 返回作业列表
"""
from __future__ import annotations

import functools
import json
import logging
import re
from pathlib import Path

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

_PRTS_GET = "https://prts.maa.plus/copilot/get/{}"
_PRTS_SET_GET = "https://prts.maa.plus/set/get?id={}"
_UA = "Maa-Web (NAS automation console)"


class CopilotFetchError(Exception):
    """作业站拉取/校验失败（业务错误，API 层映射为 400）。"""


def _copilot_dir() -> Path:
    return get_settings().maa_resource_dir / "resource" / "copilot"


def _sanitize_segment(name: str) -> str:
    """文件名安全：剔除路径分隔符/控制字符，防路径穿越。"""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return cleaned or "copilot"


# ── 关卡显示名映射（作业 stage_name 是内部 stageId，如 act53side_ex01） ──

@functools.lru_cache(maxsize=1)
def _stage_index() -> dict[str, dict]:
    """Arknights-Tile-Pos/overview.json → {stageId: {code, name}}（进程内缓存）。

    MAA 客户端用同一份数据（DataHelper.FindMap）做关卡识别与显示：
    如 stageId act53side_ex01 → code "TO-EX-1"（用户认识的关卡编号）,
    name "电影防沉迷"（关卡名）。文件缺失时返回空索引，回退原值。
    """
    p = get_settings().maa_resource_dir / "resource" / "Arknights-Tile-Pos" / "overview.json"
    index: dict[str, dict] = {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            sid = entry.get("stageId")
            if not sid:
                continue
            index[sid] = {"code": entry.get("code") or "", "name": entry.get("name") or ""}
    except Exception:  # noqa: BLE001 - 缺文件/损坏都不阻塞列表
        log.warning("stage overview unavailable: %s", p)
    return index


def stage_display_name(stage_name: str) -> str:
    """作业 stage_name（内部 stageId）→ 用户可读的关卡名。

    优先返回关卡编号 code（如 TO-EX-1 / CE-6），无 code 用关卡名 name，
    都不是（或映射缺失）则回退原值。仅用于展示，不影响执行参数。
    """
    if not stage_name:
        return ""
    entry = _stage_index().get(stage_name)
    if entry:
        return entry["code"] or entry["name"] or stage_name
    return stage_name


def _job_type(content: dict) -> str:
    """作业类型：type=SSS → sss（保全专用格式，无 opers/groups）；其余 → copilot。

    对齐 MAA 客户端：SSSCopilotModel.Type == "SSS"，CopilotModel 为标准作业格式
    （悖论模拟作业同为标准格式，走 ParadoxCopilotTask 加载）。
    """
    return "sss" if str(content.get("type") or "").strip().upper() == "SSS" else "copilot"


def copilot_files() -> list[dict]:
    """本地作业 JSON 列表：[{filename, stage_name, stage_display, job_type}]。

    filename 相对 resource/（含 copilot/ 前缀）；stage_name 是作业内部关卡
    stageId（执行用）；stage_display 是用户可读的关卡名（展示用）。
    """
    base = get_settings().maa_resource_dir / "resource"
    d = _copilot_dir()
    if not d.is_dir():
        return []
    out: list[dict] = []
    for rel in sorted(f.relative_to(base).as_posix() for f in d.rglob("*.json")):
        stage = ""
        jtype = "copilot"
        try:
            data = json.loads((base / rel).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                stage = str(data.get("stage_name") or "")
                jtype = _job_type(data)
        except Exception:  # noqa: BLE001 - 单个作业解析失败不阻塞列表
            pass
        out.append(
            {
                "filename": rel,
                "stage_name": stage,
                "stage_display": stage_display_name(stage),
                "job_type": jtype,
            }
        )
    return out


def resolve_code(code: str) -> tuple[str, int]:
    """解析作业站代码 → (type, id)。type: copilot | set。格式见模块 docstring。"""
    s = (code or "").strip()
    if not s:
        raise CopilotFetchError("请输入作业站代码")
    # 长前缀优先：prts://s(8) / prts://(7) / maa://(6)，避免 prts://s 被 prts:// 抢先
    if s.lower().startswith("prts://s"):
        return "set", _parse_id(s[8:])
    if s.lower().startswith("prts://"):
        return "copilot", _parse_id(s[7:])
    if s.lower().startswith("maa://"):
        return "copilot", _parse_id(s[6:])
    if len(s) > 1 and s[0] in "sS":
        return "set", _parse_id(s[1:])
    return "copilot", _parse_id(s)


def _parse_id(rest: str) -> int:
    rest = rest.strip()
    if not rest.isdigit():
        raise CopilotFetchError(f"无法从代码中解析作业 ID：{rest!r}")
    return int(rest)


async def _request_json(url: str) -> dict:
    """GET 并解析 JSON；网络错误抛 CopilotFetchError。"""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            timeout=settings.maa_resource_api_timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001 - network/binding surface
        log.warning("prts.plus request failed %s: %s", url, exc)
        raise CopilotFetchError("作业站请求失败，请检查网络或稍后重试") from exc


async def fetch_from_prts(copilot_id: int) -> dict:
    """拉取 prts.plus 单个作业 → 校验 → 保存到 resource/copilot/ → 返回元信息。

    返回 {id, filename, stage_name, uploader, views, rating, upload_time}。
    保存文件名带唯一 id，避免同名关卡覆盖。失败抛 CopilotFetchError。
    """
    data = await _request_json(_PRTS_GET.format(copilot_id))

    if data.get("status_code") != 200 or not isinstance(data.get("data"), dict):
        msg = data.get("message") or "作业不存在或已下架"
        log.warning("prts.plus returned error id=%s: %s", copilot_id, msg)
        raise CopilotFetchError(str(msg))

    info = data["data"]
    content = info.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError as exc:
            raise CopilotFetchError("作业内容 JSON 解析失败") from exc
    if not isinstance(content, dict):
        raise CopilotFetchError("作业内容格式异常")
    # 按作业类型细分校验（对齐 MAA 客户端 CopilotView 场景分发）：
    # 保全（SSS）专用格式（type=SSS，无 opers/groups）→ 要求 stage_name/strategy；
    # 普通/悖论模拟作业 → 标准格式，要求 opers/groups。
    jtype = _job_type(content)
    if jtype == "sss":
        if not content.get("stage_name") or not content.get("strategy"):
            raise CopilotFetchError("保全（SSS）作业缺少 stage_name/strategy，不是有效作业")
    elif not content.get("opers") and not content.get("groups"):
        raise CopilotFetchError("作业内容缺少 opers/groups，可能不是有效作业")

    stage = str(content.get("stage_name") or info.get("id") or copilot_id)
    filename = f"copilot/{_sanitize_segment(stage)}_{copilot_id}.json"
    dest = get_settings().maa_resource_dir / "resource" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("copilot saved from prts id=%s → %s", copilot_id, filename)

    return {
        "id": int(info.get("id") or copilot_id),
        "filename": filename,
        "stage_name": stage,
        "stage_display": stage_display_name(stage),
        "job_type": _job_type(content),
        "uploader": str(info.get("uploader") or ""),
        "views": int(info.get("views") or 0),
        "rating": int(info.get("rating_level") or 0),
        "upload_time": str(info.get("upload_time") or ""),
    }


async def fetch_set_from_prts(set_id: int) -> dict:
    """拉取 prts.plus 作业集 → 逐个下载作业保存 → 返回 {name, description, jobs}。

    作业集 = 多个作业依次执行（对齐 MAA 客户端 ParseCopilotSetAsync）。
    copilot_ids 去重；单个作业失败跳过并记入 skipped。失败抛 CopilotFetchError。
    """
    data = await _request_json(_PRTS_SET_GET.format(set_id))
    if data.get("status_code") != 200 or not isinstance(data.get("data"), dict):
        msg = data.get("message") or "作业集不存在或已下架"
        log.warning("prts.plus set error id=%s: %s", set_id, msg)
        raise CopilotFetchError(str(msg))

    d = data["data"]
    ids = d.get("copilot_ids")
    if not isinstance(ids, list):
        raise CopilotFetchError("作业集内容格式异常（缺少 copilot_ids）")

    jobs: list[dict] = []
    skipped: list[int] = []
    seen: set[int] = set()
    for cid in ids:
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        try:
            jobs.append(await fetch_from_prts(cid))
        except CopilotFetchError as exc:
            log.warning("set %s job %s skipped: %s", set_id, cid, exc)
            skipped.append(cid)

    if not jobs:
        raise CopilotFetchError("作业集内没有可用作业")

    return {
        "id": int(d.get("id") or set_id),
        "name": str(d.get("name") or f"作业集 {set_id}"),
        "description": str(d.get("description") or ""),
        "jobs": jobs,
        "skipped": skipped,
    }
