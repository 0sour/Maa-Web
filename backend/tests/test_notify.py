"""外部通知 (M6) — 渠道消息构造 + 发送/记录 + API（测试/日志/重发）。"""
from __future__ import annotations

import json

import pytest

from app.engine import notify as notify_mod


class _Resp:
    def __init__(self, status: int = 200, text: str = "ok") -> None:
        self.status_code = status
        self.text = text


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        self.calls.append((url, kw))
        return _Resp(self.status)


async def _seed_notify(**values) -> None:
    from app.db.session import get_sessionmaker
    from app.models.setting import Setting

    async with get_sessionmaker()() as s:
        for k, v in values.items():
            row = await s.get(Setting, f"notify.{k}")
            if row is None:
                s.add(Setting(key=f"notify.{k}", value=json.dumps(v)))
            else:
                row.value = json.dumps(v)
        await s.commit()


async def _clear_notify() -> None:
    from sqlalchemy import delete

    from app.db.session import get_sessionmaker
    from app.models.notify import NotifyLog
    from app.models.setting import Setting

    async with get_sessionmaker()() as s:
        await s.execute(delete(Setting).where(Setting.key.like("notify.%")))
        await s.execute(delete(NotifyLog))
        await s.commit()


# ── 渠道消息构造 ─────────────────────────────────────────────

class TestBuilders:
    def test_serverchan_url(self) -> None:
        url, payload, _ = notify_mod._serverchan({"send_key": "KEY123"}, "标题", "内容")
        assert url == "https://sctapi.ftqq.com/KEY123.send"
        assert payload == {"title": "标题", "desp": "内容"}

    def test_dingtalk_signed(self) -> None:
        url, payload, _ = notify_mod._dingtalk(
            {"access_token": "TOK", "secret": "SEC"}, "标题", "内容"
        )
        assert url.startswith("https://oapi.dingtalk.com/robot/send?access_token=TOK&timestamp=")
        assert "&sign=" in url and url.split("sign=")[1] != ""
        assert payload["msgtype"] == "text"
        assert "标题" in payload["text"]["content"]

    def test_dingtalk_no_secret(self) -> None:
        url, _, _ = notify_mod._dingtalk({"access_token": "TOK"}, "t", "c")
        assert "sign=" in url and url.split("sign=")[1] == ""

    def test_custom_template(self) -> None:
        url, body, headers = notify_mod._custom(
            {"url": "https://example.com/hook", "headers": "X-Auth: abc\nX-Tag: 1", "body": "{title}--{content}"},
            "标题", "内容",
        )
        assert url == "https://example.com/hook"
        assert body == "标题--内容"
        assert headers["X-Auth"] == "abc"
        assert headers["Content-Type"] == "text/plain"

    def test_custom_default_json(self) -> None:
        url, body, headers = notify_mod._custom({"url": "https://example.com/hook"}, "标题", "内容")
        assert json.loads(body) == {"title": "标题", "content": "内容"}
        assert headers["Content-Type"] == "application/json"


# ── 发送主流程 ───────────────────────────────────────────────

async def _notify_db() -> list[dict]:
    from sqlalchemy import select

    from app.db.session import get_sessionmaker
    from app.models.notify import NotifyLog

    async with get_sessionmaker()() as s:
        rows = (
            (await s.execute(select(NotifyLog).order_by(NotifyLog.id))).scalars().all()
        )
        return [
            {"channel": r.channel, "event": r.event, "ok": r.ok, "error": r.error}
            for r in rows
        ]


class TestSend:
    @pytest.fixture(autouse=True)
    async def _db_tables(self):
        """独立建表（无 client fixture 时 settings/notify_logs 表不存在）。"""
        from app.db.session import get_engine
        from app.models import (  # noqa: F401  (registers tables)
            notify as _notify_models,
        )
        from app.models.device import Base

        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield

    async def test_no_config_returns_empty(self) -> None:
        await _clear_notify()
        results = await notify_mod.send("complete", "标题", "内容")
        assert results == []

    async def test_disabled_event_skips(self) -> None:
        await _clear_notify()
        await _seed_notify(enabled_complete=False)
        results = await notify_mod.send("complete", "标题", "内容")
        assert results == []

    async def test_send_all_channels(self, monkeypatch) -> None:
        await _clear_notify()
        client = FakeClient()
        monkeypatch.setattr(notify_mod.httpx, "AsyncClient", lambda *a, **k: client)
        await _seed_notify(
            channels=[
                {"type": "serverchan", "enabled": True, "send_key": "K1"},
                {"type": "dingtalk", "enabled": True, "access_token": "T", "secret": "S"},
                {"type": "custom", "enabled": True, "url": "https://hook/x"},
                {"type": "custom", "enabled": False, "url": "https://hook/off"},
            ]
        )
        results = await notify_mod.send("complete", "标题", "内容")
        assert len(results) == 3  # 禁用的渠道不发
        assert all(r["ok"] for r in results)
        assert len(client.calls) == 3
        # 发送记录落库
        rows = await _notify_db()
        assert len(rows) == 3
        assert all(r["ok"] for r in rows)

    async def test_http_error_recorded(self, monkeypatch) -> None:
        await _clear_notify()
        client = FakeClient()
        client.status = 500
        monkeypatch.setattr(notify_mod.httpx, "AsyncClient", lambda *a, **k: client)
        await _seed_notify(
            channels=[{"type": "serverchan", "enabled": True, "send_key": "K1"}]
        )
        results = await notify_mod.send("error", "标题", "内容")
        assert results[0]["ok"] is False
        assert "HTTP 500" in results[0]["error"]
        rows = await _notify_db()
        assert rows[0]["ok"] is False and rows[0]["error"].startswith("HTTP 500")

    async def test_exception_recorded(self, monkeypatch) -> None:
        await _clear_notify()

        class Boom:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kw):
                raise RuntimeError("boom")

        monkeypatch.setattr(notify_mod.httpx, "AsyncClient", lambda *a, **k: Boom())
        await _seed_notify(
            channels=[{"type": "serverchan", "enabled": True, "send_key": "K1"}]
        )
        results = await notify_mod.send("complete", "标题", "内容")
        assert results[0]["ok"] is False
        assert "boom" in results[0]["error"]


# ── API ──────────────────────────────────────────────────────

class TestApi:
    async def test_test_and_logs_and_resend(self, client, monkeypatch) -> None:
        async def fake_send(event, title, content):
            return [{"channel": "serverchan", "ok": True, "error": None}]

        monkeypatch.setattr("app.api.v1.notifications.notify.send", fake_send)
        resp = await client.post("/api/v1/notifications/test")
        assert resp.status_code == 200
        assert resp.json()["results"][0]["ok"] is True

        # 记录列表（fake_send 不落库 → 空）
        resp = await client.get("/api/v1/notifications/logs")
        assert resp.status_code == 200
        assert resp.json() == []

        resp = await client.post("/api/v1/notifications/logs/999/resend")
        assert resp.status_code == 404
