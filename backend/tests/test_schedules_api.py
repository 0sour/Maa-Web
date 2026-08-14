"""Schedule jobs API (M6) — CRUD + 立即试跑（POST /schedules/{id}/run）。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.engine.taskrunner import TaskQueueError


class StubRunner:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.offline_ok = True

    async def start(self, device, tasks):
        self.calls.append((device.id, [t.name for t in tasks]))
        if device.status != "online":
            raise TaskQueueError(f"设备 {device.name} 未连接（状态 {device.status}）")
        return SimpleNamespace(id=99, status="running")


@pytest.fixture
def stub_runner(monkeypatch):
    runner = StubRunner()
    monkeypatch.setattr(
        "app.engine.taskrunner.TaskRunner.get", staticmethod(lambda device_id: runner)
    )
    return runner


def _scheme_payload(device_id: int, **kw) -> dict:
    payload = {
        "device_id": device_id,
        "name": "每日长草",
        "enabled": True,
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "time": "06:30",
        "plan_name": "日常方案",
        "tasks": [
            {"name": "开始唤醒", "entry": "StartUp", "type": "StartUp", "params": {}},
            {"name": "领取奖励", "entry": "Award", "type": "Award", "params": {}},
        ],
    }
    payload.update(kw)
    return payload


async def _create_device(client, status: str = "online", port: int = 16384) -> int:
    resp = await client.post(
        "/api/v1/devices",
        json={
            "name": "MuMu12", "adb_host": "192.168.1.10", "adb_port": port,
            "touch_mode": "Minitouch", "client_type": "Official",
        },
    )
    assert resp.status_code == 201, resp.text
    device_id = resp.json()["id"]
    from app.db.session import get_sessionmaker
    from app.models.device import Device

    async with get_sessionmaker()() as s:
        dev = await s.get(Device, device_id)
        dev.status = status
        await s.commit()
    return device_id


async def test_schedule_crud(client, stub_runner) -> None:
    """创建 → 列表 → 更新 → 删除 全流程。"""
    device_id = await _create_device(client)
    resp = await client.post("/api/v1/schedules", json=_scheme_payload(device_id))
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["name"] == "每日长草"
    assert job["weekdays"] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert len(job["tasks"]) == 2
    assert job["last_run_at"] is None

    resp = await client.get("/api/v1/schedules")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 部分更新
    resp = await client.put(
        f"/api/v1/schedules/{job['id']}",
        json={"enabled": False, "time": "07:00", "weekdays": ["Mon", "Fri"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["time"] == "07:00"
    assert body["weekdays"] == ["Mon", "Fri"]
    assert body["name"] == "每日长草"  # 未更新字段保留

    resp = await client.delete(f"/api/v1/schedules/{job['id']}")
    assert resp.status_code == 200
    assert (await client.get("/api/v1/schedules")).json() == []


async def test_schedule_validation(client, stub_runner) -> None:
    """空星期 / 空方案 / 坏时间 / 设备不存在 → 422/404。"""
    device_id = await _create_device(client)
    # 空星期
    resp = await client.post(
        "/api/v1/schedules", json=_scheme_payload(device_id, weekdays=[])
    )
    assert resp.status_code == 422
    assert "星期" in resp.json()["detail"]
    # 空方案
    resp = await client.post(
        "/api/v1/schedules", json=_scheme_payload(device_id, tasks=[])
    )
    assert resp.status_code == 422
    assert "方案" in resp.json()["detail"]
    # 坏时间格式
    resp = await client.post(
        "/api/v1/schedules", json=_scheme_payload(device_id, time="25:99")
    )
    assert resp.status_code == 422
    # 设备不存在
    resp = await client.post("/api/v1/schedules", json=_scheme_payload(9999))
    assert resp.status_code == 404


async def test_schedule_run_now(client, stub_runner) -> None:
    """立即试跑：在线设备 → TaskRunner.start 收到方案任务；离线 → 409。"""
    device_id = await _create_device(client, status="online")
    resp = await client.post("/api/v1/schedules", json=_scheme_payload(device_id))
    job_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/schedules/{job_id}/run")
    assert resp.status_code == 200
    assert stub_runner.calls[0][0] == device_id
    assert stub_runner.calls[0][1] == ["开始唤醒", "领取奖励"]

    # 离线设备上的 job → 409（设备状态变化不影响 job 记录）
    offline_id = await _create_device(client, status="offline", port=16385)
    resp = await client.post("/api/v1/schedules", json=_scheme_payload(offline_id))
    offline_job = resp.json()["id"]
    resp = await client.post(f"/api/v1/schedules/{offline_job}/run")
    assert resp.status_code == 409
    assert "未连接" in resp.json()["detail"]


async def test_schedule_not_found(client, stub_runner) -> None:
    resp = await client.post("/api/v1/schedules/999/run")
    assert resp.status_code == 404
    resp = await client.put("/api/v1/schedules/999", json={"enabled": False})
    assert resp.status_code == 404
