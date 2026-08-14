"""Pydantic-settings based configuration loader.

All tunables live as environment variables. Load order (env vars win):
    1. Defaults in the Settings class
    2. .env file (if present)
    3. OS environment variables

Docker-compose passes env vars directly (see docker-compose.yml).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Maa-Web runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Runtime ────────────────────────────────────────────
    app_name: str = "Maa-Web"
    app_version: str = "0.1.0"
    debug: bool = Field(default=False, alias="MAAWEB_DEBUG")
    env: str = Field(default="production", alias="MAAWEB_ENV")
    log_level: str = Field(default="INFO", alias="MAAWEB_LOG_LEVEL")

    # ── Security ───────────────────────────────────────────
    # Single-user bearer token. If empty a random 32-char key is generated at startup
    # and printed to the log once (for initial login).
    secret_key: str = Field(default="", alias="MAAWEB_SECRET_KEY")

    # CORS: frontend origin for local dev. Production served by same-origin nginx.
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        alias="MAAWEB_CORS_ORIGINS",
    )

    # ── Data paths (aligned with Docker volume mounts) ─────
    data_dir: Path = Field(default=Path("/data"))
    config_file: Path = Field(default=Path("/data/config/maaweb.db"))
    log_dir: Path = Field(default=Path("/data/logs"))
    cache_dir: Path = Field(default=Path("/data/cache"))
    media_dir: Path = Field(default=Path("/data/media"))
    maa_resource_dir: Path = Field(default=Path("/data/cache/maa-resource"))

    # ── Database ───────────────────────────────────────────
    # SQLite file-backed; trivial for <10 users single-instance NAS.
    database_url: str = Field(
        default="sqlite+aiosqlite:////data/config/maaweb.db",
        alias="DATABASE_URL",
    )

    # ── Server ─────────────────────────────────────────────
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # ── ADB / engine (M2) ──────────────────────────────────
    # Empty → auto-discover from PATH; set to a full path to pin a specific adb.
    adb_path: str = Field(default="", alias="MAAWEB_ADB_PATH")
    # Seconds before a single adb subprocess call is aborted.
    adb_command_timeout: float = Field(default=8.0, alias="MAAWEB_ADB_TIMEOUT")

    # ── MAA Asst engine (M2, 引擎切换) ───────────────────────
    # MAA 引擎包目录 = maa_resource_dir（官方发布包根目录：MaaCore 动态库 + resource/），
    # 由 S-07 资源包管理器下载安装，见 resource_mgr.py。

    # ── MAA engine pack (S-07 主动下载/更新) ─────────────────
    # 官方 release 资产平台：win-x64 | win-arm64 | linux-x86_64 | linux-aarch64。
    # 决定下载的资产名（zip / tar.gz）与引擎库名（MaaCore.dll / libMaaCore.so）。
    maa_resource_platform: str = Field(
        default="win-x64", alias="MAAWEB_RESOURCE_PLATFORM"
    )
    # 下载镜像前缀（逗号/换行分隔的多个 ghproxy 类镜像，如
    # "https://ghproxy.net/,https://ghfast.top/"），用法为「前缀 + 完整 GitHub
    # URL」；留空用官方 GitHub 直连。客户端并发 HEAD 测速择优 + 失败 fallback。
    maa_resource_mirror: str = Field(default="", alias="MAAWEB_RESOURCE_MIRROR")
    # GitHub API 查询与下载超时（秒）。
    maa_resource_api_timeout: float = Field(
        default=10.0, alias="MAAWEB_RESOURCE_API_TIMEOUT"
    )
    maa_resource_download_timeout: float = Field(
        default=300.0, alias="MAAWEB_RESOURCE_DL_TIMEOUT"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton loader — read once per process lifetime."""
    return Settings()
