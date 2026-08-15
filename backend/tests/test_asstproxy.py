"""AsstProxy (MAA Asst 核心 / MaaCore 动态库) unit tests.

The adapter loads MaaCore via ctypes and drives the Asst C API. These tests
inject a FAKE lib object into `asstproxy._lib` (and stub `_ensure_loaded`) so
session lifecycle, pool logic, task mapping & callback parsing are covered
without the real native DLL.
"""
from __future__ import annotations

import json

import pytest

from app.engine import asstproxy
from app.engine.asstproxy import AsstSession, EngineCreateError, EngineUnavailableError
from app.models.device import Device
from app.schemas.task import TaskItem


class FakeLib:
    """Scripted stand-in for the ctypes MaaCore surface used by the adapter."""

    Callback = staticmethod(lambda func: func)  # 测试里直接透传 Python 回调

    def __init__(self, version: bytes = b"v6.16.6-test", create_result: int = 1001) -> None:
        self.version = version
        self.create_result = create_result
        self.create_calls: list = []
        self.destroyed: list = []
        self.connects: list = []
        self.instance_opts: list = []
        self.appended: list = []
        self.starts = 0
        self.stops = 0
        self.connect_result = True

    def AsstGetVersion(self) -> bytes:
        return self.version

    def AsstLoadResource(self, path: bytes) -> bool:
        return True

    def AsstCreateEx(self, cb, arg) -> int:
        self.create_calls.append((cb, arg))
        return self.create_result

    def AsstDestroy(self, ptr) -> None:
        self.destroyed.append(ptr)

    def AsstSetInstanceOption(self, ptr, key: int, value: bytes) -> bool:
        self.instance_opts.append((ptr, key, value))
        return True

    def AsstConnect(self, ptr, adb: bytes, address: bytes, cfg: bytes) -> bool:
        self.connects.append((ptr, adb, address, cfg))
        return self.connect_result

    def AsstAppendTask(self, ptr, ttype: bytes, params: bytes) -> int:
        self.appended.append((ttype, params))
        return 77

    def AsstStart(self, ptr) -> bool:
        self.starts += 1
        return True

    def AsstStop(self, ptr) -> bool:
        self.stops += 1
        return True

    def AsstRunning(self, ptr) -> bool:
        return True


def _install_fake(monkeypatch, **kwargs) -> FakeLib:
    lib = FakeLib(**kwargs)
    monkeypatch.setattr(asstproxy, "_lib", lib)
    monkeypatch.setattr(asstproxy, "_ensure_loaded", lambda: (True, ""))
    return lib


def _make_unavailable(monkeypatch, reason: str = "引擎包未安装") -> None:
    monkeypatch.setattr(asstproxy, "_ensure_loaded", lambda: (False, reason))


@pytest.fixture(autouse=True)
def _reset_pool():
    yield
    asstproxy._SESSION_POOL.clear()
    asstproxy.release()


@pytest.fixture
def device() -> Device:
    return Device(
        id=1, name="t", adb_host="127.0.0.1", adb_port=16384,
        touch_mode="Minitouch", client_type="Official", status="offline",
    )


# ── availability ────────────────────────────────────────────────────────

class TestAvailability:
    async def test_unavailable_when_engine_missing(self, monkeypatch):
        _make_unavailable(monkeypatch, "MAA 引擎包未安装：/x 下无 resource/")
        assert asstproxy.is_available() is False
        assert asstproxy.engine_version() == "unavailable"
        with pytest.raises(EngineUnavailableError):
            await AsstSession.create(Device(id=1, name="t", adb_host="h", adb_port=1), "adb")

    def test_available_after_fake_install(self, monkeypatch):
        _install_fake(monkeypatch)
        assert asstproxy.is_available() is True
        assert asstproxy.engine_version() == "v6.16.6-test"


# ── session lifecycle ───────────────────────────────────────────────────

class TestSessionLifecycle:
    async def test_create_connects_with_device_address(self, device, monkeypatch):
        lib = _install_fake(monkeypatch)
        session = await AsstSession.create(device, adb_path="/usr/bin/adb")
        assert isinstance(session, AsstSession)
        assert session.device_id == 1
        ptr, adb, address, cfg = lib.connects[-1]
        assert adb == b"/usr/bin/adb"
        assert address == b"127.0.0.1:16384"
        assert cfg == b"General"
        # touch_mode → InstanceOption (TouchMode key=2)
        assert lib.instance_opts[-1][1] == 2
        assert lib.instance_opts[-1][2] == b"minitouch"

    async def test_connect_false_raises_and_closes(self, device, monkeypatch):
        # AsstConnect false 时按失败处理：抛错且不残留会话（避免引擎异常状态崩溃）
        lib = _install_fake(monkeypatch)
        lib.connect_result = False
        with pytest.raises(EngineCreateError, match="连接设备失败"):
            await AsstSession.create(device, adb_path="adb")
        assert lib.destroyed  # 会话已销毁

    async def test_create_handle_failure_maps_to_error(self, device, monkeypatch):
        _install_fake(monkeypatch, create_result=0)
        with pytest.raises(EngineCreateError, match="AsstCreateEx"):
            await AsstSession.create(device, adb_path="/usr/bin/adb")

    async def test_create_connect_exception_maps_to_error(self, device, monkeypatch):
        lib = _install_fake(monkeypatch)

        def boom(*a, **k):
            raise RuntimeError("bad adb")
        lib.AsstConnect = boom
        with pytest.raises(EngineCreateError, match="bad adb"):
            await AsstSession.create(device, adb_path="/usr/bin/adb")

    async def test_append_task_serializes_params(self, device, monkeypatch):
        lib = _install_fake(monkeypatch)
        session = await AsstSession.create(device, adb_path="adb")
        task_id = session.append_task("Fight", {"stage": "CE-6", "times": 3})
        assert task_id == 77
        ttype, params = lib.appended[-1]
        assert ttype == b"Fight"
        assert '"CE-6"' in params.decode()

    def test_close_never_raises(self, monkeypatch):
        lib = _install_fake(monkeypatch)
        session = AsstSession(device_id=1, ptr=1, lib=lib, cb_ref=None)
        session.close()  # must not raise
        session.close()  # idempotent

    async def test_pool_create_and_close(self, device, monkeypatch):
        _install_fake(monkeypatch)
        session = await asstproxy.create_session(device, adb_path="/usr/bin/adb")
        assert asstproxy.session_count() == 1
        assert asstproxy._SESSION_POOL[1] is session
        asstproxy.close_session(1)
        assert asstproxy.session_count() == 0

    async def test_create_replaces_existing_session(self, device, monkeypatch):
        _install_fake(monkeypatch)
        await asstproxy.create_session(device, adb_path="/usr/bin/adb")
        session2 = await asstproxy.create_session(device, adb_path="/usr/bin/adb")
        assert asstproxy.session_count() == 1
        assert asstproxy._SESSION_POOL[1] is session2


# ── 回调解析（AsstMsg → emit / on_event） ───────────────────────────────

class TestCallbackParsing:
    def _session_with_handlers(self, monkeypatch) -> tuple[AsstSession, list, list]:
        lib = _install_fake(monkeypatch)
        session = AsstSession(device_id=1, ptr=1, lib=lib, cb_ref=None)
        emitted: list[tuple[str, str]] = []
        events: list[dict] = []
        session.set_handler(
            lambda level, msg: emitted.append((level, msg)),
            lambda ev: events.append(ev),
        )
        return session, emitted, events

    def test_taskchain_start_and_complete(self, monkeypatch):
        session, emitted, events = self._session_with_handlers(monkeypatch)
        session._dispatch(10001, b'{"taskchain":"Fight","taskid":1}')
        session._dispatch(10002, b'{"taskchain":"Fight","taskid":1}')
        assert events[0] == {"event": "task_start", "taskchain": "Fight", "taskid": 1}
        assert events[1]["event"] == "task_completed"
        assert ("info", "▶ 任务链 Fight 开始") in emitted
        assert ("ok", "✔ 任务链 Fight 完成") in emitted

    def test_taskchain_error_emits_error_event(self, monkeypatch):
        session, emitted, events = self._session_with_handlers(monkeypatch)
        session._dispatch(10000, b'{"taskchain":"Fight"}')
        assert events[0]["event"] == "task_error"
        assert ("error", "[任务链] Fight 执行错误") in emitted

    def test_all_tasks_completed(self, monkeypatch):
        session, emitted, events = self._session_with_handlers(monkeypatch)
        session._dispatch(3, b"")
        assert events == [{"event": "all_completed"}]

    def test_connection_info_mapping(self, monkeypatch):
        session, emitted, _ = self._session_with_handlers(monkeypatch)
        session._dispatch(2, b'{"what":"ConnectFailed"}')
        assert ("error", "[连接] 设备连接失败") in emitted
        session._dispatch(2, b'{"what":"Reconnecting"}')
        assert ("warn", "[连接] 连接中断，正在重连…") in emitted

    def test_stage_drops_extra_info(self, monkeypatch):
        session, emitted, _ = self._session_with_handlers(monkeypatch)
        details = json.dumps(
            {
                "what": "StageDrops",
                "details": {
                    "stage": {"stageCode": "CE-6"},
                    "stars": 3,
                    "drops": [{"itemName": "龙门币", "quantity": 10}],
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        session._dispatch(20003, details)
        assert any("CE-6" in m and "龙门币" in m for _, m in emitted)

    def test_malformed_details_is_safe(self, monkeypatch):
        session, emitted, events = self._session_with_handlers(monkeypatch)
        session._dispatch(3, b"{not json")
        assert events == [{"event": "all_completed"}]


# ── 任务参数映射 ────────────────────────────────────────────────────────

class TestToAsstTask:
    def test_recruit_legacy_key_mapped(self):
        item = TaskItem(
            name="公招", entry="Recruit", type="公招",
            params={"recruit_max_times": 4},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert ttype == "Recruit"
        assert params["times"] == 4
        assert "recruit_max_times" not in params
        assert params["select"]  # MAA 必填字段已补默认

    def test_infrast_facility_default(self):
        item = TaskItem(name="基建", entry="Infrast", type="基建", params={"mode": 0})
        ttype, params = asstproxy.to_asst_task(item)
        assert params["mode"] == 0
        assert "Mfg" in params["facility"]

    def test_fight_params_pass_through(self):
        item = TaskItem(
            name="刷理智", entry="Fight", type="刷理智",
            params={"stage": "CE-6", "medicine": 1, "times": 3, "series": 0},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert ttype == "Fight"
        assert params == {"stage": "CE-6", "medicine": 1, "times": 3, "series": 0}

    def test_startup_injects_client_type(self):
        item = TaskItem(name="启动游戏", entry="StartUp", type="启动游戏", params={})
        ttype, params = asstproxy.to_asst_task(item, client_type="Bilibili")
        assert ttype == "StartUp"
        assert params["client_type"] == "Bilibili"
        assert params["start_game_enabled"] is True

    def test_startup_keeps_explicit_client_type(self):
        item = TaskItem(
            name="启动游戏", entry="StartUp", type="启动游戏",
            params={"client_type": "YoStarEN"},
        )
        ttype, params = asstproxy.to_asst_task(item, client_type="Bilibili")
        assert params["client_type"] == "YoStarEN"

    def test_closedown_injects_client_type(self):
        item = TaskItem(name="关闭游戏", entry="CloseDown", type="关闭游戏", params={})
        ttype, params = asstproxy.to_asst_task(item, client_type="Bilibili")
        assert ttype == "CloseDown"
        assert params["client_type"] == "Bilibili"

    # ── 账号切换（自动任务账号轮换：StartUp/CloseDown 注入 account_name） ──

    def test_startup_injects_account_name(self):
        item = TaskItem(name="启动游戏", entry="StartUp", type="启动游戏", params={})
        ttype, params = asstproxy.to_asst_task(item, account_name="账号A")
        assert params["account_name"] == "账号A"

    def test_startup_keeps_explicit_account_name(self):
        item = TaskItem(
            name="启动游戏", entry="StartUp", type="启动游戏",
            params={"account_name": "显式账号"},
        )
        ttype, params = asstproxy.to_asst_task(item, account_name="账号A")
        assert params["account_name"] == "显式账号"

    def test_closedown_injects_account_name(self):
        item = TaskItem(name="关闭游戏", entry="CloseDown", type="关闭游戏", params={})
        ttype, params = asstproxy.to_asst_task(item, account_name="账号A")
        assert params["account_name"] == "账号A"

    def test_non_startup_ignores_account_name(self):
        item = TaskItem(name="刷理智", entry="Fight", type="刷理智", params={})
        ttype, params = asstproxy.to_asst_task(item, account_name="账号A")
        assert "account_name" not in params

    # ── Copilot 参数（对齐引擎 CopilotTask 键名） ─────────────────

    def test_copilot_legacy_auto_squad_mapped(self):
        item = TaskItem(
            name="自动战斗", entry="Copilot", type="抄作业",
            params={"auto_squad": True, "jobs": []},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert ttype == "Copilot"
        assert params["formation"] is True
        assert "auto_squad" not in params

    def test_copilot_mode_distributes_task_type(self):
        """作业场景分发：0/1 → Copilot，2 → ParadoxCopilot，3 → SSSCopilot（键剥离）。"""
        for mode, expected in ((0, "Copilot"), (1, "Copilot"), (2, "ParadoxCopilot"), (3, "SSSCopilot")):
            item = TaskItem(
                name="自动战斗", entry="Copilot", type="抄作业",
                params={"copilot_mode": mode, "jobs": []},
            )
            ttype, params = asstproxy.to_asst_task(item)
            assert ttype == expected
            assert "copilot_mode" not in params

    def test_copilot_user_additional_structured(self):
        item = TaskItem(
            name="自动战斗", entry="Copilot", type="抄作业",
            params={
                "formation": True,
                "add_user_additional": [{"name": "澄闪", "skill": 2}, {"name": "银灰"}],
                "jobs": [],
            },
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["user_additional"] == [{"name": "澄闪", "skill": 2}, {"name": "银灰", "skill": 0}]
        assert "add_user_additional" not in params

    def test_copilot_user_additional_legacy_strings(self):
        item = TaskItem(
            name="自动战斗", entry="Copilot", type="抄作业",
            params={"formation": True, "add_user_additional": ["澄闪", "银灰"], "jobs": []},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["user_additional"] == [{"name": "澄闪", "skill": 0}, {"name": "银灰", "skill": 0}]

    def test_copilot_formation_index_disabled_without_use_formation(self):
        item = TaskItem(
            name="自动战斗", entry="Copilot", type="抄作业",
            params={"formation": True, "use_formation": False, "formation_index": 2, "jobs": []},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["formation_index"] == 0

    def test_copilot_keeps_formation_index_when_use_formation(self):
        item = TaskItem(
            name="自动战斗", entry="Copilot", type="抄作业",
            params={"formation": True, "use_formation": True, "formation_index": 2, "jobs": []},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["formation_index"] == 2

    def test_copilot_extra_options_pass_through(self):
        item = TaskItem(
            name="自动战斗", entry="Copilot", type="抄作业",
            params={
                "formation": True, "use_sanity_potion": True, "loop_times": 3,
                "support_unit_usage": 2, "support_unit_name": "澄闪", "jobs": [],
            },
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["use_sanity_potion"] is True
        assert params["loop_times"] == 3
        assert params["support_unit_usage"] == 2
        assert params["support_unit_name"] == "澄闪"

    # ── Recruit 开关（对齐客户端 3 星 Tag 倾向 / 保留 Tag 启用开关） ──

    def test_recruit_prefer_tags_enabled_true_keeps_first_tags(self):
        item = TaskItem(
            name="公招", entry="Recruit", type="公招",
            params={"prefer_tags_enabled": True, "first_tags": ["近战位"], "confirm": [3, 4]},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["first_tags"] == ["近战位"]

    def test_recruit_prefer_tags_disabled_clears_first_tags(self):
        item = TaskItem(
            name="公招", entry="Recruit", type="公招",
            params={"prefer_tags_enabled": False, "first_tags": ["近战位"], "confirm": [3, 4]},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["first_tags"] == []

    def test_recruit_preserve_tags_disabled_clears_preserve_tags(self):
        item = TaskItem(
            name="公招", entry="Recruit", type="公招",
            params={"preserve_tags_enabled": False, "preserve_tags": ["支援机械"], "confirm": [3, 4]},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["preserve_tags"] == []

    def test_recruit_preserve_tags_enabled_true_keeps_preserve_tags(self):
        item = TaskItem(
            name="公招", entry="Recruit", type="公招",
            params={"preserve_tags_enabled": True, "preserve_tags": ["支援机械"], "confirm": [3, 4]},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["preserve_tags"] == ["支援机械"]

    def test_recruit_legacy_without_switch_keys_keeps_lists(self):
        # 旧数据无开关键：不触发清空，保留既有列表
        item = TaskItem(
            name="公招", entry="Recruit", type="公招",
            params={"first_tags": ["近战位"], "preserve_tags": ["支援机械"], "confirm": [3, 4]},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["first_tags"] == ["近战位"]
        assert params["preserve_tags"] == ["支援机械"]

    def test_recruit_force_refresh_passes_through(self):
        item = TaskItem(
            name="公招", entry="Recruit", type="公招",
            params={"refresh": True, "force_refresh": False, "confirm": [3, 4]},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["refresh"] is True
        assert params["force_refresh"] is False

    # ── Roguelike 种子门控（start_with_seed_enabled 开关） ──

    def test_roguelike_seed_disabled_drops_seed(self):
        item = TaskItem(
            name="肉鸽", entry="Roguelike", type="肉鸽",
            params={"theme": "JieGarden", "start_with_seed_enabled": False, "start_with_seed": "abc,rogue_6,3"},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert "start_with_seed" not in params

    def test_roguelike_seed_enabled_keeps_seed_string(self):
        item = TaskItem(
            name="肉鸽", entry="Roguelike", type="肉鸽",
            params={"theme": "JieGarden", "start_with_seed_enabled": True, "start_with_seed": "abc,rogue_6,3"},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["start_with_seed"] == "abc,rogue_6,3"


    def test_offline_confirm_emits_event(self):
        """引擎 OfflineConfirm 回调 → 结构化事件（供 runner 决定续刷/停止）。"""
        from app.engine.asstproxy import AsstSession

        events: list[dict] = []

        def on_event(ev: dict) -> None:
            events.append(ev)

        session = AsstSession(device_id=1, ptr=1, lib=None, cb_ref=None)
        session.set_handler(lambda _level, _msg: None, on_event)
        session._dispatch(20003, b'{"what": "OfflineConfirm", "details": {}}')
        assert events == [{"event": "offline_confirm"}]

    def test_fight_times_unlimited_stripped(self):
        """战斗次数 -1/0 = 不限（对齐 MAA 默认 int.MaxValue）：不下发，引擎默认 INT_MAX。"""
        for v in (-1, 0):
            item = TaskItem(
                name="刷理智", entry="Fight", type="刷理智",
                params={"stage": "CE-6", "times": v},
            )
            ttype, params = asstproxy.to_asst_task(item)
            assert ttype == "Fight"
            assert "times" not in params

    def test_fight_times_positive_kept(self):
        item = TaskItem(
            name="刷理智", entry="Fight", type="刷理智",
            params={"stage": "CE-6", "times": 3},
        )
        ttype, params = asstproxy.to_asst_task(item)
        assert params["times"] == 3
