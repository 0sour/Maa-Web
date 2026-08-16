"""AsstProxy — MAA Asst 核心（MaaCore 动态库）引擎适配器（M2，引擎切换版）。

背景（2026-08 决策，见 docs/architecture.md §3.1）：
  MaaFw 5.x 的 `Resource.post_pipeline` 只接受 Pipeline v2 格式；MAA 官方资源
  （resource/tasks/…）是 MAA 自研旧格式（algorithm/action 字符串），且战斗/公招/
  基建依赖 MaaCore 内部私有识别器 —— 纯 MaaFw 无法加载官方资源。
  因此引擎切换为 MAA 官方 Asst 核心：ctypes 直调发布包内的 MaaCore 动态库。

C API（与官方 Python/asst 绑定一致，见 docs.maa.plus/protocol/integration.html）：
  AsstCreateEx(cb, arg) / AsstDestroy / AsstLoadResource(dir) / AsstSetUserDir(dir)
  AsstSetInstanceOption(handle, key, value)   — touch_type=2 等
  AsstConnect(handle, adb_path, address, config)
  AsstAppendTask(handle, type, params_json) / AsstSetTaskParams
  AsstStart / AsstStop / AsstRunning / AsstGetVersion / AsstLog

回调消息（AsstMsg，见 docs.maa.plus/protocol/callback-schema.html）：
  1 ConnectionInfo / 3 AllTasksCompleted / 10000~10004 TaskChain*
  20000~20004 SubTask* / 30000 ReportRequest —— 由会话解析后线程安全投递。

降级契约（docs/testing.md R9/R12 语义不变）：
  - 引擎包未安装/加载失败 → engine unavailable（设备仍可 ADB 连接；UI 显示"仅 ADB"）
  - 会话创建失败 → 结构化原因，异常不外泄
  - 引擎会话失败只降级不降状态（ADB 在线即在线）

Testability: tests 注入 FakeLib（monkeypatch asstproxy._lib），不触碰真实 DLL。
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.models.device import Device

log = logging.getLogger(__name__)

# ── 平台相关 ───────────────────────────────────────────────

_ENGINE_LIB_NAME = {
    "win32": "MaaCore.dll",
    "darwin": "libMaaCore.dylib",
    "linux": "libMaaCore.so",
}


def engine_lib_name() -> str:
    """当前平台的 MAA 引擎库文件名（按发布包布局）。"""
    return _ENGINE_LIB_NAME.get(sys.platform, "libMaaCore.so")


def engine_version() -> str:
    """引擎版本（如 v6.16.6），不可用时返回 unavailable。"""
    if not is_available():
        return "unavailable"
    try:
        return str(_lib.AsstGetVersion().decode("utf-8"))
    except Exception:  # noqa: BLE001 - binding surface
        return "unknown"


def is_available() -> bool:
    """引擎库可加载且资源已加载成功。"""
    ok, _ = _ensure_loaded()
    return ok


# ── MaaCore 动态库封装 ─────────────────────────────────────

class AsstLib:
    """ctypes 绑定 MaaCore 的 Asst C API（仅在加载成功后构建）。"""

    Callback = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)

    def __init__(self, handle: Any) -> None:
        self._h = handle

        def fn(name: str, restype: Any, argtypes: tuple[Any, ...]) -> Any:
            f = getattr(handle, name)
            f.restype = restype
            f.argtypes = argtypes
            return f

        self.AsstLoadResource = fn("AsstLoadResource", ctypes.c_bool, [ctypes.c_char_p])
        self.AsstSetUserDir = fn("AsstSetUserDir", ctypes.c_bool, [ctypes.c_char_p])
        self.AsstCreateEx = fn("AsstCreateEx", ctypes.c_void_p, [self.Callback, ctypes.c_void_p])
        self.AsstDestroy = fn("AsstDestroy", None, [ctypes.c_void_p])
        self.AsstSetInstanceOption = fn(
            "AsstSetInstanceOption", ctypes.c_bool, [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
        )
        self.AsstConnect = fn(
            "AsstConnect",
            ctypes.c_bool,
            [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p],
        )
        self.AsstAppendTask = fn(
            "AsstAppendTask", ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        )
        self.AsstSetTaskParams = fn(
            "AsstSetTaskParams", ctypes.c_bool, [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
        )
        self.AsstStart = fn("AsstStart", ctypes.c_bool, [ctypes.c_void_p])
        self.AsstStop = fn("AsstStop", ctypes.c_bool, [ctypes.c_void_p])
        self.AsstRunning = fn("AsstRunning", ctypes.c_bool, [ctypes.c_void_p])
        self.AsstGetVersion = fn("AsstGetVersion", ctypes.c_char_p, [])
        self.AsstLog = fn("AsstLog", None, [ctypes.c_char_p, ctypes.c_char_p])


_lib: AsstLib | None = None
_lib_error: str | None = None
_lib_lock = threading.Lock()
_loaded_sig: str | None = None  # 已加载资源包的 version.json 签名


def _package_root() -> Path:
    return get_settings().maa_resource_dir


def _resource_signature() -> str:
    """版本签名：资源包 version.json 的 tag（用于检测包更新后重载资源）。"""
    vf = _package_root() / "version.json"
    try:
        return str(json.loads(vf.read_text(encoding="utf-8")).get("tag", ""))
    except (OSError, ValueError):
        return ""


def _load_lib() -> tuple[AsstLib | None, str | None]:
    """从安装包目录加载 MaaCore 动态库。返回 (lib, error)。"""
    root = _package_root()
    lib_path = root / engine_lib_name()
    if not lib_path.exists():
        return None, f"MAA 引擎包未安装：{root} 下缺少 {engine_lib_name()}（请先下载资源包）"
    try:
        if sys.platform == "win32":
            # Windows 加载器按 PATH 解析依赖 DLL —— 与官方 Python/asst 绑定一致
            os.environ["PATH"] = str(root) + os.pathsep + os.environ.get("PATH", "")
            loader = ctypes.WinDLL
        else:
            os.environ["LD_LIBRARY_PATH"] = str(root) + os.pathsep + os.environ.get(
                "LD_LIBRARY_PATH", ""
            )
            loader = ctypes.CDLL
        handle = loader(str(lib_path))
    except OSError as exc:
        return None, f"MaaCore 加载失败: {exc}"
    return AsstLib(handle), None


def _ensure_loaded() -> tuple[bool, str]:
    """懒加载引擎库并确保资源已加载（线程安全，包更新后自动重载资源）。"""
    global _lib, _lib_error, _loaded_sig
    with _lib_lock:
        if _lib is None:
            if not (_package_root() / "resource").is_dir():
                _lib_error = f"MAA 引擎包未安装：{_package_root()} 下无 resource/（请先下载资源包）"
                return False, _lib_error
            _lib, _lib_error = _load_lib()
            if _lib is None:
                return False, _lib_error or "engine lib missing"
            log.info("MaaCore 动态库加载成功（%s）", _package_root() / engine_lib_name())

        sig = _resource_signature()
        if sig != _loaded_sig:
            ok = bool(_lib.AsstLoadResource(str(_package_root()).encode("utf-8")))
            if not ok:
                _lib_error = f"AsstLoadResource 失败：{_package_root()} 资源无法加载"
                return False, _lib_error
            _loaded_sig = sig
            log.info("MAA 资源已加载（%s）", _package_root())
        return True, ""


def release() -> None:
    """释放引擎引用（供资源包更新/测试清理；Windows 下 DLL 可能仍占用文件）。"""
    global _lib, _loaded_sig, _lib_error
    with _lib_lock:
        _lib = None
        _loaded_sig = None
        _lib_error = None


# ── 会话（每设备一个 Asst 实例） ────────────────────────────

_MSG_START = 10001
_MSG_COMPLETED = 10002
_MSG_STOPPED = 10004

_DEFAULT_EMIT: Callable[[str, str], None] = lambda level, msg: None  # noqa: E731


class EngineUnavailableError(RuntimeError):
    """MAA 引擎不可用（包未安装 / 库加载失败 / 资源加载失败）。"""


class EngineCreateError(RuntimeError):
    """引擎可加载但会话初始化失败。"""


class AsstSession:
    """一个绑定到设备的 MaaCore Asst 实例（任务串行，同设备不并发）。"""

    def __init__(self, device_id: int, ptr: int, lib: AsstLib, cb_ref: Any) -> None:
        self.device_id = device_id
        self._ptr = ptr
        self._lib = lib
        self._cb_ref: Any = cb_ref  # 保持回调对象存活（C 回调必须引用有效）
        self._emit: Callable[[str, str], None] = _DEFAULT_EMIT
        self._on_event: Callable[[dict], None] | None = None
        self.closed = False

    # ── 回调接线（MaaCore 线程 → 调用方线程安全出口） ──
    def set_handler(
        self,
        emit: Callable[[str, str], None],
        on_event: Callable[[dict], None] | None = None,
    ) -> None:
        """绑定日志/事件出口。回调来自 MaaCore 内部线程，必须线程安全。"""
        self._emit = emit
        self._on_event = on_event

    # ── Asst C API 直调 ─────────────────────────────────
    def append_task(self, type_name: str, params: dict) -> int:
        """添加一个任务（返回 task_id；0 表示参数不被接受）。"""
        payload = json.dumps(params, ensure_ascii=False)
        task_id = int(
            self._lib.AsstAppendTask(self._ptr, type_name.encode("utf-8"), payload.encode("utf-8"))
        )
        if not task_id:
            # 诊断：记录被引擎拒绝的完整参数（实机排障用）
            log.error("AsstAppendTask rejected type=%s params=%s", type_name, payload)
        return task_id

    def set_task_params(self, task_id: int, params: dict) -> bool:
        return bool(
            self._lib.AsstSetTaskParams(
                self._ptr, int(task_id), json.dumps(params, ensure_ascii=False).encode("utf-8")
            )
        )

    def start(self) -> bool:
        """非阻塞：AsstStart 立即返回，引擎后台线程执行，结果走回调。"""
        return bool(self._lib.AsstStart(self._ptr))

    def stop(self) -> bool:
        return bool(self._lib.AsstStop(self._ptr))

    def running(self) -> bool:
        return bool(self._lib.AsstRunning(self._ptr))

    def close(self) -> None:
        """销毁实例（幂等，teardown 绝不抛异常）。"""
        if self.closed:
            return
        self.closed = True
        self._emit = _DEFAULT_EMIT
        self._on_event = None
        try:
            self._lib.AsstDestroy(self._ptr)
        except Exception:  # noqa: BLE001 - teardown must never raise
            log.debug("AsstDestroy failed (ignored) device=%s", self.device_id)
        self._ptr = 0
        self._cb_ref = None

    # ── 回调解析 ─────────────────────────────────────────
    def _dispatch(self, msg: int, details: bytes) -> None:
        d: dict[str, Any] = {}
        if details:
            try:
                d = json.loads(details.decode("utf-8", errors="replace"))
            except ValueError:
                d = {}
        on_event = self._on_event
        if msg == 0:
            self._emit("error", "[引擎] 内部错误")
        elif msg == 1:
            self._emit("error", f"[引擎] 初始化失败：{d.get('what', '')} {d.get('why', '')}")
        elif msg == 2:
            self._conn_info(d)
        elif msg == 3:
            if on_event:
                on_event({"event": "all_completed"})
            self._emit("ok", "── 全部任务完成 ──")
        elif msg == 10000:
            if on_event:
                on_event({"event": "task_error", "taskchain": d.get("taskchain", "")})
            self._emit("error", f"[任务链] {d.get('taskchain', '')} 执行错误")
        elif msg == _MSG_START:
            if on_event:
                on_event(
                    {"event": "task_start", "taskchain": d.get("taskchain", ""), "taskid": d.get("taskid")}
                )
            self._emit("info", f"▶ 任务链 {d.get('taskchain', '')} 开始")
        elif msg == _MSG_COMPLETED:
            if on_event:
                on_event(
                    {"event": "task_completed", "taskchain": d.get("taskchain", ""), "taskid": d.get("taskid")}
                )
            self._emit("ok", f"✔ 任务链 {d.get('taskchain', '')} 完成")
        elif msg == _MSG_STOPPED:
            if on_event:
                on_event(
                    {"event": "task_stopped", "taskchain": d.get("taskchain", ""), "taskid": d.get("taskid")}
                )
            self._emit("warn", f"■ 任务链 {d.get('taskchain', '')} 已停止")
        elif msg == 20000:
            self._emit("warn", f"[子任务] {d.get('subtask', '')} 识别/执行错误")
        elif msg == 20003:
            self._extra_info(d)
            # 透传子任务额外信息（识别结果等）给 on_event 订阅方（工具箱识别会话用；
            # TaskRunner 忽略未知 event 类型）
            if on_event:
                on_event({"event": "extra_info", "payload": d})
        elif msg == 20004:
            self._emit("warn", f"[子任务] {d.get('subtask', '')} 已停止")
        # 其余（AsyncCallInfo/Destroyed/ReportRequest/SubTaskStart 等）静默

    def _conn_info(self, d: dict[str, Any]) -> None:
        what = d.get("what", "")
        table = {
            "ConnectFailed": ("error", "设备连接失败"),
            "Disconnect": ("error", "设备连接断开"),
            "ScreencapFailed": ("warn", "截图失败"),
            "Reconnecting": ("warn", "连接中断，正在重连…"),
            "UnsupportedResolution": ("warn", "分辨率不受支持"),
            "TouchModeNotAvailable": ("warn", "触控模式不可用"),
            "Connected": ("ok", "引擎已连接设备"),
            "UuidGot": ("ok", f"已获取设备唯一码 {d.get('uuid', '')}"),
            "ResolutionGot": ("info", "已获取分辨率"),
        }
        level, text = table.get(what, ("info", f"连接信息：{what}"))
        self._emit(level, f"[连接] {text}")

    def _extra_info(self, d: dict[str, Any]) -> None:
        what = d.get("what")
        det = d.get("details") or {}
        if what == "StageDrops":
            stage = (det.get("stage") or {}).get("stageCode", "")
            stars = det.get("stars", "?")
            drops = det.get("drops") or []
            brief = " · ".join(f"{x.get('itemName', '')}×{x.get('quantity', '')}" for x in drops[:6])
            self._emit("info", f"[掉落] {stage} {stars}星 {brief}".rstrip())
        elif what == "RecruitResult":
            result = det.get("result") or []
            top = result[0] if result else {}
            names = "、".join(o.get("name", "") for o in (top.get("opers") or [])[:4])
            self._emit("info", f"[公招] {top.get('level', '?')} 星组合：{names}")
        elif what == "RecruitSpecialTag":
            self._emit("ok", f"[公招] 特殊 Tag：{det.get('tag', '')}")
        elif what == "RecruitTagsDetected":
            self._emit("info", f"[公招] Tags：{'、'.join(det.get('tags') or [])}")
        elif what == "EnterFacility":
            self._emit("info", f"[基建] 进入设施 {det.get('facility', '')} #{det.get('index', '')}")
        elif what == "NotEnoughStaff":
            self._emit("warn", f"[基建] {det.get('facility', '')} 可用干员不足")
        elif what == "ProductOfFacility":
            self._emit("info", f"[基建] 产物：{det.get('product', '')}")
        elif what == "StageInfo":
            self._emit("info", f"[作战] 关卡 {det.get('name', '')}")
        elif what == "OfflineConfirm":
            # 游戏掉线/闪退确认弹窗：客户端据此决定自动重启续刷或停止
            self._emit("warn", "[作战] 游戏掉线/闪退")
            if self._on_event:
                self._on_event({"event": "offline_confirm"})

    @classmethod
    async def create(cls, device: Device, adb_path: str) -> AsstSession:
        """构建并连接一个设备会话（引擎/资源加载在线程池执行）。"""
        ok, reason = await asyncio.to_thread(_ensure_loaded)
        if not ok:
            raise EngineUnavailableError(reason or "MAA 引擎不可用")
        lib = _lib
        assert lib is not None  # _ensure_loaded 成功即已加载
        try:
            return await asyncio.to_thread(cls._create_sync, device, adb_path, lib)
        except EngineUnavailableError:
            raise
        except EngineCreateError:
            raise
        except Exception as exc:  # noqa: BLE001 - binding surface differences
            raise EngineCreateError(f"MAA 会话创建失败: {exc}") from exc

    @classmethod
    def _create_sync(cls, device: Device, adb_path: str, lib: AsstLib) -> AsstSession:
        holder: dict[str, AsstSession] = {}

        def _cb(msg: int, details: bytes, arg: Any) -> None:  # noqa: ANN001
            session = holder.get("session")
            if session is None:
                return
            try:
                session._dispatch(int(msg), details)
            except Exception:  # noqa: BLE001 - 回调线程绝不能抛异常
                log.exception("asst callback error msg=%s", msg)

        cb = lib.Callback(_cb)
        ptr = lib.AsstCreateEx(cb, None)
        if not ptr:
            raise EngineCreateError("MaaCore AsstCreateEx 返回空句柄")
        session = cls(device_id=device.id, ptr=ptr, lib=lib, cb_ref=cb)
        holder["session"] = session
        try:
            touch = _touch_mode_value(device.touch_mode)
            if touch:
                lib.AsstSetInstanceOption(ptr, 2, touch.encode("utf-8"))  # TouchMode
            # USB/本地 serial 设备（port<=0）直接以 serial 作为地址，否则 host:port
            address = (
                device.adb_host
                if device.adb_port <= 0
                else f"{device.adb_host}:{device.adb_port}"
            )
            connected = lib.AsstConnect(ptr, adb_path.encode("utf-8"), address.encode("utf-8"), b"General")
            if not connected:
                # MAA 客户端在 AsstConnect 失败时会停止而非继续：继续执行任务会让
                # MaaCore 在异常连接状态下崩溃（实测 UNHANDLED EXCEPTION → 进程退出），
                # 因此这里按失败处理，由 manager 映射为设备 error 状态。
                session.close()
                raise EngineCreateError(
                    f"MAA 引擎连接设备失败（{address}）—— 请检查 ADB 连接与触控模式"
                )
        except EngineCreateError:
            session.close()
            raise
        except Exception as exc:  # noqa: BLE001
            session.close()
            raise EngineCreateError(f"MAA 会话初始化失败: {exc}") from exc
        return session


def _touch_mode_value(mode: str | None) -> str:
    """设备 touch_mode → MAA InstanceOption TouchMode 值（未知值留空 = 引擎自动）。"""
    table = {
        "Minitouch": "minitouch",
        "MaaTouch": "maatouch",
        "Adb": "adb",
        "MaaFwAdb": "maafwadb",
        "MuMuExtras": "mumuextras",
    }
    return table.get((mode or "").strip(), "")


# ── 任务参数映射（前端 TaskItem → MAA AsstAppendTask 参数） ──

_DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    # client_type 不在此硬编码：由 to_asst_task 按设备配置注入（缺省 Official）
    "StartUp": {"start_game_enabled": True},
    "Recruit": {
        "select": [5, 4, 3, 2],
        "confirm": [5, 4, 3, 2],
        "refresh": False,
        "expedite": False,
    },
    "Infrast": {
        "facility": [
            "Mfg", "Trade", "Control", "Power", "Reception",
            "Office", "Dorm", "Processing", "Training",
        ],
        "drones": "_NotUse",
    },
}
_LEGACY_KEYS: dict[str, dict[str, str]] = {
    "Recruit": {"recruit_max_times": "times"},
    # Copilot 旧前端键名（auto_squad）→ 引擎键名（formation）
    "Copilot": {"auto_squad": "formation"},
}


def _to_user_additional(raw: Any) -> list[dict]:
    """前端追加干员 → 引擎 user_additional 结构 [{name, skill}]。

    兼容旧数据（字符串数组/逗号分隔字符串）与新结构（[{name, skill}]）。
    """
    out: list[dict] = []
    items = raw if isinstance(raw, list) else ([raw] if isinstance(raw, str) else [])
    for x in items:
        if isinstance(x, str) and x.strip():
            out.append({"name": x.strip(), "skill": 0})
        elif isinstance(x, dict) and x.get("name"):
            out.append({"name": str(x["name"]), "skill": int(x.get("skill") or 0)})
    return out


def to_asst_task(
    item: Any, client_type: str = "Official", account_name: str | None = None
) -> tuple[str, dict]:
    """把前端 TaskItem（entry + params）映射为 MAA (任务类型, 参数)。

    MAA 任务类型即 entry（StartUp/Fight/Recruit/Infrast/Mall/Award/Roguelike/
    Copilot…），参数补齐 MAA 必填字段（如 StartUp 的 client_type 取自设备配置）
    并做旧字段名兼容（recruit_max_times → times、auto_squad → formation）。
    account_name 为可选账号名（自动任务账号轮换用，引擎 AccountSwitchTask 原生支持）。
    """
    ttype = str(getattr(item, "entry", ""))
    params = dict(getattr(item, "params", None) or {})
    for old, new in _LEGACY_KEYS.get(ttype, {}).items():
        if old in params:
            params[new] = params.pop(old)
    merged = {**_DEFAULT_PARAMS.get(ttype, {}), **params}
    if ttype == "Fight":
        # 客户端本地行为（引擎不消费）：周计划由 taskrunner 按星期过滤，掉线重启由 runner 监听
        merged.pop("weekly_schedule", None)
        merged.pop("auto_restart_on_drop", None)
        # 战斗次数 -1/0 = 不限（对齐 MAA 客户端默认 int.MaxValue）：不下发，
        # 引擎 FightTimesTaskPlugin 默认 INT_MAX 即无限（次数不触发停止）
        t = merged.get("times")
        if t is not None and str(t).lstrip("-").isdigit() and int(t) <= 0:
            merged.pop("times", None)
    if ttype == "Copilot":
        # 前端 add_user_additional（[{name, skill}]）→ 引擎 user_additional
        ua = merged.pop("add_user_additional", None)
        if ua:
            merged["user_additional"] = _to_user_additional(ua)
        # 作业场景分发（对齐 MAA 客户端 CopilotView 场景页签 → AsstTaskType）：
        #   0/1 普通·SS → Copilot（引擎按 stageId 自动导航）
        #   2 悖论模拟 → ParadoxCopilot（标准作业格式，CopilotTask.cpp 明确要求用该类型）
        #   3 保全作战 → SSSCopilot（SSS 专用作业格式 + loop_times）
        mode = int(merged.pop("copilot_mode", 0) or 0)
        if mode == 2:
            ttype = "ParadoxCopilot"
        elif mode == 3:
            ttype = "SSSCopilot"
        # 未启用「使用编队」时禁掉编队编号（引擎 formation_index=0 表示不选）
        if not merged.get("use_formation"):
            merged["formation_index"] = 0
    if ttype == "Recruit":
        # 客户端 UI：3 星 Tag 倾向 / 保留 Tag 有启用开关，关闭时对应列表不传（旧数据无键则保留）
        if merged.get("prefer_tags_enabled") is False:
            merged["first_tags"] = []
        if merged.get("preserve_tags_enabled") is False:
            merged["preserve_tags"] = []
    if ttype == "Roguelike":
        # 使用种子为 UI 门控开关（引擎键 start_with_seed 为种子字符串），关闭时不下发
        if not merged.get("start_with_seed_enabled"):
            merged.pop("start_with_seed", None)
    if ttype in ("StartUp", "CloseDown"):
        # StartUp/CloseDown 的 client_type 为必填，缺省时注入设备配置
        if not merged.get("client_type"):
            merged["client_type"] = client_type or "Official"
        # 自动任务账号轮换：注入账号名（AccountSwitchTask 按此切换目标账号）
        if account_name and not merged.get("account_name"):
            merged["account_name"] = account_name
    return ttype, merged


# ── 会话池（device_id → AsstSession） ──────────────────────

_SESSION_POOL: dict[int, AsstSession] = {}


async def create_session(device: Device, adb_path: str) -> AsstSession:
    """创建并缓存设备会话（替换同设备旧会话）。"""
    old = _SESSION_POOL.pop(device.id, None)
    if old is not None:
        old.close()
    session = await AsstSession.create(device, adb_path)
    _SESSION_POOL[device.id] = session
    log.info("engine session created device=%s", device.id)
    return session


def close_session(device_id: int) -> None:
    session = _SESSION_POOL.pop(device_id, None)
    if session is not None:
        session.close()
        log.info("engine session closed device=%s", device_id)


def get_session(device_id: int) -> AsstSession | None:
    return _SESSION_POOL.get(device_id)


def session_count() -> int:
    return len(_SESSION_POOL)
