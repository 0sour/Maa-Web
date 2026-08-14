"""Maa-Web FastAPI application factory.

Mounts:
    /healthz/*       ← 3 probe endpoints (startup / ready / live)
    /api/v1/*        ← versioned REST API (v1 prefix, 预留 MaaFw 任务等)
    /api/v1/ws/*     ← versioned WebSocket API (M2+ for log streaming)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1.copilot import router as copilot_router
from app.api.v1.devices import router as devices_router
from app.api.v1.health import router as health_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.resources import router as resources_router
from app.api.v1.schedules import router as schedules_router
from app.api.v1.settings import router as settings_router
from app.api.v1.tasks import router as tasks_router
from app.core.config import get_settings
from app.core.events import on_shutdown, on_startup

# ── Structured logging (minimal MVP; M2+ adds JSON renderer + trace IDs) ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("maaweb.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: startup hooks → yield → shutdown hooks (drain contract)."""
    settings = get_settings()

    effective_key = await on_startup(settings)
    app.state.effective_secret_key = effective_key

    log.info(
        "%s v%s startup complete (env=%s, debug=%s)",
        settings.app_name,
        settings.app_version,
        settings.env,
        settings.debug,
    )

    try:
        yield
    finally:
        await on_shutdown()
        log.info("Maa-Web backend drained successfully.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Maa-Web Backend — Docker-deployable MaaFramework Web UI for NAS. "
            "Offers REST + WebSocket APIs to orchestrate Arknights daily tasks."
        ),
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── Middleware ──────────────────────────────────────────
    # CORS: NAS deployment is same-origin via nginx, but keep it permissive for
    # local dev (frontend on 5173, backend on 8000) and for any future ingress.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ─────────────────────────────────────────────
    # Health probes are top-level (not /api/v1) — they're ops endpoints.
    app.include_router(health_router, prefix="")
    app.include_router(devices_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(resources_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(copilot_router, prefix="/api/v1")
    app.include_router(schedules_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")

    # Root API info
    @app.get("/api", tags=["meta"])
    async def api_root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/api/docs",
            "v1_prefix": "/api/v1",
        }

    @app.get("/api/v1", tags=["meta"])
    async def api_v1_root() -> dict:
        return {
            "v1": True,
            "endpoints": {
                "health": "/healthz/{startup,ready,live}",
                "devices": "/api/v1/devices      (M2)",
                "tasks":   "/api/v1/tasks        (M2)",
                "ws-logs": "/api/v1/ws/logs      (M2)",
            },
        }

    return app


app = create_app()
