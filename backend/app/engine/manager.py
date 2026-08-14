"""Engine connection manager (M2).

Orchestrates the real device connect/disconnect flow and maps every outcome to
the Device status machine:  offline → online | error.

Flow (connect):
    resolve adb → `adb connect`  →  engine session (MAA Asst, optional)
    adb missing / connect failed  → status=error + human-readable reason
    adb ok                        → status=online (+last_online_at)

Flow (disconnect):
    close engine session → `adb disconnect` → offline (idempotent, never fails hard)

Keep this layer DB-agnostic: it only computes (status, message); the router
persists to the Device row.
"""
from __future__ import annotations

import logging

from app.engine import adb, asstproxy
from app.models.device import Device

log = logging.getLogger(__name__)


async def connect_device(device: Device) -> tuple[str, str]:
    """Real ADB handshake + optional MAA Asst session. Returns (status, message)."""
    if device.status == "online":
        return "online", "设备已在线"

    # 1) ADB transport — the source of truth for reachability.
    try:
        ok, msg = await adb.connect(device.adb_host, device.adb_port)
    except adb.AdbUnavailableError as exc:
        return "error", str(exc)
    if not ok:
        return "error", f"ADB 连接失败: {msg}"

    # 2) Engine session — optional; a missing engine degrades, not blocks.
    if asstproxy.is_available():
        try:
            await asstproxy.create_session(device, adb.resolve_adb_path())
        except (asstproxy.EngineUnavailableError, asstproxy.EngineCreateError) as exc:
            log.warning("device=%s engine session failed: %s", device.id, exc)
            return "online", f"ADB 已连接；引擎降级: {exc}"
    return "online", "ADB 连接成功"


async def disconnect_device(device: Device) -> tuple[str, str]:
    """Close engine session then adb disconnect. Idempotent → offline."""
    if device.status == "offline":
        return "offline", "设备已离线"

    asstproxy.close_session(device.id)
    try:
        await adb.disconnect(device.adb_host, device.adb_port)
    except adb.AdbUnavailableError:
        pass  # nothing to tear down at the binary level
    return "offline", "已断开连接"


def release_device(device_id: int) -> None:
    """Drop any live engine session for a device (used on device delete)."""
    asstproxy.close_session(device_id)


async def engine_status() -> dict:
    """Environment summary for the devices page header (engine chip)."""
    try:
        adb_path = adb.resolve_adb_path()
    except adb.AdbUnavailableError:
        adb_path = ""
    return {
        "adb_available": bool(adb_path),
        "adb_path": adb_path,
        "adb_version": await adb.adb_version() if adb_path else None,
        "engine_available": asstproxy.is_available(),
        "engine_version": asstproxy.engine_version(),
        "active_sessions": asstproxy.session_count(),
    }
