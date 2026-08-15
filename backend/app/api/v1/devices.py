"""Device management API (C-01) — now wired to the real engine (M2).

Routes:
    GET    /devices                  list
    POST   /devices                  create
    POST   /devices/detect           scan `adb devices -l` (real ADB)
    GET    /devices/{id}             detail
    PUT    /devices/{id}             partial update
    DELETE /devices/{id}             delete
    POST   /devices/{id}/connect     real ADB connect (+optional MaaFw session)
    POST   /devices/{id}/disconnect  real ADB disconnect

Status machine: offline → connecting → online | error (docs/testing.md R4/R9).
connect/disconnect delegate to app.engine.manager and persist the outcome
(status + last_error + last_online_at) to the Device row.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.engine import adb, asstproxy, manager
from app.models.device import Device
from app.schemas.device import (
    DetectedDevice,
    DeviceConnectResult,
    DeviceCreate,
    DeviceDetectResult,
    DeviceRead,
    DeviceResolutionResult,
    DeviceUpdate,
    ResolutionSetPayload,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


async def _get_device_or_404(session: AsyncSession, device_id: int) -> Device:
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"device {device_id} not found",
        )
    return device


# ── Scan (declared before /{device_id} routes: no path collision, keeps order sane) ──

@router.post("/detect", response_model=DeviceDetectResult)
async def detect_devices() -> DeviceDetectResult:
    """Run `adb devices -l` and report reachable emulators/devices.

    adb_available=False → reason explains how to fix (install platform-tools /
    set MAAWEB_ADB_PATH). Never raises: scan failures are reported in-band.
    """
    try:
        found = await adb.scan_devices()
        version = await adb.adb_version()
        path = adb.resolve_adb_path()
    except adb.AdbUnavailableError as exc:
        return DeviceDetectResult(
            adb_available=False,
            reason=str(exc),
            engine_available=asstproxy.is_available(),
            engine_version=asstproxy.engine_version(),
        )
    except adb.AdbCommandError as exc:
        # adb 失败不影响引擎状态：必须带 engine 字段，否则前端 KPI 误判「引擎降级」
        return DeviceDetectResult(
            adb_available=True,
            adb_path=adb.resolve_adb_path(),
            reason=f"adb 扫描失败: {exc}",
            engine_available=asstproxy.is_available(),
            engine_version=asstproxy.engine_version(),
        )
    devices = [
        DetectedDevice(
            serial=d.serial, state=d.state, model=d.model, host=d.host, port=d.port
        )
        for d in found
        # offline = adb 记录的「已知但不可达」端点（曾尝试连接/通信失败），
        # 无法添加/连接，对用户无价值 → 过滤；unauthorized 保留（提示手机授权）
        if d.state != "offline"
    ]
    return DeviceDetectResult(
        adb_available=True,
        adb_path=path,
        adb_version=version,
        devices=devices,
        engine_available=asstproxy.is_available(),
        engine_version=asstproxy.engine_version(),
    )


# ── CRUD ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[DeviceRead])
async def list_devices(session: AsyncSession = Depends(get_session)) -> list[Device]:
    # 探活降级：扫描真实 adb devices，把「已不在线」的 online 设备置为 offline
    # （状态是连接时刻的快照，拔线/断开后需要真实扫描修正；只降不升，避免误判）。
    # adb 缺失/扫描失败时跳过（保持既有状态，不阻塞列表）。
    try:
        found = await adb.scan_devices()
    except (adb.AdbUnavailableError, adb.AdbCommandError):
        found = None
    if found is not None:
        online_serials = {d.serial for d in found}
        rows = (await session.execute(select(Device).where(Device.status == "online"))).scalars().all()
        for dev in rows:
            # USB/本地设备 serial 即 adb_host；TCP 设备在 adb 中的 serial 为 host:port
            expected = dev.adb_host if dev.adb_port <= 0 else f"{dev.adb_host}:{dev.adb_port}"
            if expected not in online_serials:
                dev.status = "offline"
                dev.last_error = "设备已断开（不在 adb devices 列表中）"
        if rows:
            await session.commit()
    result = await session.execute(select(Device).order_by(Device.id))
    return list(result.scalars().all())


@router.post("", response_model=DeviceRead, status_code=http_status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate, session: AsyncSession = Depends(get_session)
) -> Device:
    # 相同设备（host + port）不可重复添加：USB 设备按 serial（port=0）识别
    dup = await session.scalar(
        select(Device).where(
            Device.adb_host == payload.adb_host,
            Device.adb_port == payload.adb_port,
        )
    )
    if dup is not None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                f"相同设备已存在（{payload.adb_host}"
                f"{'' if payload.adb_port <= 0 else ':' + str(payload.adb_port)}），"
                f"即「{dup.name}」，请勿重复添加"
            ),
        )
    device = Device(**payload.model_dump())
    session.add(device)
    await session.commit()
    await session.refresh(device)
    log.info("device created id=%s host=%s:%s", device.id, device.adb_host, device.adb_port)
    return device


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: int, session: AsyncSession = Depends(get_session)
) -> Device:
    return await _get_device_or_404(session, device_id)


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
) -> Device:
    device = await _get_device_or_404(session, device_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    await session.commit()
    await session.refresh(device)
    log.info("device updated id=%s", device.id)
    return device


@router.delete("/{device_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    device = await _get_device_or_404(session, device_id)
    # Release any live engine session before dropping the row.
    manager.release_device(device_id)
    await session.delete(device)
    await session.commit()
    log.info("device deleted id=%s", device_id)


# ── Connection control (real engine) ────────────────────────────────────

@router.post("/{device_id}/connect", response_model=DeviceConnectResult)
async def connect_device(
    device_id: int, session: AsyncSession = Depends(get_session)
) -> DeviceConnectResult:
    device = await _get_device_or_404(session, device_id)
    status, message = await manager.connect_device(device)
    device.status = status
    device.last_error = None if status == "online" else message
    if status == "online":
        device.last_online_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(device)
    log.info("device connect id=%s → %s (%s)", device.id, status, message)
    return DeviceConnectResult(device=DeviceRead.model_validate(device), message=message)


@router.post("/{device_id}/disconnect", response_model=DeviceConnectResult)
async def disconnect_device(
    device_id: int, session: AsyncSession = Depends(get_session)
) -> DeviceConnectResult:
    device = await _get_device_or_404(session, device_id)
    status, message = await manager.disconnect_device(device)
    device.status = status
    device.last_error = None
    await session.commit()
    await session.refresh(device)
    log.info("device disconnect id=%s → %s", device.id, status)
    return DeviceConnectResult(device=DeviceRead.model_validate(device), message=message)


# ── 分辨率调整（MAA 需要 16:9 固定分辨率；真机临时调整后需复位） ─────────

def _resolution_errors(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=http_status.HTTP_400_BAD_REQUEST,
        detail=f"分辨率操作失败: {exc}",
    )


@router.get("/{device_id}/resolution", response_model=DeviceResolutionResult)
async def get_device_resolution(
    device_id: int, session: AsyncSession = Depends(get_session)
) -> DeviceResolutionResult:
    device = await _get_device_or_404(session, device_id)
    try:
        size = await adb.get_resolution(device.adb_host, device.adb_port)
    except (adb.AdbUnavailableError, adb.AdbCommandError) as exc:
        raise _resolution_errors(exc) from exc
    return DeviceResolutionResult(
        device_id=device.id,
        width=size[0] if size else None,
        height=size[1] if size else None,
        message=f"当前分辨率 {size[0]}x{size[1]}" if size else "无法获取分辨率",
    )


@router.post("/{device_id}/resolution", response_model=DeviceResolutionResult)
async def set_device_resolution(
    device_id: int,
    payload: ResolutionSetPayload,
    session: AsyncSession = Depends(get_session),
) -> DeviceResolutionResult:
    device = await _get_device_or_404(session, device_id)
    try:
        msg = await adb.set_resolution(device.adb_host, device.adb_port, payload.width, payload.height)
    except (adb.AdbUnavailableError, adb.AdbCommandError) as exc:
        raise _resolution_errors(exc) from exc
    return DeviceResolutionResult(
        device_id=device.id, width=payload.width, height=payload.height, message=msg
    )


@router.post("/{device_id}/resolution/reset", response_model=DeviceResolutionResult)
async def reset_device_resolution(
    device_id: int, session: AsyncSession = Depends(get_session)
) -> DeviceResolutionResult:
    device = await _get_device_or_404(session, device_id)
    try:
        msg = await adb.reset_resolution(device.adb_host, device.adb_port)
    except (adb.AdbUnavailableError, adb.AdbCommandError) as exc:
        raise _resolution_errors(exc) from exc
    return DeviceResolutionResult(device_id=device.id, message=msg)
