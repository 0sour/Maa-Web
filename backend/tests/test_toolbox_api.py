"""Toolbox API（M5 第一批）— 识别触发/任务状态/历史记录/招募联动 + 结果解析。"""
from __future__ import annotations

import pytest

from app.engine import toolbox


class StubRunner:
    def __init__(self) -> None:
        self.status = "IDLE"
        self.calls: list[tuple] = []

    async def start(self, device, tasks, **kw):
        self.calls.append((device.id, list(tasks), kw))
        from types import SimpleNamespace
        return SimpleNamespace(id=99, status="running")


@pytest.fixture
def stub_runner(monkeypatch):
    runner = StubRunner()
    monkeypatch.setattr(
        "app.engine.taskrunner.TaskRunner.get", staticmethod(lambda device_id: runner)
    )
    return runner


_PORT_SEQ = [16384]

async def _create_device(client, status: str = "online") -> int:
    _PORT_SEQ[0] += 1
    resp = await client.post(
        "/api/v1/devices",
        json={
            "name": "MuMu12", "adb_host": "192.168.1.10", "adb_port": _PORT_SEQ[0],
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


async def test_recognize_trigger_and_status(client, monkeypatch) -> None:
    """触发识别 → task_id；轮询状态（running → done + result）。"""
    device_id = await _create_device(client)
    states = {
        "tb-1": {"status": "running", "result": None, "error": None},
        "tb-2": {"status": "done", "result": {"items": {"30011": 5}}, "error": None},
    }

    def _fake_start(device, tool):
        return "tb-1"

    monkeypatch.setattr(toolbox, "start_recognize", _fake_start)
    monkeypatch.setattr(toolbox, "task_status", lambda tid: states.get(tid))

    resp = await client.post("/api/v1/toolbox/recognize",
                             json={"device_id": device_id, "tool": "depot"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_id"] == "tb-1"

    # running 态
    resp = await client.get("/api/v1/toolbox/tasks/tb-1")
    assert resp.json()["status"] == "running"

    # 未知 task
    resp = await client.get("/api/v1/toolbox/tasks/nope")
    assert resp.status_code == 404


async def test_recognize_validation(client, stub_runner) -> None:
    """非法工具 422 / 设备不存在 404 / 设备离线 409 / 任务运行中 409。"""
    device_id = await _create_device(client)
    resp = await client.post("/api/v1/toolbox/recognize",
                             json={"device_id": device_id, "tool": "gacha"})
    assert resp.status_code == 422

    resp = await client.post("/api/v1/toolbox/recognize",
                             json={"device_id": 999, "tool": "recruit"})
    assert resp.status_code == 404

    off_id = await _create_device(client, status="offline")
    resp = await client.post("/api/v1/toolbox/recognize",
                             json={"device_id": off_id, "tool": "recruit"})
    assert resp.status_code == 409
    assert "未连接" in resp.json()["detail"]

    stub_runner.status = "RUNNING"
    resp = await client.post("/api/v1/toolbox/recognize",
                             json={"device_id": device_id, "tool": "recruit"})
    assert resp.status_code == 409
    assert "正在执行" in resp.json()["detail"]


async def test_records_crud(client, monkeypatch) -> None:
    """历史记录：识别完成自动保存 → 列表/详情/删除。"""
    from sqlalchemy import insert

    from app.db.session import get_sessionmaker
    from app.models.toolbox import ToolboxRecord

    device_id = await _create_device(client)
    async with get_sessionmaker()() as s:
        await s.execute(insert(ToolboxRecord).values(
            tool="recruit", device_id=device_id,
            result='{"results": [{"level": 5, "tags": ["资深干员"], "opers": [{"name": "能天使"}]}]}',
        ))
        await s.execute(insert(ToolboxRecord).values(
            tool="depot", device_id=device_id, result='{"items": {"30011": 5}}',
        ))
        await s.commit()

    resp = await client.get("/api/v1/toolbox/records")
    records = resp.json()["records"]
    assert len(records) == 2
    assert records[0]["tool"] == "depot"  # 倒序
    assert "5★" in records[1]["summary"]

    # 按工具过滤
    resp = await client.get("/api/v1/toolbox/records", params={"tool": "recruit"})
    assert len(resp.json()["records"]) == 1

    # 详情（历史结果调用展示）
    rid = records[1]["id"]
    resp = await client.get(f"/api/v1/toolbox/records/{rid}")
    assert resp.json()["result"]["results"][0]["opers"][0]["name"] == "能天使"

    # 删除
    resp = await client.delete(f"/api/v1/toolbox/records/{rid}")
    assert resp.status_code == 200
    resp = await client.get(f"/api/v1/toolbox/records/{rid}")
    assert resp.status_code == 404


async def test_recruit_execute(client, stub_runner) -> None:
    """识别联动：按星级执行真实公招（Recruit 任务 select/confirm）。"""
    device_id = await _create_device(client)
    resp = await client.post("/api/v1/toolbox/recruit/execute",
                             json={"device_id": device_id, "level": 5})
    assert resp.status_code == 200, resp.text
    assert resp.json()["run_id"] == 99
    assert stub_runner.calls[0][0] == device_id
    params = stub_runner.calls[0][1][0].params
    assert params["select"] == [5] and params["confirm"] == [5]

    # 离线 409
    off_id = await _create_device(client, status="offline")
    resp = await client.post("/api/v1/toolbox/recruit/execute",
                             json={"device_id": off_id, "level": 4})
    assert resp.status_code == 409

    # 非法星级 422
    resp = await client.post("/api/v1/toolbox/recruit/execute",
                             json={"device_id": device_id, "level": 7})
    assert resp.status_code == 422


# ── 引擎层：识别结果解析（纯函数） ─────────────────────────────

def test_parse_recruit_result() -> None:
    acc: dict = {"tags": []}
    toolbox._parse_recruit("RecruitResult", {
        "result": [
            {"level": 5, "tags": ["资深干员", "狙击干员"],
             "opers": [{"id": "char_102_texas", "name": "能天使", "level": 5}]},
            {"level": 3, "tags": ["近战位"], "opers": []},
        ],
    }, acc)
    assert acc["results"][0]["level"] == 5
    assert acc["results"][0]["opers"][0]["name"] == "能天使"
    assert acc["results"][1]["level"] == 3
    assert toolbox.summary_of("recruit", acc) == "5★ 组合：能天使"


def test_parse_recruit_tags_detected() -> None:
    acc: dict = {"tags": []}
    toolbox._parse_recruit("RecruitTagsDetected", {"tags": ["近战位", "近卫干员"]}, acc)
    assert acc["tags"] == ["近战位", "近卫干员"]


def test_parse_depot_data() -> None:
    acc: dict = {}
    toolbox._parse_depot("", {"data": {"30011": "5", "30012": 3}}, acc)
    assert acc["items"] == {"30011": 5, "30012": 3}
    assert toolbox.summary_of("depot", acc) == "材料 2 种"


def test_parse_operbox() -> None:
    acc: dict = {}
    toolbox._parse_operbox("", {"own_opers": [
        {"id": "char_102_texas", "rarity": 5, "elite": 2, "level": 60, "potential": 1},
        {"id": "char_123_fang", "rarity": 1, "elite": 0, "level": 30, "potential": 6},
    ]}, acc)
    assert len(acc["opers"]) == 2
    assert acc["opers"][0]["rarity"] == 5
    assert toolbox.summary_of("operbox", acc) == "干员 2 名 · 六星 1"
