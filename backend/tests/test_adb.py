"""ADB layer unit tests (app.engine.adb).

Covers: pure parsers (canned adb output), binary resolution, and the async
runner with a mocked subprocess seam. No real adb is required.
"""
from __future__ import annotations

import pytest

from app.engine import adb

# ── _split_serial ───────────────────────────────────────────────────────

class TestSplitSerial:
    def test_ipv4_with_port(self):
        assert adb._split_serial("127.0.0.1:16384") == ("127.0.0.1", 16384)

    def test_emulator_serial_is_local(self):
        # emulator-5554 是本地模拟器 serial，无需端口（port=0 = USB/本地设备）
        assert adb._split_serial("emulator-5554") == ("emulator-5554", 0)

    def test_usb_serial_kept_as_host(self):
        # USB 真机 serial（无冒号）→ host=serial, port=0（修复误识别为 127.0.0.1:5555）
        assert adb._split_serial("9b65ff77") == ("9b65ff77", 0)

    def test_hostname_with_port(self):
        assert adb._split_serial("nas.local:5555") == ("nas.local", 5555)


# ── parse_devices_output ────────────────────────────────────────────────

class TestParseDevices:
    def test_typical_output(self):
        out = (
            "List of devices attached\n"
            "127.0.0.1:16384\tdevice product:MuMu12 model:MuMu12 device:MuMu12 transport_id:3\n"
            "emulator-5554\toffline\n"
        )
        devices = adb.parse_devices_output(out)
        assert len(devices) == 2
        first = devices[0]
        assert first.serial == "127.0.0.1:16384"
        assert first.state == "device"
        assert first.model == "MuMu12"
        assert (first.host, first.port) == ("127.0.0.1", 16384)
        assert devices[1].state == "offline"

    def test_empty_and_header_only(self):
        assert adb.parse_devices_output("List of devices attached\n") == []
        assert adb.parse_devices_output("") == []

    def test_garbage_lines_skipped(self):
        out = "* daemon not running; starting now at tcp:5037\n* daemon started successfully\n"
        assert adb.parse_devices_output(out) == []


# ── parse_connect_output ────────────────────────────────────────────────

class TestParseConnect:
    @pytest.mark.parametrize(
        "out",
        [
            "connected to 127.0.0.1:16384",
            "already connected to 127.0.0.1:16384",
            "  connected to 127.0.0.1:16384  ",
        ],
    )
    def test_success_markers(self, out):
        ok, _ = adb.parse_connect_output(out)
        assert ok is True

    @pytest.mark.parametrize(
        "out",
        [
            "failed to connect to '127.0.0.1:16384': Connection refused",
            "cannot connect to 127.0.0.1:16384: Connection refused",
            "unable to connect to 127.0.0.1:16384",
        ],
    )
    def test_failure_markers(self, out):
        ok, msg = adb.parse_connect_output(out)
        assert ok is False
        assert msg  # message preserved for the UI

    def test_unknown_output_treated_as_failure(self):
        ok, msg = adb.parse_connect_output("daemon started successfully")
        assert ok is False
        assert "daemon" in msg


# ── resolve_adb_path ────────────────────────────────────────────────────

class TestResolvePath:
    def test_pinned_config_wins(self, monkeypatch):
        monkeypatch.setattr(adb.get_settings(), "adb_path", "C:/tools/adb.exe")
        monkeypatch.setattr(adb.shutil, "which", lambda p: "C:/tools/adb.exe" if p == "C:/tools/adb.exe" else None)
        assert adb.resolve_adb_path() == "C:/tools/adb.exe"

    def test_config_missing_raises(self, monkeypatch):
        monkeypatch.setattr(adb.get_settings(), "adb_path", "C:/nope/adb.exe")
        monkeypatch.setattr(adb.shutil, "which", lambda p: None)
        with pytest.raises(adb.AdbUnavailableError):
            adb.resolve_adb_path()

    def test_path_discovery(self, monkeypatch):
        monkeypatch.setattr(adb.get_settings(), "adb_path", "")
        monkeypatch.setattr(adb.shutil, "which", lambda p: "/usr/bin/adb" if p == "adb" else None)
        assert adb.resolve_adb_path() == "/usr/bin/adb"

    def test_not_found_raises(self, monkeypatch):
        monkeypatch.setattr(adb.get_settings(), "adb_path", "")
        monkeypatch.setattr(adb.shutil, "which", lambda p: None)
        with pytest.raises(adb.AdbUnavailableError) as exc:
            adb.resolve_adb_path()
        assert "adb" in str(exc.value)


# ── async runner / public API (mocked _run_async) ───────────────────────

class TestAsyncApi:
    @pytest.fixture(autouse=True)
    def _fake_adb_binary(self, monkeypatch):
        """All async API tests assume an adb binary is resolvable."""
        monkeypatch.setattr(adb, "resolve_adb_path", lambda: "/usr/bin/adb")

    async def test_connect_success(self, monkeypatch):
        async def fake_run(argv, timeout=None):
            assert argv[-1] == "127.0.0.1:16384"
            return "connected to 127.0.0.1:16384"
        monkeypatch.setattr(adb, "_run_async", fake_run)
        ok, msg = await adb.connect("127.0.0.1", 16384)
        assert ok is True
        assert "connected" in msg

    async def test_connect_refused(self, monkeypatch):
        async def fake_run(argv, timeout=None):
            return "cannot connect to 127.0.0.1:16384: Connection refused"
        monkeypatch.setattr(adb, "_run_async", fake_run)
        ok, msg = await adb.connect("127.0.0.1", 16384)
        assert ok is False
        assert "Connection refused" in msg

    async def test_connect_command_error_mapped(self, monkeypatch):
        async def fake_run(argv, timeout=None):
            raise adb.AdbCommandError("adb 命令失败 (exit=1): adb: error: device unauthorized")
        monkeypatch.setattr(adb, "_run_async", fake_run)
        ok, msg = await adb.connect("127.0.0.1", 16384)
        assert ok is False
        assert "unauthorized" in msg

    async def test_connect_usb_serial_skips_adb_connect(self, monkeypatch):
        # USB/本地 serial（port=0）在线（serial 在 adb 列表）→ 成功且不执行 adb connect
        called = False

        async def fake_run(argv, timeout=None):
            nonlocal called
            called = True
            return "9b65ff77\tdevice\n"
        monkeypatch.setattr(adb, "_run_async", fake_run)
        ok, msg = await adb.connect("9b65ff77", 0)
        assert ok is True
        assert called is True  # 仍会扫描 adb devices（校验在线）
        assert "无需 adb connect" in msg

    async def test_disconnect_usb_serial_skips_adb(self, monkeypatch):
        called = False

        async def fake_run(argv, timeout=None):
            nonlocal called
            called = True
            return "disconnected"
        monkeypatch.setattr(adb, "_run_async", fake_run)
        assert "无独立连接" in await adb.disconnect("9b65ff77", 0)
        assert called is False

    async def test_scan_devices(self, monkeypatch):
        async def fake_run(argv, timeout=None):
            return (
                "List of devices attached\n"
                "127.0.0.1:16384\tdevice product:MuMu12 model:MuMu12\n"
            )
        monkeypatch.setattr(adb, "_run_async", fake_run)
        found = await adb.scan_devices()
        assert len(found) == 1
        assert found[0].model == "MuMu12"
        assert (found[0].host, found[0].port) == ("127.0.0.1", 16384)

    async def test_scan_usb_device(self, monkeypatch):
        async def fake_run(argv, timeout=None):
            return (
                "List of devices attached\n"
                "9b65ff77\tdevice product:phoenix model:Redmi_K30 device:phoenix transport_id:4\n"
            )
        monkeypatch.setattr(adb, "_run_async", fake_run)
        found = await adb.scan_devices()
        assert len(found) == 1
        assert found[0].serial == "9b65ff77"
        assert found[0].is_usb is True
        assert (found[0].host, found[0].port) == ("9b65ff77", 0)
        assert found[0].address == "9b65ff77"

    async def test_disconnect(self, monkeypatch):
        async def fake_run(argv, timeout=None):
            return "disconnected 127.0.0.1:16384"
        monkeypatch.setattr(adb, "_run_async", fake_run)
        assert "disconnected" in await adb.disconnect("127.0.0.1", 16384)


# ── 分辨率（wm size） ───────────────────────────────────────────────────

class TestResolution:
    def test_parse_physical_size(self):
        assert adb.parse_wm_size("Physical size: 1080x2340\n") == (1080, 2340)

    def test_parse_override_size(self):
        # 调整分辨率后生效的是 Override size（Physical 为原始物理尺寸）
        assert adb.parse_wm_size("Physical size: 1080x2340\nOverride size: 1920x1080\n") == (1920, 1080)

    def test_parse_override_only(self):
        assert adb.parse_wm_size("Override size: 1280x720\n") == (1280, 720)

    def test_parse_unrecognized(self):
        assert adb.parse_wm_size("error: no devices\n") is None

    async def test_get_resolution(self, monkeypatch):
        async def fake_run(argv, timeout=None):
            assert argv == ["adb", "-s", "9b65ff77", "shell", "wm", "size"]
            return "Physical size: 1080x2340\n"
        monkeypatch.setattr(adb, "resolve_adb_path", lambda: "adb")
        monkeypatch.setattr(adb, "_run_async", fake_run)
        assert await adb.get_resolution("9b65ff77", 0) == (1080, 2340)

    async def test_set_resolution_uses_serial(self, monkeypatch):
        seen: list[list[str]] = []

        async def fake_run(argv, timeout=None):
            seen.append(argv)
            return ""
        monkeypatch.setattr(adb, "resolve_adb_path", lambda: "adb")
        monkeypatch.setattr(adb, "_run_async", fake_run)
        await adb.set_resolution("9b65ff77", 0, 1920, 1080)
        assert seen[-1] == ["adb", "-s", "9b65ff77", "shell", "wm", "size", "1920x1080"]

    async def test_reset_resolution(self, monkeypatch):
        seen: list[list[str]] = []

        async def fake_run(argv, timeout=None):
            seen.append(argv)
            return ""
        monkeypatch.setattr(adb, "resolve_adb_path", lambda: "adb")
        monkeypatch.setattr(adb, "_run_async", fake_run)
        await adb.reset_resolution("192.168.1.10", 5555)
        assert seen[-1] == ["adb", "-s", "192.168.1.10:5555", "shell", "wm", "size", "reset"]


# ── resolve_adb_path 优先级（设置页热更新 > .env > PATH） ────────────────

class TestResolvePathPriority:
    def test_runtime_settings_wins_over_env(self, monkeypatch):
        """设置页保存的 adb_path（runtime_settings.json）优先于 MAAWEB_ADB_PATH。"""
        import app.core.runtime_settings as rt

        monkeypatch.setattr(rt, "adb_path", lambda: "C:/rt/adb.exe")
        monkeypatch.setattr(adb.get_settings(), "adb_path", "C:/env/adb.exe")
        monkeypatch.setattr(adb.shutil, "which", lambda p: p if p in ("C:/rt/adb.exe", "C:/env/adb.exe") else None)
        assert adb.resolve_adb_path() == "C:/rt/adb.exe"

    def test_runtime_settings_invalid_raises(self, monkeypatch):
        """设置页路径无效 → 明确报错（不静默回退）。"""
        import app.core.runtime_settings as rt

        monkeypatch.setattr(rt, "adb_path", lambda: "C:/nope/adb.exe")
        monkeypatch.setattr(adb.get_settings(), "adb_path", "")
        monkeypatch.setattr(adb.shutil, "which", lambda p: None)
        with pytest.raises(adb.AdbUnavailableError, match="设置页配置的 ADB 路径无效"):
            adb.resolve_adb_path()

    def test_runtime_settings_unconfigured_falls_back(self, monkeypatch):
        """未在设置页配置（_configured 前）→ 回退 .env / PATH。"""
        import app.core.runtime_settings as rt

        monkeypatch.setattr(rt, "adb_path", lambda: "")
        monkeypatch.setattr(adb.get_settings(), "adb_path", "C:/env/adb.exe")
        monkeypatch.setattr(adb.shutil, "which", lambda p: "C:/env/adb.exe" if p == "C:/env/adb.exe" else None)
        assert adb.resolve_adb_path() == "C:/env/adb.exe"


# ── USB/本地设备 connect 校验（serial 必须在 adb devices 列表中） ─────────

class TestUsbConnectValidation:
    async def test_usb_connect_requires_online_serial(self, monkeypatch):
        """USB 设备 connect：serial 不在 adb 列表 → 失败 + 人话提示（拔线场景）。"""
        async def scan_empty():
            return []

        monkeypatch.setattr(adb, "scan_devices", scan_empty)
        ok, msg = await adb.connect("9b65ff77", 0)
        assert ok is False
        assert "不在线" in msg and "USB" in msg

    async def test_usb_connect_ok_when_serial_present(self, monkeypatch):
        """USB 设备在线（serial 在列表）→ 直接就绪。"""
        async def scan_with():
            return [adb.AdbDeviceInfo(serial="9b65ff77", state="device")]

        monkeypatch.setattr(adb, "scan_devices", scan_with)
        ok, msg = await adb.connect("9b65ff77", 0)
        assert ok is True
        assert "已就绪" in msg

    async def test_usb_connect_scan_failure_reports(self, monkeypatch):
        """扫描失败（adb 缺失）→ 明确报错而非假装在线。"""
        async def scan_fail():
            raise adb.AdbUnavailableError("no adb")

        monkeypatch.setattr(adb, "scan_devices", scan_fail)
        ok, msg = await adb.connect("9b65ff77", 0)
        assert ok is False
        assert "无法确认" in msg
