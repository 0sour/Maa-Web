"""Settings API tests (M3) — mirror sources & MirrorChyan CDK check routes."""
from __future__ import annotations

import pytest

from app.core import runtime_settings
from app.engine import resource_mgr


@pytest.fixture(autouse=True)
def _runtime_isolated(monkeypatch, tmp_path):
    """把运行时设置指向临时文件，避免污染真实 data 目录。"""
    rt_file = tmp_path / "config" / "runtime_settings.json"
    rt_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runtime_settings, "_path", lambda: rt_file)
    monkeypatch.setattr(runtime_settings, "_cache", None)


async def test_read_default_mirror_empty(client) -> None:
    """未配置时：更新源为 github，mirror 前缀为空，CDK 未配置。"""
    resp = await client.get("/api/v1/settings/mirror")
    assert resp.status_code == 200
    body = resp.json()
    assert body["update_source"] == "github"
    assert body["mirror_prefixes"] == ""
    assert body["mirror_prefix_list"] == []
    assert body["mirrorchyan_cdk_configured"] is False
    assert body["mirrorchyan_cdk_expired_time"] == 0


async def test_put_update_source(client) -> None:
    """PUT 保存更新源为 mirrorchyan → GET 回显。"""
    resp = await client.put(
        "/api/v1/settings/mirror", json={"update_source": "mirrorchyan"}
    )
    assert resp.status_code == 200
    assert resp.json()["update_source"] == "mirrorchyan"
    resp2 = await client.get("/api/v1/settings/mirror")
    assert resp2.json()["update_source"] == "mirrorchyan"


async def test_put_update_source_invalid(client) -> None:
    """非法更新源 → 422。"""
    resp = await client.put(
        "/api/v1/settings/mirror", json={"update_source": "foo"}
    )
    assert resp.status_code == 422


async def test_put_saves_and_reads_back(client, monkeypatch) -> None:
    """PUT 保存镜像前缀 + CDK → GET 回显（CDK 脱敏、有效期未知）。"""
    resp = await client.put(
        "/api/v1/settings/mirror",
        json={"mirror_prefixes": "https://ghproxy.net/, https://ghfast.top/", "mirrorchyan_cdk": "1234567890ABCDEF12345678"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mirror_prefix_list"] == ["https://ghproxy.net/", "https://ghfast.top/"]
    # CDK 已配置且回显明文（单用户 NAS 场景），同时提供脱敏值供展示
    assert body["mirrorchyan_cdk_configured"] is True
    assert body["mirrorchyan_cdk"] == "1234567890ABCDEF12345678"
    assert body["mirrorchyan_cdk_masked"] == "1234" + "*" * 16 + "5678"

    # 再次 GET 应一致
    resp2 = await client.get("/api/v1/settings/mirror")
    assert resp2.json()["mirror_prefix_list"] == ["https://ghproxy.net/", "https://ghfast.top/"]
    assert resp2.json()["mirrorchyan_cdk"] == "1234567890ABCDEF12345678"


async def test_put_clear_cdk_resets_validity(client) -> None:
    """保存新 CDK 时应清除旧有效期（下一次 check 重新获取）。"""
    await client.put(
        "/api/v1/settings/mirror",
        json={"mirrorchyan_cdk": "ABCDEFGHIJKLMNOPQRSTUVWX"},
    )
    runtime_settings.update(mirrorchyan_cdk_expired_time=5_000_000_000)
    resp = await client.put(
        "/api/v1/settings/mirror",
        json={"mirrorchyan_cdk": "NEWCDK1234567890ABCDEFGH"},
    )
    body = resp.json()
    assert body["mirrorchyan_cdk_expired_time"] == 0
    assert body["mirrorchyan_cdk_remaining_days"] is None


async def test_put_same_cdk_keeps_validity(client) -> None:
    """原样保存同一个 CDK（前端回显后未修改）→ 保留既有有效期，不清零。"""
    await client.put(
        "/api/v1/settings/mirror",
        json={"mirrorchyan_cdk": "SAMECDK1234567890ABCDEF"},
    )
    runtime_settings.update(mirrorchyan_cdk_expired_time=5_000_000_000)
    resp = await client.put(
        "/api/v1/settings/mirror",
        json={"mirrorchyan_cdk": "SAMECDK1234567890ABCDEF"},
    )
    body = resp.json()
    assert body["mirrorchyan_cdk_expired_time"] == 5_000_000_000
    assert body["mirrorchyan_cdk_remaining_days"] is not None


async def test_put_empty_cdk_resets_validity(client) -> None:
    """清空 CDK → 有效期清零。"""
    await client.put(
        "/api/v1/settings/mirror",
        json={"mirrorchyan_cdk": "SAMECDK1234567890ABCDEF"},
    )
    runtime_settings.update(mirrorchyan_cdk_expired_time=5_000_000_000)
    resp = await client.put(
        "/api/v1/settings/mirror",
        json={"mirrorchyan_cdk": ""},
    )
    body = resp.json()
    assert body["mirrorchyan_cdk_configured"] is False
    assert body["mirrorchyan_cdk_expired_time"] == 0


async def test_check_cdk_valid(client, monkeypatch) -> None:
    """POST check：CDK 有效 → ok=True + 剩余天数，并持久化。"""
    async def fake_check(cdk: str) -> dict:
        return {
            "ok": True, "code": 0, "message": "Mirror酱 CDK 有效，剩余 12.3 天",
            "cdk_expired_time": 5_000_000_000, "remaining_days": 12.3,
        }

    monkeypatch.setattr(resource_mgr, "check_mirrorchyan_cdk", fake_check)
    resp = await client.post(
        "/api/v1/settings/mirror/check", json={"cdk": "ABCDEFGHIJKLMNOPQRSTUVWX"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["remaining_days"] == pytest.approx(12.3)
    assert "剩余" in body["message"]


async def test_check_cdk_expired(client, monkeypatch) -> None:
    """POST check：CDK 过期（code 7001）→ ok=False + 过期提示。"""
    async def fake_check(cdk: str) -> dict:
        return {"ok": False, "code": 7001, "message": "Mirror酱 CDK 已过期，请续费或更换", "cdk_expired_time": 0, "remaining_days": None}

    monkeypatch.setattr(resource_mgr, "check_mirrorchyan_cdk", fake_check)
    resp = await client.post("/api/v1/settings/mirror/check", json={"cdk": "A" * 24})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["code"] == 7001
    assert "已过期" in body["message"]


# ── 通用设置分组（Setting 表） ───────────────────────────────

async def test_settings_groups_default_empty(client) -> None:
    """未配置时 GET /settings 返回空分组。"""
    resp = await client.get("/api/v1/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"game", "connection", "ui", "notify"}
    assert body["game"] == {} and body["connection"] == {}
    assert body["ui"] == {} and body["notify"] == {}


async def test_put_and_get_settings_group(client) -> None:
    """PUT /settings/game 保存 → GET /settings 回读（键去前缀）。"""
    resp = await client.put(
        "/api/v1/settings/game",
        json={"values": {"client_type": "Bilibili", "block_sleep": True, "penguin_id": "12345"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["game"]["client_type"] == "Bilibili"
    assert body["game"]["block_sleep"] is True
    assert body["game"]["penguin_id"] == "12345"

    # 其他分组不受影响
    assert body["connection"] == {}
    assert body["ui"] == {}

    # 再读一次（持久化）
    resp2 = await client.get("/api/v1/settings")
    assert resp2.json()["game"]["client_type"] == "Bilibili"


async def test_put_settings_group_upsert_and_delete(client) -> None:
    """同键覆盖；传 None 删除。"""
    await client.put("/api/v1/settings/game", json={"values": {"client_type": "Official", "block_sleep": False}})
    await client.put("/api/v1/settings/game", json={"values": {"client_type": "txwy"}})
    body = (await client.get("/api/v1/settings")).json()
    assert body["game"]["client_type"] == "txwy"
    assert body["game"]["block_sleep"] is False

    await client.put("/api/v1/settings/game", json={"values": {"client_type": None}})
    body = (await client.get("/api/v1/settings")).json()
    assert "client_type" not in body["game"]
    assert body["game"]["block_sleep"] is False


async def test_put_settings_group_invalid(client) -> None:
    """非法分组名 / 含点键 → 422。"""
    resp = await client.put("/api/v1/settings/bad", json={"values": {"x": 1}})
    assert resp.status_code == 422
    assert "仅支持" in resp.json()["detail"]

    resp = await client.put("/api/v1/settings/game", json={"values": {"a.b": 1}})
    assert resp.status_code == 422
    assert "无效的设置键" in resp.json()["detail"]


async def test_logs_export_zip(client, monkeypatch, tmp_path) -> None:
    """日志导出：临时日志目录打包为 zip（含文件，空目录给说明）。"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "app.log").write_text("hello maaweb\n", encoding="utf-8")
    monkeypatch.setattr("app.api.v1.settings.get_settings", lambda: type("S", (), {"log_dir": log_dir})())

    resp = await client.get("/api/v1/settings/logs-export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    assert "attachment" in resp.headers["content-disposition"]
    data = resp.content
    assert data[:2] == b"PK"  # zip magic

    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert any(n.endswith("app.log") for n in names)
        content = zf.read([n for n in names if n.endswith("app.log")][0])
        assert b"hello maaweb" in content


async def test_geoip_success(client, monkeypatch) -> None:
    """GET /settings/geoip：ip-api 返回 success → 经纬度 + 城市。"""
    from app.api.v1 import settings as settings_mod

    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "status": "success", "lat": 31.2304, "lon": 121.4737,
                "city": "Shanghai", "country": "China",
            }

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw) -> _Resp:
            assert url.startswith("http://ip-api.com/json/")
            return _Resp()

    monkeypatch.setattr(settings_mod.httpx, "AsyncClient", _Client)
    resp = await client.get("/api/v1/settings/geoip")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lat"] == 31.2304 and body["lon"] == 121.4737
    assert body["city"] == "Shanghai"


async def test_geoip_service_failure(client, monkeypatch) -> None:
    """ip-api 服务不可用/返回非 success → 502 + 人话 detail。"""
    from app.api.v1 import settings as settings_mod

    class _Resp:
        def raise_for_status(self) -> None:
            raise RuntimeError("connection refused")

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw) -> _Resp:
            return _Resp()

    monkeypatch.setattr(settings_mod.httpx, "AsyncClient", _Client)
    resp = await client.get("/api/v1/settings/geoip")
    assert resp.status_code == 502
    assert "定位服务不可用" in resp.json()["detail"]


async def test_proxy_test_success(client, monkeypatch) -> None:
    """POST /settings/proxy-test：经代理访问成功 → ok + 耗时。"""
    from app.api.v1 import settings as settings_mod

    class _Resp:
        def raise_for_status(self) -> None:
            pass

    class _Client:
        def __init__(self, *a, **k):
            self.kw = k

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw) -> _Resp:
            assert url == "https://api.github.com/rate_limit"
            assert self.kw.get("proxy") == "http://127.0.0.1:7890"
            return _Resp()

    monkeypatch.setattr(settings_mod.httpx, "AsyncClient", _Client)
    resp = await client.post(
        "/api/v1/settings/proxy-test",
        json={"proxy": "http://127.0.0.1:7890"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["latency_ms"] >= 0 and body["error"] is None


async def test_proxy_test_failure(client, monkeypatch) -> None:
    """代理不可达 → ok=False + 错误信息。"""
    from app.api.v1 import settings as settings_mod

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(settings_mod.httpx, "AsyncClient", _Client)
    resp = await client.post(
        "/api/v1/settings/proxy-test", json={"proxy": "http://127.0.0.1:9"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "connection refused" in body["error"]


async def test_mirror_dynamic_source_roundtrip(client) -> None:
    """PUT /settings/mirror 保存 dynamic_source → GET 回显；非法值 422。"""
    resp = await client.put(
        "/api/v1/settings/mirror",
        json={"update_source": "github", "dynamic_source": "mirrorchyan"},
    )
    assert resp.status_code == 200
    assert resp.json()["dynamic_source"] == "mirrorchyan"
    resp = await client.get("/api/v1/settings/mirror")
    assert resp.json()["dynamic_source"] == "mirrorchyan"

    resp = await client.put(
        "/api/v1/settings/mirror", json={"dynamic_source": "bogus"}
    )
    assert resp.status_code == 422

    # 空 = 跟随引擎包源
    resp = await client.put("/api/v1/settings/mirror", json={"dynamic_source": ""})
    assert resp.status_code == 200
    assert resp.json()["dynamic_source"] == "github"  # 回退 update_source
