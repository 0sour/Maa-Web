"""今日开放关卡模块测试（stages_today）— 解析/星期过滤/掉落映射。

纯函数为主（不触发网络）；活动开放判断用可控的 yj_now 注入。
"""
import asyncio
import json
from datetime import datetime

import pytest

from app.engine import stages_today


def test_parse_dt_timezone() -> None:
    # 2026/08/17 12:00:00 Asia/Shanghai(+8) -> UTC 04:00
    assert stages_today._parse_dt({"UtcStartTime": "2026/08/17 12:00:00", "TimeZone": 8}, "UtcStartTime") == \
        datetime(2026, 8, 17, 4, 0, 0)
    # 缺字段 -> None
    assert stages_today._parse_dt({}, "UtcStartTime") is None
    assert stages_today._parse_dt({"UtcStartTime": "bad"}, "UtcStartTime") is None


def test_parse_activities_open_window(monkeypatch: pytest.MonkeyPatch) -> None:
    # 注入固定「现在」= 2026-08-17 10:00 UTC（东八区 18:00，YJ 日 = 08-17）
    monkeypatch.setattr(stages_today, "_yj_now", lambda: datetime(2026, 8, 17, 10, 0, 0))

    data = {
        "CN": {
            "resourceCollection": {
                "Tip": "龙门市区", "UtcStartTime": "2026/08/10 04:00:00", "UtcExpireTime": "2026/08/20 04:00:00", "TimeZone": 8,
            },
            "sideStoryStage": {
                "s1": {
                    "Activity": {"StageName": "夏日活动", "UtcStartTime": "2026/08/11 04:00:00", "UtcExpireTime": "2026/08/19 04:00:00", "TimeZone": 8},
                    "Stages": [
                        {"Display": "TO-1", "Value": "TO-1", "Drop": "30012"},
                        {"Display": "TO-2", "Value": "TO-2", "Drop": "30013"},
                    ],
                },
                "s2": {
                    "Activity": {"StageName": "已结束活动", "UtcStartTime": "2026/07/01 04:00:00", "UtcExpireTime": "2026/07/10 04:00:00", "TimeZone": 8},
                    "Stages": [{"Display": "EX-1", "Value": "EX-1", "Drop": "30011"}],
                },
            },
        }
    }
    rc, activities = stages_today._parse_activities(data)
    # 2026/08/20 04:00 +8 = UTC 08-19 20:00；now=08-17 10:00 UTC → 2.4 天 → 2
    assert rc == {"name": "龙门市区", "days_left": 2}
    # 只保留开放中的活动（s2 已过期被滤除）
    assert len(activities) == 1
    act = activities[0]
    assert act["name"] == "夏日活动"
    # 08/19 04:00+8 = UTC 08-18 20:00；now 08-17 10:00 UTC → 1.4 天 → 1
    assert act["days_left"] == 1
    assert act["stages"] == [
        {"stage": "TO-1", "drop": "30012"},
        {"stage": "TO-2", "drop": "30013"},
    ]


def test_parse_activities_no_client() -> None:
    assert stages_today._parse_activities({}) == (None, [])
    assert stages_today._parse_activities({"US": {}}) == (None, [])


def test_parse_permanent_weekday(monkeypatch: pytest.MonkeyPatch) -> None:
    # 周一：CE-6（二/四/六/日）不开，AP-5（一/四/六/日）开，LS-6（每天）开
    monkeypatch.setattr(stages_today, "_yj_now", lambda: datetime(2026, 8, 17, 2, 0, 0))  # UTC Monday
    out = stages_today._parse_permanent("Monday")
    stages = [o["stage"] for o in out]
    assert "CE-6" not in stages
    assert "AP-5" in stages
    assert "LS-6" in stages
    assert "PR-A-1" in stages  # 周一开放
    assert "PR-D-1" not in stages  # 二/三/六/日 开，周一不开
    # 芯片本掉落组照抄客户端映射（item 映射缺失时回退原 id）
    pr_a1 = next(o for o in out if o["stage"] == "PR-A-1")
    assert pr_a1["drops"] == [["3261", "3231"], ["3262", "3232"]]


def test_compute_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """无缓存且网络失败时返回常驻关卡（source=local），不抛异常。"""

    async def _no_net() -> None:
        return None

    monkeypatch.setattr(stages_today, "_load_cached", lambda: None)
    monkeypatch.setattr(stages_today, "_fetch_activity_json", _no_net)
    result = asyncio.run(stages_today.compute())
    assert result["source"] == "local"
    assert isinstance(result["game_day"]["weekday"], str)
    assert isinstance(result["open_stages"], list)
    assert json.dumps(result, ensure_ascii=False)  # 可序列化
