"""Auto-tasks API (M6+) — CRUD（嵌套 slots/accounts）+ run-test（手动测试）。"""
from __future__ import annotations

import pytest

from app.engine.scheduler import auto_runner


class StubRunner:
    """run-test 只检查空闲状态；submit 走 monkeypatch 记录。"""

    def __init__(self) -> None:
        self.status = "IDLE"


@pytest.fixture
def stub_runner(monkeypatch):
    runner = StubRunner()
    monkeypatch.setattr(
        "app.engine.taskrunner.TaskRunner.get", staticmethod(lambda device_id: runner)
    )
    monkeypatch.setattr(
        "app.engine.scheduler.TaskRunner.get", staticmethod(lambda device_id: runner)
    )
    return runner


@pytest.fixture
def submitted(monkeypatch):
    """记录 auto_runner.submit 调用（不真正起 worker）。"""
    calls: list[dict] = []

    async def _fake_submit(**kw) -> None:
        calls.append(kw)

    monkeypatch.setattr(auto_runner, "submit", _fake_submit)
    return calls


async def _create_device(client, status: str = "online") -> int:
    resp = await client.post(
        "/api/v1/devices",
        json={
            "name": "MuMu12", "adb_host": "192.168.1.10", "adb_port": 16384,
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


def _task_payload(device_id: int, **kw) -> dict:
    payload = {
        "name": "每日长草",
        "device_id": device_id,
        "enabled": True,
        "slots": [
            {
                "name": "早间长草",
                "enabled": True,
                "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                "time": "06:30",
                "conflict": "queue",
                "accounts": [
                    {
                        "account_name": "账号A",
                        "client_type": "Official",
                        "enabled": True,
                        "plan_name": "日常方案",
                        "tasks": [
                            {"name": "开始唤醒", "entry": "StartUp", "type": "StartUp", "params": {}},
                        ],
                    }
                ],
            },
            {
                "name": "晚间活动",
                "enabled": True,
                "weekdays": ["Sat", "Sun"],
                "time": "19:00",
                "conflict": "force",
                "accounts": [],
            },
        ],
    }
    payload.update(kw)
    return payload


async def test_auto_task_crud_roundtrip(client, stub_runner) -> None:
    """创建（嵌套 slots/accounts）→ 列表 → 整体保存 → 删除 全流程。"""
    device_id = await _create_device(client)
    resp = await client.post("/api/v1/auto-tasks", json=_task_payload(device_id))
    assert resp.status_code == 200, resp.text
    task = resp.json()
    assert task["name"] == "每日长草"
    assert len(task["slots"]) == 2
    slot0 = task["slots"][0]
    assert slot0["name"] == "早间长草"
    assert slot0["time"] == "06:30"
    assert slot0["conflict"] == "queue"
    assert slot0["weekdays"] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert len(slot0["accounts"]) == 1
    acc = slot0["accounts"][0]
    assert acc["account_name"] == "账号A"
    assert acc["client_type"] == "Official"
    assert acc["tasks"][0]["entry"] == "StartUp"
    assert task["slots"][1]["accounts"] == []

    # 列表回显
    resp = await client.get("/api/v1/auto-tasks")
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == task["id"]

    # 整体保存：改名 + 删槽 + 换账号
    payload = _task_payload(device_id)
    payload["name"] = "长草改"
    payload["slots"] = [payload["slots"][0]]
    payload["slots"][0]["accounts"][0]["account_name"] = "账号B"
    payload["slots"][0]["accounts"][0]["client_type"] = "Bilibili"
    resp = await client.put(f"/api/v1/auto-tasks/{task['id']}", json=payload)
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["name"] == "长草改"
    assert len(updated["slots"]) == 1
    assert updated["slots"][0]["accounts"][0]["account_name"] == "账号B"
    assert updated["slots"][0]["accounts"][0]["client_type"] == "Bilibili"

    # 删除
    resp = await client.delete(f"/api/v1/auto-tasks/{task['id']}")
    assert resp.status_code == 200
    resp = await client.get("/api/v1/auto-tasks")
    assert resp.json() == []
    # 槽与账号级联删除
    from sqlalchemy import func, select

    from app.db.session import get_sessionmaker
    from app.models.auto_task import AutoSlot, AutoSlotAccount

    async with get_sessionmaker()() as s:
        n_slots = (await s.execute(select(func.count(AutoSlot.id)))).scalar()
        n_accs = (await s.execute(select(func.count(AutoSlotAccount.id)))).scalar()
    assert n_slots == 0 and n_accs == 0


async def test_create_validation(client, stub_runner) -> None:
    device_id = await _create_device(client)

    # 星期为空 → 422
    bad = _task_payload(device_id)
    bad["slots"][0]["weekdays"] = []
    resp = await client.post("/api/v1/auto-tasks", json=bad)
    assert resp.status_code == 422
    assert "至少选择一个星期" in resp.json()["detail"]

    # 时间格式错误 → 422
    bad = _task_payload(device_id)
    bad["slots"][0]["time"] = "25:99"
    resp = await client.post("/api/v1/auto-tasks", json=bad)
    assert resp.status_code == 422

    # 设备不存在 → 404
    resp = await client.post("/api/v1/auto-tasks", json=_task_payload(999))
    assert resp.status_code == 404

    # 不存在的任务 → 404
    resp = await client.put("/api/v1/auto-tasks/999", json=_task_payload(device_id))
    assert resp.status_code == 404


async def test_run_test_submits_manual_source(client, stub_runner, submitted) -> None:
    """RUN TEST：提交目标槽的启用账号，source=manual_auto。"""
    device_id = await _create_device(client)
    resp = await client.post("/api/v1/auto-tasks", json=_task_payload(device_id))
    task = resp.json()
    slot_id = task["slots"][0]["id"]

    resp = await client.post(f"/api/v1/auto-tasks/{task['id']}/run-test", json={"slot_id": slot_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert len(submitted) == 1
    call = submitted[0]
    assert call["device_id"] == device_id
    assert call["slot_name"] == "早间长草"
    assert call["source"] == "manual_auto"
    assert len(call["accounts"]) == 1
    assert call["accounts"][0]["account_name"] == "账号A"


async def test_run_test_busy_409(client, stub_runner) -> None:
    device_id = await _create_device(client)
    resp = await client.post("/api/v1/auto-tasks", json=_task_payload(device_id))
    task = resp.json()
    stub_runner.status = "RUNNING"
    resp = await client.post(
        f"/api/v1/auto-tasks/{task['id']}/run-test",
        json={"slot_id": task["slots"][0]["id"]},
    )
    assert resp.status_code == 409


async def test_run_test_offline_409(client, stub_runner) -> None:
    device_id = await _create_device(client, status="offline")
    resp = await client.post("/api/v1/auto-tasks", json=_task_payload(device_id))
    task = resp.json()
    resp = await client.post(
        f"/api/v1/auto-tasks/{task['id']}/run-test",
        json={"slot_id": task["slots"][0]["id"]},
    )
    assert resp.status_code == 409
    assert "未连接" in resp.json()["detail"]


async def test_run_test_no_enabled_accounts_422(client, stub_runner) -> None:
    device_id = await _create_device(client)
    payload = _task_payload(device_id)
    payload["slots"][0]["accounts"][0]["enabled"] = False
    resp = await client.post("/api/v1/auto-tasks", json=payload)
    task = resp.json()
    resp = await client.post(
        f"/api/v1/auto-tasks/{task['id']}/run-test",
        json={"slot_id": task["slots"][0]["id"]},
    )
    assert resp.status_code == 422
    assert "没有启用账号" in resp.json()["detail"]


async def test_run_test_slot_not_in_task_404(client, stub_runner) -> None:
    device_id = await _create_device(client)
    resp = await client.post("/api/v1/auto-tasks", json=_task_payload(device_id))
    task_a = resp.json()
    resp = await client.post(
        f"/api/v1/auto-tasks/{task_a['id']}/run-test",
        json={"slot_id": 999},
    )
    assert resp.status_code == 404


async def test_create_empty_name_group(client, stub_runner) -> None:
    """未命名组允许创建并立即落库（跨浏览器一致；UI 显示「未命名」）。"""
    device_id = await _create_device(client)
    payload = _task_payload(device_id)
    payload["name"] = ""
    resp = await client.post("/api/v1/auto-tasks", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == ""
    assert len(resp.json()["slots"]) == 2
    # 列表可见（其他浏览器同样可见）
    resp = await client.get("/api/v1/auto-tasks")
    assert len(resp.json()) == 1


async def test_save_empty_slot_name(client, stub_runner) -> None:
    """槽名允许为空（未命名时间点）：整组保存不因空槽名失败（2026-08-16）。"""
    device_id = await _create_device(client)
    payload = _task_payload(device_id)
    payload["slots"][0]["name"] = ""
    resp = await client.post("/api/v1/auto-tasks", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["slots"][0]["name"] == ""
