"""Health check endpoints — strictly follow container-runtime spec.

Three probes (per Staff-Engineer container specialist):
  - /healthz/startup → Startup Probe:   "can the app begin serving at all?"
  - /healthz/ready   → Readiness Probe: "should we route traffic to this instance?"
  - /healthz/live    → Liveness Probe:  "is the event loop alive? (do NOT check deps)"

Hard rules:
  LIVENESS MUST NEVER CHECK EXTERNAL DEPENDENCIES.
    (Otherwise a simulator disconnect triggers a restart cascade.)
  READINESS MUST NOT CHECK ENGINE READINESS.
    (Engine pack download itself goes through this API; a readiness gate on
    the engine deadlocks first-boot — nginx waits for healthy, user can't
    reach the UI to download the pack. Found in D-08 on-machine verification.)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from fastapi import APIRouter, Response
from fastapi import status as http_status

from app.core.config import get_settings
from app.core.events import get_startup_status
from app.schemas.common import HealthStatus

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _engine_ready_live() -> bool:
    """实时探测 MAA Asst 引擎可用性（懒加载，包更新后无需重启即生效）。"""
    try:
        from app.engine import asstproxy

        return await asyncio.to_thread(asstproxy.is_available)
    except Exception:  # noqa: BLE001 - probe must never raise
        return False


def _free_mem_mb() -> int:
    """Best-effort free memory check (Linux /proc/meminfo). Return -1 if unknown."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    # e.g. "MemAvailable: 1234567 kB"
                    return int(line.split()[1]) // 1024
    except OSError:
        return -1
    return -1


@router.get(
    "/healthz/startup",
    response_model=HealthStatus,
    # NOTE: status_code set dynamically — 503 while starting, 200 when ready.
)
async def health_startup(response: Response) -> HealthStatus:
    """Startup probe: passed once, after which k8s/compose switches to liveness/readiness.

    Fails when:
      - required dirs not writable
      - MAA Asst engine（MaaCore + 资源包）不可用
    """
    settings = get_settings()
    checks = get_startup_status()
    engine_ok = await _engine_ready_live()

    all_ok = checks.get("dirs_created", False) and engine_ok

    status = "ok" if all_ok else "starting"
    message: str | None = None
    if not all_ok:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
        if not engine_ok:
            message = (
                "MAA Asst engine not ready — download the MAA engine pack via "
                "POST /api/v1/resources/update (MAAWEB_RESOURCE_PLATFORM)."
            )
        else:
            message = "Data directories not yet created / writable."

    checks = {**checks, "engine_ready": engine_ok}
    return HealthStatus(
        status=status,
        service="maaweb-api",
        version=settings.app_version,
        checks=checks,
        message=message,
    )


@router.get("/healthz/ready", response_model=HealthStatus)
async def health_ready(response: Response) -> HealthStatus:
    """Readiness probe: should ingress route traffic to us?

    首次部署语义（D-08 实机验证）：引擎包未下载（MAA Asst engine NOT
    ready）时也必须路由流量 —— WebUI「识别资源包」正是通过本 API 下载
    引擎包；若 ready 依赖引擎就绪，nginx 因 service_healthy 永不启动，
    形成部署死锁。引擎状态仅作诊断信息（checks.engine_ready）。

    Fails when:
      - startup not passed yet
      - free memory < 256MB (risk of OOM on next MaaFW job)
      - (M2 adds) deadlock task detected by AsstProxy watchdog
    """
    settings = get_settings()
    mem = _free_mem_mb()
    engine_ok = await _engine_ready_live()
    startup_ok = bool(get_startup_status().get("dirs_created", False))

    checks = {
        "startup_ok": startup_ok,
        "engine_ready": engine_ok,
        "free_mem_mb": mem,
    }
    mem_ok = mem == -1 or mem >= 256  # allow unknown (non-Linux) for local dev
    all_ok = startup_ok and mem_ok

    if not all_ok:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE

    message: str | None = None
    if not all_ok:
        if not startup_ok:
            message = "Application startup not completed (data dirs missing)."
        else:
            message = "Free memory below 256MB — OOM risk; wait for GC or increase NAS swap."

    return HealthStatus(
        status="ok" if all_ok else "degraded",
        service="maaweb-api",
        version=settings.app_version,
        checks=checks,
        message=message,
    )


@router.get("/healthz/live", response_model=HealthStatus)
async def health_live() -> HealthStatus:
    """Liveness probe: is the process alive?

    EXTREMELY conservative. Only checks process info + event loop sanity.
    NEVER checks DB, ADB, MaaFw init, network — that's READINESS's job.
    """
    settings = get_settings()
    checks = {
        "pid": os.getpid(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "event_loop": "running",  # we're inside an async handler → loop is alive, QED.
    }
    return HealthStatus(
        status="ok",
        service="maaweb-api",
        version=settings.app_version,
        checks=checks,
    )
