"""Scheduler (M6) — 分钟级 tick：星期 × 时间匹配 → 触发方案执行 + 防重。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.engine import scheduler as sched_mod
from app.engine.scheduler import scheduler


@pytest.fixture(autouse=True)
def _stop_scheduler():
    """测试期间不跑真实 tick 循环（只测 _check/_fire）。"""
    if sched_mod.scheduler._task is not None:
        sched_mod.scheduler._task.cancel()
        sched_mod.scheduler._task = None
    yield


@pytest.fixture
async def sched_env(monkeypatch, tmp_path):
    """建表 + stub 设备/runner，返回 helper。"""
    from sqlalchemy import delete

    from app.db.session import get_engine, get_sessionmaker
    from app.models import (
        schedule as _schedule_models,  # noqa: F401
        task as _task_models,  # noqa: F401
    )
    from app.models.device import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.models.device import Device
    from app.models.schedule import ScheduleJob

    async with get_sessionmaker()() as s:
        # 共享测试库：先清表保证 id=1 设备可插入
        await s.execute(delete(ScheduleJob))
        await s.execute(delete(Device))
        s.add(Device(
            id=1, name="t", adb_host="127.0.0.1", adb_port=16384,
            touch_mode="Minitouch", client_type="Official", status="online",
        ))
        await s.commit()

    class FakeRunner:
        def __init__(self) -> None:
            self.started: list[list[str]] = []

        async def start(self, device, tasks):
            self.started.append([t.name for t in tasks])
            from types import SimpleNamespace

            return SimpleNamespace(id=1, status="running")

    fake = FakeRunner()
    monkeypatch.setattr(
        "app.engine.scheduler.TaskRunner.get", staticmethod(lambda device_id: fake)
    )
    monkeypatch.setattr(
        "app.engine.taskrunner.TaskRunner.get", staticmethod(lambda device_id: fake)
    )
    return fake


async def _add_job(**kw) -> int:
    from app.db.session import get_sessionmaker
    from app.models.schedule import ScheduleJob

    payload = {
        "device_id": 1, "name": "定时测试", "enabled": True,
        "weekdays": json.dumps(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
        "time": datetime.now().astimezone().strftime("%H:%M"),
        "plan_name": "方案A",
        "tasks": json.dumps([
            {"name": "开始唤醒", "entry": "StartUp", "type": "StartUp", "params": {}},
        ]),
    }
    payload.update(kw)
    async with get_sessionmaker()() as s:
        job = ScheduleJob(**payload)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return job.id


async def test_tick_fires_matching_job(sched_env) -> None:
    """时间 + 星期匹配 → 触发方案执行（TaskRunner.start 收到任务）。"""
    job_id = await _add_job()
    await scheduler._check()
    assert sched_env.started == [["开始唤醒"]]

    # last_run_at 已写入 → 同分钟防重
    sched_env.started.clear()
    await scheduler._check()
    assert sched_env.started == []


async def test_tick_skips_time_mismatch(sched_env) -> None:
    job_id = await _add_job(time="23:59")
    await scheduler._check()
    assert sched_env.started == []


async def test_tick_skips_weekday_mismatch(sched_env) -> None:
    from app.engine.taskrunner import _today_abbr

    other = "Mon" if _today_abbr() != "Mon" else "Tue"
    await _add_job(weekdays=json.dumps([other]))
    await scheduler._check()
    assert sched_env.started == []


async def test_tick_skips_disabled_job(sched_env) -> None:
    await _add_job(enabled=False)
    await scheduler._check()
    assert sched_env.started == []


async def test_fire_marks_last_run_and_logs(sched_env) -> None:
    """触发后 last_run_at 落库；任务日志写入 log_entries（实时日志可见）。"""
    from app.db.session import get_sessionmaker
    from app.models.schedule import ScheduleJob
    from app.models.task import LogEntry

    job_id = await _add_job()
    await scheduler._check()
    async with get_sessionmaker()() as s:
        job = await s.get(ScheduleJob, job_id)
        assert job.last_run_at is not None
        rows = (
            await s.execute(
                __import__("sqlalchemy").select(LogEntry).where(LogEntry.device_id == 1)
            )
        ).scalars().all()
    assert any("定时任务" in r.message for r in rows)
