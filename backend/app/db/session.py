"""Async SQLAlchemy infrastructure (SQLite via aiosqlite).

M2+ uses this for Device / TaskConfig / Schedule / Setting tables
(see docs/architecture.md §4). Engine is created lazily on first use so that
pytest (conftest) can point DATABASE_URL at an isolated temp file first.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """Lazily create the global async engine (once per process)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            echo=False,
            # SQLite: wait for a busy lock instead of failing fast — the task
            # runner writes logs concurrently with API traffic (S-05).
            connect_args={"timeout": 30},
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Lazily create the session factory bound to the global engine."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, auto-close."""
    async with get_sessionmaker()() as session:
        yield session
