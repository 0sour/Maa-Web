"""Shared health & status DTOs."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """Standard health-check payload shared across all 3 probes."""

    status: str = Field(description="ok | starting | degraded | error")
    service: str
    version: str
    checks: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
