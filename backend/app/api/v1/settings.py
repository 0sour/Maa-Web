"""Settings API (M3/M6) — mirror download sources & generic setting groups.

Routes:
    GET  /settings/mirror          读取镜像源配置（含 CDK 有效期诊断）
    PUT  /settings/mirror          保存镜像源配置（运行时热更新，无需重启）
    POST /settings/mirror/check    检查 MirrorChyan CDK 有效期
    GET  /settings                 读取全部设置（按分组前缀 game/connection/ui）
    PUT  /settings/{group}         保存一组设置（SQLite Setting 表）
    GET  /settings/logs-export     打包日志目录为 zip 下载（问题反馈）
    GET  /settings/geoip           IP 定位（NAS 出口 IP → 经纬度/城市，主题「按日出日落」用）

持久化：镜像源写入 `data/config/runtime_settings.json`（运行时立即生效，
覆盖 .env 默认值）；通用设置分组写入 SQLite `settings` 表（key 前缀分组）。
"""
from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import runtime_settings
from app.core.config import get_settings
from app.db.session import get_session
from app.engine import resource_mgr
from app.models.setting import Setting
from app.schemas.settings import (
    SETTING_GROUPS,
    MirrorCdkCheckPayload,
    MirrorCdkCheckResult,
    MirrorSourceSettings,
    MirrorSourceUpdate,
    SettingsGroupsRead,
    SettingsGroupUpdate,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def _mask_cdk(cdk: str) -> str:
    """CDK 脱敏：保留前 4 与后 4 位，中间用 * 代替。"""
    if not cdk:
        return ""
    if len(cdk) <= 8:
        return "*" * len(cdk)
    return f"{cdk[:4]}{'*' * (len(cdk) - 8)}{cdk[-4:]}"


def _cdk_diagnostic(expired_time: int) -> tuple[float | None, str]:
    """根据已保存的有效期计算剩余天数与展示文案。"""
    if expired_time <= 0:
        return None, ""
    remaining = (expired_time - datetime.now(timezone.utc).timestamp()) / 86400
    if remaining <= 0:
        return None, "Mirror酱 CDK 已过期，请续费或更换"
    return remaining, f"Mirror酱 CDK 有效，剩余 {remaining:.1f} 天"


@router.get("/mirror", response_model=MirrorSourceSettings)
async def read_mirror_settings() -> MirrorSourceSettings:
    """读取镜像源配置：更新源 + ghproxy 前缀 + MirrorChyan CDK 状态（脱敏）。"""
    rt = runtime_settings.load()
    cdk = runtime_settings.mirrorchyan_cdk()
    expired_time = int(rt.get("mirrorchyan_cdk_expired_time") or 0)
    remaining, message = _cdk_diagnostic(expired_time)
    return MirrorSourceSettings(
        update_source=runtime_settings.update_source(),
        mirror_prefixes=(
            str(rt.get("maa_resource_mirror", ""))
            if rt.get("_configured")
            else ""
        ),
        mirror_prefix_list=runtime_settings.mirror_prefixes(),
        effective_prefix_list=resource_mgr._mirror_prefixes(),
        mirrorchyan_cdk_masked=_mask_cdk(cdk),
        mirrorchyan_cdk=cdk,  # 单用户 NAS：设置页回显完整 CDK（前端默认以掩码输入框展示）
        mirrorchyan_cdk_configured=bool(cdk),
        mirrorchyan_cdk_expired_time=expired_time,
        mirrorchyan_cdk_remaining_days=remaining,
        mirrorchyan_cdk_message=message,
        http_proxy=runtime_settings.http_proxy(),
    )


@router.put("/mirror", response_model=MirrorSourceSettings)
async def update_mirror_settings(payload: MirrorSourceUpdate) -> MirrorSourceSettings:
    """保存镜像源配置（热更新，立即生效）。"""
    kw: dict = {}
    if payload.update_source is not None:
        if payload.update_source not in ("github", "mirrorchyan"):
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="update_source 仅支持 github / mirrorchyan",
            )
        kw["update_source"] = payload.update_source
    if payload.mirror_prefixes is not None:
        kw["maa_resource_mirror"] = payload.mirror_prefixes.strip()
    if payload.mirrorchyan_cdk is not None:
        new_cdk = payload.mirrorchyan_cdk.strip()
        old_cdk = runtime_settings.mirrorchyan_cdk()
        kw["mirrorchyan_cdk"] = new_cdk
        if not new_cdk or new_cdk != old_cdk:
            # CDK 被清空或确实变更 → 清除旧有效期，下次 check 重新获取。
            # 未变更（如前端回显后原样保存）则保留既有有效期。
            kw["mirrorchyan_cdk_expired_time"] = 0
    if payload.http_proxy is not None:
        kw["http_proxy"] = payload.http_proxy.strip()
    if kw:
        runtime_settings.update(**kw)
    return await read_mirror_settings()


@router.post("/mirror/check", response_model=MirrorCdkCheckResult)
async def check_mirror_cdk(payload: MirrorCdkCheckPayload) -> MirrorCdkCheckResult:
    """检查 MirrorChyan CDK 有效期（对齐 MAA 客户端 cdk_expired_time 机制）。"""
    result = await resource_mgr.check_mirrorchyan_cdk(payload.cdk)
    return MirrorCdkCheckResult(**result)


# ── 通用设置分组（S-04/§4.4 设置中心） ─────────────────────

async def _load_setting_values(session: AsyncSession) -> dict[str, object]:
    """读全部 Setting 行 → {key: 反序列化 value}。"""
    rows = (await session.execute(select(Setting))).scalars().all()
    out: dict[str, object] = {}
    for row in rows:
        try:
            out[row.key] = json.loads(row.value)
        except (ValueError, TypeError):
            out[row.key] = row.value
    return out


@router.get("", response_model=SettingsGroupsRead)
async def read_all_settings(
    session: AsyncSession = Depends(get_session),
) -> SettingsGroupsRead:
    """读取全部设置，按分组前缀组织（key 去掉 `{group}.` 前缀）。"""
    all_values = await _load_setting_values(session)
    groups: dict[str, dict[str, object]] = {g: {} for g in SETTING_GROUPS}
    for key, value in all_values.items():
        group, _, rest = key.partition(".")
        if group in groups and rest:
            groups[group][rest] = value
    return SettingsGroupsRead(**groups)


@router.put("/{group}", response_model=SettingsGroupsRead)
async def save_settings_group(
    group: str,
    payload: SettingsGroupUpdate,
    session: AsyncSession = Depends(get_session),
) -> SettingsGroupsRead:
    """保存一组设置（`{group}.{key}` 前缀，逐键 upsert；删除键传 None）。"""
    if group not in SETTING_GROUPS:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"设置分组仅支持 {'/'.join(SETTING_GROUPS)}",
        )
    for key, value in payload.values.items():
        if not key or not isinstance(key, str) or "." in key:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"无效的设置键：{key!r}",
            )
        full = f"{group}.{key}"
        row = await session.get(Setting, full)
        if value is None:
            if row is not None:
                await session.delete(row)
            continue
        if row is None:
            session.add(Setting(key=full, value=json.dumps(value, ensure_ascii=False)))
        else:
            row.value = json.dumps(value, ensure_ascii=False)
    await session.commit()
    return await read_all_settings(session)


@router.get("/logs-export")
async def export_logs() -> StreamingResponse:
    """打包日志目录为 zip 下载（问题反馈「导出日志」）。

    日志目录缺失/为空时仍返回 zip（仅含说明文件），不报错。
    """
    log_dir = get_settings().log_dir
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if log_dir.is_dir():
            for f in sorted(log_dir.rglob("*")):
                if f.is_file():
                    try:
                        zf.write(f, f.relative_to(log_dir.parent).as_posix())
                    except OSError:
                        log.warning("日志打包跳过占用文件: %s", f)
        if not zf.namelist():
            zf.writestr("README.txt", "日志目录为空（data/logs）\n")
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="maaweb-logs-{stamp}.zip"'},
    )


@router.get("/geoip")
async def geoip() -> dict:
    """IP 定位（ip-api.com 免费版，按 NAS 出口 IP → 当地经纬度/城市）。

    浏览器 geolocation 需要 HTTPS/localhost——NAS 走 http://192.168.x.x 访问时
    不可用，此接口兜底；「主题=自动 → 按当地日出日落」填入经纬度用。
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "http://ip-api.com/json/",
                params={"fields": "status,message,lat,lon,city,country"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - 定位是锦上添花，失败给明确错误
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"定位服务不可用：{exc}",
        ) from exc
    if data.get("status") != "success":
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"定位失败：{data.get('message', '未知原因')}",
        )
    return {
        "lat": data["lat"],
        "lon": data["lon"],
        "city": str(data.get("city", "")),
        "country": str(data.get("country", "")),
    }


class ProxyTestPayload(BaseModel):
    """HTTP 代理连通性测试请求体。"""

    proxy: str = ""


@router.post("/proxy-test")
async def proxy_test(payload: ProxyTestPayload) -> dict:
    """测试 HTTP 代理连通性：经代理访问 GitHub API（轻量请求），返回耗时或错误。

    供设置页「更新设置 → HTTP 代理 → 测试连通性」按钮使用。
    """
    proxy = payload.proxy.strip()
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            proxy=proxy or None,
            headers={"User-Agent": "Maa-Web/0.1"},
        ) as client:
            resp = await client.get("https://api.github.com/rate_limit")
            resp.raise_for_status()
        return {
            "ok": True,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - 测试失败返回错误信息
        return {
            "ok": False,
            "latency_ms": None,
            "error": str(exc)[:200] or "连接失败",
        }
