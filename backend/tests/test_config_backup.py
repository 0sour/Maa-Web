"""Config export/import API — 全量配置备份与覆盖恢复。"""
from __future__ import annotations

import io
import json
import zipfile


async def _seed_config(client) -> None:
    """造一份完整配置：设备 / 设置 / 方案 / 自动任务 / 草稿。"""
    resp = await client.post(
        "/api/v1/devices",
        json={
            "name": "MuMu12", "adb_host": "192.168.1.10", "adb_port": 16384,
            "touch_mode": "Minitouch", "client_type": "Official",
        },
    )
    assert resp.status_code == 201, resp.text
    device_id = resp.json()["id"]

    await client.put(
        "/api/v1/settings/accounts",
        json={"values": {"list": [{"name": "账号A", "client_type": "Official"}]}},
    )
    await client.post(
        "/api/v1/task-schemes",
        json={
            "name": "日常方案",
            "tasks": [{"type": "StartUp", "entry": "StartUp", "label": "开始唤醒",
                       "params": {}, "checked": True, "once": False}],
        },
    )
    resp = await client.post(
        "/api/v1/auto-tasks",
        json={
            "name": "每日长草", "device_id": device_id, "enabled": True,
            "slots": [{
                "name": "早间", "enabled": True,
                "weekdays": ["Mon", "Tue"], "time": "06:30", "conflict": "force",
                "accounts": [{
                    "account_name": "账号A", "client_type": "Official",
                    "enabled": True, "plan_name": "日常方案",
                    "tasks": [{"name": "开始唤醒", "entry": "StartUp", "type": "StartUp", "params": {}}],
                }],
            }],
        },
    )
    assert resp.status_code == 200, resp.text
    await client.put("/api/v1/tasks/queue-drafts/daily", json={"tasks": [
        {"type": "Award", "entry": "Award", "label": "领取奖励",
         "params": {}, "checked": True, "once": False},
    ]})


async def test_export_config_zip(client) -> None:
    """导出 zip 包含 config.json（设备/设置/方案/自动任务/草稿/runtime_settings）。"""
    await _seed_config(client)
    resp = await client.get("/api/v1/settings/export-config")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    assert "maaweb-config-" in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "config.json" in names and "README.txt" in names
        data = json.loads(zf.read("config.json"))

    assert data["version"] == 1
    assert len(data["devices"]) == 1
    assert data["devices"][0]["name"] == "MuMu12"
    assert data["settings"]["accounts"]["list"] == [{"name": "账号A", "client_type": "Official"}]
    assert data["task_schemes"][0]["name"] == "日常方案"
    assert data["auto_tasks"][0]["name"] == "每日长草"
    assert data["auto_tasks"][0]["slots"][0]["conflict"] == "force"
    assert data["queue_drafts"]["daily"][0]["label"] == "领取奖励"
    assert "runtime_settings" in data


async def test_import_config_restores(client, monkeypatch) -> None:
    """导出 → 清空 → 导入 → 数据一致（覆盖恢复 + 自动备份）。"""
    from app.core.config import get_settings

    await _seed_config(client)
    # 记录导出时的数据
    resp = await client.get("/api/v1/settings/export-config")
    zip_bytes = resp.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        original = json.loads(zf.read("config.json"))
    assert original["devices"][0]["name"] == "MuMu12"  # 确保种子数据在导出中

    # 清空当前配置（模拟丢失/重装）
    from sqlalchemy import delete

    from app.db.session import get_sessionmaker
    from app.models.auto_task import AutoSlot, AutoSlotAccount, AutoTask
    from app.models.device import Device
    from app.models.setting import Setting
    from app.models.task import TaskScheme

    async with get_sessionmaker()() as s:
        await s.execute(delete(AutoSlotAccount))
        await s.execute(delete(AutoSlot))
        await s.execute(delete(AutoTask))
        await s.execute(delete(TaskScheme))
        await s.execute(delete(Device))
        await s.execute(delete(Setting))
        await s.commit()
    assert (await client.get("/api/v1/auto-tasks")).json() == []
    assert (await client.get("/api/v1/task-schemes")).json() == []

    # 导入 zip 恢复
    resp = await client.post(
        "/api/v1/settings/import-config",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert "自动任务 1" in body["message"]
    assert body["backup"].startswith("import-backup-")

    # 一致性断言
    devices = (await client.get("/api/v1/devices")).json()
    assert len(devices) == 1 and devices[0]["name"] == "MuMu12"
    schemes = (await client.get("/api/v1/task-schemes")).json()
    assert schemes[0]["name"] == "日常方案"
    tasks = (await client.get("/api/v1/auto-tasks")).json()
    assert tasks[0]["name"] == "每日长草"
    assert tasks[0]["slots"][0]["accounts"][0]["account_name"] == "账号A"
    drafts = (await client.get("/api/v1/tasks/queue-drafts")).json()
    assert drafts["daily"][0]["label"] == "领取奖励"
    settings = (await client.get("/api/v1/settings")).json()
    assert settings["accounts"]["list"] == [{"name": "账号A", "client_type": "Official"}]

    # 自动备份文件已写入（conftest 临时日志目录）
    assert (get_settings().log_dir / "backup" / body["backup"]).exists()


async def test_import_config_invalid(client) -> None:
    """非法输入：空文件 / 坏 JSON / 缺 version → 422。"""
    resp = await client.post(
        "/api/v1/settings/import-config",
        files={"file": ("x.json", b"", "application/json")},
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/api/v1/settings/import-config",
        files={"file": ("x.json", b"not json", "application/json")},
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/api/v1/settings/import-config",
        files={"file": ("x.json", b'{"foo": 1}', "application/json")},
    )
    assert resp.status_code == 422
    assert "不是有效的" in resp.json()["detail"]
