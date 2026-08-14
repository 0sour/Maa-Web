"""TaskRunner (S-01) unit tests — serial queue state machine + real-engine bridge.

The MAA Asst surface (session.append_task / session.start / session.stop /
session.set_handler) is injected as fakes that replay AsstMsg-style events;
`_resource_ready` is stubbed so tests never touch the disk.
Covers R13 (task queue) + R14 (stop semantics) from docs/testing.md.
"""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.engine import adb, asstproxy, taskrunner
from app.engine.taskrunner import (
    ERROR,
    FINISHED,
    IDLE,
    RUNNING,
    STOPPED,
    STOPPING,
    TaskQueueError,
    TaskRunner,
)
from app.models.device import Device
from app.models.task import LogEntry, TaskRun
from app.schemas.task import TaskItem

# ── Fake MAA Asst session (replays AsstMsg events) ───────────────────────

class FakeSession:
    def __init__(self, succeed: bool = True, gate: threading.Event | None = None) -> None:
        self.succeed = succeed
        self._gate = gate
        self.handler: tuple | None = None
        self.appended: list[tuple[str, dict]] = []
        self.started = False
        self.stopped = False
        self.append_result = 7  # 非 0 = 添加成功

    def set_handler(self, emit, on_event=None) -> None:
        self.handler = (emit, on_event)

    def append_task(self, ttype: str, params: dict) -> int:
        self.appended.append((ttype, params))
        return self.append_result

    def start(self) -> bool:
        """模拟引擎执行：按入队顺序回放 TaskChain + AllTasksCompleted。"""
        self.started = True
        emit, on_event = self.handler
        for ttype, _ in self.appended:
            on_event({"event": "task_start", "taskchain": ttype})
            emit("info", f"▶ 任务链 {ttype} 开始")
        if self._gate is not None:
            self._gate.wait(timeout=5)
        for ttype, _ in self.appended:
            if self.succeed:
                on_event({"event": "task_completed", "taskchain": ttype})
                emit("ok", f"✔ 任务链 {ttype} 完成")
            else:
                on_event({"event": "task_error", "taskchain": ttype})
                emit("error", f"✖ 任务链 {ttype} 执行错误")
        on_event({"event": "all_completed"})
        emit("ok", "── 全部任务完成 ──")
        return True

    def stop(self) -> bool:
        """模拟引擎异步停止：稍后才回发 AllTasksCompleted（同真实 AsstStop）。"""
        self.stopped = True

        def _later() -> None:
            time.sleep(0.15)
            try:
                if self.handler and self.handler[1]:
                    self.handler[1]({"event": "all_completed"})
            except Exception:  # noqa: BLE001 - 测试循环可能已关闭
                pass

        threading.Thread(target=_later, daemon=True).start()
        return True


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_runners():
    """TaskRunner caches instances per device — reset between tests."""
    yield
    TaskRunner._runners.clear()


@pytest.fixture
def device() -> Device:
    return Device(
        id=1, name="t", adb_host="127.0.0.1", adb_port=16384,
        touch_mode="Minitouch", client_type="Official", status="online",
    )


@pytest.fixture
async def engine_env(monkeypatch, tmp_path):
    """Wire the runner to fakes; returns a mutable holder for the fake session.

    Holder keys: session (live FakeSession), succeed, gate, append_result.
    create_session and get_session both resolve to the same instance, so
    `stop()` can reach the fake session's stop (mirrors the real session pool).
    Also ensures the task tables exist (standalone run, no client fixture).
    """
    from app.db.session import get_engine
    from app.models import task as _task_models  # noqa: F401  (registers tables)
    from app.models.device import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    holder: dict = {
        "session": None, "succeed": True, "gate": None, "append_result": 7,
    }

    async def _create(*a, **k):
        session = FakeSession(
            succeed=holder["succeed"],
            gate=holder["gate"],
        )
        session.append_result = holder["append_result"]
        holder["session"] = session
        return session

    monkeypatch.setattr(asstproxy, "is_available", lambda: True)
    monkeypatch.setattr(asstproxy, "create_session", _create)
    monkeypatch.setattr(asstproxy, "get_session", lambda device_id: holder["session"])

    monkeypatch.setattr(taskrunner, "_resource_ready", lambda: (True, str(tmp_path)))
    return holder


async def _wait_done(runner: TaskRunner, timeout: float = 5.0) -> None:
    """Block until the worker coroutine finishes (or timeout)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while runner._worker is not None and loop.time() < deadline:
        await asyncio.sleep(0.01)
    assert runner._worker is None, "worker did not finish in time"


def _tasks(*names: str) -> list[TaskItem]:
    return [
        TaskItem(name=n, entry=n.upper(), type=n, params={"stage": "CE-6"})
        for n in names
    ]


# ── Precondition failures (R13) ──────────────────────────────────────────

class TestPreconditions:
    async def test_device_offline_rejected(self, device, engine_env):
        device.status = "offline"
        with pytest.raises(TaskQueueError, match="未连接"):
            await TaskRunner.get(1).start(device, _tasks("刷理智"))

    async def test_engine_unavailable_rejected(self, device, monkeypatch):
        monkeypatch.setattr(asstproxy, "is_available", lambda: False)
        with pytest.raises(TaskQueueError, match="引擎不可用"):
            await TaskRunner.get(1).start(device, _tasks("刷理智"))

    async def test_resource_missing_rejected(self, device, engine_env, monkeypatch):
        monkeypatch.setattr(taskrunner, "_resource_ready", lambda: (False, "MAA 引擎包缺失：/x"))
        with pytest.raises(TaskQueueError, match="引擎包"):
            await TaskRunner.get(1).start(device, _tasks("刷理智"))

    async def test_unsupported_resolution_rejected(self, device, engine_env, monkeypatch):
        """非 16:9/9:16（如 20:9 全面屏）→ 启动前给出明确引导，而非模糊的引擎连接失败。"""
        async def _res(*a, **k):
            return (1080, 2400)

        monkeypatch.setattr(adb, "get_resolution", _res)
        with pytest.raises(TaskQueueError, match="16:9 / 9:16"):
            await TaskRunner.get(1).start(device, _tasks("刷理智"))

    async def test_resolution_hint_suggests_emulator_1920(self, device, engine_env, monkeypatch):
        """模拟器（host:port）提示用 1920x1080。"""
        async def _res(*a, **k):
            return (1080, 2400)

        monkeypatch.setattr(adb, "get_resolution", _res)
        with pytest.raises(TaskQueueError, match="1920x1080"):
            await TaskRunner.get(1).start(device, _tasks("刷理智"))

    async def test_usb_device_hint_suggests_1080x1920(self, engine_env, monkeypatch):
        """竖屏真机（USB serial, port<=0）提示用 1080x1920。"""
        usb = Device(
            id=1, name="usb", adb_host="9b65ff77", adb_port=0,
            touch_mode="Adb", client_type="Official", status="online",
        )
        async def _res(*a, **k):
            return (1080, 2400)

        monkeypatch.setattr(adb, "get_resolution", _res)
        with pytest.raises(TaskQueueError, match="1080x1920"):
            await TaskRunner.get(1).start(usb, _tasks("刷理智"))

    async def test_supported_9x16_resolution_passes(self, device, engine_env, monkeypatch):
        """1080x1920（9:16 竖屏）通过预检并正常启动。"""
        async def _res(*a, **k):
            return (1080, 1920)

        monkeypatch.setattr(adb, "get_resolution", _res)
        runner = TaskRunner.get(1)
        await runner.start(device, _tasks("刷理智"))
        assert runner.status == RUNNING
        await _wait_done(runner)
        assert runner.status == FINISHED

    def test_is_maa_aspect_ratio(self):
        assert taskrunner._is_maa_aspect_ratio(1920, 1080)
        assert taskrunner._is_maa_aspect_ratio(1080, 1920)
        assert taskrunner._is_maa_aspect_ratio(1280, 720)
        assert not taskrunner._is_maa_aspect_ratio(1080, 2400)

    async def test_append_failure_sets_error(self, device, engine_env):
        engine_env["append_result"] = 0  # MAA 拒绝该任务参数
        runner = TaskRunner.get(1)
        await runner.start(device, _tasks("刷理智"))
        await _wait_done(runner)

        assert runner.status == ERROR
        assert "添加失败" in (runner.error or "")

    async def test_double_start_rejected(self, device, engine_env):
        engine_env["gate"] = threading.Event()
        runner = TaskRunner.get(1)
        await runner.start(device, _tasks("刷理智"))
        assert runner.status == RUNNING
        with pytest.raises(TaskQueueError, match="正在运行"):
            await runner.start(device, _tasks("刷理智"))
        engine_env["gate"].set()
        await _wait_done(runner)


# ── Happy path (R13) ─────────────────────────────────────────────────────

class TestHappyPath:
    async def test_run_finished_persists_run_and_logs(self, device, engine_env):
        runner = TaskRunner.get(1)
        run = await runner.start(device, _tasks("刷理智", "公开招募"))
        assert run.status == RUNNING
        assert runner.status == RUNNING
        await _wait_done(runner)

        assert runner.status == FINISHED
        assert runner.error is None
        assert runner.run_id == run.id

        from sqlalchemy import select as sa_select

        from app.db.session import get_sessionmaker
        async with get_sessionmaker()() as s:
            saved = await s.get(TaskRun, run.id)
            assert saved is not None
            assert saved.status == FINISHED
            assert saved.finished_at is not None
            assert "刷理智" in saved.summary

            log_rows = (await s.execute(sa_select(LogEntry).where(LogEntry.run_id == run.id))).scalars().all()
        messages = " ".join(entry.message for entry in log_rows)
        assert "▶ 入队 刷理智" in messages
        assert "✔ 任务链 刷理智 完成" in messages
        assert "✔ 任务链 公开招募 完成" in messages
        assert "全部任务完成" in messages

    async def test_task_failure_sets_error(self, device, engine_env):
        engine_env["succeed"] = False
        runner = TaskRunner.get(1)
        await runner.start(device, _tasks("刷理智"))
        await _wait_done(runner)

        assert runner.status == ERROR
        assert "失败" in (runner.error or "")


# ── Stop semantics (R14) ─────────────────────────────────────────────────

class TestStop:
    async def test_stop_marks_stopped(self, device, engine_env):
        engine_env["gate"] = threading.Event()
        runner = TaskRunner.get(1)
        await runner.start(device, _tasks("刷理智"))
        await asyncio.sleep(0.05)  # let the worker reach start()/gate wait
        assert runner.status == RUNNING

        await runner.stop()
        assert runner.status == STOPPING
        engine_env["gate"].set()  # release the fake engine → all_completed
        await _wait_done(runner)

        assert runner.status == STOPPED

    async def test_stop_when_idle_is_noop(self, device):
        runner = TaskRunner.get(1)
        await runner.stop()
        assert runner.status == IDLE

    async def test_status_snapshot(self, device, engine_env):
        runner = TaskRunner.get(1)
        status = runner.snapshot(device_online=True, engine_available=True)
        assert status.device_id == 1
        assert status.status == IDLE
        assert status.device_online is True
        assert status.engine_available is True
        assert status.resource_ready is True


# ── Copilot 多作业展开（作业集：勾选启用的作业逐个执行） ─────────────────

class TestCopilotJobs:
    def _copilot(self, jobs: list[dict]) -> TaskItem:
        return TaskItem(
            name="自动战斗",
            entry="Copilot",
            type="抄作业",
            params={"filename": "", "stage_name": "", "copilot_mode": 0, "jobs": jobs},
        )

    # ── 纯函数 _expand_copilot_jobs ─────────────────────────

    def test_non_copilot_returns_none(self):
        assert taskrunner._expand_copilot_jobs("Fight", {"jobs": [{}]}) is None
        assert taskrunner._expand_copilot_jobs("Copilot", {"stage": "CE-6"}) is None

    def test_expand_enabled_jobs(self):
        jobs = [
            {"filename": "copilot/a.json", "stage_name": "EX1", "enabled": True},
            {"filename": "copilot/b.json", "stage_name": "EX2", "enabled": True},
            {"filename": "copilot/c.json", "stage_name": "EX3", "enabled": False},
        ]
        out = taskrunner._expand_copilot_jobs("Copilot", {"filename": "", "jobs": jobs})
        assert out is not None and len(out) == 2
        filenames = [pp["filename"] for _, pp in out]
        assert filenames == ["copilot/a.json", "copilot/b.json"]
        # jobs 键剔除，避免引擎收到未知字段
        assert all("jobs" not in pp for _, pp in out)
        assert out[0][1]["stage_name"] == "EX1"

    def test_expand_all_disabled_returns_empty(self):
        jobs = [{"filename": "copilot/a.json", "stage_name": "", "enabled": False}]
        assert taskrunner._expand_copilot_jobs("Copilot", {"jobs": jobs}) == []

    # ── 集成：一个 Copilot 任务拆成多个 append ─────────────────

    async def test_copilot_jobs_append_multiple(self, device, engine_env):
        runner = TaskRunner.get(1)
        await runner.start(
            device,
            [self._copilot([
                {"filename": "copilot/ex01.json", "stage_name": "EX1", "enabled": True},
                {"filename": "copilot/ex02.json", "stage_name": "EX2", "enabled": True},
            ])],
        )
        await _wait_done(runner)

        session = engine_env["session"]
        assert session.started
        appended = session.appended
        assert len(appended) == 2
        assert all(t == "Copilot" for t, _ in appended)
        assert [pp["filename"] for _, pp in appended] == ["copilot/ex01.json", "copilot/ex02.json"]
        assert [pp["stage_name"] for _, pp in appended] == ["EX1", "EX2"]
        assert runner.status == FINISHED

    async def test_copilot_all_disabled_skips_task(self, device, engine_env):
        runner = TaskRunner.get(1)
        await runner.start(
            device,
            [self._copilot([
                {"filename": "copilot/a.json", "stage_name": "", "enabled": False},
            ])],
        )
        await _wait_done(runner)

        session = engine_env["session"]
        assert session.appended == []
        assert not session.started  # 无任何任务 → 不启动引擎
        assert runner.status == FINISHED

    async def test_copilot_without_jobs_falls_back_to_filename(self, device, engine_env):
        runner = TaskRunner.get(1)
        await runner.start(
            device,
            [TaskItem(
                name="自动战斗", entry="Copilot", type="抄作业",
                params={"filename": "copilot/legacy.json", "stage_name": "CE-6"},
            )],
        )
        await _wait_done(runner)

        session = engine_env["session"]
        assert len(session.appended) == 1
        assert session.appended[0] == (
            "Copilot",
            {"filename": "copilot/legacy.json", "stage_name": "CE-6", "formation_index": 0},
        )
        assert runner.status == FINISHED


    async def test_stale_events_from_previous_run_dropped(self, device, engine_env):
        """上一 run 收尾时晚到的残留回调（如停止时的 TaskChainStopped）不串线到本次日志。"""
        runner = TaskRunner.get(1)
        await runner._log_q.put(("warn", "■ 任务链 StartUp 已停止"))  # 模拟残留
        run = await runner.start(device, _tasks("刷理智"))
        assert run.status == RUNNING
        await _wait_done(runner)
        assert runner.status == FINISHED

        from sqlalchemy import select as sa_select

        from app.db.session import get_sessionmaker
        async with get_sessionmaker()() as s:
            log_rows = (await s.execute(sa_select(LogEntry).where(LogEntry.run_id == run.id))).scalars().all()
        messages = " ".join(entry.message for entry in log_rows)
        assert "StartUp 已停止" not in messages  # 残留被丢弃，未串线
        assert "刷理智" in messages
        assert messages.count("全部任务完成") == 1  # 完成日志只打一次（不重复）


    async def test_weekly_schedule_skips_when_disabled_today(self, device, engine_env, monkeypatch):
        """周计划：当天未启用 → 任务跳过（不入队执行）。"""
        runner = TaskRunner.get(1)
        monkeypatch.setattr(taskrunner, "_today_abbr", lambda: "Wed")
        task = TaskItem(
            name="刷理智", entry="Fight", type="刷理智",
            params={"stage": "CE-6", "weekly_schedule": {"Mon": True, "Wed": False}},
        )
        run = await runner.start(device, [task])
        await _wait_done(runner)
        assert runner.status == FINISHED
        # 无任务入队 → 引擎未启动
        assert engine_env["session"].started is False

        from sqlalchemy import select as sa_select

        from app.db.session import get_sessionmaker
        async with get_sessionmaker()() as s:
            rows = (await s.execute(sa_select(LogEntry).where(LogEntry.run_id == run.id))).scalars().all()
        messages = " ".join(e.message for e in rows)
        assert "不在周计划内" in messages

    async def test_weekly_schedule_runs_when_enabled(self, device, engine_env, monkeypatch):
        """周计划：当天启用 → 正常入队执行；缺省（无 weekly_schedule）默认执行。"""
        runner = TaskRunner.get(1)
        monkeypatch.setattr(taskrunner, "_today_abbr", lambda: "Wed")
        task = TaskItem(
            name="刷理智", entry="Fight", type="刷理智",
            params={"stage": "CE-6", "weekly_schedule": {"Wed": True}},
        )
        await runner.start(device, [task])
        await _wait_done(runner)
        assert runner.status == FINISHED
        assert engine_env["session"].started is True

    async def test_offline_confirm_stops_when_restart_disabled(self, device, engine_env):
        """游戏掉线 + auto_restart_on_drop=false → 任务停止。"""
        import threading

        engine_env["gate"] = threading.Event()
        runner = TaskRunner.get(1)
        task = TaskItem(
            name="刷理智", entry="Fight", type="刷理智",
            params={"stage": "CE-6", "auto_restart_on_drop": False},
        )
        await runner.start(device, [task])
        await asyncio.sleep(0.05)  # worker 已到达 start()/gate 等待
        # 模拟引擎 OfflineConfirm 事件（任务仍在运行）
        emit, on_event = engine_env["session"].handler
        on_event({"event": "offline_confirm"})
        await asyncio.sleep(0.05)
        engine_env["gate"].set()  # 释放引擎 → all_completed
        await _wait_done(runner)
        assert runner.status in (STOPPED, ERROR)

        from sqlalchemy import select as sa_select

        from app.db.session import get_sessionmaker
        async with get_sessionmaker()() as s:
            rows = (await s.execute(sa_select(LogEntry).where(LogEntry.run_id == runner.run_id))).scalars().all()
        messages = " ".join(e.message for e in rows)
        assert "自动重启已关闭" in messages

    async def test_offline_confirm_continues_when_restart_enabled(self, device, engine_env):
        """游戏掉线 + auto_restart_on_drop=true（默认）→ 不停止，任务正常完成。"""
        import threading

        engine_env["gate"] = threading.Event()
        runner = TaskRunner.get(1)
        task = TaskItem(
            name="刷理智", entry="Fight", type="刷理智",
            params={"stage": "CE-6", "auto_restart_on_drop": True},
        )
        await runner.start(device, [task])
        await asyncio.sleep(0.05)
        emit, on_event = engine_env["session"].handler
        on_event({"event": "offline_confirm"})
        engine_env["gate"].set()
        await _wait_done(runner)
        assert runner.status == FINISHED


    async def test_paradox_copilot_jobs_expand(self, device, engine_env):
        """悖论模拟（ParadoxCopilot）：多作业展开为逐个 ParadoxCopilot 任务。"""
        runner = TaskRunner.get(1)
        task = TaskItem(
            name="悖论模拟", entry="Copilot", type="抄作业",
            params={
                "copilot_mode": 2,
                "jobs": [
                    {"filename": "paradox/a.json", "stage_name": "tough_01-07", "enabled": True},
                    {"filename": "paradox/b.json", "stage_name": "", "enabled": True},
                    {"filename": "paradox/c.json", "enabled": False},
                ],
            },
        )
        await runner.start(device, [task])
        await _wait_done(runner)
        assert runner.status == FINISHED
        appended = engine_env["session"].appended
        assert [t for t, _ in appended] == ["ParadoxCopilot", "ParadoxCopilot"]
        assert appended[0][1]["filename"] == "paradox/a.json"
        assert "jobs" not in appended[0][1]


# ── Mall 一日只执行一次（客户端本地语义，MallTask.cs） ───────────────────

class TestMallOnceADay:
    """「一日只执行一次」在 WebUI 侧模拟：Setting 表 last_time（游戏日，凌晨 4 点重置）。

    - once 启用且今天已执行过 → 入队前该子项强制关闭（credit_fight/visit_friends=False）
    - 未执行过 / once 关闭 → 参数保持
    - Mall 任务链完成 → 写两个 last_time（对齐客户端 Mall 完成即写 LastTime）
    """

    LAST_KEYS = ("mall.visit_friends_last_time", "mall.credit_fight_last_time")

    async def _clear(self) -> None:
        from app.db.session import get_sessionmaker
        from app.models.setting import Setting

        async with get_sessionmaker()() as s:
            for k in self.LAST_KEYS:
                row = await s.get(Setting, k)
                if row is not None:
                    await s.delete(row)
            await s.commit()

    async def _seed(self, key: str, value: str) -> None:
        import json

        from app.db.session import get_sessionmaker
        from app.models.setting import Setting

        async with get_sessionmaker()() as s:
            s.add(Setting(key=key, value=json.dumps(value)))
            await s.commit()

    def _mall(self, **overrides) -> TaskItem:
        params = {
            "visit_friends": True, "visit_friends_once_a_day": False,
            "shopping": False, "credit_fight": True, "credit_fight_once_a_day": True,
        }
        params.update(overrides)
        return TaskItem(name="信用购物", entry="Mall", type="Mall", params=params)

    async def test_credit_fight_skipped_when_done_today(self, device, engine_env) -> None:
        from app.engine.taskrunner import _yj_today

        await self._clear()
        await self._seed("mall.credit_fight_last_time", _yj_today())
        runner = TaskRunner.get(1)
        await runner.start(device, [self._mall()])
        await _wait_done(runner)
        assert runner.status == FINISHED
        ttype, params = engine_env["session"].appended[0]
        assert ttype == "Mall"
        assert params["credit_fight"] is False
        # visit_friends_once_a_day 未启用 → 不受 last_time 影响
        assert params["visit_friends"] is True

    async def test_visit_friends_skipped_when_done_today(self, device, engine_env) -> None:
        from app.engine.taskrunner import _yj_today

        await self._clear()
        await self._seed("mall.visit_friends_last_time", _yj_today())
        runner = TaskRunner.get(1)
        await runner.start(device, [self._mall(visit_friends_once_a_day=True)])
        await _wait_done(runner)
        _, params = engine_env["session"].appended[0]
        assert params["visit_friends"] is False
        assert params["credit_fight"] is True

    async def test_runs_when_not_done_today(self, device, engine_env) -> None:
        await self._clear()
        runner = TaskRunner.get(1)
        await runner.start(device, [self._mall()])
        await _wait_done(runner)
        _, params = engine_env["session"].appended[0]
        assert params["credit_fight"] is True
        assert params["visit_friends"] is True

    async def test_yesterday_last_time_allows_run(self, device, engine_env) -> None:
        from app.engine.taskrunner import _yj_today
        from datetime import timedelta, datetime

        await self._clear()
        yesterday = (datetime.now().astimezone() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert yesterday != _yj_today()
        await self._seed("mall.credit_fight_last_time", yesterday)
        runner = TaskRunner.get(1)
        await runner.start(device, [self._mall()])
        await _wait_done(runner)
        _, params = engine_env["session"].appended[0]
        assert params["credit_fight"] is True

    async def test_disabled_once_keeps_params(self, device, engine_env) -> None:
        from app.engine.taskrunner import _yj_today

        await self._clear()
        await self._seed("mall.credit_fight_last_time", _yj_today())
        runner = TaskRunner.get(1)
        await runner.start(device, [self._mall(credit_fight_once_a_day=False)])
        await _wait_done(runner)
        _, params = engine_env["session"].appended[0]
        assert params["credit_fight"] is True

    async def test_completed_records_last_times(self, device, engine_env) -> None:
        import json

        from app.db.session import get_sessionmaker
        from app.engine.taskrunner import _yj_today
        from app.models.setting import Setting

        await self._clear()
        runner = TaskRunner.get(1)
        await runner.start(device, [self._mall()])
        await _wait_done(runner)
        async with get_sessionmaker()() as s:
            values = {}
            for k in self.LAST_KEYS:
                row = await s.get(Setting, k)
                values[k] = json.loads(row.value) if row is not None else None
        assert values["mall.credit_fight_last_time"] == _yj_today()
        assert values["mall.visit_friends_last_time"] == _yj_today()


# ── 停滞检测（对齐 MAA RunningState StallTimer） ─────────────

class TestStallDetection:
    """卡死超时内无新任务进展 → 日志警告 + 停滞通知；按提醒间隔重复；新任务重置。"""

    async def _seed_game(self, **values) -> None:
        import json

        from app.db.session import get_sessionmaker
        from app.models.setting import Setting

        async with get_sessionmaker()() as s:
            for k, v in values.items():
                row = await s.get(Setting, f"game.{k}")
                if row is None:
                    s.add(Setting(key=f"game.{k}", value=json.dumps(v)))
                else:
                    row.value = json.dumps(v)
            await s.commit()

    def _runner(self) -> TaskRunner:
        runner = TaskRunner.get(1)
        runner.status = RUNNING
        runner._device_name = "Redmi"
        runner._last_progress = datetime.now(timezone.utc) - timedelta(minutes=20)
        runner._stall_last_fire = None
        return runner

    async def test_stall_fires_after_timeout(self, engine_env, monkeypatch) -> None:
        from app.engine import notify

        calls: list[tuple] = []
        async def _fake_send(*a, **k):
            calls.append(a)
        monkeypatch.setattr(notify, "send", _fake_send)
        await self._seed_game(enable_stall_timeout=True, stall_timeout_minutes=10)
        runner = self._runner()
        await runner._check_stall(datetime.now(timezone.utc))
        assert len(calls) == 1
        assert calls[0][0] == "stalled"
        assert "Redmi" in calls[0][1]
        # 日志警告入队
        kind, msg = runner._log_q.get_nowait()
        assert kind == "warn" and "可能卡住" in msg

    async def test_stall_not_fired_with_recent_progress(self, engine_env, monkeypatch) -> None:
        from app.engine import notify

        calls: list[tuple] = []
        async def _fake_send(*a, **k):
            calls.append(a)
        monkeypatch.setattr(notify, "send", _fake_send)
        await self._seed_game(enable_stall_timeout=True, stall_timeout_minutes=10)
        runner = self._runner()
        runner._last_progress = datetime.now(timezone.utc)  # 刚有进展
        await runner._check_stall(datetime.now(timezone.utc))
        assert calls == []

    async def test_stall_disabled_by_setting(self, engine_env, monkeypatch) -> None:
        from app.engine import notify

        calls: list[tuple] = []
        async def _fake_send(*a, **k):
            calls.append(a)
        monkeypatch.setattr(notify, "send", _fake_send)
        await self._seed_game(enable_stall_timeout=False, stall_timeout_minutes=10)
        runner = self._runner()
        await runner._check_stall(datetime.now(timezone.utc))
        assert calls == []

    async def test_stall_reminder_interval(self, engine_env, monkeypatch) -> None:
        from app.engine import notify

        calls: list[tuple] = []
        async def _fake_send(*a, **k):
            calls.append(a)
        monkeypatch.setattr(notify, "send", _fake_send)
        await self._seed_game(
            enable_stall_timeout=True, stall_timeout_minutes=10, reminder_interval_minutes=5
        )
        runner = self._runner()
        now = datetime.now(timezone.utc)
        # 首次触发
        await runner._check_stall(now)
        assert len(calls) == 1
        # 1 分钟后（< 提醒间隔）不重复
        runner._stall_last_fire = now - timedelta(minutes=1)
        await runner._check_stall(now)
        assert len(calls) == 1
        # 10 分钟后（≥ 提醒间隔）重复提醒
        runner._stall_last_fire = now - timedelta(minutes=10)
        await runner._check_stall(now)
        assert len(calls) == 2

    async def test_stall_not_fired_when_idle(self, engine_env, monkeypatch) -> None:
        from app.engine import notify

        calls: list[tuple] = []
        async def _fake_send(*a, **k):
            calls.append(a)
        monkeypatch.setattr(notify, "send", _fake_send)
        await self._seed_game(enable_stall_timeout=True, stall_timeout_minutes=10)
        runner = self._runner()
        runner.status = IDLE
        await runner._check_stall(datetime.now(timezone.utc))
        assert calls == []
