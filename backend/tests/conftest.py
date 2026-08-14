"""Pytest shared fixtures for Maa-Web backend.

Isolation contract (docs/testing.md §7):
  - Each pytest session gets its own temp data dir (never touches /data or dev DB).
  - Env overrides MUST be set before `app.main` is imported (Settings is cached).
  - Lifespan hooks (on_startup / on_shutdown) run per client fixture so probes
    behave exactly like production startup.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# ── 1) Override data paths BEFORE importing the app (Settings reads env once) ──
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="maaweb-tests-"))
os.environ["DATA_DIR"] = str(_TEST_ROOT)
os.environ["CONFIG_FILE"] = str(_TEST_ROOT / "config" / "maaweb.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_ROOT / 'config' / 'maaweb.db'}"
os.environ["LOG_DIR"] = str(_TEST_ROOT / "logs")
os.environ["CACHE_DIR"] = str(_TEST_ROOT / "cache")
os.environ["MEDIA_DIR"] = str(_TEST_ROOT / "media")
os.environ["MAA_RESOURCE_DIR"] = str(_TEST_ROOT / "cache" / "maa-resource")
os.environ["MAAWEB_SECRET_KEY"] = "test-secret-not-for-production"
# SQLite 要求父目录先存在；会话级创建一次，保证任意测试（不依赖 client fixture
# 的执行顺序）都能打开 DB。
(_TEST_ROOT / "config").mkdir(parents=True, exist_ok=True)

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
async def client():
    """ASGI test client with real lifespan (startup/shutdown hooks run).

    Hermetic: no network, no real MaaFw, isolated temp data dir.
    Table isolation: each test gets a freshly created schema (drop + create),
    so tests never share rows (flake guard, docs/testing.md §7).
    """
    from app.db.session import get_engine
    from app.models import task as _task_models  # noqa: F401  (registers task tables)
    from app.models.device import Base

    # SQLite requires the parent dir to exist before connecting.
    (_TEST_ROOT / "config").mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _mock_run_empty(argv: list, timeout: float | None = None) -> str:
    """默认 adb 子进程输出：空（无设备、无内容），避免触碰真实 adb。"""
    return ""


@pytest.fixture(autouse=True)
def _no_real_adb(monkeypatch):
    """测试隔离：adb 子进程默认返回空输出（hermetic）。

    这样 scan_devices / connect 等真实解析逻辑照常运行（空输出 → 无设备），
    需要特定输出的测试再单独 monkeypatch `adb._run_async` 覆盖。
    """
    from app.engine import adb

    monkeypatch.setattr(adb, "_run_async", _mock_run_empty)


@pytest.fixture
def test_data_root() -> Path:
    """Absolute path of this session's isolated temp dir (for assertions)."""
    return _TEST_ROOT
