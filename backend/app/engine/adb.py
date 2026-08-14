"""ADB integration layer (M2, real engine).

Wraps the `adb` platform-tools binary via subprocess (run in a thread so the
event loop never blocks). Every flow is split into a **pure parser** (testable
with canned output) and a **runner** (thin subprocess glue).

Degradation contract (docs/testing.md R9-style):
  - adb binary missing           → AdbUnavailableError (caller maps to status=error)
  - command fails / times out    → AdbCommandError (caller maps to status=error)
No exception is swallowed here — the engine manager decides the device status.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass

from app.core.config import get_settings

log = logging.getLogger(__name__)

DEFAULT_ADB_PORT = 5555


class AdbUnavailableError(RuntimeError):
    """adb binary could not be located (not on PATH and not configured)."""


class AdbCommandError(RuntimeError):
    """adb ran but returned a non-success / unparseable result."""


@dataclass
class AdbDeviceInfo:
    """One entry from `adb devices -l`."""

    serial: str          # e.g. "127.0.0.1:16384" / "emulator-5554" / USB serial "9b65ff77"
    state: str           # device | offline | unauthorized | ...
    model: str = ""      # product/model from the -l extra columns
    host: str = "127.0.0.1"
    port: int = DEFAULT_ADB_PORT

    @property
    def is_usb(self) -> bool:
        """USB 直连或本地模拟器 serial（无 host:port 形式，无需 adb connect）。"""
        return self.port <= 0

    @property
    def address(self) -> str:
        return self.host if self.is_usb else f"{self.host}:{self.port}"


def _split_serial(serial: str) -> tuple[str, int]:
    """'127.0.0.1:16384' → ('127.0.0.1', 16384); 'emulator-5554' → ('emulator-5554', 0).

    USB 真机 serial（如 '9b65ff77'，无冒号）→ (serial, 0)：port=0 表示本地设备，
    无需 `adb connect`，AsstConnect 直接以 serial 作为地址。
    """
    if ":" in serial and not serial.startswith("["):  # IPv4:port or host:port
        host, _, port = serial.rpartition(":")
        if port.isdigit():
            return host, int(port)
    if serial:
        return serial, 0
    return "127.0.0.1", DEFAULT_ADB_PORT


# ── Pure parsers (unit-tested with canned adb output) ───────────────────

def parse_devices_output(text: str) -> list[AdbDeviceInfo]:
    """Parse `adb devices -l` stdout → list[AdbDeviceInfo].

    Lines:  <serial>\t<state>  [product:... model:... device:... transport_id:...]
    Blank/comment lines and the header are skipped.
    """
    devices: list[AdbDeviceInfo] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("List of"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        model = ""
        for token in parts[2:]:
            if token.startswith("model:"):
                model = token.split(":", 1)[1]
                break
        host, port = _split_serial(serial)
        devices.append(
            AdbDeviceInfo(serial=serial, state=state, model=model, host=host, port=port)
        )
    return devices


def parse_connect_output(text: str) -> tuple[bool, str]:
    """Parse `adb connect <addr>` stdout → (ok, message).

    Success markers: "connected to", "already connected".
    Failure markers: "cannot connect", "failed to connect", "refused", "unable".
    """
    msg = " ".join(text.split()).strip()
    low = msg.lower()
    if "connected to" in low or "already connected" in low:
        return True, msg or "connected"
    if any(m in low for m in ("cannot connect", "failed to connect", "refused", "unable to")):
        return False, msg or "connect failed"
    # Unrecognised output → treat as failure (be conservative, surface the raw text).
    return False, msg or "unknown adb connect result"


# ── Runner helpers ──────────────────────────────────────────────────────

def resolve_adb_path() -> str:
    """Locate the adb binary. Order: runtime_settings(设置页热更新) → MAAWEB_ADB_PATH → PATH search → error."""
    # 设置页「连接设置」保存的路径（runtime_settings.json，热更新，优先级最高）
    from app.core import runtime_settings

    rt_path = runtime_settings.adb_path()
    if rt_path:
        if shutil.which(rt_path):
            return rt_path
        raise AdbUnavailableError(f"设置页配置的 ADB 路径无效: {rt_path}")
    cfg = get_settings().adb_path.strip()
    if cfg:
        if shutil.which(cfg):
            return cfg
        raise AdbUnavailableError(f"ADB_PATH 配置的路径无效: {cfg}")
    found = shutil.which("adb")
    if found:
        return found
    raise AdbUnavailableError(
        "未找到 adb 可执行文件：请安装 Android platform-tools 并加入 PATH，"
        "或通过 MAAWEB_ADB_PATH 指定完整路径"
    )


def _run(argv: list[str], timeout: float | None = None) -> str:
    """Run a command synchronously, capture stdout. Raises on non-zero exit."""
    settings = get_settings()
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout or settings.adb_command_timeout,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise AdbCommandError(f"adb 命令失败 (exit={proc.returncode}): {err}")
    return proc.stdout or ""


async def _run_async(argv: list[str], timeout: float | None = None) -> str:
    """Threaded async wrapper so the event loop is never blocked by adb."""
    return await asyncio.to_thread(_run, argv, timeout)


# ── Public async API (used by engine manager / devices router) ──────────

async def adb_version() -> str:
    """Return `adb version` first line, or 'unknown'."""
    path = resolve_adb_path()
    try:
        out = await _run_async([path, "version"], timeout=10)
    except AdbCommandError:
        return "unknown"
    first = out.strip().splitlines()[0] if out.strip() else "unknown"
    return first


async def scan_devices() -> list[AdbDeviceInfo]:
    """Run `adb devices -l` and return parsed devices (empty list if none)."""
    path = resolve_adb_path()
    out = await _run_async([path, "devices", "-l"])
    return parse_devices_output(out)


async def connect(host: str, port: int = DEFAULT_ADB_PORT) -> tuple[bool, str]:
    """`adb connect host:port` → (ok, message)。

    USB / 本地模拟器 serial（port<=0）已在 adb 列表中，无需（也无法）connect，
    但仍会**校验设备当前是否真实在线**（serial 不在 `adb devices -l` 中 = 已断开）。
    """
    if port <= 0:
        try:
            found = await scan_devices()
        except (AdbUnavailableError, AdbCommandError) as exc:
            return False, f"无法确认设备 {host} 在线状态: {exc}"
        if not any(d.serial == host for d in found):
            return False, f"设备 {host} 不在线（USB 已断开？请检查连接线/调试授权）"
        return True, f"{host} 为 USB/本地设备，已就绪（无需 adb connect）"
    path = resolve_adb_path()
    address = f"{host}:{port}"
    try:
        out = await _run_async([path, "connect", address])
    except AdbCommandError as exc:
        return False, str(exc)
    ok, msg = parse_connect_output(out)
    if ok:
        log.info("adb connect ok %s", address)
    else:
        log.warning("adb connect failed %s: %s", address, msg)
    return ok, msg


async def disconnect(host: str, port: int = DEFAULT_ADB_PORT) -> str:
    """`adb disconnect host:port` → message. USB 设备无连接可断，直接返回。"""
    if port <= 0:
        return "USB/本地设备无独立连接"
    path = resolve_adb_path()
    address = f"{host}:{port}"
    try:
        out = await _run_async([path, "disconnect", address])
    except AdbCommandError as exc:
        log.warning("adb disconnect error %s: %s", address, exc)
        return str(exc)
    return out.strip() or "disconnected"


# ── 设备分辨率（MAA 需要 16:9 固定分辨率，真机需临时调整后复位） ─────────

def serial_of(host: str, port: int) -> str:
    """adb -s 使用的设备标识：USB/本地 serial 直接用 serial，否则 host:port。"""
    return host if port <= 0 else f"{host}:{port}"


async def shell(host: str, port: int, command: list[str]) -> str:
    """`adb -s <serial> shell <command>` → stdout（失败抛 AdbCommandError）。"""
    path = resolve_adb_path()
    argv = [path, "-s", serial_of(host, port), "shell", *command]
    return await _run_async(argv)


def parse_wm_size(text: str) -> tuple[int, int] | None:
    """`adb shell wm size` 输出 → (宽, 高)。

    优先取 Override size（wm size 调整后的生效值），无则取物理尺寸。
    """
    override = re.search(r"Override size:\s*(\d+)x(\d+)", text)
    if override:
        return int(override.group(1)), int(override.group(2))
    physical = re.search(r"Physical size:\s*(\d+)x(\d+)", text)
    if physical:
        return int(physical.group(1)), int(physical.group(2))
    return None


async def get_resolution(host: str, port: int) -> tuple[int, int] | None:
    """查询设备当前分辨率（wm size 物理/覆盖尺寸）。"""
    out = await shell(host, port, ["wm", "size"])
    return parse_wm_size(out)


async def set_resolution(host: str, port: int, width: int, height: int) -> str:
    """临时调整分辨率：`wm size WxH`。

    MAA 仅支持 16:9 / 9:16（≥720p）。模拟器横屏用 1920x1080 / 1280x720 /
    2560x1440；竖屏真机按「短边×长边」用 1080x1920 / 720x1280。
    """
    out = await shell(host, port, ["wm", "size", f"{width}x{height}"])
    return (out or f"已设置分辨率 {width}x{height}").strip()


async def reset_resolution(host: str, port: int) -> str:
    """恢复设备原始分辨率：`wm size reset`。"""
    out = await shell(host, port, ["wm", "size", "reset"])
    return (out or "已重置分辨率").strip()
