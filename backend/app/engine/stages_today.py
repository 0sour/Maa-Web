"""今日开放关卡（M5 扩展）— 对齐 MAA 客户端 StageManager 主界面「今日开放」提示。

数据源（对齐客户端 StageManager.cs）：
  - 官方接口 `gui/StageActivityV2.json`（MAA API，活动/资源收集/活动关卡与掉落），
    带本地缓存（`<maa-resource>/.stages_today.json`，>6h 刷新，失败用缓存降级）
  - 本地常驻关卡表（对齐客户端 AddPermanentStages：资源本 CE-6/AP-5/CA-5/LS-6/SK-5、
    芯片本 PR-*、剿灭；按星期开放）

判断逻辑（对齐 StageInfo.IsStageOpen）：
  - 游戏日 YJ 历（凌晨 4 点重置，复用 taskrunner._yj_today）取「今天星期」
  - 活动在 StartTimeUtc..ExpireTimeUtc 窗口内 → 开放（剩余 N 天）
  - 资源/芯片关卡 OpenDaysOfWeek 含今天 → 开放
  - 常驻关卡 → 总开放

掉落材料中文名取自引擎包 item_index.json（resource_mgr.item_list）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.runtime_settings import http_proxy as runtime_http_proxy
from app.engine import resource_mgr

log = logging.getLogger(__name__)

_STAGE_API = "gui/StageActivityV2.json"
_API_BASES = (
    "https://api.maa.plus/MaaAssistantArknights/api/",
    "https://api2.maa.plus/MaaAssistantArknights/api/",
)
_REFRESH_AFTER = timedelta(hours=6)

# 中文星期（与 C# DayOfWeek 枚举名对应，客户端 JSON 用 "Monday" 等字符串）
_WEEKDAY_CN = {
    "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三", "Thursday": "周四",
    "Friday": "周五", "Saturday": "周六", "Sunday": "周日",
}


def _yj_now() -> datetime:
    """游戏日历当前时刻（凌晨 4 点重置，对齐客户端 DateTimeExtension.ToYjDate）。"""
    return datetime.now().astimezone() - timedelta(hours=4)


def _weekday_cn() -> str:
    return _WEEKDAY_CN.get(_yj_now().strftime("%A"), "")


def _parse_dt(token: dict, key: str) -> datetime | None:
    """解析 `yyyy/MM/dd HH:mm:ss` + TimeZone 字段 → UTC（对齐客户端 ParseDateTime）。"""
    raw = token.get(key)
    if not raw:
        return None
    try:
        dt = datetime.strptime(str(raw), "%Y/%m/%d %H:%M:%S")
        tz = int(token.get("TimeZone") or 0)
        return dt - timedelta(hours=tz)
    except (ValueError, TypeError):
        return None


def _days_left(expire: datetime | None, now: datetime) -> int | None:
    """剩余天数（对齐客户端 GetDaysLeftText：不足一日归 0 由前端显示「不足一日」）。"""
    if expire is None:
        return None
    return max(0, (expire - now).days)


@dataclass
class _Stage:
    """常驻资源/芯片关卡（对齐客户端 AddPermanentStages 表）。"""

    value: str
    label: str
    open_days: list[str] = field(default_factory=list)  # C# DayOfWeek 名，空=每天
    drops: list[list[str]] = field(default_factory=list)  # 掉落或掉落组（芯片本多组）
    hidden: bool = False


# 常驻关卡表（对齐 MAA 客户端 AddPermanentStages；掉落组照抄：芯片本按
# 远程/近战/术师/重装分组的 PR-X-1/2 双掉落组合）
_PERMANENT_STAGES: list[_Stage] = [
    # 资源本（CE/AP/CA/LS/SK）
    _Stage("CE-6", "龙门币本", ["Tuesday", "Thursday", "Saturday", "Sunday"]),
    _Stage("AP-5", "经验本", ["Monday", "Thursday", "Saturday", "Sunday"]),
    _Stage("CA-5", "技巧概要本", ["Tuesday", "Wednesday", "Friday", "Sunday"], [["3301", "3302", "3303"]]),
    _Stage("LS-6", "作战记录本", []),
    _Stage("SK-5", "碳本", ["Monday", "Wednesday", "Friday", "Saturday"]),
    # 芯片本（掉落组：[[PR-X-1 掉落], [PR-X-2 掉落]]，照抄客户端）
    _Stage("PR-A-1", "近战·芯片本", ["Monday", "Thursday", "Friday", "Sunday"], [["3261", "3231"], ["3262", "3232"]]),
    _Stage("PR-A-2", "近战·芯片本", ["Monday", "Thursday", "Friday", "Sunday"]),
    _Stage("PR-B-1", "远程·芯片本", ["Monday", "Tuesday", "Friday", "Saturday"], [["3251", "3241"], ["3252", "3242"]]),
    _Stage("PR-B-2", "远程·芯片本", ["Monday", "Tuesday", "Friday", "Saturday"]),
    _Stage("PR-C-1", "术师·芯片本", ["Wednesday", "Thursday", "Saturday", "Sunday"], [["3211", "3271"], ["3212", "3272"]]),
    _Stage("PR-C-2", "术师·芯片本", ["Wednesday", "Thursday", "Saturday", "Sunday"]),
    _Stage("PR-D-1", "重装·芯片本", ["Tuesday", "Wednesday", "Saturday", "Sunday"], [["3221", "3281"], ["3222", "3282"]]),
    _Stage("PR-D-2", "重装·芯片本", ["Tuesday", "Wednesday", "Saturday", "Sunday"]),
    # 剿灭（总开放）
    _Stage("Annihilation", "剿灭", []),
    # 隐藏关（活动复刻时注入 OF-1/OF-F3）
    _Stage("OF-1", "OF-1", [], hidden=True),
    _Stage("OF-F3", "OF-F3", [], hidden=True),
]


def _cache_path() -> Path:
    root = get_settings().maa_resource_dir
    return root / ".stages_today.json"


def _load_cached() -> dict | None:
    """读取本地缓存（结构 {fetched_at, data}），损坏/缺失返回 None。"""
    try:
        raw = json.loads(_cache_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            return raw
    except (OSError, ValueError):
        pass
    return None


def _save_cache(data: dict) -> None:
    try:
        _cache_path().parent.mkdir(parents=True, exist_ok=True)
        _cache_path().write_text(
            json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "data": data},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        log.warning("stages_today cache write failed", exc_info=True)


async def _fetch_activity_json() -> dict | None:
    """拉取官方 StageActivityV2.json（api.maa.plus / api2 备用，走 HTTP 代理）。"""
    settings = get_settings()
    proxy = runtime_http_proxy() or None
    headers = {"User-Agent": "Maa-Web/1.0"}
    for base in _API_BASES:
        try:
            async with httpx.AsyncClient(
                timeout=settings.maa_resource_api_timeout,
                headers=headers,
                follow_redirects=True,
                proxy=proxy,
            ) as client:
                resp = await client.get(base + _STAGE_API)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    return data
        except Exception as exc:  # noqa: BLE001 - network surface
            log.warning("StageActivityV2 fetch failed (%s): %s", base, exc)
    return None


def _parse_activities(data: dict) -> tuple[dict | None, list[dict]]:
    """解析 sideStoryStage + resourceCollection（CN 客户端）：

    返回 (资源收集信息或 None, 活动列表)。
    活动条目：{name, days_left, stages: [{stage, drop}]}；只保留开放中的。
    """
    now = _yj_now()
    cn = data.get("CN") or data.get("cn") or {}
    if not isinstance(cn, dict):
        return None, []

    # 资源收集活动（龙门市区剿灭等全资源开放）
    rc: dict | None = None
    rc_raw = cn.get("resourceCollection") or cn.get("resource_collection")
    if isinstance(rc_raw, dict):
        start = _parse_dt(rc_raw, "UtcStartTime")
        expire = _parse_dt(rc_raw, "UtcExpireTime")
        if start is not None and expire is not None and start <= now <= expire:
            rc = {
                "name": rc_raw.get("Tip") or "资源全开放",
                "days_left": _days_left(expire, now),
            }

    # SideStory 活动
    activities: list[dict] = []
    side = cn.get("sideStoryStage") or cn.get("side_story_stage")
    if not isinstance(side, dict):
        return rc, activities

    for key, group in side.items():
        if not isinstance(group, dict):
            continue
        act = group.get("Activity") or group.get("activity")
        stages_raw = group.get("Stages") or group.get("stages")
        if not isinstance(act, dict) or not isinstance(stages_raw, list):
            continue
        start = _parse_dt(act, "UtcStartTime")
        expire = _parse_dt(act, "UtcExpireTime")
        if start is None or expire is None or not (start <= now <= expire):
            continue  # 未开放/已过期
        stages: list[dict] = []
        for s in stages_raw:
            if not isinstance(s, dict):
                continue
            display = s.get("Display") or s.get("Value") or ""
            drop = s.get("Drop")
            if not display or not drop:
                continue
            stages.append({"stage": str(display), "drop": str(drop)})
        activities.append({
            "name": act.get("StageName") or key,
            "days_left": _days_left(expire, now),
            "stages": stages,
        })
    return rc, activities


def _parse_permanent(weekday_cn_en: str) -> list[dict]:
    """常驻资源/芯片关卡：今天开放的条目（含掉落中文名与掉落组）。"""
    names = resource_mgr.item_names_map()
    out: list[dict] = []
    for s in _PERMANENT_STAGES:
        if s.hidden:
            continue
        if s.open_days and weekday_cn_en not in s.open_days:
            continue
        drops: list[list[str]] = []
        if s.drops:
            for group in s.drops:
                drops.append([names.get(i, i) for i in group])
        out.append({
            "stage": s.value,
            "label": s.label,
            "drops": drops,
        })
    return out


async def compute() -> dict:
    """计算今日开放关卡（供 GET /resources/stages/today）。

    优先网络刷新（>6h 或缓存缺失），失败降级缓存；无缓存则仅常驻关卡。
    """
    now_utc = datetime.now(timezone.utc)
    cached = _load_cached()

    data: dict | None = None
    source = "local"

    stale = True
    if cached is not None and cached.get("fetched_at"):
        try:
            stale = datetime.fromisoformat(str(cached["fetched_at"])) + _REFRESH_AFTER <= now_utc
        except ValueError:
            stale = True

    if stale:
        fresh = await _fetch_activity_json()
        if fresh is not None:
            data = fresh
            source = "web"
            _save_cache(fresh)
        elif cached is not None:
            data = cached.get("data")
            source = "cache"
    elif cached is not None:
        data = cached.get("data")

    rc: dict | None = None
    activities: list[dict] = []
    if data is not None:
        rc, activities = _parse_activities(data)

    weekday_en = _yj_now().strftime("%A")
    return {
        "game_day": {
            "date": _yj_now().strftime("%Y-%m-%d"),
            "weekday": _WEEKDAY_CN.get(weekday_en, weekday_en),
        },
        "source": source,
        "fetched_at": now_utc.isoformat(),
        "resource_collection": rc,
        "activities": activities,
        "open_stages": _parse_permanent(weekday_en),
    }
