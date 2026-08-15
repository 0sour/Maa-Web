"""Resource pack manager (S-07) unit tests.

Covers: local state detection, remote latest-version lookup (mocked httpx),
and the full download → extract → atomic-swap → version-file flow using a
real in-memory zip (no network, no real MAA release).

Isolation: every test gets its own `maa_resource_dir` / `cache_dir` via the
`res_env` fixture, so file-system state never leaks between tests.
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from types import SimpleNamespace

import pytest

from app.core import runtime_settings
from app.engine import resource_mgr


@pytest.fixture(autouse=True)
def _reset_globals():
    """Resource manager keeps module-level caches — reset between tests."""
    resource_mgr._remote_cache.update(at=0.0, data=None)
    resource_mgr._pick_cache.clear()
    resource_mgr._UPDATE.update(
        running=False, progress=0.0, stage="idle", error=None, started_at=None
    )
    resource_mgr._dynamic_cache.update(at=0.0, commit="", files=None)
    resource_mgr._DYNAMIC.update(
        running=False, stage="idle", progress=0.0, error=None, started_at=None,
        mode="", pending=0, done=0,
    )
    resource_mgr.item_list.cache_clear()
    resource_mgr.operator_list.cache_clear()
    resource_mgr.recruit_tags.cache_clear()
    resource_mgr.roguelike_core_chars.cache_clear()
    yield


@pytest.fixture
def res_env(monkeypatch, tmp_path):
    """Point the manager at an isolated resource/cache dir for this test."""
    res = tmp_path / "maa-resource"
    res.mkdir(parents=True, exist_ok=True)
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_dir", res)
    monkeypatch.setattr(resource_mgr.get_settings(), "cache_dir", cache)
    return res


def _make_release_json(tag: str = "v6.16.6", size: int = 64, platform: str = "win-x64") -> dict:
    ext = ".tar.gz" if platform.startswith("linux") else ".zip"
    asset = f"MAA-{tag}-{platform}{ext}"
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": asset,
                "size": size,
                "browser_download_url": (
                    f"https://github.com/MaaAssistantArknights/MaaAssistantArknights/"
                    f"releases/download/{tag}/{asset}"
                ),
            }
        ],
    }


def _make_resource_zip(tag: str = "v6.16.6", nested: bool = False) -> bytes:
    """Mimic the official package zip layout (win-x64).

    Real MAA releases use a TOP-LEVEL `resource/` dir + 平铺的 `MaaCore.dll`
    引擎库。Some archives wrap it as {root}/resource/ — both must be supported.
    """
    root = f"MAA-{tag}/" if nested else ""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            f"{root}resource/pipeline/Fight.json",
            json.dumps({"Fight": {"algorithm": "TemplateMatch"}}),
        )
        zf.writestr(f"{root}resource/template/stage-CE-6.png", b"\x89PNG-fake")
        zf.writestr(f"{root}MaaCore.dll", b"\x90\x00fake-dll")  # 引擎库（校验必需）
    return buf.getvalue()


def _make_linux_tar(tag: str = "v6.16.6") -> bytes:
    """Mimic the official linux tar.gz layout: {root}/resource/ + libMaaCore.so."""
    import io as _io
    import tarfile as _tarfile

    root = f"MAA-{tag}-linux-x86_64"
    buf = _io.BytesIO()
    with _tarfile.open(fileobj=buf, mode="w:gz") as tf:
        payload = json.dumps({"Fight": {"algorithm": "TemplateMatch"}}).encode()
        info = _tarfile.TarInfo(f"{root}/resource/pipeline/Fight.json")
        info.size = len(payload)
        tf.addfile(info, _io.BytesIO(payload))
        lib = b"\x7fELF-fake"
        libinfo = _tarfile.TarInfo(f"{root}/libMaaCore.so")
        libinfo.size = len(lib)
        tf.addfile(libinfo, _io.BytesIO(lib))
    return buf.getvalue()


class FakeStream:
    def __init__(self, data: bytes, fail: bool = False) -> None:
        self._data = data
        self._fail = fail
        self.headers = {"content-length": str(len(data))}

    async def __aenter__(self):
        if self._fail:
            raise RuntimeError("stream down")
        return self

    async def __aexit__(self, *args) -> None:
        pass

    def raise_for_status(self) -> None:
        pass

    async def aiter_bytes(self, chunk_size: int):
        yield self._data


class FakeClient:
    def __init__(
        self,
        release: dict,
        zip_bytes: bytes,
        head_latency: dict[str, float] | None = None,
        head_fail: set[str] | None = None,
        stream_fail: set[str] | None = None,
    ) -> None:
        self._release = release
        self._zip = zip_bytes
        self._head_latency = head_latency or {}
        self._head_fail = head_fail or set()
        self._stream_fail = stream_fail or set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def head(self, url):
        if url in self._head_fail:
            raise RuntimeError("head down")
        await asyncio.sleep(self._head_latency.get(url, 0.0))
        return SimpleNamespace(status_code=200)

    async def get(self, url):
        return SimpleNamespace(json=lambda: self._release, raise_for_status=lambda: None)

    def stream(self, method, url):
        return FakeStream(self._zip, fail=(url in self._stream_fail))


def _install_fake_http(monkeypatch, release: dict, zip_bytes: bytes, **kw) -> None:
    def _factory(*args, **kwargs):
        return FakeClient(release, zip_bytes, **kw)

    monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", _factory)


# ── local state ─────────────────────────────────────────────

class TestLocalState:
    def test_empty_dir_not_ready(self, res_env):
        state = resource_mgr.local_state()
        assert state["ready"] is False
        assert state["installed"] is False
        assert state["pipelines"] == 0

    def test_local_pack_detected(self, res_env):
        (res_env / "resource" / "pipeline").mkdir(parents=True, exist_ok=True)
        (res_env / "resource" / "pipeline" / "Fight.json").write_text("{}", encoding="utf-8")
        (res_env / "MaaCore.dll").write_bytes(b"\x90fake-dll")
        (res_env / "version.json").write_text(
            json.dumps({"tag": "v6.16.6", "source": "test"}), encoding="utf-8"
        )
        state = resource_mgr.local_state()
        assert state["ready"] is True
        assert state["installed"] is True
        assert state["local_version"] == "v6.16.6"
        assert state["pipelines"] >= 1

    def test_stage_codes_reads_and_sorts(self, res_env):
        """候选 = 导航任务（常驻/活动）+ 主线格式关卡；无导航的活动关（TO-6）排除。"""
        res = res_env / "resource"
        (res / "tasks" / "Stages").mkdir(parents=True, exist_ok=True)
        (res / "tasks" / "Stages" / "Supplies.json").write_text(
            json.dumps({"CE-6": {}, "CE6@Stage": {}}), encoding="utf-8"
        )
        (res / "tasks" / "Stages" / "TO.json").write_text(
            json.dumps({"TO-5": {}, "TO-7": {}, "TO-Open": {}, "TOChapterToTO": {}}),
            encoding="utf-8",
        )
        (res / "stages.json").write_text(
            json.dumps([
                {"code": "CE-6", "apCost": 30},
                {"code": "1-7", "apCost": 9},
                {"code": "1-7", "apCost": 9},  # 重复应去重
                {"code": "TO-6", "apCost": 12},  # 活动关但无导航任务 → 排除
                {"apCost": 12},  # 无 code 应跳过
            ]),
            encoding="utf-8",
        )
        assert resource_mgr.stage_codes() == ["1-7", "CE-6", "TO-5", "TO-7"]

    def test_stage_codes_missing_returns_empty(self, res_env):
        assert resource_mgr.stage_codes() == []


# ── remote lookup ───────────────────────────────────────────

class TestRemote:
    async def test_remote_latest_parses_asset(self, monkeypatch, res_env):
        zip_bytes = _make_resource_zip()
        _install_fake_http(monkeypatch, _make_release_json(size=len(zip_bytes)), zip_bytes)
        remote = await resource_mgr.remote_latest()
        assert remote is not None
        assert remote["tag"] == "v6.16.6"
        assert "win-x64" in remote["asset"]
        assert "releases/download/v6.16.6" in remote["url"]
        assert remote["size"] == len(zip_bytes)

    async def test_remote_failure_returns_none(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", _boom)
        assert await resource_mgr.remote_latest() is None

    async def test_asset_missing_returns_none(self, monkeypatch):
        def _factory(*args, **kwargs):
            release = _make_release_json()
            release["assets"] = []  # no matching asset
            return FakeClient(release, b"")

        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", _factory)
        assert await resource_mgr.remote_latest() is None

    async def test_status_without_network_ok(self, monkeypatch, res_env):
        def _boom(*args, **kwargs):
            raise RuntimeError("down")

        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", _boom)
        data = await resource_mgr.status()
        assert data["ready"] is False
        assert data["remote_latest"] is None
        assert data["updating"] is False


# ── mirror sources（多候选 + 测速择优 + fallback） ─────────

class TestMirror:
    def test_mirror_prefixes_parse(self, monkeypatch):
        monkeypatch.setattr(
            resource_mgr.get_settings(), "maa_resource_mirror",
            "https://ghproxy.net/,\nhttps://ghfast.top/, https://mirror.ghproxy.com",
        )
        assert resource_mgr._mirror_prefixes() == [
            "https://ghproxy.net/", "https://ghfast.top/", "https://mirror.ghproxy.com/",
        ]

    def test_candidate_urls_order(self, monkeypatch):
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_mirror", "https://ghproxy.net/")
        urls = resource_mgr._candidate_urls("https://github.com/a/b.zip")
        assert urls == [
            "https://ghproxy.net/https://github.com/a/b.zip",
            "https://github.com/a/b.zip",  # 直连兜底
        ]

    async def test_pick_fastest_sorts_by_latency(self, monkeypatch):
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_mirror", "https://m1.example/")
        raw = "https://github.com/a/b.zip"
        mirror = "https://m1.example/https://github.com/a/b.zip"
        client = FakeClient({}, b"", head_latency={mirror: 0.02, raw: 0.0})
        urls = await resource_mgr.pick_fastest_urls(raw, client)
        assert urls == [raw, mirror]  # 直连更快 → 直连在前

    async def test_pick_fastest_unreachable_tail(self, monkeypatch):
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_mirror", "https://m1.example/")
        raw = "https://github.com/a/b.zip"
        mirror = "https://m1.example/https://github.com/a/b.zip"
        client = FakeClient({}, b"", head_fail={mirror})
        urls = await resource_mgr.pick_fastest_urls(raw, client)
        assert urls[0] == raw
        assert urls[-1] == mirror  # 不可达镜像保留在尾部兜底

    async def test_remote_latest_prefers_mirror(self, monkeypatch, res_env):
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_mirror", "https://ghproxy.net/")
        zip_bytes = _make_resource_zip()
        release = _make_release_json(size=len(zip_bytes))
        raw_url = release["assets"][0]["browser_download_url"]
        mirror_url = "https://ghproxy.net/" + raw_url
        _install_fake_http(monkeypatch, release, zip_bytes, head_latency={mirror_url: 0.0, raw_url: 1.0})
        remote = await resource_mgr.remote_latest()
        assert remote is not None
        assert remote["url"] == mirror_url
        assert remote["urls"][0] == mirror_url
        assert raw_url in remote["urls"]

    async def test_remote_latest_mirror_down_falls_back_to_direct(self, monkeypatch, res_env):
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_mirror", "https://ghproxy.net/")
        zip_bytes = _make_resource_zip()
        release = _make_release_json(size=len(zip_bytes))
        raw_url = release["assets"][0]["browser_download_url"]
        _install_fake_http(
            monkeypatch, release, zip_bytes, head_fail={"https://ghproxy.net/" + raw_url}
        )
        remote = await resource_mgr.remote_latest()
        assert remote is not None
        assert remote["url"] == raw_url  # 镜像不可达 → 直连兜底

    async def test_update_download_falls_back_to_direct(self, monkeypatch, res_env):
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_mirror", "https://ghproxy.net/")
        zip_bytes = _make_resource_zip()
        release = _make_release_json(size=len(zip_bytes))
        raw_url = release["assets"][0]["browser_download_url"]
        mirror_url = "https://ghproxy.net/" + raw_url
        # 镜像 GET 流式失败 → 自动切直连完成下载
        _install_fake_http(monkeypatch, release, zip_bytes, stream_fail={mirror_url})
        await resource_mgr.update()
        for _ in range(100):
            if not resource_mgr._UPDATE["running"]:
                break
            await asyncio.sleep(0.02)
        assert resource_mgr._UPDATE["error"] is None, resource_mgr._UPDATE["error"]
        assert resource_mgr._UPDATE["stage"] == "done"
        state = resource_mgr.local_state()
        assert state["ready"] is True
        assert (res_env / "resource" / "pipeline" / "Fight.json").exists()


# ── full update flow ────────────────────────────────────────

class TestUpdate:
    async def test_update_downloads_and_swaps(self, monkeypatch, res_env):
        zip_bytes = _make_resource_zip()  # top-level resource/ (real MAA layout)
        _install_fake_http(monkeypatch, _make_release_json(size=len(zip_bytes)), zip_bytes)

        result = await resource_mgr.update()
        assert result["running"] is True

        # wait for the background task to finish
        for _ in range(100):
            if not resource_mgr._UPDATE["running"]:
                break
            await asyncio.sleep(0.02)

        assert resource_mgr._UPDATE["error"] is None, resource_mgr._UPDATE["error"]
        assert resource_mgr._UPDATE["stage"] == "done"
        assert resource_mgr._UPDATE["progress"] == 1.0

        # local dir now ready with pipeline + version file
        state = resource_mgr.local_state()
        assert state["ready"] is True
        assert state["local_version"] == "v6.16.6"
        assert (res_env / "resource" / "pipeline" / "Fight.json").exists()
        assert (res_env / "MaaCore.dll").exists()
        assert (res_env / "version.json").exists()

    async def test_update_nested_root_layout_supported(self, monkeypatch, res_env):
        """{root}/resource/ layout (linux tar / wrapped zips) must also extract."""
        zip_bytes = _make_resource_zip(nested=True)
        _install_fake_http(monkeypatch, _make_release_json(size=len(zip_bytes)), zip_bytes)

        await resource_mgr.update()
        for _ in range(100):
            if not resource_mgr._UPDATE["running"]:
                break
            await asyncio.sleep(0.02)

        assert resource_mgr._UPDATE["error"] is None, resource_mgr._UPDATE["error"]
        state = resource_mgr.local_state()
        assert state["ready"] is True
        assert (res_env / "resource" / "pipeline" / "Fight.json").exists()
        assert (res_env / "MaaCore.dll").exists()

    async def test_update_linux_tar_layout(self, monkeypatch, res_env):
        """NAS 场景：linux-x86_64 资产（tar.gz + libMaaCore.so）同样可用。"""
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_platform", "linux-x86_64")
        monkeypatch.setattr(resource_mgr.asstproxy, "engine_lib_name", lambda: "libMaaCore.so")
        tar_bytes = _make_linux_tar()
        _install_fake_http(
            monkeypatch, _make_release_json(size=len(tar_bytes), platform="linux-x86_64"), tar_bytes
        )

        await resource_mgr.update()
        for _ in range(100):
            if not resource_mgr._UPDATE["running"]:
                break
            await asyncio.sleep(0.02)

        assert resource_mgr._UPDATE["error"] is None, resource_mgr._UPDATE["error"]
        state = resource_mgr.local_state()
        assert state["ready"] is True
        assert (res_env / "resource" / "pipeline" / "Fight.json").exists()
        assert (res_env / "libMaaCore.so").exists()

    async def test_update_idempotent_while_running(self, monkeypatch, res_env):
        zip_bytes = _make_resource_zip()
        _install_fake_http(monkeypatch, _make_release_json(size=len(zip_bytes)), zip_bytes)
        await resource_mgr.update()
        second = await resource_mgr.update()
        assert second["running"] is True  # same in-flight task, no double start
        for _ in range(100):
            if not resource_mgr._UPDATE["running"]:
                break
            await asyncio.sleep(0.02)

    async def test_update_remote_failure_reports_error(self, monkeypatch, res_env):
        def _boom(*args, **kwargs):
            raise RuntimeError("api down")

        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", _boom)
        result = await resource_mgr.update()
        assert result["running"] is False
        assert result["error"]
        assert "无法获取" in result["error"]


# ── 动态资源同步（MaaResource 增量） ───────────────────────

def _make_tree(commit: str = "c1", files: dict[str, str] | None = None) -> dict:
    files = files or {"Arknights-Tile-Pos/1-7.json": "sha-a", "stages.json": "sha-b"}
    tree = [
        {"type": "blob", "path": f"resource/{p}", "sha": s}
        for p, s in files.items()
    ]
    tree.append({"type": "tree", "path": "resource", "sha": "tree-x"})  # 应被忽略
    return {"sha": commit, "tree": tree}


def _make_dynamic_tar(files: dict[str, bytes] | None = None) -> bytes:
    """Mimic codeload tarball: {MaaResource-main}/resource/..."""
    import io as _io
    import tarfile as _tf

    files = files or {
        "Arknights-Tile-Pos/1-7.json": b'{"tile":1}',
        "stages.json": b'{"stage":"CE-6"}',
    }
    root = "MaaResource-main"
    buf = _io.BytesIO()
    with _tf.open(fileobj=buf, mode="w:gz") as tf:
        for rel, data in files.items():
            info = _tf.TarInfo(f"{root}/resource/{rel}")
            info.size = len(data)
            tf.addfile(info, _io.BytesIO(data))
    return buf.getvalue()


def _install_fake_dynamic(monkeypatch, tree: dict, files: dict[str, bytes], tar: bytes | None = None) -> None:
    """按 URL 分发的 FakeClient：tree API → json；raw → content；tarball → stream。"""
    class FakeDynClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, url):
            if "git/trees" in url:
                return SimpleNamespace(json=lambda: tree, raise_for_status=lambda: None)
            rel = url.split("/main/", 1)[1]
            return SimpleNamespace(content=files.get(rel, b""), raise_for_status=lambda: None)

        def stream(self, method, url):
            return FakeStream(tar or _make_dynamic_tar())

    monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda *a, **k: FakeDynClient())


def _install_engine_pack(res_env) -> None:
    (res_env / "resource" / "Arknights-Tile-Pos").mkdir(parents=True, exist_ok=True)
    (res_env / "resource" / "Arknights-Tile-Pos" / "1-7.json").write_text("old", encoding="utf-8")
    (res_env / "MaaCore.dll").write_bytes(b"\x90fake")
    (res_env / "version.json").write_text(json.dumps({"tag": "v6.16.6"}), encoding="utf-8")


class TestDynamicPlan:
    def test_no_manifest_means_full(self):
        tree = {"a.json": "s1", "b.json": "s2"}
        mode, down, delete = resource_mgr._plan_diff(tree, {})
        assert mode == "full"

    def test_add_change_remove_detected(self):
        tree = {"a.json": "s1", "b.json": "s2-new", "c.json": "s3"}
        manifest = {"files": {"a.json": "s1", "b.json": "s2-old", "d.json": "s4"}}
        mode, down, delete = resource_mgr._plan_diff(tree, manifest)
        assert mode == "diff"
        assert down == ["b.json", "c.json"]  # 变更 + 新增，有序
        assert delete == ["d.json"]

    def test_threshold_triggers_full(self, monkeypatch):
        monkeypatch.setattr(resource_mgr, "_FULL_THRESHOLD", 3)
        tree = {f"f{i}.json": f"s{i}" for i in range(10)}
        manifest = {"files": {f"f{i}.json": "old" for i in range(10)}}
        mode, down, delete = resource_mgr._plan_diff(tree, manifest)
        assert mode == "full"

    def test_up_to_date_detects_no_diff(self):
        tree = {"a.json": "s1"}
        manifest = {"commit": "c1", "files": {"a.json": "s1"}}
        mode, down, delete = resource_mgr._plan_diff(tree, manifest)
        assert mode == "diff"
        assert down == []
        assert delete == []


class TestDynamicSync:
    async def test_diff_flow_downloads_and_manifests(self, monkeypatch, res_env):
        _install_engine_pack(res_env)
        # 预置 manifest：1-7.json 有旧 sha（本次变更），stages.json 为新增
        resource_mgr._write_manifest("c0", {"Arknights-Tile-Pos/1-7.json": "old-sha"})
        tree = _make_tree(files={
            "Arknights-Tile-Pos/1-7.json": "sha-a",
            "stages.json": "sha-b",
        })
        _install_fake_dynamic(
            monkeypatch, tree,
            {"Arknights-Tile-Pos/1-7.json": b"new-tile", "stages.json": b'{"s":1}'},
        )
        result = await resource_mgr.sync_dynamic()
        assert result["running"] is True
        assert result["mode"] == "diff"
        assert result["pending"] == 2
        for _ in range(100):
            if not resource_mgr._DYNAMIC["running"]:
                break
            await asyncio.sleep(0.02)
        assert resource_mgr._DYNAMIC["error"] is None, resource_mgr._DYNAMIC["error"]
        assert resource_mgr._DYNAMIC["stage"] == "done"
        # 文件已合并 + manifest 已写
        assert (res_env / "resource" / "Arknights-Tile-Pos" / "1-7.json").read_bytes() == b"new-tile"
        assert (res_env / "resource" / "stages.json").exists()
        manifest = resource_mgr._read_manifest()
        assert manifest["commit"] == "c1"
        assert manifest["files"]["stages.json"] == "sha-b"

    async def test_full_flow_merges_tarball(self, monkeypatch, res_env):
        _install_engine_pack(res_env)
        tree = _make_tree(files={
            "Arknights-Tile-Pos/1-7.json": "sha-a",
            "stages.json": "sha-b",
        })
        _install_fake_dynamic(
            monkeypatch, tree,
            {"x.json": b"ignored"},  # raw 下载不应被全量模式使用
            tar=_make_dynamic_tar(),
        )
        await resource_mgr.sync_dynamic()
        for _ in range(100):
            if not resource_mgr._DYNAMIC["running"]:
                break
            await asyncio.sleep(0.02)
        assert resource_mgr._DYNAMIC["error"] is None, resource_mgr._DYNAMIC["error"]
        # tarball 内容合并进 resource/
        assert (res_env / "resource" / "Arknights-Tile-Pos" / "1-7.json").read_bytes() == b'{"tile":1}'
        assert (res_env / "resource" / "stages.json").read_bytes() == b'{"stage":"CE-6"}'
        assert resource_mgr._read_manifest()["commit"] == "c1"

    async def test_up_to_date_returns_idle(self, monkeypatch, res_env):
        _install_engine_pack(res_env)
        tree = _make_tree(files={"Arknights-Tile-Pos/1-7.json": "sha-a"})
        _install_fake_dynamic(monkeypatch, tree, {"Arknights-Tile-Pos/1-7.json": b"x"})
        # 预置一致 manifest
        resource_mgr._write_manifest("c1", {"Arknights-Tile-Pos/1-7.json": "sha-a"})
        result = await resource_mgr.sync_dynamic()
        assert result["running"] is False
        assert result["stage"] == "idle"

    async def test_idempotent_while_running(self, monkeypatch, res_env):
        _install_engine_pack(res_env)
        tree = _make_tree(files={"Arknights-Tile-Pos/1-7.json": "sha-a"})
        _install_fake_dynamic(monkeypatch, tree, {"Arknights-Tile-Pos/1-7.json": b"x"})
        await resource_mgr.sync_dynamic()
        second = await resource_mgr.sync_dynamic()
        assert second["running"] is True
        for _ in range(100):
            if not resource_mgr._DYNAMIC["running"]:
                break
            await asyncio.sleep(0.02)

    async def test_engine_pack_missing_reports_error(self, monkeypatch, res_env):
        tree = _make_tree()
        _install_fake_dynamic(monkeypatch, tree, {"x.json": b"x"})
        result = await resource_mgr.sync_dynamic()
        assert result["running"] is True
        for _ in range(100):
            if not resource_mgr._DYNAMIC["running"]:
                break
            await asyncio.sleep(0.02)
        assert resource_mgr._DYNAMIC["error"]
        assert "引擎包未安装" in resource_mgr._DYNAMIC["error"]

    async def test_tree_failure_reports_error(self, monkeypatch, res_env):
        def _boom(*args, **kwargs):
            raise RuntimeError("api down")

        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", _boom)
        result = await resource_mgr.sync_dynamic()
        assert result["running"] is False
        assert "动态资源清单" in result["error"]


# ── MirrorChyan CDK 有效期检查 ─────────────────────────────

class _CdkResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload


class _CdkClient:
    def __init__(self, payload: dict):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def get(self, url):
        return _CdkResp(self._payload)


@pytest.fixture(autouse=True)
def _cdk_runtime_isolated(monkeypatch, tmp_path):
    """把运行时设置指向临时文件，并重置缓存。"""
    from app.core import runtime_settings

    rt_file = tmp_path / "config" / "runtime_settings.json"
    rt_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runtime_settings, "_path", lambda: rt_file)
    monkeypatch.setattr(runtime_settings, "_cache", None)


class TestMirrorChyan:
    async def test_cdk_valid_persists_expiry(self, monkeypatch):
        from app.core import runtime_settings

        payload = {
            "code": 0,
            "data": {"cdk_expired_time": 5_000_000_000},
        }
        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda **kw: _CdkClient(payload))
        result = await resource_mgr.check_mirrorchyan_cdk("A" * 24)
        assert result["ok"] is True
        assert result["cdk_expired_time"] == 5_000_000_000
        assert result["remaining_days"] is not None
        # 已持久化到运行时设置
        assert runtime_settings.mirrorchyan_cdk() == "A" * 24
        assert runtime_settings.load()["mirrorchyan_cdk_expired_time"] == 5_000_000_000

    async def test_cdk_expired(self, monkeypatch):
        payload = {"code": 7001, "msg": "expired"}
        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda **kw: _CdkClient(payload))
        result = await resource_mgr.check_mirrorchyan_cdk("A" * 24)
        assert result["ok"] is False
        assert "已过期" in result["message"]
        assert result["code"] == 7001

    async def test_cdk_invalid(self, monkeypatch):
        payload = {"code": 7002, "msg": "invalid"}
        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda **kw: _CdkClient(payload))
        result = await resource_mgr.check_mirrorchyan_cdk("bad" * 8)
        assert result["ok"] is False
        assert "无效" in result["message"]

    async def test_network_failure_friendly(self, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("conn reset")

        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", _boom)
        result = await resource_mgr.check_mirrorchyan_cdk("A" * 24)
        assert result["ok"] is False
        assert "无法连接" in result["message"]


# ── MirrorChyan 更新源（sync_dynamic 分支） ───────────────

class _MirrorChyanClient:
    """按 URL 分发：API 检查 → json；增量包 → stream zip。"""

    def __init__(self, payload: dict, zip_bytes: bytes, stream_fail: bool = False):
        self._payload = payload
        self._zip = zip_bytes
        self._stream_fail = stream_fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def get(self, url):
        return SimpleNamespace(json=lambda: self._payload, raise_for_status=lambda: None)

    def stream(self, method, url):
        return FakeStream(self._zip, fail=self._stream_fail)


def _make_mirrorchyan_zip(files: dict[str, bytes] | None = None) -> bytes:
    """Mirror酱增量包（zip，平铺 resource/）。"""
    import io as _io

    files = files or {"Arknights-Tile-Pos/1-7.json": b'{"tile":9}', "stages.json": b'{"stage":"SL-8"}'}
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for rel, data in files.items():
            zf.writestr(f"resource/{rel}", data)
    return buf.getvalue()


class TestMirrorChyanSync:
    async def test_no_cdk_returns_error(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "")
        result = await resource_mgr.sync_dynamic()
        assert result["running"] is False
        assert "CDK" in result["error"]

    async def test_downloads_and_merges(self, monkeypatch, res_env):
        _install_engine_pack(res_env)
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        monkeypatch.setattr(runtime_settings, "mirrorchyan_sp_id", lambda: "spid-1")
        payload = {"code": 0, "data": {"version_name": "2026-08-14 08:00:00.000", "url": "https://mirror/x.zip"}}
        monkeypatch.setattr(
            resource_mgr.httpx, "AsyncClient",
            lambda *a, **k: _MirrorChyanClient(payload, _make_mirrorchyan_zip()),
        )
        result = await resource_mgr.sync_dynamic()
        assert result["running"] is True
        assert result["mode"] == "mirrorchyan"
        for _ in range(100):
            if not resource_mgr._DYNAMIC["running"]:
                break
            await asyncio.sleep(0.02)
        assert resource_mgr._DYNAMIC["stage"] == "done"
        assert resource_mgr._DYNAMIC["error"] is None
        # 合并后的文件已更新 + manifest 记录版本
        merged = (res_env / "resource" / "Arknights-Tile-Pos" / "1-7.json").read_text(encoding="utf-8")
        assert "tile" in merged
        m = resource_mgr._read_manifest()
        assert m["version"] == "2026-08-14 08:00:00.000"
        assert m["source"] == "mirrorchyan"

    async def test_api_error_surfaced(self, monkeypatch, res_env):
        _install_engine_pack(res_env)
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        payload = {"code": 7002, "msg": "invalid"}
        monkeypatch.setattr(
            resource_mgr.httpx, "AsyncClient",
            lambda *a, **k: _MirrorChyanClient(payload, b""),
        )
        result = await resource_mgr.sync_dynamic()
        assert result["running"] is False
        assert "无效" in result["error"]


class TestMirrorChyanEngineUpdate:
    """引擎包 update() 的 MirrorChyan 分支：API 查询 → 下载（content-length 进度）→ 换包写版本。"""

    async def test_update_no_cdk_returns_error(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "")
        result = await resource_mgr.update()
        assert result["running"] is False
        assert "CDK" in result["error"]

    async def test_update_downloads_engine_pack(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        monkeypatch.setattr(runtime_settings, "mirrorchyan_sp_id", lambda: "spid-1")
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_platform", "win-x64")
        payload = {
            "code": 0,
            "data": {
                "version_name": "2026-08-14 08:00:00.000",
                "url": "https://mirrorchyan.example/dl/MAA-win-x64-v6.17.0.zip",
            },
        }
        monkeypatch.setattr(
            resource_mgr.httpx, "AsyncClient",
            lambda *a, **k: _MirrorChyanClient(payload, _make_resource_zip()),
        )
        result = await resource_mgr.update()
        assert result["running"] is True
        for _ in range(100):
            if not resource_mgr._UPDATE["running"]:
                break
            await asyncio.sleep(0.02)
        assert resource_mgr._UPDATE["stage"] == "done", resource_mgr._UPDATE["error"]
        assert resource_mgr._UPDATE["error"] is None
        assert resource_mgr._UPDATE["progress"] == 1.0  # content-length 计算进度
        v = json.loads((res_env / "version.json").read_text(encoding="utf-8"))
        assert v["source"] == "MirrorChyan"

    async def test_update_up_to_date(self, monkeypatch, res_env):
        _install_engine_pack(res_env)  # version.json tag = v6.16.6
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        payload = {
            "code": 0,
            "data": {
                "version_name": "v6.16.6",
                "url": "https://mirrorchyan.example/dl/MAA-v6.16.6.zip",
            },
        }
        monkeypatch.setattr(
            resource_mgr.httpx, "AsyncClient",
            lambda *a, **k: _MirrorChyanClient(payload, b""),
        )
        result = await resource_mgr.update()
        assert result["running"] is False
        assert result["error"] is None
        assert result["stage"] == "idle"  # 已是最新，不进入下载

    async def test_update_applies_incremental_ota(self, monkeypatch, res_env):
        """Mirror酱 返回 update_type=incremental 时：覆盖 + changes.json deleted。"""
        _install_engine_pack(res_env)  # resource/Arknights-Tile-Pos/1-7.json + MaaCore.dll
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        # 增量包：覆盖 pipeline JSON + 删除 1-7.json
        import io as _io

        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "resource/pipeline/Fight.json",
                json.dumps({"Fight": {"algorithm": "Sobel"}}),
            )
            zf.writestr(
                "changes.json",
                json.dumps({"deleted": ["resource/Arknights-Tile-Pos/1-7.json"]}),
            )
        payload = {
            "code": 0,
            "data": {
                "version_name": "v6.16.8",
                "url": "https://mirrorchyan.example/dl/ota-v6.16.8",
                "update_type": "incremental",
                "filesize": buf.getbuffer().nbytes,
            },
        }
        monkeypatch.setattr(
            resource_mgr.httpx, "AsyncClient",
            lambda *a, **k: _MirrorChyanClient(payload, buf.getvalue()),
        )
        result = await resource_mgr.update()
        assert result["running"] is True
        for _ in range(100):
            if not resource_mgr._UPDATE["running"]:
                break
            await asyncio.sleep(0.02)
        assert resource_mgr._UPDATE["stage"] == "done", resource_mgr._UPDATE["error"]
        assert resource_mgr._UPDATE["error"] is None
        assert resource_mgr._UPDATE["progress"] == 1.0
        # 覆盖生效 + deleted 生效 + 引擎库保留
        merged = json.loads(
            (res_env / "resource" / "pipeline" / "Fight.json").read_text(encoding="utf-8")
        )
        assert merged["Fight"]["algorithm"] == "Sobel"
        assert not (res_env / "resource" / "Arknights-Tile-Pos" / "1-7.json").exists()
        assert (res_env / "MaaCore.dll").exists()
        v = json.loads((res_env / "version.json").read_text(encoding="utf-8"))
        assert v["tag"] == "v6.16.8"
        assert v["source"] == "MirrorChyan"

    async def test_status_uses_mirrorchyan_source(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        payload = {
            "code": 0,
            "data": {
                "version_name": "2026-08-14 08:00:00.000",
                "url": "https://mirrorchyan.example/dl/MAA-win-x64.zip",
            },
        }
        monkeypatch.setattr(
            resource_mgr.httpx, "AsyncClient",
            lambda *a, **k: _MirrorChyanClient(payload, b""),
        )
        st = await resource_mgr.status()
        assert st["update_source"] == "mirrorchyan"
        assert st["remote_latest"] == "2026-08-14 08:00:00.000"


class TestRemoteLatestMirrorChyan:
    """remote_latest_mirrorchyan() 单元：URL 构造 / asset 取 URL 末尾 / 拒绝码 / 已最新。"""

    class _Rec:
        def __init__(self, payload: dict):
            self.payload = payload
            self.seen_url = ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, url):
            self.seen_url = url
            return SimpleNamespace(json=lambda: self.payload)

    async def test_builds_url_and_asset_from_url_tail(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "CDK" * 8)
        monkeypatch.setattr(runtime_settings, "mirrorchyan_sp_id", lambda: "spid-9")
        monkeypatch.setattr(resource_mgr.get_settings(), "maa_resource_platform", "win-x64")
        rec = self._Rec(
            {
                "code": 0,
                "data": {
                    "version_name": "2026-08-14 08:00:00.000",
                    "url": "https://mirrorchyan.example/dl/abc/MAA-win-x64-2026-08-14.zip",
                },
            }
        )
        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda *a, **k: rec)
        remote = await resource_mgr.remote_latest_mirrorchyan()
        assert remote["asset"] == "MAA-win-x64-2026-08-14.zip"
        assert remote["size"] == 0
        assert "os=win" in rec.seen_url and "arch=x64" in rec.seen_url
        assert "channel=Stable" in rec.seen_url and "sp_id=spid-9" in rec.seen_url

    async def test_rejected_code_returns_none(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        rec = self._Rec({"code": 7002, "msg": "invalid cdk"})
        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda *a, **k: rec)
        assert await resource_mgr.remote_latest_mirrorchyan() is None

    async def test_no_download_url_returns_none(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        rec = self._Rec({"code": 0, "data": {"version_name": "x"}})
        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda *a, **k: rec)
        assert await resource_mgr.remote_latest_mirrorchyan() is None

    async def test_up_to_date_when_same_version(self, monkeypatch, res_env):
        _install_engine_pack(res_env)  # version.json tag = v6.16.6
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        rec = self._Rec(
            {
                "code": 0,
                "data": {
                    "version_name": "v6.16.6",
                    "url": "https://mirrorchyan.example/dl/MAA-v6.16.6.zip",
                },
            }
        )
        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda *a, **k: rec)
        remote = await resource_mgr.remote_latest_mirrorchyan()
        assert remote["up_to_date"] is True

    async def test_up_to_date_without_url(self, monkeypatch, res_env):
        """已最新时服务端不返回 url → 仍应判定为 up_to_date，而非查询失败。"""
        _install_engine_pack(res_env)  # version.json tag = v6.16.6
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)
        rec = self._Rec({"code": 0, "data": {"version_name": "v6.16.6"}})
        monkeypatch.setattr(resource_mgr.httpx, "AsyncClient", lambda *a, **k: rec)
        remote = await resource_mgr.remote_latest_mirrorchyan()
        assert remote["up_to_date"] is True


# ── item_index（指定掉落材料表） ─────────────────────────────

def _install_item_index(res_env, data: dict) -> None:
    (res_env / "resource").mkdir(exist_ok=True)
    (res_env / "resource" / "item_index.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def test_item_list_parses_index(res_env):
    """正常解析：返回 [{id, name, classify_type}]，按 ID 排序，跳过无名字条。"""
    _install_item_index(
        res_env,
        {
            "30062": {"name": "聚酸酯", "classifyType": "MATERIAL"},
            "30011": {"name": "源岩", "classifyType": "MATERIAL"},
            "2001": {"name": "赤金", "classifyType": "MATERIAL"},
            "bad": {"classifyType": "MATERIAL"},  # 无 name → 跳过
        },
    )
    items = resource_mgr.item_list()
    assert [it["id"] for it in items] == ["2001", "30011", "30062"]  # 按 ID 排序
    assert [it["name"] for it in items] == ["赤金", "源岩", "聚酸酯"]
    assert items[0]["classify_type"] == "MATERIAL"
    assert all(it["id"] != "bad" for it in items)


def test_item_list_filters_non_numeric_and_excluded(res_env):
    """对齐 MAA 客户端 InitDrops()：非数字 ID 与黑名单（双芯片/许可/源石/高级合成）一律排除。"""
    _install_item_index(
        res_env,
        {
            "30011": {"name": "源岩", "classifyType": "MATERIAL"},
            "1stact": {"name": "幸运金币", "classifyType": "CURSED"},  # 非数字 → 排除
            "2026recruitment10_1": {"name": "寻访凭证", "classifyType": "CONSUME"},  # 非数字 → 排除
            "3213": {"name": "双芯片", "classifyType": "MATERIAL"},  # 双芯片 → 排除
            "7001": {"name": "招聘许可", "classifyType": "CONSUME"},  # 许可 → 排除
            "30115": {"name": "聚合剂", "classifyType": "MATERIAL"},  # 高级合成 → 排除
            "4002": {"name": "合成玉", "classifyType": "CURRENCY"},  # 合成玉 → 排除
        },
    )
    items = resource_mgr.item_list()
    assert [it["id"] for it in items] == ["30011"]
    assert items[0]["name"] == "源岩"


def test_item_list_missing_file_returns_empty(res_env):
    """文件缺失 → 空列表（不抛异常，不阻断其他功能）。"""
    assert resource_mgr.item_list() == []


def test_item_list_corrupt_file_returns_empty(res_env):
    """文件损坏（非法 JSON / 非 dict）→ 空列表。"""
    (res_env / "resource").mkdir(exist_ok=True)
    (res_env / "resource" / "item_index.json").write_text("not json", encoding="utf-8")
    assert resource_mgr.item_list() == []
    (res_env / "resource" / "item_index.json").write_text("[1,2]", encoding="utf-8")
    resource_mgr.item_list.cache_clear()
    assert resource_mgr.item_list() == []


# ── 干员表（battle_data.json，追加干员搜索） ─────────────────

def _install_battle_data(res_env, chars: dict) -> None:
    (res_env / "resource").mkdir(exist_ok=True)
    (res_env / "resource" / "battle_data.json").write_text(
        json.dumps({"chars": chars}, ensure_ascii=False), encoding="utf-8"
    )


def test_operator_list_parses_chars(res_env):
    """正常解析：返回 [{id, name}]，按名称排序，跳过无名字条。"""
    _install_battle_data(
        res_env,
        {
            "char_002_amiya": {"name": "阿米娅", "profession": "CASTER"},
            "char_124_gladiia": {"name": "歌蕾蒂娅", "profession": "PIONEER"},
            "char_1001_amiya2": {"name": "阿米娅（近卫）", "profession": "GUARD"},
            "char_bad": {"profession": "SNIPER"},  # 无 name → 跳过
        },
    )
    ops = resource_mgr.operator_list()
    assert [o["name"] for o in ops] == ["阿米娅", "阿米娅（近卫）", "歌蕾蒂娅"]
    assert ops[0]["id"] == "char_002_amiya"
    assert all(o["id"] != "char_bad" for o in ops)


def test_operator_list_missing_or_corrupt(res_env):
    """文件缺失/损坏/非预期结构 → 空列表（不抛异常）。"""
    assert resource_mgr.operator_list() == []
    (res_env / "resource").mkdir(exist_ok=True)
    (res_env / "resource" / "battle_data.json").write_text("not json", encoding="utf-8")
    resource_mgr.operator_list.cache_clear()
    assert resource_mgr.operator_list() == []
    (res_env / "resource" / "battle_data.json").write_text(
        json.dumps({"chars": [1, 2]}, ensure_ascii=False), encoding="utf-8"
    )
    resource_mgr.operator_list.cache_clear()
    assert resource_mgr.operator_list() == []


# ── 公招 Tag 列表（recruitment.json，首选/保留 Tags 多选） ─────────

def _install_recruitment(res_env, tags: dict) -> None:
    (res_env / "resource").mkdir(exist_ok=True)
    (res_env / "resource" / "recruitment.json").write_text(
        json.dumps({"tags": tags}, ensure_ascii=False), encoding="utf-8"
    )


def test_recruit_tags_parses(res_env):
    """正常解析：返回排序后的 tag 名列表，跳过空名。"""
    _install_recruitment(res_env, {"近战位": "近战位", "输出": "输出", "  ": "  "})
    tags = resource_mgr.recruit_tags()
    assert tags == ["输出", "近战位"]  # 按 Unicode 码点排序


def test_recruit_tags_missing_or_corrupt(res_env):
    """文件缺失/损坏/非预期结构 → 空列表（不抛异常）。"""
    assert resource_mgr.recruit_tags() == []
    (res_env / "resource").mkdir(exist_ok=True)
    (res_env / "resource" / "recruitment.json").write_text("bad", encoding="utf-8")
    resource_mgr.recruit_tags.cache_clear()
    assert resource_mgr.recruit_tags() == []
    (res_env / "resource" / "recruitment.json").write_text(
        json.dumps({"tags": [1, 2]}, ensure_ascii=False), encoding="utf-8"
    )
    resource_mgr.recruit_tags.cache_clear()
    assert resource_mgr.recruit_tags() == []


# ── 肉鸽开局核心干员（roguelike/{theme}/recruitment.json） ─────

def _install_rogue_recruit(res_env, theme: str, groups: list) -> None:
    p = res_env / "resource" / "roguelike" / theme
    p.mkdir(parents=True, exist_ok=True)
    (p / "recruitment.json").write_text(
        json.dumps({"priority": groups}, ensure_ascii=False), encoding="utf-8"
    )


def test_roguelike_core_chars_only_start(res_env):
    """只取 is_start=true 的干员，去重排序；非 is_start / 无名字跳过。"""
    _install_rogue_recruit(
        res_env, "JieGarden",
        [
            {"opers": [{"name": "维什戴尔", "is_start": True}, {"name": "新约能天使", "is_start": True}]},
            {"opers": [{"name": "维什戴尔", "is_start": True}, {"name": "阿米娅", "is_start": False}, {"name": ""}]},
        ],
    )
    chars = resource_mgr.roguelike_core_chars("JieGarden")
    assert chars == ["新约能天使", "维什戴尔"]


def test_roguelike_core_chars_theme_scoped(res_env):
    """按主题隔离：其他主题的文件不影响；无效主题返回空。"""
    _install_rogue_recruit(res_env, "Phantom", [{"opers": [{"name": "令", "is_start": True}]}])
    assert resource_mgr.roguelike_core_chars("Phantom") == ["令"]
    assert resource_mgr.roguelike_core_chars("Mizuki") == []  # 未安装该主题文件
    assert resource_mgr.roguelike_core_chars("Invalid") == []  # 无效主题


def test_roguelike_core_chars_missing_or_corrupt(res_env):
    """文件缺失/损坏 → 空列表（不抛异常）。"""
    assert resource_mgr.roguelike_core_chars("Sami") == []
    _install_rogue_recruit(res_env, "Sami", [])
    (res_env / "resource" / "roguelike" / "Sami" / "recruitment.json").write_text("bad", encoding="utf-8")
    resource_mgr.roguelike_core_chars.cache_clear()
    assert resource_mgr.roguelike_core_chars("Sami") == []


class TestUpdateQueryFailureState:
    """update() 查询失败必须写入 _UPDATE（否则前端轮询 status 误显示「已更新」）。"""

    async def test_mirrorchyan_query_failure_writes_state(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "mirrorchyan")
        monkeypatch.setattr(runtime_settings, "mirrorchyan_cdk", lambda: "A" * 24)

        async def _fail():
            return None

        monkeypatch.setattr(resource_mgr, "remote_latest_mirrorchyan", _fail)
        result = await resource_mgr.update()
        assert result["error"] is not None
        assert "Mirror酱" in result["error"]
        # 状态已写入：/resources/status 轮询能读到真实错误
        assert resource_mgr._UPDATE["stage"] == "error"
        assert resource_mgr._UPDATE["error"] == result["error"]

    async def test_github_query_failure_writes_state(self, monkeypatch, res_env):
        monkeypatch.setattr(runtime_settings, "update_source", lambda: "github")

        async def _fail():
            return None

        monkeypatch.setattr(resource_mgr, "remote_latest", _fail)
        result = await resource_mgr.update()
        assert result["error"] is not None
        assert "官方最新版本" in result["error"]
        assert resource_mgr._UPDATE["stage"] == "error"
