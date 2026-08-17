"""工具箱识别执行器（M5）— 公招 / 仓库 / 干员识别。

实现：复用 asstproxy 会话通道，AppendTask 对应识别任务类型，从
AsstMsg 20003（SubTaskExtraInfo，经 asstproxy 透传为 extra_info 事件）
收集识别结果，任务链完成后解析为结构化 JSON。

任务类型与参数（对齐 MAA 客户端工具箱 ToolboxViewModel / AsstRecruitTask）：
    recruit  → "Recruit"（注意：引擎无 RecruitCalc 任务——客户端工具箱
               枚举 RecruitCalc 仅 UI 层标记，实际 append 的是 AsstRecruitTask
               序列化的 "Recruit"；confirm=[-1] 触发 calc-only 纯识别模式，
               times=0 不执行招募）
    depot    → "Depot"
    operbox  → "OperBox"

结果结构（对齐 MAA 客户端解析）：
    recruit: {tags: [...], results: [{level, tags: [...], opers: [{id, name, level}]}]}
    depot:   {items: {item_id: count}}
    operbox: {opers: [{id, rarity, elite, level, potential}]}
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.db.session import get_sessionmaker
from app.engine import adb, asstproxy
from app.engine.taskrunner import TaskRunner
from app.models.device import Device

log = logging.getLogger(__name__)

# 识别任务类型映射（引擎 AsstAppendTask type，白名单见 MaaCore Assistant.cpp）
_TOOL_TASKS: dict[str, str] = {
    "recruit": "Recruit",
    "depot": "Depot",
    "operbox": "OperBox",
}

# 识别默认参数（对齐 MAA 客户端 AsstRecruitTask.Serialize()；
# confirm=[-1] = calc-only 纯识别，不消耗招募许可）
_TOOL_PARAMS: dict[str, dict] = {
    "recruit": {
        "refresh": False,
        "force_refresh": False,
        "select": [],
        "confirm": [-1],
        "times": 0,
        "set_time": True,
        "expedite": False,
        "preserve_tags": [],
        "extra_tags_mode": 0,
        "first_tags": [],
        "recruitment_time": {"3": 60, "4": 60, "5": 540, "6": 540},
        "report_to_penguin": False,
        "report_to_yituliu": False,
        "server": "CN",
    },
    "depot": {},
    "operbox": {},
}

# 识别超时（仓库扫描需翻页，放宽）
_RECOGNIZE_TIMEOUT = 120.0


class ToolboxError(RuntimeError):
    """工具箱操作错误（设备不可用/识别失败等）。"""


def _get_payload(msg: dict) -> tuple[str, dict]:
    """从 20003 消息提取 (what, 识别数据层)。

    兼容两种结构：what/识别键在消息顶层，或在 details/details.details 内。
    """
    what = str(msg.get("what") or "")
    d = msg.get("details")
    if not isinstance(d, dict):
        return what, {}
    # 优先找含识别键的层（result/data/own_opers/tags）
    for cand in (d, d.get("details")):
        if isinstance(cand, dict) and any(k in cand for k in ("result", "data", "own_opers", "tags")):
            if not what:
                what = str(cand.get("what") or msg.get("what") or "")
            return what, cand
    return what, d


def _parse_recruit(what: str, payload: dict, acc: dict) -> None:
    """公招识别：RecruitResult → results[]；RecruitTagsDetected → tags。"""
    if what == "RecruitResult":
        results = payload.get("result") or []
        if isinstance(results, list):
            acc["results"] = [
                {
                    "level": int(r.get("level", 0) or 0),
                    "tags": [str(t) for t in (r.get("tags") or [])],
                    "opers": [
                        {"id": str(o.get("id", "")), "name": str(o.get("name", "")),
                         "level": int(o.get("level", 0) or 0)}
                        for o in (r.get("opers") or [])
                        if isinstance(o, dict)
                    ],
                }
                for r in results
                if isinstance(r, dict)
            ]
    elif what == "RecruitTagsDetected":
        tags = payload.get("tags") or []
        if isinstance(tags, list):
            acc["tags"] = [str(t) for t in tags]


def _parse_depot(what: str, payload: dict, acc: dict) -> None:
    """仓库识别：data = {item_id: count}（新格式）；arkplanner items 兜底。"""
    if "data" in payload:
        data = payload.get("data")
        items: dict[str, int] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                try:
                    items[str(k)] = int(v)
                except (TypeError, ValueError):
                    continue
        elif isinstance(data, str) and data:
            try:
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        try:
                            items[str(k)] = int(v)
                        except (TypeError, ValueError):
                            continue
            except ValueError:
                pass
        if items:
            acc["items"] = items
    if not acc.get("items"):
        ark = payload.get("arkplanner") or {}
        obj = ark.get("object") or {}
        for item in obj.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                try:
                    acc.setdefault("items", {})[str(item["id"])] = int(item.get("count", 0))
                except (TypeError, ValueError):
                    continue


def _parse_operbox(what: str, payload: dict, acc: dict) -> None:
    """干员识别：own_opers = [{id, rarity, elite, level, potential}]。"""
    opers = payload.get("own_opers") or []
    if isinstance(opers, list):
        acc["opers"] = [
            {
                "id": str(o.get("id", "")),
                "rarity": int(o.get("rarity", 0) or 0),
                "elite": int(o.get("elite", 0) or 0),
                "level": int(o.get("level", 0) or 0),
                "potential": int(o.get("potential", 0) or 0),
            }
            for o in opers
            if isinstance(o, dict) and o.get("id")
        ]


_PARSERS: dict[str, Any] = {
    "recruit": _parse_recruit,
    "depot": _parse_depot,
    "operbox": _parse_operbox,
}


class _RecognizeSession:
    """一次识别会话：捕获 extra_info 消息 → 解析结果。"""

    def __init__(self, tool: str) -> None:
        self._tool = tool
        self._loop = asyncio.get_running_loop()
        self._q: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self.acc: dict[str, Any] = {"tags": []} if tool == "recruit" else {}
        self.done = asyncio.Event()
        self.error: str | None = None

    def on_event(self, ev: dict) -> None:
        """asstproxy 事件回调（引擎线程）→ 事件循环队列。"""
        self._loop.call_soon_threadsafe(self._q.put_nowait, ("ev", ev))

    def on_emit(self, level: str, msg: str) -> None:
        self._loop.call_soon_threadsafe(self._q.put_nowait, ("log", (level, msg)))

    async def run(self, device: Device) -> dict:
        """执行识别任务并等待结果（任务链完成 / 错误 / 超时）。"""
        session = await asstproxy.create_session(device, adb.resolve_adb_path())
        session.set_handler(self.on_emit, self.on_event)
        ttype = _TOOL_TASKS[self._tool]
        params = dict(_TOOL_PARAMS[self._tool])
        task_id = await asyncio.to_thread(session.append_task, ttype, params)
        if not task_id:
            raise ToolboxError(f"{ttype} 任务添加失败（参数不被引擎接受）")
        if not await asyncio.to_thread(session.start):
            raise ToolboxError("AsstStart 启动失败")

        try:
            await asyncio.wait_for(self._collect(), timeout=_RECOGNIZE_TIMEOUT)
        except TimeoutError as exc:
            raise ToolboxError("识别超时（设备画面可能不在对应界面）") from exc
        finally:
            try:
                await asyncio.to_thread(session.stop)
            except Exception:  # noqa: BLE001 - teardown
                pass
        if self.error:
            raise ToolboxError(self.error)
        return self.acc

    async def _collect(self) -> None:
        while True:
            kind, payload = await self._q.get()
            if kind == "ev":
                event = payload.get("event")
                if event == "extra_info":
                    msg = payload.get("payload") or {}
                    what, data = _get_payload(msg)
                    _PARSERS[self._tool](what, data, self.acc)
                elif event == "task_error":
                    self.error = f"任务链 {payload.get('taskchain', '')} 执行失败"
                    self.done.set()
                elif event == "all_completed":
                    self.done.set()
            if self.done.is_set():
                return


# ── 任务状态（进程内；识别完成后结果写入 toolbox_records） ──────────────

_TASKS: dict[str, dict[str, Any]] = {}
_seq = 0


async def recognize(device: Device, tool: str) -> dict:
    """执行识别并返回结构化结果（供 API 调用）。"""
    if tool not in _TOOL_TASKS:
        raise ToolboxError(f"不支持的识别工具：{tool}")
    # 设备串行约束：识别与任务队列互斥
    runner = TaskRunner.get(device.id)
    if runner.status in ("RUNNING", "STOPPING"):
        raise ToolboxError("设备正在执行任务，请先停止")
    sess = _RecognizeSession(tool)
    result = await sess.run(device)
    if tool == "recruit" and not result.get("results") and not result.get("tags"):
        raise ToolboxError("未识别到公招界面信息（请确认设备画面在公招界面）")
    if tool == "depot" and not result.get("items"):
        raise ToolboxError("未识别到仓库数据（请确认设备画面在仓库/物品界面）")
    if tool == "operbox" and not result.get("opers"):
        raise ToolboxError("未识别到干员数据（请确认设备画面在干员界面）")
    return result


def start_recognize(device: Device, tool: str) -> str:
    """后台启动识别任务，返回 task_id（结果写 toolbox_records）。"""
    global _seq
    _seq += 1
    task_id = f"tb-{_seq}"
    _TASKS[task_id] = {"status": "running", "result": None, "error": None}

    async def _worker() -> None:
        try:
            result = await recognize(device, tool)
            _TASKS[task_id]["result"] = result
            _TASKS[task_id]["status"] = "done"
            await _save_record(device.id, tool, result)
        except Exception as exc:  # noqa: BLE001 - 单任务失败不影响其他
            _TASKS[task_id]["error"] = str(exc)
            _TASKS[task_id]["status"] = "error"
            log.warning("toolbox recognize failed task=%s: %s", task_id, exc)

    asyncio.create_task(_worker())
    return task_id


def task_status(task_id: str) -> dict | None:
    t = _TASKS.get(task_id)
    if t is None:
        return None
    return dict(t)


async def _save_record(device_id: int, tool: str, result: dict) -> None:
    from app.models.toolbox import ToolboxRecord

    async with get_sessionmaker()() as s:
        s.add(ToolboxRecord(
            tool=tool, device_id=device_id,
            result=json.dumps(result, ensure_ascii=False),
        ))
        await s.commit()


def summary_of(tool: str, result: dict) -> str:
    """识别结果 → 历史记录摘要（前端列表展示）。"""
    if tool == "recruit":
        results = result.get("results") or []
        if results:
            top = max(results, key=lambda r: r["level"])
            names = "、".join(o["name"] for o in top["opers"][:4])
            return f"{top['level']}★ 组合：{names}"
        return f"识别到 {len(result.get('tags') or [])} 个 Tag"
    if tool == "depot":
        items = result.get("items") or {}
        return f"材料 {len(items)} 种"
    if tool == "operbox":
        opers = result.get("opers") or []
        r6 = sum(1 for o in opers if o["rarity"] >= 5)
        return f"干员 {len(opers)} 名 · 六星 {r6}"
    return ""
