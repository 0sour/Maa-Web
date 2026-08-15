"""Task queue API tests (S-01) — routes, validation, serialization.

The TaskRunner is stubbed (deterministic) — the runner's own state machine is
unit-tested in test_taskrunner.py. Covers R13/R14 at the HTTP layer.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.engine.asstproxy import EngineCreateError
from app.engine.taskrunner import IDLE, TaskQueueError
from app.schemas.task import TaskStatusRead


class StubRunner:
    """Deterministic TaskRunner double for HTTP-layer tests."""

    def __init__(self) -> None:
        self.state = IDLE
        self.status = IDLE  # API reads runner.status after stop()
        self.run_id = None
        self.engine_fail = False

    async def start(self, device, tasks):
        if device.status != "online":
            raise TaskQueueError(f"设备 {device.name} 未连接（状态 {device.status}）")
        if self.engine_fail:
            raise EngineCreateError("MAA 引擎连接设备失败（测试）")
        return SimpleNamespace(id=7, status="running")

    async def stop(self) -> None:
        self.state = "stopping"
        self.status = "stopping"

    def snapshot(self, device_online: bool, engine_available: bool) -> TaskStatusRead:
        return TaskStatusRead(
            device_id=1,
            status=self.state,
            device_online=device_online,
            engine_available=engine_available,
        )


@pytest.fixture
def stub_runner(monkeypatch):
    runner = StubRunner()
    monkeypatch.setattr(
        "app.engine.taskrunner.TaskRunner.get", staticmethod(lambda device_id: runner)
    )
    return runner


async def _create_device(client, status: str = "online") -> int:
    payload = {
        "name": "MuMu12",
        "adb_host": "192.168.1.10",
        "adb_port": 16384,
        "touch_mode": "Minitouch",
        "client_type": "Official",
    }
    resp = await client.post("/api/v1/devices", json=payload)
    assert resp.status_code == 201, resp.text
    device_id = resp.json()["id"]
    # DeviceUpdate has no status field — flip it directly in the DB.
    from app.db.session import get_sessionmaker
    from app.models.device import Device

    async with get_sessionmaker()() as s:
        dev = await s.get(Device, device_id)
        dev.status = status
        await s.commit()
    return device_id


async def test_run_online_device(client, stub_runner) -> None:
    """POST /tasks/{id}/run on an online device → 200 + run result."""
    device_id = await _create_device(client, status="online")
    resp = await client.post(
        f"/api/v1/tasks/{device_id}/run",
        json={"tasks": [{"name": "刷理智", "entry": "Fight", "type": "刷理智", "params": {"stage": "CE-6"}}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == 7
    assert body["status"] == "running"
    assert body["message"]


async def test_run_offline_device_conflict(client, stub_runner) -> None:
    """R13: device not online → 409 (not 500)."""
    device_id = await _create_device(client, status="offline")
    resp = await client.post(
        f"/api/v1/tasks/{device_id}/run",
        json={"tasks": [{"name": "刷理智", "entry": "Fight", "type": "刷理智", "params": {}}]},
    )
    assert resp.status_code == 409
    assert "未连接" in resp.json()["detail"]


async def test_run_validation(client, stub_runner) -> None:
    """Empty / malformed queue → 422."""
    device_id = await _create_device(client, status="online")
    assert (await client.post(f"/api/v1/tasks/{device_id}/run", json={"tasks": []})).status_code == 422
    assert (await client.post(f"/api/v1/tasks/{device_id}/run", json={"tasks": "nope"})).status_code == 422


async def test_run_engine_connect_failure_502(client, stub_runner) -> None:
    """POST /tasks/{id}/run when engine connect fails → 502 + readable detail."""
    device_id = await _create_device(client, status="online")
    stub_runner.engine_fail = True
    resp = await client.post(
        f"/api/v1/tasks/{device_id}/run",
        json={"tasks": [{"name": "StartUp", "entry": "StartUp", "type": "x", "params": {}}]},
    )
    assert resp.status_code == 502
    assert "MAA 引擎连接设备失败" in resp.json()["detail"]


async def test_stop(client, stub_runner) -> None:
    device_id = await _create_device(client)
    resp = await client.post(f"/api/v1/tasks/{device_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopping"


async def test_status(client, stub_runner) -> None:
    device_id = await _create_device(client)
    resp = await client.get(f"/api/v1/tasks/{device_id}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_id"] == device_id
    assert body["status"] == IDLE
    assert body["device_online"] is True


async def test_missing_device_404(client, stub_runner) -> None:
    assert (await client.post("/api/v1/tasks/9999/run", json={"tasks": [{"name": "x", "entry": "Fight", "type": "x", "params": {}}]})).status_code == 404
    assert (await client.post("/api/v1/tasks/9999/stop")).status_code == 404
    assert (await client.get("/api/v1/tasks/9999/status")).status_code == 404


async def test_run_logs_history(client, stub_runner) -> None:
    """GET /tasks/runs/{run_id}/logs returns persisted lines (empty for none)."""
    resp = await client.get("/api/v1/tasks/runs/1/logs")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_logs_by_day_groups(client) -> None:
    """历史日志按天分组：仅今天之前的 N 天（本地时区），天内时间正序。"""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    from app.db.session import get_sessionmaker
    from app.models.task import LogEntry

    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as s:
        s.add(LogEntry(run_id=1, device_id=1, level="info", message="较早", ts=now - timedelta(seconds=5)))
        s.add(LogEntry(run_id=1, device_id=1, level="ok", message="较晚", ts=now))
        old = LogEntry(run_id=1, device_id=1, level="info", message="昨天的日志")
        s.add(old)
        await s.flush()
        await s.execute(update(LogEntry).where(LogEntry.id == old.id).values(ts=now - timedelta(days=1)))
        await s.commit()

    # 今天的日志不进历史（由 /logs/today 提供）；历史只含今天之前的天
    resp = await client.get("/api/v1/tasks/logs", params={"days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["days"]) >= 1  # 至少昨天
    yesterday = body["days"][0]  # 倒序：最新日期在前
    assert yesterday["date"] == (now - timedelta(days=1)).astimezone().strftime("%Y-%m-%d")
    assert yesterday["count"] == 1
    assert [e["message"] for e in yesterday["entries"]] == ["昨天的日志"]
    assert all(e["ts"].endswith(("Z", "+00:00")) for e in yesterday["entries"])
    # device_id 过滤
    resp2 = await client.get("/api/v1/tasks/logs", params={"days": 7, "device_id": 999})
    assert resp2.json()["days"] == []


async def test_logs_today(client) -> None:
    """GET /tasks/logs/today：当天日志（本地时区），时间正序，不含过去天。"""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    from app.db.session import get_sessionmaker
    from app.models.task import LogEntry

    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as s:
        first = LogEntry(run_id=1, device_id=1, level="info", message="今天较早", ts=now - timedelta(seconds=5))
        s.add(first)
        second = LogEntry(run_id=1, device_id=1, level="ok", message="今天较晚", ts=now)
        s.add(second)
        old = LogEntry(run_id=1, device_id=1, level="info", message="过去的")
        s.add(old)
        await s.flush()
        await s.execute(update(LogEntry).where(LogEntry.id == old.id).values(ts=now - timedelta(days=1)))
        await s.commit()

    resp = await client.get("/api/v1/tasks/logs/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == datetime.now().astimezone().strftime("%Y-%m-%d")
    assert body["count"] == 2
    assert [e["message"] for e in body["entries"]] == ["今天较早", "今天较晚"]  # 时间正序
    assert all(e["id"] > 0 and e["ts"].endswith(("Z", "+00:00")) for e in body["entries"])
    # device_id 过滤
    resp2 = await client.get("/api/v1/tasks/logs/today", params={"device_id": 999})
    assert resp2.json()["count"] == 0 and resp2.json()["entries"] == []


async def test_logs_source_filter(client) -> None:
    """日志来源过滤：normal / auto（含 manual_auto），今天与历史一致。"""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    from app.db.session import get_sessionmaker
    from app.models.task import LogEntry

    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as s:
        s.add(LogEntry(run_id=1, device_id=1, source="normal", level="info",
                       message="普通任务日志", ts=now - timedelta(seconds=3)))
        s.add(LogEntry(run_id=0, device_id=1, source="auto", level="info",
                       message="自动任务日志", ts=now - timedelta(seconds=2)))
        s.add(LogEntry(run_id=0, device_id=1, source="manual_auto", level="info",
                       message="手动运行日志", ts=now - timedelta(seconds=1)))
        old = LogEntry(run_id=0, device_id=1, source="auto", level="info",
                       message="昨天的自动日志")
        s.add(old)
        await s.flush()
        await s.execute(update(LogEntry).where(LogEntry.id == old.id).values(ts=now - timedelta(days=1)))
        await s.commit()

    # 今天：source=auto 含 manual_auto；行带 source 字段
    resp = await client.get("/api/v1/tasks/logs/today", params={"source": "auto"})
    assert resp.status_code == 200
    body = resp.json()
    assert [e["message"] for e in body["entries"]] == ["自动任务日志", "手动运行日志"]
    assert all(e["source"] in ("auto", "manual_auto") for e in body["entries"])
    resp = await client.get("/api/v1/tasks/logs/today", params={"source": "normal"})
    assert [e["message"] for e in resp.json()["entries"]] == ["普通任务日志"]
    resp = await client.get("/api/v1/tasks/logs/today", params={"source": "all"})
    assert resp.json()["count"] == 3

    # 历史：source=auto 只含昨天的自动日志
    resp = await client.get("/api/v1/tasks/logs", params={"days": 7, "source": "auto"})
    days = resp.json()["days"]
    assert days and days[0]["date"] == (now - timedelta(days=1)).astimezone().strftime("%Y-%m-%d")
    assert [e["message"] for e in days[0]["entries"]] == ["昨天的自动日志"]
    resp = await client.get("/api/v1/tasks/logs", params={"days": 7, "source": "normal"})
    msgs = [e["message"] for d in resp.json()["days"] for e in d["entries"]]
    assert "昨天的自动日志" not in msgs
