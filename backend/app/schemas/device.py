"""Pydantic DTOs for Device CRUD (C-01)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DeviceCreate(BaseModel):
    """Payload for adding a new ADB device."""

    name: str = Field(min_length=1, max_length=64)
    adb_host: str = Field(min_length=1, max_length=128)
    # 0 = USB/本地 serial 设备（如真机 USB 连接、emulator-5554），无端口
    adb_port: int = Field(default=5555, ge=0, le=65535)
    touch_mode: str = Field(default="Minitouch", pattern="^(Minitouch|MaaTouch|Adb)$")
    client_type: str = Field(default="Official", max_length=32)

    @field_validator("adb_host")
    @classmethod
    def _host_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("adb_host must not be blank")
        return v.strip()


class DeviceUpdate(BaseModel):
    """Partial update payload (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    adb_host: str | None = Field(default=None, min_length=1, max_length=128)
    adb_port: int | None = Field(default=None, ge=0, le=65535)
    touch_mode: str | None = Field(
        default=None, pattern="^(Minitouch|MaaTouch|Adb)$"
    )
    client_type: str | None = Field(default=None, max_length=32)


class DeviceRead(BaseModel):
    """Device representation returned to the API client."""

    id: int
    name: str
    adb_host: str
    adb_port: int
    touch_mode: str
    client_type: str
    status: str
    last_error: str | None = None
    last_online_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceConnectResult(BaseModel):
    """Result of connect/disconnect: updated device + human-readable message."""

    device: DeviceRead
    message: str


class DetectedDevice(BaseModel):
    """One device found by `adb devices -l` (from the /detect endpoint)."""

    serial: str
    state: str
    model: str = ""
    host: str
    port: int


class DeviceDetectResult(BaseModel):
    """Scan result: adb availability + discovered devices + engine info."""

    adb_available: bool
    adb_path: str | None = None
    adb_version: str | None = None
    reason: str | None = None  # set when adb_available is False
    devices: list[DetectedDevice] = []
    # MaaFw recognition engine availability (device still works with ADB only).
    engine_available: bool = False
    engine_version: str = "unavailable"


class ResolutionSetPayload(BaseModel):
    """Body of POST /devices/{id}/resolution — 目标宽高（MAA 推荐 16:9）。"""

    width: int = Field(ge=480, le=4096)
    height: int = Field(ge=480, le=4096)


class DeviceResolutionResult(BaseModel):
    """Resolution query/set/reset result."""

    device_id: int
    width: int | None = None
    height: int | None = None
    message: str = ""
