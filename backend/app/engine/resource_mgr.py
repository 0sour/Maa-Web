"""MAA 引擎包管理器（S-07）— 主动下载/更新 MAA 官方发布包。

引擎切换（2026-08）后下载的不再只是 `resource/` 目录，而是**完整发布包**：
    https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases
    /download/{tag}/MAA-{tag}-{platform}.zip        （win-x64 / win-arm64）
    /download/{tag}/MAA-{tag}-linux-{arch}.tar.gz   （linux-x86_64 / linux-aarch64）

包内布局（win zip 为平铺）：`MaaCore.dll`/`libMaaCore.so` 引擎库 + `resource/`（任务/
模板/OCR 模型/global 客户端资源）+ `Python/`、`MAA.exe` 等。引擎包安装目录即
`maa_resource_dir`，AsstLoadResource(该目录) 由 MAA 引擎自己加载全部资源。

管理器能力：
    status()  — 本地引擎包状态 + 远端最新版本（可更新判断）
    update()  — 后台下载 → 解压 → 校验（resource/ + 引擎库）→ 原子替换

下载源可配置：`MAAWEB_RESOURCE_MIRROR`（逗号分隔的多个 ghproxy 类镜像前缀，
形如 `https://ghproxy.net/`，用法为「前缀 + 完整 GitHub URL」；留空用官方
GitHub 直连）。客户端对每个原始 URL 生成候选列表 [镜像×n..., 直连]，并发
HEAD 测速择优，下载失败自动切换到下一候选（参照 MAA 客户端更新机制）。
`MAAWEB_RESOURCE_PLATFORM`（默认 win-x64；linux-x86_64 / linux-aarch64 供
NAS）。远端查询失败不影响本地状态。
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import re
import shutil
import tarfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from app.core import runtime_settings
from app.core.config import get_settings
from app.engine import asstproxy

log = logging.getLogger(__name__)

_VERSION_FILE = "version.json"
_GITHUB_API = (
    "https://api.github.com/repos/"
    "MaaAssistantArknights/MaaAssistantArknights/releases/latest"
)
_UA = "Maa-Web (NAS automation console)"

# ── 后台更新任务状态（进程内单例） ─────────────────────────
_UPDATE: dict = {
    "running": False,
    "progress": 0.0,  # 0.0 ~ 1.0
    "stage": "",  # idle | fetch | download | extract | swap | done | error
    "error": None,
    "started_at": None,
}
_update_lock = asyncio.Lock()
_remote_cache: dict = {"at": 0.0, "data": None}


# ── 镜像源（多候选 + 测速择优 + fallback） ─────────────────
# 参照 MAA 客户端更新机制：对每个原始 GitHub URL 生成候选列表
# [镜像前缀×n + 完整 URL ... , 直连]，并发 HEAD 测速按延迟排序，
# 下载/查询按序尝试，失败自动切换下一候选；直连始终兜底。

_pick_cache: dict[str, tuple[float, list[str]]] = {}  # raw → (at, urls)


def _mirror_prefixes() -> list[str]:
    """解析镜像前缀为列表（逗号/换行分隔）。

    优先运行时设置（设置页保存值），未配置时回退 .env 的 MAAWEB_RESOURCE_MIRROR。
    """
    return runtime_settings.mirror_prefixes()


def _candidate_urls(raw: str) -> list[str]:
    """生成候选 URL：[镜像×n + raw..., raw(直连兜底)]。"""
    return [f"{p}{raw}" for p in _mirror_prefixes()] + [raw]


async def _probe(client: httpx.AsyncClient, url: str) -> float | None:
    """HEAD 测速：返回毫秒延迟；不可达/非 2xx 返回 None。"""
    try:
        t0 = time.monotonic()
        resp = await client.head(url)
        dt = (time.monotonic() - t0) * 1000
        return dt if resp.status_code < 400 else None
    except Exception:  # noqa: BLE001 - any network error means "not reachable"
        return None


async def pick_fastest_urls(raw: str, client: httpx.AsyncClient) -> list[str]:
    """并发 HEAD 测速 → 可达按延迟升序、不可达按原序（直连兜底），缓存 60s。"""
    now = asyncio.get_event_loop().time()
    cached = _pick_cache.get(raw)
    if cached is not None and now - cached[0] < 60:
        return cached[1]

    cands = _candidate_urls(raw)
    lats = await asyncio.gather(*(_probe(client, u) for u in cands))
    ok = [(lat, u) for lat, u in zip(lats, cands, strict=True) if lat is not None]
    ok.sort(key=lambda x: x[0])  # 稳定排序：同延迟保持候选原序（镜像在前、直连兜底）
    fail = [u for lat, u in zip(lats, cands, strict=True) if lat is None]
    urls = [u for _, u in ok] + fail
    _pick_cache[raw] = (now, urls)
    return urls


async def _get_first_json(client: httpx.AsyncClient, urls: list[str]) -> dict | None:
    """按序 GET，第一个 2xx 且可解析 JSON 的返回；全部失败返回 None。"""
    for u in urls:
        try:
            resp = await client.get(u)
            resp.raise_for_status()
            return resp.json()
        except Exception:  # noqa: BLE001 - try next candidate
            continue
    return None


def asset_name(tag: str) -> tuple[str, str]:
    """按平台返回 (资产文件名, 归档类型)。zip | tgz。"""
    p = (get_settings().maa_resource_platform or "win-x64").strip()
    if p.startswith("linux"):
        return f"MAA-{tag}-{p}.tar.gz", "tgz"
    return f"MAA-{tag}-{p}.zip", "zip"


# ── MirrorChyan（Mirror酱）CDK 有效期检查 ─────────────────
# 对齐 MAA 客户端下载源：填写 CDK 后调用官方 API 检查有效期（data.cdk_expired_time，
# unix 秒），并保存到运行时设置，供设置页展示剩余天数。
#
# 错误码（见 MAA 客户端 MirrorChyanErrorCode）：
#   1001 参数不正确 | 7001 CDK 已过期 | 7002 CDK 错误 | 7003 今日下载次数达上限
#   7004 CDK 类型与资源不匹配 | 7005 CDK 已被封禁 | 8001 资源不存在
_MIRRORCHYAN_API = (
    "https://mirrorchyan.com/api/resources/MaaResource/latest"
)
# 引擎包（MAA 应用本体）更新 API（对齐 MAA 客户端 MaaUrls.MirrorChyanAppUpdate）
_MIRRORCHYAN_APP_API = "https://mirrorchyan.com/api/resources/MAA/latest"
_MIRRORCHYAN_ERRORS: dict[int, str] = {
    1001: "参数不正确，请检查配置",
    7001: "Mirror酱 CDK 已过期，请续费或更换",
    7002: "Mirror酱 CDK 无效，请检查后重新输入",
    7003: "Mirror酱 CDK 今日下载次数已达上限",
    7004: "Mirror酱 CDK 类型与待下载资源不匹配",
    7005: "Mirror酱 CDK 已被封禁",
    8001: "对应架构/系统下的资源不存在",
}


async def check_mirrorchyan_cdk(cdk: str) -> dict:
    """调用 MirrorChyan API 校验 CDK 并持久化有效期，返回诊断结果。

    返回：
        {
            "ok": bool,             # CDK 有效（code==0 且已拿到有效期）
            "code": int,            # 原始业务码
            "message": str,         # 用户可读结果
            "cdk_expired_time": int,  # unix 秒；0 = 未知
            "remaining_days": float | None,  # 剩余天数；已过期/未知为 None
        }
    网络异常时返回 ok=False 的友好提示，不抛异常。
    """
    from datetime import datetime, timezone

    settings = get_settings()
    url = (
        f"{_MIRRORCHYAN_API}?cdk={cdk}"
        f"&sp_id={runtime_settings.mirrorchyan_sp_id()}"
        f"&user_agent={_UA}"
    )
    try:
        async with httpx.AsyncClient(
            timeout=settings.maa_resource_api_timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - network/binding surface
        log.warning("MirrorChyan CDK 检查网络失败: %s", exc)
        return {
            "ok": False, "code": 0, "message": f"无法连接 Mirror酱服务（{exc}）",
            "cdk_expired_time": 0, "remaining_days": None,
        }

    code = int(data.get("code") or 0)
    if code != 0:
        msg = _MIRRORCHYAN_ERRORS.get(code) or str(data.get("msg") or "Mirror酱请求失败")
        return {"ok": False, "code": code, "message": msg, "cdk_expired_time": 0, "remaining_days": None}

    cdk_expired_time = int((data.get("data") or {}).get("cdk_expired_time") or 0)
    remaining_days: float | None = None
    if cdk_expired_time > 0:
        remaining_days = (cdk_expired_time - datetime.now(timezone.utc).timestamp()) / 86400
        runtime_settings.update(
            mirrorchyan_cdk=cdk,
            mirrorchyan_cdk_expired_time=cdk_expired_time,
        )
        if remaining_days <= 0:
            return {
                "ok": True, "code": code,
                "message": "Mirror酱 CDK 已过期，请续费或更换",
                "cdk_expired_time": cdk_expired_time,
                "remaining_days": remaining_days,
            }
        return {
            "ok": True, "code": code,
            "message": f"Mirror酱 CDK 有效，剩余 {remaining_days:.1f} 天",
            "cdk_expired_time": cdk_expired_time,
            "remaining_days": remaining_days,
        }
    # 业务成功但未返回有效期 → 视为检查结果未知
    return {
        "ok": False, "code": code,
        "message": "Mirror酱服务未返回有效期信息，请稍后重试",
        "cdk_expired_time": 0, "remaining_days": None,
    }


# ── 本地状态 ───────────────────────────────────────────────

def _local_version_file() -> Path:
    return get_settings().maa_resource_dir / _VERSION_FILE


def _read_local_version() -> dict:
    try:
        return json.loads(_local_version_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _count_pipelines() -> int:
    d = get_settings().maa_resource_dir / "resource"
    if not d.exists():
        return 0
    return sum(1 for _ in d.rglob("*.json"))


def _package_ready() -> bool:
    """引擎包就绪：resource/ 与引擎库均存在。"""
    d = get_settings().maa_resource_dir
    return (d / "resource").is_dir() and (d / asstproxy.engine_lib_name()).exists()


def local_state() -> dict:
    """本地引擎包状态（不访问网络）。"""
    d = get_settings().maa_resource_dir
    version = _read_local_version()
    pipelines = _count_pipelines()
    ready = _package_ready()
    return {
        "installed": bool(version) and ready,
        "local_version": version.get("tag"),
        "pipelines": pipelines,
        "ready": ready,
        "dir": str(d),
        "source": version.get("source", ""),
    }


def stage_codes() -> list[str]:
    """引擎**可导航**关卡代号列表（对齐 MAA 客户端 StageManager），供前端搜索下拉。

    候选 = 常驻/活动导航任务（resource/tasks/Stages/*.json，如 CE-6、TO-5）
          + 主线格式关卡（stages.json 中 `X-NN-NN` 形，如 1-7、JT8-2、H10-1-Hard）。
    引擎无法导航的关卡（如活动未收录导航的 TO-6）不在此列——前端可「手动输入
    关卡名」自由填写（入队时引擎可能拒绝）。
    """
    import re

    root = get_settings().maa_resource_dir / "resource"
    codes: set[str] = set()

    # 1) 导航任务（tasks/Stages/*.json）：过滤 @ 后缀 / Open / Chapter 等辅助任务
    try:
        stages_dir = root / "tasks" / "Stages"
        for f in sorted(stages_dir.glob("*.json")):
            try:
                tasks = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(tasks, dict):
                continue
            for name in tasks:
                if "@" in name:
                    continue
                if re.search(r"(Open|Ocr|Opt|Chapter)", name):
                    continue
                codes.add(name)
    except OSError:
        pass

    # 2) 主线格式关卡（StageNavigationTask 支持 X-NN-NN / H10-1-Hard 等）
    mainline = re.compile(r"^[A-Za-z]{0,3}\d{1,2}-\d{1,2}(?:-\w+)?$")
    try:
        data = json.loads((root / "stages.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = []
    if isinstance(data, list):
        for s in data:
            if isinstance(s, dict) and mainline.match(str(s.get("code", ""))):
                codes.add(str(s["code"]))

    return sorted(codes)


# 关卡不可掉落的材料（对齐 MAA 客户端 FightSettingsUserControlModel._excludedValues）
_EXCLUDED_DROP_ITEMS: frozenset[str] = frozenset(
    {
        "3213", "3223", "3233", "3243",  # 双芯片
        "3253", "3263", "3273", "3283",  # 双芯片
        "7001", "7002", "7003", "7004",  # 许可（招聘/加急等）
        "4004", "4005",  # 凭证
        "3105", "3131", "3132", "3133",  # 龙骨 / 加固建材
        "6001",  # 演习券
        "3141", "4002",  # 源石 / 合成玉
        "32001",  # 芯片助剂
        "30115",  # 聚合剂
        "30125",  # 双极纳米片
        "30135",  # D32钢
        "30145",  # 晶体电子单元
        "30155",  # 烧结核凝晶
        "30165",  # 重相位对映体
    }
)


@functools.lru_cache(maxsize=1)
def item_list() -> list[dict]:
    """引擎包 resource/item_index.json 的材料/物品表（id → 名称），供「指定掉落」搜索选择。

    结构 `{itemId: {name, classifyType, ...}}`；过滤逻辑对齐 MAA 客户端
    `FightSettingsUserControlModel.InitDrops()`：只保留**纯数字 ID**（非数字的
    都是正常关卡不会掉落的特殊/活动道具），再排除 `_EXCLUDED_DROP_ITEMS`
    （关卡不可掉落：双芯片/许可/凭证/龙骨/演习券/源石/高级合成材料等），
    按 ID 排序返回 `[{id, name, classify_type}]`。文件缺失/损坏返回空列表。
    """
    try:
        data = json.loads(
            (get_settings().maa_resource_dir / "resource" / "item_index.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        log.warning("item_index.json 读取失败，返回空物品列表")
        return []
    if not isinstance(data, dict):
        return []
    items = [
        {
            "id": str(iid),
            "name": str(entry.get("name") or "").strip(),
            "classify_type": str(entry.get("classifyType") or ""),
        }
        for iid, entry in data.items()
        if str(iid).isdigit()
        and str(iid) not in _EXCLUDED_DROP_ITEMS
        and isinstance(entry, dict)
        and str(entry.get("name") or "").strip()
    ]
    items.sort(key=lambda x: x["id"])
    return items


@functools.lru_cache(maxsize=1)
def operator_list() -> list[dict]:
    """引擎包 resource/battle_data.json 的干员表（char_id → 名称），供「追加干员」搜索选择。

    结构 `{chars: {char_id: {name, ...}}}`（对齐 MAA 客户端 BattleData）；
    返回按名称排序的 `[{id, name}]`，仅保留带名称的条目。文件缺失/损坏返回空列表。
    """
    try:
        data = json.loads(
            (get_settings().maa_resource_dir / "resource" / "battle_data.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        log.warning("battle_data.json 读取失败，返回空干员列表")
        return []
    chars = data.get("chars") if isinstance(data, dict) else None
    if not isinstance(chars, dict):
        return []
    ops = [
        {"id": str(cid), "name": str(entry.get("name") or "").strip()}
        for cid, entry in chars.items()
        if isinstance(entry, dict) and str(entry.get("name") or "").strip()
    ]
    ops.sort(key=lambda x: x["id"])
    return ops


@functools.lru_cache(maxsize=1)
def recruit_tags() -> list[str]:
    """引擎包 resource/recruitment.json 的公招 Tag 列表，供「首选/保留 Tags」多选。

    结构 `{tags: {tag名: tag名, ...}}`（对齐 MAA 客户端 DataHelper.RecruitTags）；
    返回排序后的 tag 名列表。文件缺失/损坏返回空列表。
    """
    try:
        data = json.loads(
            (get_settings().maa_resource_dir / "resource" / "recruitment.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        log.warning("recruitment.json 读取失败，返回空 Tag 列表")
        return []
    tags = data.get("tags") if isinstance(data, dict) else None
    if not isinstance(tags, dict):
        return []
    return sorted(str(t) for t in tags if str(t).strip())


_ROGUE_THEMES = ("Phantom", "Mizuki", "Sami", "Sarkaz", "JieGarden")


@functools.lru_cache(maxsize=8)
def roguelike_core_chars(theme: str) -> list[str]:
    """指定肉鸽主题的开局核心干员（对齐 MAA 客户端 UpdateRoguelikeCoreCharList）。

    数据源：`resource/roguelike/{theme}/recruitment.json` 的 `priority[].opers[]`
    中 `is_start=true` 的干员名（MAA 官方按主题配置开局可选干员），去重排序。
    主题无效/文件缺失/损坏返回空列表。
    """
    if theme not in _ROGUE_THEMES:
        return []
    try:
        data = json.loads(
            (
                get_settings().maa_resource_dir
                / "resource" / "roguelike" / theme / "recruitment.json"
            ).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        log.warning("roguelike/%s recruitment.json 读取失败，返回空干员列表", theme)
        return []
    names: set[str] = set()
    for group in (data.get("priority") or []) if isinstance(data, dict) else []:
        if not isinstance(group, dict):
            continue
        for op in group.get("opers") or []:
            if isinstance(op, dict) and op.get("is_start") and str(op.get("name") or "").strip():
                names.add(str(op["name"]).strip())
    return sorted(names)


# ── 远端查询（GitHub API，带 60s 缓存） ────────────────────

async def remote_latest() -> dict | None:
    """查询官方最新 release，返回 {tag, asset, url, urls, size} 或 None（失败）。

    `url` 为测速后最优候选，`urls` 为完整候选列表（下载失败可依次 fallback）。
    """
    now = asyncio.get_event_loop().time()
    if _remote_cache["data"] is not None and now - _remote_cache["at"] < 60:
        return _remote_cache["data"]

    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            timeout=settings.maa_resource_api_timeout,
            headers={"User-Agent": _UA, "Accept": "application/vnd.github+json"},
            follow_redirects=True,
        ) as client:
            rel = await _get_first_json(client, await pick_fastest_urls(_GITHUB_API, client))
    except Exception as exc:  # noqa: BLE001 - network/binding surface
        log.warning("resource remote lookup failed: %s", exc)
        return None
    if rel is None:
        log.warning("resource remote lookup failed: all sources unreachable")
        return None

    tag = rel.get("tag_name", "")
    wanted, _kind = asset_name(tag)
    asset = next((a for a in rel.get("assets", []) if a.get("name") == wanted), None)
    if asset is None:
        log.warning("asset %s not found in release %s", wanted, tag)
        return None

    raw_url = str(asset.get("browser_download_url", ""))
    try:
        async with httpx.AsyncClient(
            timeout=settings.maa_resource_api_timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        ) as client:
            urls = await pick_fastest_urls(raw_url, client)
    except Exception as exc:  # noqa: BLE001 - keep local state usable
        log.warning("asset probe failed, fallback to direct: %s", exc)
        urls = [raw_url]

    data = {
        "tag": tag,
        "asset": wanted,
        "url": urls[0],
        "urls": urls,
        "size": asset.get("size", 0),
    }
    _remote_cache.update(at=now, data=data)
    return data


async def remote_latest_mirrorchyan() -> dict | None:
    """查询 Mirror酱 引擎包（MAA 应用本体）最新版本。

    对齐 MAA 客户端 HandleUpdateFromMirrorChyan：调用
    `mirrorchyan.com/api/resources/MAA/latest`，返回
    {tag, asset, url, urls, size} 或 None（CDK 缺失 / 网络失败 / 业务失败）。

    注意：与 GitHub 源不同，Mirror酱 的 os/arch 参数取
    `os=win|linux` + `arch=x64|arm64|x86_64|aarch64`；size 优先取响应的
    `filesize`，缺失时由 _download 从响应头 content-length 计算进度。
    """
    cdk = runtime_settings.mirrorchyan_cdk()
    if not cdk:
        log.warning("MirrorChyan 引擎包更新：未配置 CDK")
        return None

    settings = get_settings()
    local = _read_local_version()
    current_version = str(local.get("tag") or "")
    # MirrorChyan 的 os/arch 与 GitHub 资产平台命名不同：
    #   win-x64        → os=win, arch=x64
    #   win-arm64      → os=win, arch=arm64
    #   linux-x86_64   → os=linux, arch=x86_64
    #   linux-aarch64  → os=linux, arch=aarch64
    platform = settings.maa_resource_platform
    os_name = "win" if platform.startswith("win") else "linux"
    arch = platform.split("-", 1)[1] if "-" in platform else platform
    url = (
        f"{_MIRRORCHYAN_APP_API}?current_version={current_version}"
        f"&cdk={cdk}&user_agent={_UA}&os={os_name}"
        f"&arch={arch}"
        f"&channel=Stable&sp_id={runtime_settings.mirrorchyan_sp_id()}"
    )
    try:
        async with httpx.AsyncClient(
            timeout=settings.maa_resource_api_timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - network/binding surface
        log.warning("MirrorChyan 引擎包更新查询失败: %s", exc)
        return None

    code = int(data.get("code") or 0)
    if code != 0:
        log.warning(
            "MirrorChyan 引擎包更新被拒 code=%s msg=%s",
            code, data.get("msg") or _MIRRORCHYAN_ERRORS.get(code, "未知错误"),
        )
        return None

    d = data.get("data") or {}
    version_name = str(d.get("version_name") or "")
    download_url = str(d.get("url") or "")
    # 已是最新：version_name 与本地一致（服务端无 url 或同版本均属此情形）
    if version_name and version_name == current_version:
        return {"tag": current_version, "asset": "", "url": "", "urls": [], "size": 0, "up_to_date": True}
    if not download_url:
        log.warning("MirrorChyan 引擎包未返回下载地址")
        return None
    tag = version_name or "latest"
    # 缓存文件名取 URL 末尾（含 .zip/.tar.gz），避免 tag 为日期/任意格式
    asset = Path(unquote(urlparse(download_url).path)).name or f"MAA-{tag}-{settings.maa_resource_platform}.zip"
    return {
        "tag": tag,
        "asset": asset,
        "url": download_url,
        "urls": [download_url],
        "size": int(d.get("filesize") or 0),  # 部分响应带 filesize；缺失时 _download 用 content-length
        "update_type": str(d.get("update_type") or "full"),  # incremental | full（OTA 增量包）
    }


# ── 后台更新流程 ───────────────────────────────────────────

def update_state() -> dict:
    """只读拷贝当前更新任务状态。"""
    return dict(_UPDATE)


async def update() -> dict:
    """触发后台更新（幂等：已有任务进行中则直接返回当前状态）。

    按更新源分发（对齐 MAA 客户端 UpdateSource）：
        github      → GitHub release 资产（支持镜像前缀）
        mirrorchyan → Mirror酱高速更新源（MAA 引擎包）
    """
    async with _update_lock:
        if _UPDATE["running"]:
            return dict(_UPDATE)

        source = runtime_settings.update_source()
        if source == "mirrorchyan":
            remote = await remote_latest_mirrorchyan()
            if remote is None:
                # 写入 _UPDATE 供 /resources/status 轮询可见（否则前端误显示「已更新」）
                _UPDATE.update(
                    stage="error",
                    error="Mirror酱引擎包查询失败（未配置 CDK / CDK 无效 / 网络不可达），"
                          "请检查设置页更新源与 CDK 有效性",
                )
                return dict(_UPDATE)
            if remote.get("up_to_date"):
                return {**dict(_UPDATE), "stage": "idle", "error": None}
        else:
            remote = await remote_latest()
            if remote is None:
                _UPDATE.update(
                    stage="error",
                    error="无法获取官方最新版本（网络不可达或资产缺失），请检查 MAAWEB_RESOURCE_MIRROR",
                )
                return dict(_UPDATE)
        _UPDATE.update(
            running=True,
            progress=0.0,
            stage="fetch",
            error=None,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        asyncio.create_task(_download(remote))
        return dict(_UPDATE)


def _extract_archive(tmp_zip: Path, tmp_dir: Path, kind: str) -> None:
    """解压 zip / tar.gz 到 tmp_dir。

    tar 安全解压：3.12+ 用 `filter="data"`；3.11 用 `tarfile.data_filter`；
    3.10 无内置过滤，退回普通解压（仅处理受信发布包）。
    """
    if kind == "tgz":
        with tarfile.open(tmp_zip, "r:gz") as tf:
            try:
                tf.extractall(tmp_dir, filter="data")
            except TypeError:  # Python < 3.12 不支持 filter 关键字
                if hasattr(tarfile, "data_filter"):
                    tf.extractall(tmp_dir, filter=tarfile.data_filter)
                else:
                    tf.extractall(tmp_dir)
    else:
        with zipfile.ZipFile(tmp_zip) as zf:
            zf.extractall(tmp_dir)


def _locate_package_root(tmp_dir: Path) -> Path:
    """定位包根目录：含 `resource/` 的那一层（win zip 平铺 / linux tar 带根目录）。"""
    if (tmp_dir / "resource").is_dir():
        return tmp_dir
    for sub in sorted(tmp_dir.iterdir()):
        if sub.is_dir() and (sub / "resource").is_dir():
            return sub
    raise RuntimeError(f"解压后未找到 resource/ 目录（{tmp_dir.name}）")


def _validate(root: Path) -> int:
    """校验包完整性，返回 pipeline JSON 数；异常抛出明确原因。"""
    if not (root / "resource").is_dir():
        raise RuntimeError(f"解压后未找到 resource/ 目录（{root}）")
    if not (root / asstproxy.engine_lib_name()).exists():
        raise RuntimeError(
            f"解压后未找到引擎库 {asstproxy.engine_lib_name()}（请检查 MAAWEB_RESOURCE_PLATFORM 是否匹配系统架构）"
        )
    pipelines = list((root / "resource").rglob("*.json"))
    if not pipelines:
        raise RuntimeError("解压后未找到任务 JSON，资源包无效")
    return len(pipelines)


def _sync_tree(src: Path, dst: Path) -> None:
    """逐文件同步 src → dst，跳过被占用（Windows 引擎 DLL 已加载）的文件。"""
    for f in src.rglob("*"):
        rel = f.relative_to(src)
        d = dst / rel
        if f.is_dir():
            d.mkdir(parents=True, exist_ok=True)
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(f, d)
            except OSError:
                log.warning("跳过被占用的文件：%s", d)
    # 清理 dst 中 src 已不存在的文件（占用文件跳过）
    for f in dst.rglob("*"):
        rel = f.relative_to(dst)
        if not (src / rel).exists():
            try:
                if f.is_dir():
                    shutil.rmtree(f)
                else:
                    f.unlink()
            except OSError:
                pass


def _apply_incremental(tmp_zip: Path, target: Path) -> None:
    """应用 Mirror酱 OTA 增量包：覆盖目标目录（对齐 MAA 客户端增量更新）。

    增量包为 zip，条目为相对安装根目录的路径；若含 `changes.json`，
    其 `deleted` 数组列出需要删除的文件/目录。target 须已存在。
    """
    with zipfile.ZipFile(tmp_zip) as zf:
        if "changes.json" in zf.namelist():
            changes = json.loads(zf.read("changes.json"))
            for rel in changes.get("deleted", []):
                p = target / rel
                try:
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink(missing_ok=True)
                except OSError:
                    log.warning("增量删除失败，跳过：%s", rel)
        for name in zf.namelist():
            if name.endswith("/") or name == "changes.json":
                continue
            # 防御路径穿越（增量包由 MAA 官方维护，但仍校验一次）
            out = (target / name).resolve()
            if not str(out).startswith(str(target.resolve())):
                log.warning("增量包包含越界路径，跳过：%s", name)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zf.open(name) as src, out.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            except OSError:
                log.warning("增量覆盖失败（可能被占用），跳过：%s", name)


def _safe_fs_name(name: str) -> str:
    """目录/文件名安全化：替换 Windows/Unix 非法字符与空白。"""
    return re.sub(r'[\\/:*?"<>|\s]+', "-", name).strip(".-")


def _swap(tmp_root: Path, target: Path, backup: Path) -> None:
    """原子替换：先 rename 到备份再切入新目录；Windows 占用时退化为逐文件同步。"""
    if not target.exists():
        tmp_root.rename(target)
        return
    if backup.exists():
        shutil.rmtree(backup)
    try:
        target.rename(backup)
        tmp_root.rename(target)
        shutil.rmtree(backup)
    except OSError:
        log.warning("引擎包目录被占用（引擎可能已加载），退化为逐文件同步")
        _sync_tree(tmp_root, target)
        shutil.rmtree(tmp_root, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


async def _download(remote: dict) -> None:
    """下载 → 解压 → 定位根目录 → 校验 → 原子替换。异常写入 _UPDATE.error。

    兼容两种远端：
        GitHub 源   — remote 含 {tag, asset, urls, size}，包名按 tag 推导；
        MirrorChyan — remote 含 {tag, url, urls, size, update_type}，包名取
                      URL 末尾，归档类型按 URL 后缀判断；`update_type=incremental`
                      时对已安装目录做增量覆盖（changes.json deleted + 覆盖），
                      否则整包解压替换；size 缺失时进度取响应头 content-length。
    """
    settings = get_settings()
    cache = settings.cache_dir
    target = settings.maa_resource_dir
    urls = remote.get("urls") or ([remote["url"]] if remote.get("url") else [])
    if not urls:
        _UPDATE.update(stage="error", error="无可用的下载地址")
        return
    first_url = urls[0]
    if remote.get("asset"):
        asset, kind = remote["asset"], ("tgz" if str(first_url).endswith(".tar.gz") else "zip")
    else:
        asset, kind = asset_name(remote["tag"])
    tmp_zip = cache / asset
    # MirrorChyan 版本名形如 "2026-08-14 08:00:00.000"（含空格冒号），不能直接作目录名
    safe_tag = _safe_fs_name(remote["tag"])
    tmp_dir = cache / f"maa-{safe_tag}.tmp"
    backup = cache / f"maa-bak-{safe_tag}"

    try:
        # 1) 流式下载（候选 URL 逐个尝试，失败自动切换下一源）
        _UPDATE["stage"] = "download"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=30.0,
                read=settings.maa_resource_download_timeout,
                write=30.0,
                pool=30.0,
            ),
            headers={"User-Agent": _UA},
            follow_redirects=True,
        ) as client:
            total = remote.get("size") or 0
            downloaded = 0
            last_err: Exception | None = None
            for url in urls:
                tmp_zip.unlink(missing_ok=True)  # 清理上一源的半成品
                try:
                    async with client.stream("GET", url) as resp:
                        resp.raise_for_status()
                        # MirrorChyan 等源无 size → 用 content-length 计算进度
                        if not total:
                            total = int(resp.headers.get("content-length") or 0) or 0
                        with tmp_zip.open("wb") as f:
                            async for chunk in resp.aiter_bytes(1024 * 256):
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total:
                                    _UPDATE["progress"] = min(downloaded / total, 1.0)
                    break  # 下载成功
                except Exception as exc:  # noqa: BLE001 - try next candidate
                    last_err = exc
                    log.warning("下载失败，切换下一源: %s (%s)", url, exc)
            else:
                raise RuntimeError(f"所有下载源均失败: {last_err}")

        # 2) 应用更新：增量覆盖（Mirror酱 OTA）或整包解压替换
        _UPDATE["stage"] = "extract"
        if remote.get("update_type") == "incremental" and target.exists():
            await asyncio.to_thread(_apply_incremental, tmp_zip, target)
            pipeline_count = len(list((target / "resource").rglob("*.json")))
        else:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            tmp_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(_extract_archive, tmp_zip, tmp_dir, kind)
            package_root = await asyncio.to_thread(_locate_package_root, tmp_dir)
            pipeline_count = await asyncio.to_thread(_validate, package_root)

            # 3) 原子替换
            _UPDATE["stage"] = "swap"
            await asyncio.to_thread(_swap, package_root, target, backup)
        (target / _VERSION_FILE).write_text(
            json.dumps(
                {
                    "tag": remote["tag"],
                    "platform": settings.maa_resource_platform,
                    "source": "MirrorChyan" if runtime_settings.update_source() == "mirrorchyan" else "MaaAssistantArknights release",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        # 提示引擎重载（版本变化时 AsstLoadResource 会在下次使用时自动执行）
        asstproxy.release()
        tmp_zip.unlink(missing_ok=True)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

        log.info("MAA 引擎包更新至 %s（%d pipelines）", remote["tag"], pipeline_count)
        _UPDATE.update(progress=1.0, stage="done", error=None)
    except Exception as exc:  # noqa: BLE001 - keep state consistent
        log.exception("engine pack update failed")
        _UPDATE["error"] = str(exc)
        _UPDATE["stage"] = "error"
    finally:
        _UPDATE["running"] = False


async def status() -> dict:
    """合并本地状态 + 远端版本 + 更新任务状态。"""
    local = local_state()
    if runtime_settings.update_source() == "mirrorchyan":
        remote = await remote_latest_mirrorchyan()
    else:
        remote = await remote_latest()
    upd = dict(_UPDATE)
    dyn = dynamic_state()
    return {
        **local,
        "updating": upd["running"],
        "progress": upd["progress"],
        "stage": upd["stage"],
        "update_error": upd["error"],
        "remote_latest": remote["tag"] if remote else None,
        "remote_url": remote["url"] if remote else None,
        "remote_size": remote["size"] if remote else 0,
        "update_available": bool(
            remote and local.get("local_version") and remote["tag"] != local["local_version"]
        ),
        "source_hint": "未安装" if not local["installed"] else local.get("source", ""),
        # 动态资源（MaaResource 增量同步）
        "dynamic_syncing": dyn["running"],
        "dynamic_stage": dyn["stage"],
        "dynamic_error": dyn["error"],
        "dynamic_synced_at": dyn.get("synced_at"),
        "dynamic_commit": dyn.get("commit"),
        "dynamic_pending": dyn.get("pending", 0),
        "dynamic_done": dyn.get("done", 0),
        "dynamic_mode": dyn.get("mode", ""),
        "dynamic_version": dyn.get("version", ""),  # MirrorChyan 源版本名
        "update_source": runtime_settings.update_source(),  # github | mirrorchyan
    }


# ── 动态资源同步（MaaResource 增量更新） ─────────────────────
#
# MaaResource（https://github.com/MaaAssistantArknights/MaaResource）是 MAA 官方
# 动态资源仓库：活动地图格子数据（Arknights-Tile-Pos/）、活动模板（template/）、
# 关卡/公招/基建数据 JSON。它随活动热更新，且与发布包内 resource/ 路径同构，
# 可增量合并进引擎包，避免整包（~267MB）重下。
#
# 同步模型：
#   · 文件清单   — GitHub git tree API（path → blob sha），缓存 120s
#   · 差异对比   — 本地 manifest（.maaweb_dynamic.json）记录 path → sha
#   · 增量模式   — 差异文件 ≤ 阈值：按文件从 raw.githubusercontent 并发下载
#   · 全量模式   — 无 manifest 或差异过大：一次 codeload tarball 下载解压合并
#   · 完成后     — asstproxy.release() 提示引擎下次使用时重载资源

_DYNAMIC_REPO = "MaaAssistantArknights/MaaResource"
_DYNAMIC_TREE_URL = (
    f"https://api.github.com/repos/{_DYNAMIC_REPO}/git/trees/main?recursive=1"
)
_DYNAMIC_RAW = f"https://raw.githubusercontent.com/{_DYNAMIC_REPO}/main"
_DYNAMIC_TARBALL = f"https://codeload.github.com/{_DYNAMIC_REPO}/tar.gz/refs/heads/main"
_MANIFEST_FILE = ".maaweb_dynamic.json"
_FULL_THRESHOLD = 1200  # 差异文件超过该数量 → 走全量 tarball
_DL_CONCURRENCY = 8

_DYNAMIC: dict = {
    "running": False,
    "stage": "idle",  # idle | diff | download | merge | done | error
    "progress": 0.0,
    "error": None,
    "started_at": None,
    "mode": "",  # diff | full
    "pending": 0,
    "done": 0,
}
_dynamic_lock = asyncio.Lock()
_dynamic_cache: dict = {"at": 0.0, "commit": "", "files": None}


def _manifest_path() -> Path:
    return get_settings().maa_resource_dir / _MANIFEST_FILE


def _read_manifest() -> dict:
    try:
        return json.loads(_manifest_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_manifest(commit: str, files: dict[str, str]) -> None:
    data = {
        "commit": commit,
        "files": files,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    _manifest_path().write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def dynamic_state() -> dict:
    """只读动态同步任务状态（合并到 /resources/status）。"""
    d = dict(_DYNAMIC)
    m = _read_manifest()
    d["synced_at"] = m.get("synced_at")
    d["commit"] = m.get("commit")
    d["version"] = m.get("version", "")  # MirrorChyan 源版本名
    d["source"] = m.get("source", "")
    return d


async def _fetch_dynamic_tree() -> tuple[str, dict[str, str]] | None:
    """拉取 MaaResource main 分支 resource/ 文件清单（path → blob sha）。"""
    now = asyncio.get_event_loop().time()
    if _dynamic_cache["files"] is not None and now - _dynamic_cache["at"] < 120:
        return _dynamic_cache["commit"], _dynamic_cache["files"]

    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            timeout=settings.maa_resource_api_timeout,
            headers={"User-Agent": _UA, "Accept": "application/vnd.github+json"},
            follow_redirects=True,
        ) as client:
            tree = await _get_first_json(client, await pick_fastest_urls(_DYNAMIC_TREE_URL, client))
    except Exception as exc:  # noqa: BLE001 - network/binding surface
        log.warning("dynamic resource tree lookup failed: %s", exc)
        return None
    if tree is None:
        log.warning("dynamic resource tree lookup failed: all sources unreachable")
        return None

    files: dict[str, str] = {}
    for item in tree.get("tree", []):
        if item.get("type") != "blob":
            continue
        p = item.get("path", "")
        if p.startswith("resource/"):
            files[p[len("resource/"):]] = str(item.get("sha", ""))
    commit = str(tree.get("sha", ""))
    _dynamic_cache.update(at=now, commit=commit, files=files)
    return commit, files


def _plan_diff(
    tree: dict[str, str], manifest: dict
) -> tuple[str, list[str], list[str]]:
    """对比 tree 与 manifest → (mode, to_download, to_delete)。mode: diff | full。"""
    mfiles = manifest.get("files", {})
    to_download = sorted(rel for rel, sha in tree.items() if mfiles.get(rel) != sha)
    to_delete = sorted(rel for rel in mfiles if rel not in tree)
    if not mfiles or len(to_download) > _FULL_THRESHOLD:
        return "full", [], []
    return "diff", to_download, to_delete


async def _pick_fastest_base(
    bases: list[str], probe_rel: str, client: httpx.AsyncClient
) -> list[str]:
    """对 base 候选用代表文件并发 HEAD 测速 → 可达按延迟升序、不可达按原序。"""
    lats = await asyncio.gather(*(_probe(client, f"{b}/{probe_rel}") for b in bases))
    ok = [(lat, b) for lat, b in zip(lats, bases, strict=True) if lat is not None]
    ok.sort(key=lambda x: x[0])  # 稳定排序：同延迟保持候选原序
    fail = [b for lat, b in zip(lats, bases, strict=True) if lat is None]
    return [b for _, b in ok] + fail


async def _apply_diff(
    res_dir: Path, to_download: list[str], to_delete: list[str], tree: dict[str, str]
) -> None:
    """增量模式：并发下载差异文件 → 删除已移除文件 → 清理空目录。

    raw 文件走镜像候选（base 测速择优，单文件失败自动切换下一 base）。
    """
    settings = get_settings()
    sem = asyncio.Semaphore(_DL_CONCURRENCY)
    timeout = httpx.Timeout(
        connect=15.0, read=settings.maa_resource_download_timeout, write=15.0, pool=15.0
    )
    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": _UA}, follow_redirects=True
    ) as client:
        bases = _candidate_urls(_DYNAMIC_RAW)
        if to_download:
            bases = await _pick_fastest_base(bases, to_download[0], client)

        async def one(rel: str) -> None:
            content: bytes | None = None
            for base in bases:
                try:
                    resp = await client.get(f"{base}/{rel}")
                    resp.raise_for_status()
                    content = resp.content
                    break
                except Exception:  # noqa: BLE001 - try next base
                    continue
            if content is None:
                raise RuntimeError(f"差异文件下载失败（所有源）: {rel}")
            async with sem:
                dest = res_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                _DYNAMIC["done"] += 1

        await asyncio.gather(*(one(r) for r in to_download))

    for rel in to_delete:
        try:
            (res_dir / rel).unlink()
        except OSError:
            log.warning("动态资源删除失败（文件占用）: %s", rel)
    # 清理合并产生的空目录
    for d in sorted((p for p in res_dir.rglob("*") if p.is_dir()), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    log.info("dynamic diff applied: +%d files, -%d files", len(to_download), len(to_delete))


async def _apply_full(res_dir: Path, old_manifest: dict) -> None:
    """全量模式：下载 MaaResource tarball → 解压 → 合并（同名覆盖 + 新增）。"""
    settings = get_settings()
    cache = settings.cache_dir
    tmp_zip = cache / "maa-resource-dynamic.tar.gz"
    tmp_dir = cache / "maa-resource-dynamic.tmp"

    try:
        _DYNAMIC["stage"] = "download"
        timeout = httpx.Timeout(
            connect=30.0,
            read=settings.maa_resource_download_timeout,
            write=30.0,
            pool=30.0,
        )
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            last_err: Exception | None = None
            for url in await pick_fastest_urls(_DYNAMIC_TARBALL, client):
                tmp_zip.unlink(missing_ok=True)  # 清理上一源的半成品
                try:
                    async with client.stream("GET", url) as resp:
                        resp.raise_for_status()
                        with tmp_zip.open("wb") as f:
                            async for chunk in resp.aiter_bytes(256 * 1024):
                                f.write(chunk)
                    break  # 下载成功
                except Exception as exc:  # noqa: BLE001 - try next candidate
                    last_err = exc
                    log.warning("动态资源全量包下载失败，切换下一源: %s (%s)", url, exc)
            else:
                raise RuntimeError(f"动态资源全量包所有下载源均失败: {last_err}")

        _DYNAMIC["stage"] = "merge"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(_extract_archive, tmp_zip, tmp_dir, "tgz")
        root = await asyncio.to_thread(_locate_package_root, tmp_dir)
        src = root / "resource"
        if not src.is_dir():
            raise RuntimeError("动态资源包缺少 resource/ 目录")

        # 合并：同名覆盖 + 新增（不删除引擎包自身的其他资源）
        for f in src.rglob("*"):
            rel = f.relative_to(src)
            d = res_dir / rel
            if f.is_dir():
                d.mkdir(parents=True, exist_ok=True)
            else:
                d.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(f, d)
                except OSError:
                    log.warning("动态资源合并跳过占用文件: %s", d)

        # 旧 manifest 中已被 MaaResource 移除的文件 → 清理
        for rel in old_manifest.get("files", {}):
            if not (src / rel).exists():
                (res_dir / rel).unlink(missing_ok=True)
        tmp_zip.unlink(missing_ok=True)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        log.info("dynamic full merge done (resource files=%d)", len(old_manifest.get("files", {})))
    except Exception:
        tmp_zip.unlink(missing_ok=True)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        raise


async def _sync_worker(commit: str, files: dict[str, str], manifest: dict) -> None:
    settings = get_settings()
    res_dir = settings.maa_resource_dir / "resource"
    try:
        if not res_dir.is_dir():
            raise RuntimeError("引擎包未安装，请先下载引擎包再同步动态资源")
        mode, to_download, to_delete = _plan_diff(files, manifest)
        _DYNAMIC.update(stage="download", mode=mode, pending=len(to_download), done=0)
        if mode == "full":
            await _apply_full(res_dir, manifest)
            new_files = dict(files)
        else:
            await _apply_diff(res_dir, to_download, to_delete, files)
            new_files = dict(files)
        _write_manifest(commit, new_files)
        asstproxy.release()  # 提示引擎下次使用时重载资源
        _DYNAMIC.update(stage="done", progress=1.0, error=None)
        log.info("动态资源同步完成 commit=%s mode=%s", commit, mode)
    except Exception as exc:  # noqa: BLE001 - keep state consistent
        log.exception("dynamic resource sync failed")
        _DYNAMIC["error"] = str(exc)
        _DYNAMIC["stage"] = "error"
    finally:
        _DYNAMIC["running"] = False


async def sync_dynamic() -> dict:
    """触发动态资源同步（幂等：已有任务进行中则直接返回当前状态）。

    按更新源分发（对齐 MAA 客户端 UpdateSource）：
        github      → MaaResource 仓库增量 diff（现有流程）
        mirrorchyan → Mirror酱高速更新源（CDK 增量包）
    """
    async with _dynamic_lock:
        if _DYNAMIC["running"]:
            return dict(_DYNAMIC)

        source = runtime_settings.update_source()
        if source == "mirrorchyan":
            return await _sync_dynamic_mirrorchyan()
        return await _sync_dynamic_github()


async def _sync_dynamic_github() -> dict:
    """GitHub 更新源：tree diff 增量同步（原流程）。"""
    tree = await _fetch_dynamic_tree()
    if tree is None:
        return {
            **dict(_DYNAMIC),
            "error": "无法获取动态资源清单（MaaResource 仓库不可达）",
        }
    commit, files = tree
    manifest = _read_manifest()
    mode, to_download, to_delete = _plan_diff(files, manifest)
    if manifest.get("commit") == commit and not to_download and not to_delete:
        return {**dict(_DYNAMIC), "stage": "idle", "error": None, "pending": 0}

    _DYNAMIC.update(
        running=True,
        stage="diff" if mode == "diff" else "download",
        progress=0.0,
        error=None,
        started_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        pending=len(to_download),
        done=0,
    )
    asyncio.create_task(_sync_worker(commit, files, manifest))
    return dict(_DYNAMIC)


def _resource_version_name() -> str:
    """本地 resource/version.json 的 last_updated（MirrorChyan current_version）。

    缺失/损坏时返回空串（API 视为初始版本，直接返回最新包）。
    """
    try:
        data = json.loads(
            (get_settings().maa_resource_dir / "resource" / "version.json").read_text(
                encoding="utf-8"
            )
        )
        return str(data.get("last_updated", "") or "").strip()
    except (OSError, ValueError):
        return ""


async def _sync_dynamic_mirrorchyan() -> dict:
    """MirrorChyan 更新源：调 API 检查 → 有新版下载增量包 → 合并。"""
    cdk = runtime_settings.mirrorchyan_cdk()
    if not cdk:
        return {
            **dict(_DYNAMIC),
            "error": "未配置 Mirror酱 CDK（设置页 → 镜像下载源 → Mirror酱）",
        }

    settings = get_settings()
    res_dir = settings.maa_resource_dir / "resource"
    if not res_dir.is_dir():
        return {**dict(_DYNAMIC), "error": "引擎包未安装，请先下载引擎包再同步动态资源"}

    current_version = _resource_version_name()
    url = (
        f"{_MIRRORCHYAN_API}?current_version={current_version}"
        f"&cdk={cdk}&sp_id={runtime_settings.mirrorchyan_sp_id()}"
        f"&user_agent={_UA}"
    )
    try:
        async with httpx.AsyncClient(
            timeout=settings.maa_resource_api_timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - network surface
        log.warning("MirrorChyan 更新检查失败: %s", exc)
        return {
            **dict(_DYNAMIC),
            "error": f"无法连接 Mirror酱服务（{exc}）",
        }

    code = int(data.get("code") or 0)
    if code != 0:
        msg = _MIRRORCHYAN_ERRORS.get(code) or str(data.get("msg") or "Mirror酱请求失败")
        return {**dict(_DYNAMIC), "error": msg}

    d = data.get("data") or {}
    version_name = str(d.get("version_name") or "")
    download_url = str(d.get("url") or "")
    if not download_url:
        return {**dict(_DYNAMIC), "error": "Mirror酱未返回增量包地址"}

    _DYNAMIC.update(
        running=True,
        stage="download",
        progress=0.0,
        error=None,
        started_at=datetime.now(timezone.utc).isoformat(),
        mode="mirrorchyan",
        pending=1,
        done=0,
    )
    asyncio.create_task(
        _mirrorchyan_worker(download_url, version_name, current_version, res_dir)
    )
    return dict(_DYNAMIC)


async def _mirrorchyan_worker(
    download_url: str, version_name: str, current_version: str, res_dir: Path
) -> None:
    """下载 MirrorChyan 增量包 → 解压 → 合并 → 更新 manifest。"""
    settings = get_settings()
    cache = settings.cache_dir
    tmp_zip = cache / "maa-resource-mirrorchyan.zip"
    tmp_dir = cache / "maa-resource-mirrorchyan.tmp"

    def _cleanup() -> None:
        tmp_zip.unlink(missing_ok=True)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    try:
        # 1) 流式下载增量包
        timeout = httpx.Timeout(
            connect=30.0,
            read=settings.maa_resource_download_timeout,
            write=30.0,
            pool=30.0,
        )
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            async with client.stream("GET", download_url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length") or 0) or 0
                downloaded = 0
                with tmp_zip.open("wb") as f:
                    async for chunk in resp.aiter_bytes(256 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            _DYNAMIC["progress"] = min(downloaded / total, 1.0)

        # 2) 解压 + 合并（同名覆盖 + 新增，不删除引擎包自身资源）
        _DYNAMIC["stage"] = "merge"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(_extract_archive, tmp_zip, tmp_dir, "zip")
        root = await asyncio.to_thread(_locate_package_root, tmp_dir)
        src = root / "resource"
        if not src.is_dir():
            raise RuntimeError("Mirror酱增量包缺少 resource/ 目录")
        for f in src.rglob("*"):
            rel = f.relative_to(src)
            d = res_dir / rel
            if f.is_dir():
                d.mkdir(parents=True, exist_ok=True)
            else:
                d.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(f, d)
                except OSError:
                    log.warning("Mirror酱合并跳过占用文件: %s", d)

        # 3) 更新 manifest（记录版本名与更新时间）
        manifest = _read_manifest()
        manifest.update(
            commit=manifest.get("commit", ""),  # 保留 github 源记录
            version=version_name,
            source="mirrorchyan",
            synced_at=datetime.now(timezone.utc).isoformat(),
        )
        _manifest_path().write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        asstproxy.release()
        _DYNAMIC.update(stage="done", progress=1.0, error=None)
        log.info(
            "Mirror酱动态资源更新完成 version=%s (was %s)",
            version_name or "?",
            current_version or "初始",
        )
    except Exception as exc:  # noqa: BLE001 - keep state consistent
        log.exception("Mirror酱动态资源更新失败")
        _DYNAMIC["error"] = str(exc)
        _DYNAMIC["stage"] = "error"
    finally:
        _cleanup()
        _DYNAMIC["running"] = False
