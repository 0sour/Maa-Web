"""Scheduler (M6+) — 自动任务时间槽：星期 × 时间匹配 → 触发账号轮换 + 冲突策略。"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.engine import scheduler as sched_mod
from app.engine.scheduler import auto_runner, scheduler
from app.engine.taskrunner import TaskQueueError


@pytest.fixture(autouse=True)
async def _stop_scheduler():
    """测试期间不跑真实 tick 循环（只测 _check/触发链路），清理 worker 防跨测试残留。"""
    if sched_mod.scheduler._task is not None:
        sched_mod.scheduler._task.cancel()
        try:
            await sched_mod.scheduler._task
        except asyncio.CancelledError:
            pass
        sched_mod.scheduler._task = None
    for w in list(auto_runner._workers.values()):
        w.cancel()
    await asyncio.gather(*list(auto_runner._workers.values()), return_exceptions=True)
    auto_runner._workers.clear()
    auto_runner._queues.clear()
    yield
    for w in list(auto_runner._workers.values()):
        w.cancel()
    await asyncio.gather(*list(auto_runner._workers.values()), return_exceptions=True)
    auto_runner._workers.clear()
    auto_runner._queues.clear()


@pytest.fixture
async def sched_env(monkeypatch):
    """建表 + stub 设备/runner，返回 helper。"""
    from sqlalchemy import delete

    from app.db.session import get_engine, get_sessionmaker
    from app.models import (
        auto_task as _auto_task_models,  # noqa: F401
    )
    from app.models import (
        task as _task_models,  # noqa: F401
    )
    from app.models.device import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.models.auto_task import AutoSlot, AutoSlotAccount, AutoTask
    from app.models.device import Device

    async with get_sessionmaker()() as s:
        # 共享测试库：先清表保证 id=1 设备/任务可插入
        await s.execute(delete(AutoSlotAccount))
        await s.execute(delete(AutoSlot))
        await s.execute(delete(AutoTask))
        await s.execute(delete(Device))
        s.add(Device(
            id=1, name="t", adb_host="127.0.0.1", adb_port=16384,
            touch_mode="Minitouch", client_type="Official", status="online",
        ))
        # 预置自动任务组 id=1（_add_slot 默认 task_id=1）
        s.add(AutoTask(id=1, name="每日长草", enabled=True, device_id=1))
        await s.commit()

    # 空闲轮询加速（默认 5s 太久）
    monkeypatch.setattr(sched_mod, "_POLL_SECONDS", 0.01)

    class FakeRunner:
        """受控 runner：start 记录 (account_name, tasks, source)；可模拟忙碌/失败/停止。"""

        def __init__(self) -> None:
            self.started: list[dict] = []
            self.status = "idle"
            self.run_id = 0
            self.stopped = 0
            self.fail_once = False
            # start 后立即完成（否则 _wait_free 会轮询挂起）
            self.auto_finish = True

        async def start(
            self, device, tasks, *, client_type=None, account_name=None, source="normal"
        ):
            if self.fail_once:
                self.fail_once = False
                raise TaskQueueError("模拟启动失败")
            self.started.append({
                "account_name": account_name,
                "tasks": [t.name for t in tasks],
                "source": source,
            })
            self.status = "running"
            if self.auto_finish:
                self.status = "finished"
            self.run_id += 1
            return SimpleNamespace(id=self.run_id, status="running")

        async def stop(self):
            self.stopped += 1
            self.status = "stopped"

    fake = FakeRunner()
    monkeypatch.setattr(
        "app.engine.scheduler.TaskRunner.get", staticmethod(lambda device_id: fake)
    )
    monkeypatch.setattr(
        "app.engine.taskrunner.TaskRunner.get", staticmethod(lambda device_id: fake)
    )
    return fake


async def _pump(fake, n: int) -> None:
    """等待 worker 执行到 started 达 n 次（轮询，防竞态）。

    返回后再让出 0.05s，确保 worker 的收尾（last_ok 落库等）完成。
    """
    for _ in range(200):
        if len(fake.started) >= n:
            await asyncio.sleep(0.05)
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"worker 未在超时内执行 {n} 个账号（实际 {len(fake.started)}）")


async def _add_task(**kw) -> int:
    from app.db.session import get_sessionmaker
    from app.models.auto_task import AutoTask

    payload = {"name": "每日长草", "enabled": True, "device_id": 1}
    payload.update(kw)
    async with get_sessionmaker()() as s:
        task = AutoTask(**payload)
        s.add(task)
        await s.commit()
        await s.refresh(task)
        return task.id


async def _add_slot(task_id: int = 1, **kw) -> int:
    from app.db.session import get_sessionmaker
    from app.models.auto_task import AutoSlot

    payload = {
        "task_id": task_id,
        "name": "槽A",
        "enabled": True,
        "weekdays": json.dumps(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
        "time": datetime.now().astimezone().strftime("%H:%M"),
        "conflict": "queue",
    }
    payload.update(kw)
    async with get_sessionmaker()() as s:
        slot = AutoSlot(**payload)
        s.add(slot)
        await s.commit()
        await s.refresh(slot)
        return slot.id


async def _add_account(slot_id: int, name: str = "账号A", **kw) -> int:
    from app.db.session import get_sessionmaker
    from app.models.auto_task import AutoSlotAccount

    payload = {
        "slot_id": slot_id,
        "position": 0,
        "account_name": name,
        "client_type": "Official",
        "enabled": True,
        "plan_name": "方案A",
        "tasks": json.dumps([
            {"name": "开始唤醒", "entry": "StartUp", "type": "StartUp", "params": {}},
        ]),
    }
    payload.update(kw)
    async with get_sessionmaker()() as s:
        acc = AutoSlotAccount(**payload)
        s.add(acc)
        await s.commit()
        await s.refresh(acc)
        return acc.id


# ── 时间/星期匹配与防重（对齐旧行为） ──────────────────────

async def test_tick_fires_matching_slot(sched_env) -> None:
    """时间 + 星期匹配 → 触发账号轮换（TaskRunner.start 收到任务，source=auto）。"""
    slot_id = await _add_slot()
    await _add_account(slot_id, "账号A")
    await scheduler._check()
    await _pump(sched_env, 1)
    assert sched_env.started[0]["account_name"] == "账号A"
    assert sched_env.started[0]["source"] == "auto"
    assert sched_env.started[0]["tasks"] == ["开始唤醒"]

    # last_run_at 已写入 → 同分钟防重
    sched_env.started.clear()
    await scheduler._check()
    assert sched_env.started == []


async def test_tick_skips_time_mismatch(sched_env) -> None:
    await _add_slot(time="23:59")
    await scheduler._check()
    assert sched_env.started == []


async def test_tick_skips_weekday_mismatch(sched_env) -> None:
    from app.engine.taskrunner import _today_abbr

    other = "Mon" if _today_abbr() != "Mon" else "Tue"
    await _add_slot(weekdays=json.dumps([other]))
    await scheduler._check()
    assert sched_env.started == []


async def test_tick_skips_disabled_slot(sched_env) -> None:
    await _add_slot(enabled=False)
    await scheduler._check()
    assert sched_env.started == []


async def test_tick_skips_disabled_task(sched_env) -> None:
    task_id = await _add_task(enabled=False)
    await _add_slot(task_id=task_id)
    await scheduler._check()
    assert sched_env.started == []


async def test_trigger_marks_last_run_and_logs(sched_env) -> None:
    """触发后 slot.last_run_at 落库；日志写入 log_entries（source=auto）。"""
    from sqlalchemy import select

    from app.db.session import get_sessionmaker
    from app.models.auto_task import AutoSlot
    from app.models.task import LogEntry

    slot_id = await _add_slot()
    await _add_account(slot_id)
    await scheduler._check()
    await _pump(sched_env, 1)
    async with get_sessionmaker()() as s:
        slot = await s.get(AutoSlot, slot_id)
        assert slot.last_run_at is not None
        rows = (
            (await s.execute(select(LogEntry).where(LogEntry.device_id == 1)))
            .scalars()
            .all()
        )
    assert any("槽A" in r.message or "账号" in r.message for r in rows)
    assert all(r.source == "auto" for r in rows)


# ── 账号轮换 ──────────────────────────────────────────────

async def test_account_rotation_order(sched_env) -> None:
    """多账号按 position 顺序串行执行；client_type/account_name 透传。"""
    slot_id = await _add_slot()
    await _add_account(slot_id, "账号A", position=0, client_type="Bilibili")
    await _add_account(slot_id, "账号B", position=1)
    await scheduler._check()
    await _pump(sched_env, 2)
    assert [s["account_name"] for s in sched_env.started] == ["账号A", "账号B"]


async def test_disabled_account_skipped(sched_env) -> None:
    """取消勾选的账号不执行（保留配置）。"""
    slot_id = await _add_slot()
    await _add_account(slot_id, "账号A", enabled=False)
    await _add_account(slot_id, "账号B", enabled=True, position=1)
    await scheduler._check()
    await _pump(sched_env, 1)
    assert [s["account_name"] for s in sched_env.started] == ["账号B"]


async def test_failed_account_skipped_and_continues(sched_env) -> None:
    """账号启动失败 → 跳过并标记 last_ok=False，后续账号继续执行。"""
    from sqlalchemy import select

    from app.db.session import get_sessionmaker
    from app.models.auto_task import AutoSlotAccount

    slot_id = await _add_slot()
    await _add_account(slot_id, "账号A", position=0)
    await _add_account(slot_id, "账号B", position=1)
    sched_env.fail_once = True
    await scheduler._check()
    await _pump(sched_env, 1)
    assert [s["account_name"] for s in sched_env.started] == ["账号B"]
    async with get_sessionmaker()() as s:
        rows = (
            (
                await s.execute(
                    select(AutoSlotAccount).where(AutoSlotAccount.slot_id == slot_id)
                )
            )
            .scalars()
            .all()
        )
    by_name = {r.account_name: r for r in rows}
    assert by_name["账号A"].last_ok is False
    assert by_name["账号B"].last_ok is True


async def test_trigger_no_accounts_logs(sched_env) -> None:
    """槽无启用账号 → 跳过本轮并记日志。"""
    from sqlalchemy import select

    from app.db.session import get_sessionmaker
    from app.models.task import LogEntry

    await _add_slot()
    await scheduler._check()
    assert sched_env.started == []
    async with get_sessionmaker()() as s:
        rows = (
            (await s.execute(select(LogEntry).where(LogEntry.device_id == 1)))
            .scalars()
            .all()
        )
    assert any("无启用账号" in r.message for r in rows)


# ── 冲突策略（设备忙时） ───────────────────────────────────

async def test_conflict_skip(sched_env) -> None:
    slot_id = await _add_slot(conflict="skip")
    await _add_account(slot_id)
    sched_env.status = "running"  # 模拟设备忙
    await scheduler._check()
    await asyncio.sleep(0.05)
    assert sched_env.started == []


async def test_conflict_queue_waits(sched_env) -> None:

    slot_id = await _add_slot(conflict="queue")
    await _add_account(slot_id)
    sched_env.status = "running"  # 设备忙 → 排队等待
    await scheduler._check()
    await asyncio.sleep(0.05)
    assert sched_env.started == []  # 未执行
    sched_env.status = "finished"  # 上一任务完成 → 继续执行
    await _pump(sched_env, 1)
    assert sched_env.started[0]["account_name"] == "账号A"


async def test_conflict_force_stops(sched_env) -> None:
    slot_id = await _add_slot(conflict="force")
    await _add_account(slot_id)
    sched_env.status = "running"  # 设备忙 → 强制结束上一任务
    await scheduler._check()
    await _pump(sched_env, 1)
    assert sched_env.stopped == 1
    assert sched_env.started[0]["account_name"] == "账号A"


async def test_run_test_manual_source(sched_env) -> None:
    """RUN TEST（manual_auto）与定时触发（auto）来源区分。"""
    slot_id = await _add_slot()
    acc_id = await _add_account(slot_id, "账号A")
    await auto_runner.submit(
        device_id=1, slot_name="槽A", conflict="queue",
        accounts=[{
            "id": acc_id, "account_name": "账号A",
            "client_type": "Official",
            "tasks": json.dumps([
                {"name": "开始唤醒", "entry": "StartUp", "type": "StartUp", "params": {}},
            ]),
        }],
        source="manual_auto",
    )
    await _pump(sched_env, 1)
    assert sched_env.started[0]["source"] == "manual_auto"


async def test_schema_upgrade_legacy_migration(sched_env) -> None:
    """旧库升级：log_entries 缺 source 列 → ALTER 补列；schedule_jobs 数据 → auto_tasks 迁移。"""
    from sqlalchemy import delete, select, text

    from app.db.session import get_engine, get_sessionmaker
    from app.models.auto_task import AutoSlot, AutoSlotAccount, AutoTask
    from app.models.schedule import ScheduleJob

    # 清理 fixture 预置的 auto_tasks（迁移条件：auto_tasks 为空）
    async with get_sessionmaker()() as s:
        await s.execute(delete(AutoSlotAccount))
        await s.execute(delete(AutoSlot))
        await s.execute(delete(AutoTask))
        await s.commit()

    # 模拟旧库：删掉 source 列 + 插旧定时任务
    async with get_engine().begin() as conn:
        await conn.execute(text("ALTER TABLE log_entries DROP COLUMN source"))
    async with get_sessionmaker()() as s:
        s.add(ScheduleJob(
            device_id=1, name="旧任务", enabled=True,
            weekdays='["Mon"]', time="06:00", plan_name="方案", tasks="[]",
        ))
        await s.commit()

    from app.core.events import _upgrade_schema

    await _upgrade_schema(get_sessionmaker)

    # source 列已恢复
    async with get_engine().begin() as conn:
        cols = (await conn.execute(text("PRAGMA table_info(log_entries)"))).all()
    assert any(c[1] == "source" for c in cols)

    # 旧任务迁移为「旧定时任务」组 + 时间槽（账号为空）
    async with get_sessionmaker()() as s:
        tasks = (await s.execute(select(AutoTask))).scalars().all()
        slots = (await s.execute(select(AutoSlot))).scalars().all()
    assert len(tasks) == 1 and tasks[0].name == "旧定时任务"
    assert len(slots) == 1 and slots[0].name == "旧任务"
    assert slots[0].time == "06:00"
