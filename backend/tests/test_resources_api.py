"""Resource pack API tests (S-07) — status/update routes + serialization.

The resource manager is stubbed at the boundary; its internals are covered in
test_resource_mgr.py. Covers route wiring and error surfacing.
"""
from __future__ import annotations

import pytest

from app.engine import resource_mgr


async def test_status_returns_full_payload(client, monkeypatch) -> None:
    async def fake_status():
        return {
            "installed": False, "local_version": None, "pipelines": 0, "ready": False,
            "dir": "/tmp/x", "source": "", "updating": False, "progress": 0.0,
            "stage": "idle", "update_error": None, "remote_latest": None,
            "remote_url": None, "remote_size": 0, "update_available": False,
            "source_hint": "未安装",
        }

    monkeypatch.setattr(resource_mgr, "status", fake_status)
    resp = await client.get("/api/v1/resources/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["installed"] is False
    assert body["ready"] is False
    assert body["stage"] == "idle"


async def test_update_starts_or_reports(client, monkeypatch) -> None:
    async def fake_update():
        return {
            "running": True, "progress": 0.3, "stage": "download", "error": None,
            "started_at": None,
        }

    monkeypatch.setattr(resource_mgr, "update", fake_update)
    resp = await client.post("/api/v1/resources/update")
    assert resp.status_code == 200
    body = resp.json()
    assert body["updating"] is True
    assert body["progress"] == pytest.approx(0.3)
    assert "已开始" in body["message"]


async def test_update_remote_failure_surfaced(client, monkeypatch) -> None:
    async def fake_update():
        return {
            "running": False, "progress": 0.0, "stage": "idle",
            "error": "无法获取官方最新版本（网络不可达）", "started_at": None,
        }

    monkeypatch.setattr(resource_mgr, "update", fake_update)
    resp = await client.post("/api/v1/resources/update")
    assert resp.status_code == 200
    body = resp.json()
    assert body["updating"] is False
    assert "网络不可达" in body["message"]


async def test_items_returns_sorted_list(client, monkeypatch) -> None:
    """/resources/items 返回材料表（id/name/classify_type 序列化）。"""
    monkeypatch.setattr(
        resource_mgr,
        "item_list",
        lambda: [
            {"id": "30011", "name": "固源岩", "classify_type": "MATERIAL"},
            {"id": "30062", "name": "聚酸酯", "classify_type": "MATERIAL"},
        ],
    )
    resp = await client.get("/api/v1/resources/items")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["id"] == "30011"
    assert body[0]["name"] == "固源岩"
    assert body[0]["classify_type"] == "MATERIAL"


async def test_operators_returns_sorted_list(client, monkeypatch) -> None:
    """/resources/operators 返回干员表（id/name 序列化）。"""
    monkeypatch.setattr(
        resource_mgr,
        "operator_list",
        lambda: [
            {"id": "char_002_amiya", "name": "阿米娅"},
            {"id": "char_124_gladiia", "name": "歌蕾蒂娅"},
        ],
    )
    resp = await client.get("/api/v1/resources/operators")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["id"] == "char_002_amiya"
    assert body[0]["name"] == "阿米娅"
    assert body[0]["classify_type"] == ""


async def test_recruit_tags_returns_list(client, monkeypatch) -> None:
    """/resources/recruit-tags 返回公招 Tag 列表。"""
    monkeypatch.setattr(resource_mgr, "recruit_tags", lambda: ["近战位", "远程位", "输出"])
    resp = await client.get("/api/v1/resources/recruit-tags")
    assert resp.status_code == 200
    assert resp.json() == ["近战位", "远程位", "输出"]


async def test_roguelike_core_chars_returns_list(client, monkeypatch) -> None:
    """/resources/roguelike-core-chars?theme= 返回开局干员列表。"""
    monkeypatch.setattr(resource_mgr, "roguelike_core_chars", lambda theme: ["维什戴尔", "令"])
    resp = await client.get("/api/v1/resources/roguelike-core-chars", params={"theme": "JieGarden"})
    assert resp.status_code == 200
    assert resp.json() == ["维什戴尔", "令"]
