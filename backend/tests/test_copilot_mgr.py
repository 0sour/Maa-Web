"""Copilot manager (prts.plus 作业站) unit tests.

Covers: prts fetch → save to resource/copilot/, content string/object forms,
error handling (status_code / missing opers), local copilot file listing, and
filename sanitization. httpx is mocked; no real network.
"""
from __future__ import annotations

import json

import pytest

from app.engine import copilot_mgr


class FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class FakeClient:
    def __init__(self, payload) -> None:
        # payload: dict（固定响应）或 callable(url)（按 URL 分发）
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def get(self, url):
        p = self._payload(url) if callable(self._payload) else self._payload
        return FakeResp(p)


def _install_fake_http(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(
        copilot_mgr.httpx, "AsyncClient", lambda *a, **k: FakeClient(payload)
    )


@pytest.fixture
def cop_env(monkeypatch, tmp_path):
    """隔离的资源目录（含 resource/copilot/）。"""
    res = tmp_path / "maa-resource"
    (res / "resource" / "copilot").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(copilot_mgr.get_settings(), "maa_resource_dir", res)
    return res


def _prts_payload(content) -> dict:
    return {
        "status_code": 200,
        "data": {
            "id": 42,
            "uploader": "测试作者",
            "views": 123,
            "rating_level": 5,
            "upload_time": "2026-01-01T00:00:00",
            "content": content,
        },
    }


class TestSanitize:
    def test_strips_path_separators(self):
        assert copilot_mgr._sanitize_segment("a/b\\c:d") == "a_b_c_d"
        # 开头点被 trim 后不再构成路径穿越
        assert not copilot_mgr._sanitize_segment("../x").startswith("..")
        assert copilot_mgr._sanitize_segment("   ") == "copilot"


class TestCopilotFiles:
    def test_lists_existing_jobs_with_stage_name(self, cop_env):
        (cop_env / "resource" / "copilot" / "CE-6_1.json").write_text(
            json.dumps({"stage_name": "CE-6"}), encoding="utf-8"
        )
        act = cop_env / "resource" / "copilot" / "act"
        act.mkdir(parents=True, exist_ok=True)
        (act / "TO-8.json").write_text("{}", encoding="utf-8")  # 无 stage_name → 空串
        assert copilot_mgr.copilot_files() == [
            {"filename": "copilot/CE-6_1.json", "stage_name": "CE-6", "stage_display": "CE-6", "job_type": "copilot"},
            {"filename": "copilot/act/TO-8.json", "stage_name": "", "stage_display": "", "job_type": "copilot"},
        ]

    def test_missing_dir_returns_empty(self, cop_env):
        import shutil
        shutil.rmtree(cop_env / "resource" / "copilot")
        assert copilot_mgr.copilot_files() == []


class TestStageDisplay:
    """overview.json（Arknights-Tile-Pos）关卡名映射：stageId → 关卡编号/名。"""

    def _write_overview(self, cop_env):
        ov = cop_env / "resource" / "Arknights-Tile-Pos"
        ov.mkdir(parents=True, exist_ok=True)
        (ov / "overview.json").write_text(
            json.dumps({
                "act53side_ex01-activities/act53side/level_act53side_ex01": {
                    "code": "TO-EX-1", "name": "电影防沉迷", "stageId": "act53side_ex01",
                },
                "main_01-07#f#-obt-main-level_main_01-07.json": {
                    "code": "1-7", "name": "暴君", "stageId": "main_01-07",
                },
                # 无 code 的条目 → 回退 name
                "some_stage-x": {"name": "无名关卡", "stageId": "some_stage"},
            }),
            encoding="utf-8",
        )
        copilot_mgr._stage_index.cache_clear()

    def test_maps_stage_id_to_code(self, cop_env):
        self._write_overview(cop_env)
        assert copilot_mgr.stage_display_name("act53side_ex01") == "TO-EX-1"
        assert copilot_mgr.stage_display_name("main_01-07") == "1-7"

    def test_falls_back_to_name_and_original(self, cop_env):
        self._write_overview(cop_env)
        assert copilot_mgr.stage_display_name("some_stage") == "无名关卡"
        # 未知 stageId（映射缺失）→ 回退原值
        assert copilot_mgr.stage_display_name("ce-6_unknown") == "ce-6_unknown"
        assert copilot_mgr.stage_display_name("") == ""

    def test_list_includes_stage_display(self, cop_env):
        self._write_overview(cop_env)
        (cop_env / "resource" / "copilot" / "ex_1.json").write_text(
            json.dumps({"stage_name": "act53side_ex01"}), encoding="utf-8"
        )
        files = copilot_mgr.copilot_files()
        assert files[0]["stage_name"] == "act53side_ex01"  # 执行用保持原值
        assert files[0]["stage_display"] == "TO-EX-1"  # 展示用映射为编号


class TestFetchPrts:
    async def test_fetch_saves_and_returns_meta(self, monkeypatch, cop_env):
        content = {"stage_name": "CE-6", "opers": [{"name": "Saria", "role": "TANK"}]}
        _install_fake_http(monkeypatch, _prts_payload(content))
        meta = await copilot_mgr.fetch_from_prts(42)
        assert meta["filename"] == "copilot/CE-6_42.json"
        assert meta["stage_name"] == "CE-6"
        assert meta["uploader"] == "测试作者"
        assert meta["rating"] == 5
        saved = json.loads((cop_env / "resource" / "copilot" / "CE-6_42.json").read_text(encoding="utf-8"))
        assert saved["stage_name"] == "CE-6"

    async def test_content_as_string_parsed(self, monkeypatch, cop_env):
        content = json.dumps({"stage_name": "TO-8", "opers": [{"name": "X", "role": "TANK"}]})
        _install_fake_http(monkeypatch, _prts_payload(content))
        meta = await copilot_mgr.fetch_from_prts(7)
        assert meta["filename"].startswith("copilot/TO-8_7.json")

    async def test_status_code_error_raises(self, monkeypatch, cop_env):
        _install_fake_http(monkeypatch, {"status_code": 404, "message": "作业不存在"})
        with pytest.raises(copilot_mgr.CopilotFetchError, match="作业不存在"):
            await copilot_mgr.fetch_from_prts(1)

    async def test_missing_opers_groups_raises(self, monkeypatch, cop_env):
        _install_fake_http(monkeypatch, _prts_payload({"stage_name": "CE-6"}))
        with pytest.raises(copilot_mgr.CopilotFetchError, match="opers/groups"):
            await copilot_mgr.fetch_from_prts(2)

    async def test_network_error_raises(self, monkeypatch, cop_env):
        def _boom(*args, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(copilot_mgr.httpx, "AsyncClient", _boom)
        with pytest.raises(copilot_mgr.CopilotFetchError, match="作业站请求失败"):
            await copilot_mgr.fetch_from_prts(3)


class TestResolveCode:
    """对齐 MAA 客户端 TryParseCopilotCode：5 种代码格式。"""

    def test_all_formats(self):
        assert copilot_mgr.resolve_code("prts://99359") == ("copilot", 99359)
        assert copilot_mgr.resolve_code("prts://s51251") == ("set", 51251)
        assert copilot_mgr.resolve_code("maa://99359") == ("copilot", 99359)
        assert copilot_mgr.resolve_code("s51251") == ("set", 51251)
        assert copilot_mgr.resolve_code("99359") == ("copilot", 99359)

    def test_case_insensitive_prefix(self):
        assert copilot_mgr.resolve_code("PRTS://S51251") == ("set", 51251)
        assert copilot_mgr.resolve_code("S51251") == ("set", 51251)
        assert copilot_mgr.resolve_code("Prts://99359") == ("copilot", 99359)

    def test_long_prefix_wins(self):
        # prts://s 不能被 prts:// 抢先匹配成作业
        assert copilot_mgr.resolve_code("prts://s51251")[0] == "set"

    def test_invalid_raises(self):
        with pytest.raises(copilot_mgr.CopilotFetchError):
            copilot_mgr.resolve_code("abc")
        with pytest.raises(copilot_mgr.CopilotFetchError):
            copilot_mgr.resolve_code("prts://xyz")
        with pytest.raises(copilot_mgr.CopilotFetchError):
            copilot_mgr.resolve_code("   ")


class TestFetchSet:
    """作业集拉取：逐个下载、去重、跳过失败（对齐 ParseCopilotSetAsync）。"""

    def _set_payload(self, name, ids):
        return {
            "status_code": 200,
            "data": {"id": 1, "name": name, "description": "集描述", "copilot_ids": ids},
        }

    def _route(self, ids, fail_ids=()):
        def _route_impl(url):
            if "set/get" in url:
                return self._set_payload("测试作业集", ids)
            cid = int(url.rsplit("/", 1)[-1])
            if cid in fail_ids:
                return {"status_code": 404, "message": "作业不存在或已下架"}
            return _prts_payload({"stage_name": f"CE-{cid}", "opers": [{"name": "X", "role": "TANK"}]})

        return _route_impl

    async def test_fetch_set_downloads_all(self, monkeypatch, cop_env):
        _install_fake_http(monkeypatch, self._route([11, 12]))
        result = await copilot_mgr.fetch_set_from_prts(1)
        assert result["name"] == "测试作业集"
        assert result["description"] == "集描述"
        assert len(result["jobs"]) == 2
        assert result["skipped"] == []
        stages = {j["stage_name"] for j in result["jobs"]}
        assert stages == {"CE-11", "CE-12"}
        # 两个作业都已落盘
        saved = list((cop_env / "resource" / "copilot").glob("CE-*.json"))
        assert len(saved) == 2

    async def test_fetch_set_dedupes_ids(self, monkeypatch, cop_env):
        _install_fake_http(monkeypatch, self._route([11, 11, 12]))
        result = await copilot_mgr.fetch_set_from_prts(1)
        assert len(result["jobs"]) == 2

    async def test_fetch_set_skips_failed_jobs(self, monkeypatch, cop_env):
        _install_fake_http(monkeypatch, self._route([11, 99], fail_ids=(99,)))
        result = await copilot_mgr.fetch_set_from_prts(1)
        assert len(result["jobs"]) == 1
        assert result["skipped"] == [99]

    async def test_fetch_set_missing_copilot_ids_raises(self, monkeypatch, cop_env):
        _install_fake_http(
            monkeypatch, {"status_code": 200, "data": {"id": 1, "name": "空集"}}
        )
        with pytest.raises(copilot_mgr.CopilotFetchError, match="copilot_ids"):
            await copilot_mgr.fetch_set_from_prts(1)

    async def test_fetch_set_no_jobs_raises(self, monkeypatch, cop_env):
        _install_fake_http(monkeypatch, self._route([99], fail_ids=(99,)))
        with pytest.raises(copilot_mgr.CopilotFetchError, match="没有可用作业"):
            await copilot_mgr.fetch_set_from_prts(1)

    async def test_fetch_set_error_response_raises(self, monkeypatch, cop_env):
        _install_fake_http(monkeypatch, {"status_code": 404, "message": "作业集不存在"})
        with pytest.raises(copilot_mgr.CopilotFetchError, match="作业集不存在"):
            await copilot_mgr.fetch_set_from_prts(1)


    async def test_fetch_sss_job_skips_oper_check(self, monkeypatch, cop_env):
        """保全（SSS）作业：type=SSS 专用格式（无 opers/groups，有 stage_name/strategy）允许导入。"""
        import json as _json

        calls = {"n": 0}

        def fake_get(url):
            calls["n"] += 1
            return {
                "status_code": 200,
                "data": {
                    "id": 777,
                    "content": _json.dumps(
                        {
                            "type": "SSS", "stage_name": "SSS_1",
                            "strategy": "按顺序放工具人", "stage": [], "deploy_plan": [],
                        },
                        ensure_ascii=False,
                    ),
                },
            }

        monkeypatch.setattr(copilot_mgr.httpx, "AsyncClient", lambda *a, **k: FakeClient(fake_get))
        info = await copilot_mgr.fetch_from_prts(777)
        assert info["job_type"] == "sss"
        assert info["filename"] == "copilot/SSS_1_777.json"
        assert (cop_env / "resource" / "copilot" / "SSS_1_777.json").exists()

    async def test_fetch_sss_missing_required_fields_rejected(self, monkeypatch, cop_env):
        """SSS 作业缺 stage_name/strategy（核心字段）→ 拒绝，细分校验生效。"""
        import json as _json

        def fake_get(url):
            return {
                "status_code": 200,
                "data": {
                    "id": 889,
                    "content": _json.dumps({"type": "SSS", "stage": [], "deploy_plan": []}),
                },
            }

        monkeypatch.setattr(copilot_mgr.httpx, "AsyncClient", lambda *a, **k: FakeClient(fake_get))
        with pytest.raises(copilot_mgr.CopilotFetchError, match="stage_name/strategy"):
            await copilot_mgr.fetch_from_prts(889)

    async def test_fetch_sss_missing_type_still_rejected(self, monkeypatch, cop_env):
        """无 type 标记且无 opers/groups 的作业 → 仍拒绝（保持普通格式校验）。"""
        def fake_get(url):
            return {"status_code": 200, "data": {"id": 888, "content": '{"stage_name": "CE-6"}'}}

        monkeypatch.setattr(copilot_mgr.httpx, "AsyncClient", lambda *a, **k: FakeClient(fake_get))
        with pytest.raises(copilot_mgr.CopilotFetchError, match="opers/groups"):
            await copilot_mgr.fetch_from_prts(888)
