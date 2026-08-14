"""Health probe tests — cover risk R2 (ORJSON JSON body) + R3 (status codes).

Contract (docs/testing.md §2, §3.3):
  - /healthz/live   → always 200, JSON body with status=ok, pid/python/event_loop
  - /healthz/ready  → 200 if MaaFw importable & mem ok, else 503 + JSON
  - /healthz/startup→ 200 if dirs + MaaFw ok, else 503 + JSON
  - All probes MUST return valid JSON regardless of status code (R2 regression).
"""
from __future__ import annotations


async def test_live_probe_returns_ok_json(client) -> None:
    """R3: liveness never fails and always returns structured JSON."""
    resp = await client.get("/healthz/live")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "maaweb-api"
    assert body["version"]
    assert body["checks"]["pid"] > 0
    assert body["checks"]["event_loop"] == "running"


async def test_ready_probe_has_valid_shape(client) -> None:
    """R3: readiness either ok(200) or degraded(503) but always valid JSON."""
    resp = await client.get("/healthz/ready")

    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert body["service"] == "maaweb-api"
    # checks must always carry the two documented keys (R2/contract)
    assert "startup_ok" in body["checks"]
    assert "free_mem_mb" in body["checks"]


async def test_startup_probe_has_valid_shape(client) -> None:
    """R3: startup either ok(200) or starting(503) but always valid JSON."""
    resp = await client.get("/healthz/startup")

    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["status"] in ("ok", "starting")
    assert body["service"] == "maaweb-api"
    assert "engine_ready" in body["checks"]
    assert "dirs_created" in body["checks"]


async def test_startup_probe_created_data_dirs(client, test_data_root) -> None:
    """R8: startup hook must have materialized the expected directory tree."""
    for sub in ("config", "logs", "cache", "media", "cache/maa-resource"):
        assert (test_data_root / sub).is_dir(), f"missing {sub}"
