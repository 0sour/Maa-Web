"""Task schemes API — task_schemes 表（原 localStorage → 后端化，跨浏览器一致）。"""
from __future__ import annotations


def _scheme_payload(**kw) -> dict:
    payload = {
        "name": "每日日常",
        "tasks": [
            {"type": "StartUp", "entry": "StartUp", "label": "开始唤醒",
             "params": {"start_game_enabled": True}, "checked": True, "once": False},
            {"type": "Award", "entry": "Award", "label": "领取奖励",
             "params": {}, "checked": True, "once": False},
        ],
    }
    payload.update(kw)
    return payload


async def test_scheme_crud_roundtrip(client) -> None:
    """创建 → 列表 → 更新（改名/换任务）→ 删除 全流程。"""
    resp = await client.post("/api/v1/task-schemes", json=_scheme_payload())
    assert resp.status_code == 200, resp.text
    scheme = resp.json()
    assert scheme["name"] == "每日日常"
    assert len(scheme["tasks"]) == 2
    assert scheme["id"] > 0

    # 列表回显
    resp = await client.get("/api/v1/task-schemes")
    assert [s["name"] for s in resp.json()] == ["每日日常"]

    # 更新：改名 + 换任务
    payload = _scheme_payload(name="每日日常改", tasks=[
        {"type": "Fight", "entry": "Fight", "label": "刷理智",
         "params": {"stage": "CE-6"}, "checked": True, "once": False},
    ])
    resp = await client.put(f"/api/v1/task-schemes/{scheme['id']}", json=payload)
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["name"] == "每日日常改"
    assert updated["tasks"][0]["entry"] == "Fight"

    # 删除
    resp = await client.delete(f"/api/v1/task-schemes/{scheme['id']}")
    assert resp.status_code == 200
    resp = await client.get("/api/v1/task-schemes")
    assert resp.json() == []


async def test_save_same_name_overwrites(client) -> None:
    """同名保存 = 覆盖（upsert by name，不产生重复）。"""
    resp = await client.post("/api/v1/task-schemes", json=_scheme_payload(name="同名"))
    first_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/task-schemes",
        json=_scheme_payload(name="同名", tasks=[{"type": "Award", "entry": "Award",
                                                  "label": "A", "params": {},
                                                  "checked": True, "once": False}]),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == first_id  # 同一条记录被覆盖
    assert len(resp.json()["tasks"]) == 1
    resp = await client.get("/api/v1/task-schemes")
    assert len(resp.json()) == 1


async def test_scheme_validation(client) -> None:
    """空名 422 / 更新不存在 404 / 改名冲突 409。"""
    resp = await client.post("/api/v1/task-schemes", json=_scheme_payload(name="  "))
    assert resp.status_code == 422

    resp = await client.put("/api/v1/task-schemes/999", json=_scheme_payload())
    assert resp.status_code == 404

    resp = await client.delete("/api/v1/task-schemes/999")
    assert resp.status_code == 404

    await client.post("/api/v1/task-schemes", json=_scheme_payload(name="A"))
    created = await client.post("/api/v1/task-schemes", json=_scheme_payload(name="B"))
    resp = await client.put(
        f"/api/v1/task-schemes/{created.json()['id']}",
        json=_scheme_payload(name="A"),
    )
    assert resp.status_code == 409


async def test_queue_drafts_roundtrip(client) -> None:
    """队列草稿（首页 daily / 编排页 tasks）：读写与非法键 422。"""
    resp = await client.get("/api/v1/tasks/queue-drafts")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"daily": [], "tasks": []}

    draft = [
        {"type": "Infrast", "entry": "Infrast", "label": "基建换班",
         "params": {"mode": 0}, "checked": True, "once": False},
    ]
    resp = await client.put("/api/v1/tasks/queue-drafts/daily", json={"tasks": draft})
    assert resp.status_code == 200
    resp = await client.put("/api/v1/tasks/queue-drafts/tasks", json={"tasks": []})
    assert resp.status_code == 200

    resp = await client.get("/api/v1/tasks/queue-drafts")
    body = resp.json()
    assert body["daily"] == draft
    assert body["tasks"] == []

    # 非法键 422
    resp = await client.put("/api/v1/tasks/queue-drafts/bad", json={"tasks": []})
    assert resp.status_code == 422
