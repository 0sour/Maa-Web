"""Device CRUD + lifecycle tests — cover risk R4 (regression) + C-01 contract.

Device lifecycle tested end-to-end through the ASGI app (SQLite in temp dir):
    create → list → get → connect → disconnect → update → delete → 404.

The connect/disconnect paths delegate to app.engine.manager; those calls are
monkeypatched with deterministic stubs here (the real adb binary is never a
test dependency). The manager itself is unit-tested separately (test_manager.py)
and the endpoint's failure path is covered by test_connect_without_adb.
"""
from __future__ import annotations

import pytest

from app.engine import adb, asstproxy
from app.engine.adb import AdbUnavailableError


async def _create_device(client, **overrides) -> dict:
    payload = {
        "name": "MuMu12",
        "adb_host": "192.168.1.10",
        "adb_port": 16384,
        "touch_mode": "Minitouch",
        "client_type": "Official",
        **overrides,
    }
    resp = await client.post("/api/v1/devices", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def fake_engine(monkeypatch):
    """Deterministic connect/disconnect stubs (adb is NOT a test dependency)."""

    async def fake_connect(device) -> tuple[str, str]:
        return ("online", "ADB 连接成功")

    async def fake_disconnect(device) -> tuple[str, str]:
        return ("offline", "已断开连接")

    monkeypatch.setattr("app.engine.manager.connect_device", fake_connect)
    monkeypatch.setattr("app.engine.manager.disconnect_device", fake_disconnect)


async def test_device_crud_full_lifecycle(client, fake_engine) -> None:
    """R4/C-01: create→list→get→connect→disconnect→update→delete→404."""
    # create
    created = await _create_device(client)
    device_id = created["id"]
    assert created["status"] == "offline"
    assert created["adb_port"] == 16384
    assert created["last_error"] is None

    # list contains it
    lst = await client.get("/api/v1/devices")
    assert lst.status_code == 200
    ids = [d["id"] for d in lst.json()]
    assert device_id in ids

    # get
    got = await client.get(f"/api/v1/devices/{device_id}")
    assert got.status_code == 200
    assert got.json()["name"] == "MuMu12"

    # connect → result wrapper: device online + last_online_at set + message
    conn = await client.post(f"/api/v1/devices/{device_id}/connect")
    assert conn.status_code == 200
    body = conn.json()
    assert body["device"]["status"] == "online"
    assert body["device"]["last_online_at"] is not None
    assert body["device"]["last_error"] is None
    assert body["message"] == "ADB 连接成功"

    # idempotent connect
    conn2 = await client.post(f"/api/v1/devices/{device_id}/connect")
    assert conn2.json()["device"]["status"] == "online"

    # disconnect → offline
    disc = await client.post(f"/api/v1/devices/{device_id}/disconnect")
    assert disc.status_code == 200
    assert disc.json()["device"]["status"] == "offline"

    # update (partial)
    upd = await client.put(
        f"/api/v1/devices/{device_id}", json={"name": "MuMu12-NAS", "adb_port": 5555}
    )
    assert upd.status_code == 200
    body = upd.json()
    assert body["name"] == "MuMu12-NAS"
    assert body["adb_port"] == 5555
    assert body["adb_host"] == "192.168.1.10"  # untouched field preserved

    # delete → 204 then 404
    dele = await client.delete(f"/api/v1/devices/{device_id}")
    assert dele.status_code == 204
    gone = await client.get(f"/api/v1/devices/{device_id}")
    assert gone.status_code == 404


async def test_connect_without_adb_reports_error(client, monkeypatch) -> None:
    """R9: adb binary missing → status=error + persisted last_error (no 500)."""
    monkeypatch.setattr(
        "app.engine.manager.adb.resolve_adb_path",
        lambda: (_ for _ in ()).throw(AdbUnavailableError("未找到 adb 可执行文件")),
    )
    created = await _create_device(client, adb_host="10.0.0.99")
    resp = await client.post(f"/api/v1/devices/{created['id']}/connect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["device"]["status"] == "error"
    assert "adb" in body["device"]["last_error"].lower()
    assert body["device"]["last_online_at"] is None


async def test_detect_no_adb(client, monkeypatch) -> None:
    """Detect reports adb_available=False + fix hint when binary missing."""
    monkeypatch.setattr(adb, "resolve_adb_path", lambda: (_ for _ in ()).throw(AdbUnavailableError("未找到 adb")))
    resp = await client.post("/api/v1/devices/detect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["adb_available"] is False
    assert body["devices"] == []
    assert body["reason"]


async def test_detect_returns_devices(client, monkeypatch) -> None:
    """Detect surfaces `adb devices -l` output as structured entries."""
    monkeypatch.setattr(adb, "resolve_adb_path", lambda: "C:/adb.exe")
    monkeypatch.setattr(adb, "adb_version", _fake_version)
    monkeypatch.setattr(adb, "scan_devices", _fake_scan)
    monkeypatch.setattr(asstproxy, "is_available", lambda: False)
    monkeypatch.setattr(asstproxy, "engine_version", lambda: "unavailable")
    resp = await client.post("/api/v1/devices/detect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["adb_available"] is True
    assert body["adb_version"] == "Android Debug Bridge version 1.0.41"
    assert len(body["devices"]) == 2
    first = body["devices"][0]
    assert first["serial"] == "127.0.0.1:16384"
    assert first["state"] == "device"
    assert first["model"] == "MuMu12"
    assert (first["host"], first["port"]) == ("127.0.0.1", 16384)
    # Engine (MaaFw) info is surfaced for the env chip (absent in tests → unavailable).
    assert body["engine_available"] is False
    assert body["engine_version"] == "unavailable"


async def _fake_version() -> str:
    return "Android Debug Bridge version 1.0.41"


async def _fake_scan() -> list:
    return [
        adb.AdbDeviceInfo(serial="127.0.0.1:16384", state="device", model="MuMu12", host="127.0.0.1", port=16384),
        adb.AdbDeviceInfo(serial="emulator-5554", state="offline", model="", host="127.0.0.1", port=5555),
    ]


async def test_create_device_validation(client) -> None:
    """C-01: invalid payloads rejected with 422 (not 500)."""
    cases = [
        {"name": "", "adb_host": "1.2.3.4"},                    # blank name
        {"name": "x", "adb_host": "   "},                       # blank host
        {"name": "x", "adb_host": "1.2.3.4", "adb_port": 70000},  # port overflow
        {"name": "x", "adb_host": "1.2.3.4", "touch_mode": "Bogus"},  # bad enum
    ]
    for payload in cases:
        resp = await client.post("/api/v1/devices", json=payload)
        assert resp.status_code == 422, f"expected 422 for {payload}, got {resp.status_code}"


async def test_device_not_found(client) -> None:
    """C-01: get/update/delete/connect on missing id → 404."""
    assert (await client.get("/api/v1/devices/9999")).status_code == 404
    assert (await client.put("/api/v1/devices/9999", json={"name": "z"})).status_code == 404
    assert (await client.delete("/api/v1/devices/9999")).status_code == 404
    assert (await client.post("/api/v1/devices/9999/connect")).status_code == 404
    assert (await client.post("/api/v1/devices/9999/disconnect")).status_code == 404


async def test_devices_isolated_between_tests(client) -> None:
    """R8/flake: each test starts with an empty device table (temp DB isolation)."""
    lst = await client.get("/api/v1/devices")
    assert lst.status_code == 200
    assert lst.json() == []


async def test_create_duplicate_device_conflict(client) -> None:
    """相同设备（host+port，含 USB port=0）重复添加 → 409 + 人话 detail。"""
    await _create_device(client)
    resp = await client.post(
        "/api/v1/devices",
        json={
            "name": "另一个名字",
            "adb_host": "192.168.1.10",
            "adb_port": 16384,
            "touch_mode": "Minitouch",
            "client_type": "Official",
        },
    )
    assert resp.status_code == 409
    assert "相同设备已存在" in resp.json()["detail"]
    assert "MuMu12" in resp.json()["detail"]

    # USB 设备（port=0，serial 相同）同样拦截
    await _create_device(client, name="USB设备", adb_host="9b65ff77", adb_port=0)
    resp = await client.post(
        "/api/v1/devices",
        json={"name": "USB重复", "adb_host": "9b65ff77", "adb_port": 0},
    )
    assert resp.status_code == 409
    assert "USB设备" in resp.json()["detail"]

    # 不同端口 → 允许
    resp = await client.post(
        "/api/v1/devices",
        json={"name": "同IP不同端口", "adb_host": "192.168.1.10", "adb_port": 5555},
    )
    assert resp.status_code == 201



async def _force_online(client, device_id: int) -> None:
    """绕过 API 直接置 online（status 由 connect 端点管理，不允许 PUT 修改）。"""
    from app.db.session import get_sessionmaker
    from app.models.device import Device as DeviceModel

    async with get_sessionmaker()() as s:
        dev = await s.get(DeviceModel, device_id)
        assert dev is not None
        dev.status = "online"
        await s.commit()


async def test_list_devices_probe_downgrades_stale_online(client, monkeypatch) -> None:
    """列表探活：已不在 adb devices 中的 online 设备被降级为 offline。"""
    from app.engine import adb

    created = await _create_device(client, name="USB设备", adb_host="9b65ff77", adb_port=0)
    # 置为 online（模拟之前连接成功）
    await _force_online(client, created["id"])

    # 真实扫描：设备不在列表 → GET /devices 后降级 offline
    async def scan_without_device():
        return [adb.AdbDeviceInfo(serial="other-device", state="device")]

    monkeypatch.setattr(adb, "scan_devices", scan_without_device)
    resp = await client.get("/api/v1/devices")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "offline"
    assert "已断开" in body[0]["last_error"]

    # TCP 设备：serial 为 host:port，同样校验
    tcp = await _create_device(client, name="TCP设备", adb_host="192.168.1.10", adb_port=5555)
    await _force_online(client, tcp["id"])
    await client.get("/api/v1/devices")
    body = (await client.get("/api/v1/devices")).json()
    assert [d["status"] for d in body] == ["offline", "offline"]


async def test_list_devices_probe_keeps_online_when_present(client, monkeypatch) -> None:
    """探活：设备仍在 adb 列表中 → 保持 online，不误降级。"""
    from app.engine import adb

    created = await _create_device(client, name="USB设备", adb_host="9b65ff77", adb_port=0)
    await _force_online(client, created["id"])

    async def scan_with_device():
        return [adb.AdbDeviceInfo(serial="9b65ff77", state="device")]

    monkeypatch.setattr(adb, "scan_devices", scan_with_device)
    body = (await client.get("/api/v1/devices")).json()
    assert body[0]["status"] == "online"


async def test_list_devices_probe_scan_failure_keeps_state(client, monkeypatch) -> None:
    """探活失败（adb 缺失/命令错误）→ 保持既有状态，不阻塞列表。"""
    from app.engine import adb
    from app.engine.adb import AdbUnavailableError

    created = await _create_device(client, name="USB设备", adb_host="9b65ff77", adb_port=0)
    await _force_online(client, created["id"])

    async def scan_fail():
        raise AdbUnavailableError("no adb")

    monkeypatch.setattr(adb, "scan_devices", scan_fail)
    body = (await client.get("/api/v1/devices")).json()
    assert body[0]["status"] == "online"
