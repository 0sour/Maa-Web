"""Startup / shutdown lifecycle hooks.

Perform:
    1. Ensure required directories exist (even if volume not yet provisioned)
    2. Write SQLite DB parent dir (SQLite itself creates the .db file on first connect)
    3. Probe MAA Asst engine (MaaCore 动态库 + 资源包) → engine_ready 状态
"""
from __future__ import annotations

import logging
import secrets
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)

_STARTUP_CHECKS: dict[str, bool] = {
    "dirs_created": False,
    "engine_ready": None,  # None → not yet attempted; bool → success/failure
    "secret_key_generated": False,
}


def get_startup_status() -> dict[str, bool]:
    """Expose internal startup checks for /healthz/startup."""
    return dict(_STARTUP_CHECKS)


async def on_startup(settings: Settings) -> str:
    """Run startup tasks. Returns final effective SECRET_KEY (for logging)."""

    # 1) Ensure directory tree
    for p in (
        settings.data_dir,
        settings.config_file.parent,
        settings.log_dir,
        settings.cache_dir,
        settings.media_dir,
        settings.maa_resource_dir,
    ):
        Path(p).mkdir(parents=True, exist_ok=True)
    _STARTUP_CHECKS["dirs_created"] = True
    log.info("Data directories ensured under %s", settings.data_dir)

    # 2) Probe MAA Asst engine（MaaCore 动态库 + 资源包，懒加载）
    #    We probe inside the function (not at module-level) so that:
    #      - failures are visible through /healthz/startup and don't crash import-time
    #      - 引擎包未下载时后端仍可启动（UI 显示"引擎降级 · 仅 ADB"），下载后自动就绪
    try:
        from app.engine import asstproxy

        _STARTUP_CHECKS["engine_ready"] = asstproxy.is_available()
        if _STARTUP_CHECKS["engine_ready"]:
            log.info("MAA Asst engine ready (version=%s)", asstproxy.engine_version())
        else:
            log.warning(
                "MAA Asst engine NOT ready — 请通过「识别资源包」下载 MAA 引擎包 "
                "（MAAWEB_RESOURCE_PLATFORM=%s）",
                settings.maa_resource_platform,
            )
    except Exception as exc:  # noqa: BLE001 - pragma: no cover - very env-specific
        _STARTUP_CHECKS["engine_ready"] = False
        log.warning("MAA Asst engine probe failed: %s", exc)

    # 3) Create database tables (SQLite via aiosqlite)
    try:
        from app.db.session import get_engine, get_sessionmaker
        from app.models import (
            auto_task as _auto_task_models,  # noqa: F401  (registers AutoTask/Slot/Account)
        )
        from app.models import (
            notify as _notify_models,  # noqa: F401  (registers NotifyLog)
        )
        from app.models import (
            schedule as _schedule_models,  # noqa: F401  (registers ScheduleJob, legacy)
        )
        from app.models import (
            setting as _setting_models,  # noqa: F401  (registers Setting)
        )
        from app.models import (
            task as _task_models,  # noqa: F401  (registers TaskRun/LogEntry)
        )
        from app.models import (
            toolbox as _toolbox_models,  # noqa: F401  (registers ToolboxRecord)
        )
        from app.models.device import Base  # noqa: F401  (registers Device)

        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # 轻量 schema 升级（无 alembic）：新列 ALTER + 旧定时任务数据迁移
        await _upgrade_schema(get_sessionmaker)
        log.info("Database tables ensured (devices, task_runs, log_entries, settings, auto_tasks)")
    except Exception as exc:  # noqa: BLE001 - pragma: no cover - env-specific (e.g. unwritable dir)
        log.warning("Database init failed: %s", exc)

    # 3.5) Start minute-level scheduler（定时执行，M6）
    try:
        from app.engine.scheduler import scheduler

        scheduler.start()
    except Exception as exc:  # noqa: BLE001 - scheduler failure must not block startup
        log.warning("Scheduler start failed: %s", exc)

    # 4) Resolve single-user secret key
    effective_key = settings.secret_key.strip()
    if not effective_key:
        effective_key = secrets.token_urlsafe(32)
        _STARTUP_CHECKS["secret_key_generated"] = True
        # IMPORTANT: print (not log) so user sees it even if logging is silenced
        print("\n" + "=" * 72)
        print(" Maa-Web · Auto-generated single-user SECRET_KEY (save this!):")
        print(f"   MAAWEB_SECRET_KEY={effective_key}")
        print(" Next startup: pass this value via env to avoid generating a new one.")
        print("=" * 72 + "\n", flush=True)
    else:
        _STARTUP_CHECKS["secret_key_generated"] = False

    return effective_key


async def _upgrade_schema(sessionmaker) -> None:
    """轻量 schema 升级（无 alembic，SQLite 场景）。

    1. log_entries 缺 source 列 → ALTER 补列（默认 normal，旧行归普通任务）。
    2. 旧 schedule_jobs 有数据且 auto_tasks 为空 → 迁移为「旧定时任务」组：
       每 job 一个时间槽（名称/星期/时间/启停保留，冲突默认 queue），
       账号列表为空（旧定时任务无账号概念，需用户在自动任务页补账号）。
    """
    from sqlalchemy import func, select, text

    from app.db.session import get_engine
    from app.models.auto_task import AutoSlot, AutoTask
    from app.models.schedule import ScheduleJob

    engine = get_engine()
    async with engine.begin() as conn:
        cols = (await conn.execute(text("PRAGMA table_info(log_entries)"))).all()
        if not any(c[1] == "source" for c in cols):
            await conn.execute(
                text(
                    "ALTER TABLE log_entries "
                    "ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'normal'"
                )
            )
            log.info("schema upgrade: log_entries.source added")

    async with sessionmaker()() as s:
        old = (await s.execute(select(ScheduleJob))).scalars().all()
        if not old:
            return
        new_count = (await s.execute(select(func.count(AutoTask.id)))).scalar()
        if new_count:
            return
        by_device: dict[int, list[ScheduleJob]] = {}
        for job in old:
            by_device.setdefault(job.device_id, []).append(job)
        for device_id, jobs in by_device.items():
            task = AutoTask(name="旧定时任务", enabled=True, device_id=device_id)
            s.add(task)
            await s.flush()
            for job in jobs:
                s.add(
                    AutoSlot(
                        task_id=task.id,
                        name=job.name or "旧定时任务",
                        enabled=job.enabled,
                        weekdays=job.weekdays,
                        time=job.time,
                        conflict="queue",
                    )
                )
        await s.commit()
        log.warning(
            "schema upgrade: migrated %d legacy schedule_jobs → auto_tasks "
            "(账号列表为空，请在自动任务页为各时间槽添加账号)",
            len(old),
        )


async def on_shutdown() -> None:
    """Graceful shutdown — drain contract placeholder.

    M2 will:
      1. Stop accepting new requests (FastAPI already does this in uvicorn shutdown)
      2. Tell AsstProxy to AsstStop() any running pipeline
      3. Persist interrupted tasks to SQLite
    """
    try:
        from app.engine.scheduler import scheduler

        await scheduler.stop()
    except Exception:  # noqa: BLE001 - best-effort shutdown
        pass
    log.info("Shutdown signal received: draining Maa-Web backend.")
