"""Engine manager (connect/disconnect state machine) unit tests.

The manager is DB-agnostic: it maps adb/asstproxy outcomes to (status, message).
All engine calls are monkeypatched → deterministic, no real adb/MaaFw needed.
"""
from __future__ import annotations

from app.engine import asstproxy, manager
from app.engine.adb import AdbUnavailableError
from app.models.device import Device


def _device(status: str = "offline") -> Device:
    return Device(
        id=7, name="t", adb_host="127.0.0.1", adb_port=16384,
        touch_mode="Minitouch", client_type="Official", status=status,
    )


# ── connect ─────────────────────────────────────────────────────────────

async def test_connect_success_no_engine(monkeypatch) -> None:
    async def ok_connect(host, port): return (True, "connected to 127.0.0.1:16384")
    monkeypatch.setattr(manager.adb, "connect", ok_connect)
    monkeypatch.setattr(manager.asstproxy, "is_available", lambda: False)
    status, msg = await manager.connect_device(_device())
    assert status == "online"
    assert "ADB 连接成功" in msg


async def test_connect_success_with_engine_session(monkeypatch) -> None:
    calls: list[int] = []

    async def ok_connect(host, port):
        return (True, "connected")

    async def create_session(device, adb_path):
        calls.append(device.id)
        return object()
    monkeypatch.setattr(manager.adb, "connect", ok_connect)
    monkeypatch.setattr(manager.adb, "resolve_adb_path", lambda: "/usr/bin/adb")
    monkeypatch.setattr(manager.asstproxy, "is_available", lambda: True)
    monkeypatch.setattr(manager.asstproxy, "create_session", create_session)

    status, msg = await manager.connect_device(_device())
    assert status == "online"
    assert calls == [7]
    assert "ADB 连接成功" in msg


async def test_connect_already_online_short_circuit(monkeypatch) -> None:
    async def boom(host, port): raise AssertionError("must not call adb")
    monkeypatch.setattr(manager.adb, "connect", boom)
    status, msg = await manager.connect_device(_device(status="online"))
    assert status == "online"
    assert "已在线" in msg


async def test_connect_adb_refused(monkeypatch) -> None:
    async def refused(host, port): return (False, "cannot connect to 127.0.0.1:16384: Connection refused")
    monkeypatch.setattr(manager.adb, "connect", refused)
    status, msg = await manager.connect_device(_device())
    assert status == "error"
    assert "Connection refused" in msg


async def test_connect_adb_missing(monkeypatch) -> None:
    async def boom(host, port): raise AdbUnavailableError("未找到 adb 可执行文件")
    monkeypatch.setattr(manager.adb, "connect", boom)
    status, msg = await manager.connect_device(_device())
    assert status == "error"
    assert "adb" in msg.lower()


async def test_connect_engine_failure_degrades_online(monkeypatch) -> None:
    async def ok_connect(host, port): return (True, "connected")
    async def boom_session(device, adb_path): raise asstproxy.EngineCreateError("MaaFw 会话创建失败: x")
    monkeypatch.setattr(manager.adb, "connect", ok_connect)
    monkeypatch.setattr(manager.adb, "resolve_adb_path", lambda: "/usr/bin/adb")
    monkeypatch.setattr(manager.asstproxy, "is_available", lambda: True)
    monkeypatch.setattr(manager.asstproxy, "create_session", boom_session)

    status, msg = await manager.connect_device(_device())
    # ADB works → device online; engine issue is surfaced as degradation, not failure.
    assert status == "online"
    assert "降级" in msg


# ── disconnect ──────────────────────────────────────────────────────────

async def test_disconnect_closes_session_and_adb(monkeypatch) -> None:
    closed: list[int] = []

    async def ok_disconnect(host, port): return "disconnected"
    monkeypatch.setattr(manager.asstproxy, "close_session", lambda did: closed.append(did))
    monkeypatch.setattr(manager.adb, "disconnect", ok_disconnect)

    status, msg = await manager.disconnect_device(_device(status="online"))
    assert status == "offline"
    assert closed == [7]


async def test_disconnect_idempotent_when_offline(monkeypatch) -> None:
    async def boom(host, port): raise AssertionError("must not call adb")
    monkeypatch.setattr(manager.adb, "disconnect", boom)
    status, msg = await manager.disconnect_device(_device(status="offline"))
    assert status == "offline"
    assert "已离线" in msg


async def test_disconnect_without_adb_still_offline(monkeypatch) -> None:
    async def boom(host, port): raise AdbUnavailableError("未找到 adb")
    monkeypatch.setattr(manager.adb, "disconnect", boom)
    status, _ = await manager.disconnect_device(_device(status="online"))
    assert status == "offline"


# ── engine_status ───────────────────────────────────────────────────────

async def test_engine_status_full(monkeypatch) -> None:
    monkeypatch.setattr(manager.adb, "resolve_adb_path", lambda: "C:/adb.exe")
    monkeypatch.setattr(manager.adb, "adb_version", _fake_version)
    monkeypatch.setattr(manager.asstproxy, "is_available", lambda: True)
    monkeypatch.setattr(manager.asstproxy, "engine_version", lambda: "5.12.3")
    monkeypatch.setattr(manager.asstproxy, "session_count", lambda: 2)

    info = await manager.engine_status()
    assert info["adb_available"] is True
    assert info["adb_path"] == "C:/adb.exe"
    assert info["adb_version"] == "Android Debug Bridge version 1.0.41"
    assert info["engine_available"] is True
    assert info["engine_version"] == "5.12.3"
    assert info["active_sessions"] == 2


async def test_engine_status_adb_missing(monkeypatch) -> None:
    monkeypatch.setattr(manager.adb, "resolve_adb_path", lambda: (_ for _ in ()).throw(AdbUnavailableError("未找到 adb")))
    info = await manager.engine_status()
    assert info["adb_available"] is False
    assert info["adb_path"] == ""
    assert info["adb_version"] is None


async def _fake_version() -> str:
    return "Android Debug Bridge version 1.0.41"
