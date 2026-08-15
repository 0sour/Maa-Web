"""全量配置导出 / 导入 API（2026-08-16）— 备份与恢复。

Routes:
    GET  /settings/export-config   导出全部配置为 zip（设备/方案/草稿/自动任务/
                                   设置含账号组/旧定时任务/运行时设置）
    POST /settings/import-config   覆盖式恢复（自动备份当前配置 → 清空重建，
                                   保留原 id 引用关系；支持 zip 或直接 config.json）

数据持久化说明：SQLite（maaweb.db）+ runtime_settings.json 均在 Docker named volume
`maaweb-config`（/data/config）——容器重启/重建/删除重建均不丢失；本导出功能用于
跨机迁移或手动备份。
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.models.auto_task import AutoSlot, AutoSlotAccount, AutoTask
from app.models.device import Device
from app.models.schedule import ScheduleJob
from app.models.setting import Setting
from app.models.task import TaskScheme
from app.schemas.settings import SETTING_GROUPS

log = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def _json_list(raw: str) -> list:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


async def _collect_config(session: AsyncSession) -> dict:
    """收集全部配置数据（设备/方案/草稿/自动任务/设置/旧定时任务/运行时设置）。"""
    devices = []
    for d in (await session.execute(select(Device))).scalars().all():
        devices.append({
            "id": d.id, "name": d.name, "adb_host": d.adb_host, "adb_port": d.adb_port,
            "touch_mode": d.touch_mode, "client_type": d.client_type,
            "status": "offline",  # 恢复后按实际连接重新探测
        })

    # settings 全量（含 queue_draft.* 草稿键）
    rows = (await session.execute(select(Setting))).scalars().all()
    groups: dict[str, dict[str, object]] = {g: {} for g in SETTING_GROUPS}
    queue_drafts: dict[str, list] = {"daily": [], "tasks": []}
    for row in rows:
        try:
            value = json.loads(row.value)
        except (ValueError, TypeError):
            value = row.value
        if row.key.startswith("queue_draft."):
            name = row.key.split(".", 1)[1]
            if name in queue_drafts and isinstance(value, list):
                queue_drafts[name] = value
            continue
        group, _, rest = row.key.partition(".")
        if group in groups and rest:
            groups[group][rest] = value

    schemes = []
    for s in (await session.execute(select(TaskScheme))).scalars().all():
        schemes.append({"id": s.id, "name": s.name, "tasks": _json_list(s.tasks)})

    auto_tasks = []
    for t in (await session.execute(select(AutoTask))).scalars().all():
        slots = (
            (
                await session.execute(
                    select(AutoSlot).where(AutoSlot.task_id == t.id).order_by(AutoSlot.id)
                )
            )
            .scalars()
            .all()
        )
        slot_out = []
        for sl in slots:
            accs = (
                (
                    await session.execute(
                        select(AutoSlotAccount).where(AutoSlotAccount.slot_id == sl.id)
                    )
                )
                .scalars()
                .all()
            )
            slot_out.append({
                "id": sl.id, "name": sl.name, "enabled": sl.enabled,
                "weekdays": _json_list(sl.weekdays), "time": sl.time, "conflict": sl.conflict,
                "accounts": [
                    {
                        "id": a.id, "position": a.position, "account_name": a.account_name,
                        "client_type": a.client_type, "enabled": a.enabled,
                        "plan_name": a.plan_name, "tasks": _json_list(a.tasks),
                    }
                    for a in accs
                ],
            })
        auto_tasks.append({
            "id": t.id, "name": t.name, "enabled": t.enabled,
            "device_id": t.device_id, "slots": slot_out,
        })

    schedule_jobs = []
    for j in (await session.execute(select(ScheduleJob))).scalars().all():
        schedule_jobs.append({
            "id": j.id, "device_id": j.device_id, "name": j.name, "enabled": j.enabled,
            "weekdays": _json_list(j.weekdays), "time": j.time,
            "plan_name": j.plan_name, "tasks": _json_list(j.tasks),
        })

    from app.core import runtime_settings

    rs = dict(runtime_settings.load())
    rs.pop("_configured", None)

    return {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "devices": devices,
        "settings": groups,
        "queue_drafts": queue_drafts,
        "task_schemes": schemes,
        "auto_tasks": auto_tasks,
        "schedule_jobs": schedule_jobs,
        "runtime_settings": rs,
    }


async def _build_export_zip(session: AsyncSession) -> bytes:
    """打包 config.json + README 为 zip 字节。"""
    config = await _collect_config(session)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))
        zf.writestr(
            "README.txt",
            "Maa-Web 全量配置备份\n"
            "包含：设备 / 任务方案 / 队列草稿 / 自动任务 / 设置（含账号组）/ 旧定时任务 / 运行时设置（镜像源、代理等）。\n"
            "恢复：设置 → 问题反馈 → 导入配置（覆盖当前配置，导入前会自动备份当前配置）。\n"
            f"导出时间：{config['exported_at']}\n",
        )
    buf.seek(0)
    return buf.getvalue()


@router.get("/export-config")
async def export_config(
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """导出全部配置为 zip（备份/迁移用，含设置与账号组等全部持久数据）。"""
    data = await _build_export_zip(session)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="maaweb-config-{ts}.zip"'},
    )


@router.post("/import-config")
async def import_config(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """覆盖式恢复配置：自动备份当前配置 → 清空重建（保留原 id，引用关系不变）。

    支持上传 zip（含 config.json）或直接 config.json。
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT, detail="上传文件为空")
    # 解析：zip 内取 config.json；否则按 JSON 解析
    data: dict | None = None
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            if "config.json" not in names:
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="zip 内缺少 config.json",
                )
            raw = zf.read("config.json")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"配置解析失败：{exc}",
        ) from exc
    if not isinstance(data, dict) or "version" not in data:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="不是有效的 Maa-Web 配置备份",
        )

    # 1) 自动备份当前配置（导入前）
    backup = await _build_export_zip(session)
    backup_dir = get_settings().log_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"import-backup-{ts}.zip"
    backup_path.write_bytes(backup)
    log.info("config import: backup saved to %s", backup_path)

    # 2) 清空现有配置表（session 已在 FastAPI dependency 事务中，直接执行后统一 commit）
    await session.execute(delete(AutoSlotAccount))
    await session.execute(delete(AutoSlot))
    await session.execute(delete(AutoTask))
    await session.execute(delete(TaskScheme))
    await session.execute(delete(ScheduleJob))
    await session.execute(delete(Device))
    await session.execute(delete(Setting))

    # 3) 重建（保留原 id，引用关系不变）
    for d in data.get("devices", []):
        session.add(Device(
            id=d["id"], name=d.get("name", ""), adb_host=d.get("adb_host", ""),
            adb_port=int(d.get("adb_port", 5555)),
            touch_mode=d.get("touch_mode", "Minitouch"),
            client_type=d.get("client_type", "Official"),
            status="offline",
        ))
    for s in data.get("task_schemes", []):
        session.add(TaskScheme(
            id=s["id"], name=s.get("name", ""),
            tasks=json.dumps(s.get("tasks", []), ensure_ascii=False),
        ))
    for j in data.get("schedule_jobs", []):
        session.add(ScheduleJob(
            id=j["id"], device_id=j.get("device_id", 0), name=j.get("name", ""),
            enabled=bool(j.get("enabled", True)),
            weekdays=json.dumps(j.get("weekdays", [])),
            time=j.get("time", "06:00"),
            plan_name=j.get("plan_name", ""),
            tasks=json.dumps(j.get("tasks", []), ensure_ascii=False),
        ))
    for t in data.get("auto_tasks", []):
        session.add(AutoTask(
            id=t["id"], name=t.get("name", ""),
            enabled=bool(t.get("enabled", True)), device_id=t.get("device_id", 0),
        ))
        for sl in t.get("slots", []):
            session.add(AutoSlot(
                id=sl["id"], task_id=t["id"], name=sl.get("name", ""),
                enabled=bool(sl.get("enabled", True)),
                weekdays=json.dumps(sl.get("weekdays", [])),
                time=sl.get("time", "06:00"),
                conflict=sl.get("conflict", "queue"),
            ))
            for a in sl.get("accounts", []):
                session.add(AutoSlotAccount(
                    id=a["id"], slot_id=sl["id"],
                    position=int(a.get("position", 0)),
                    account_name=a.get("account_name", ""),
                    client_type=a.get("client_type", "Official"),
                    enabled=bool(a.get("enabled", True)),
                    plan_name=a.get("plan_name", ""),
                    tasks=json.dumps(a.get("tasks", []), ensure_ascii=False),
                ))
    for group, values in data.get("settings", {}).items():
        if group not in SETTING_GROUPS or not isinstance(values, dict):
            continue
        for key, value in values.items():
            session.add(Setting(
                key=f"{group}.{key}",
                value=json.dumps(value, ensure_ascii=False),
            ))
    for name, tasks in data.get("queue_drafts", {}).items():
        if name in ("daily", "tasks") and isinstance(tasks, list):
            session.add(Setting(
                key=f"queue_draft.{name}",
                value=json.dumps(tasks, ensure_ascii=False),
            ))
    await session.commit()

    # 4) 运行时设置热更新（镜像源/代理等，立即生效）
    from app.core import runtime_settings

    rs = data.get("runtime_settings", {})
    if isinstance(rs, dict):
        runtime_settings.update(**rs)

    return {
        "ok": True,
        "message": (
            f"配置已恢复：设备 {len(data.get('devices', []))} · "
            f"方案 {len(data.get('task_schemes', []))} · "
            f"自动任务 {len(data.get('auto_tasks', []))} · "
            f"设置分组 {sum(1 for v in data.get('settings', {}).values() if v)}"
        ),
        "backup": backup_path.name,
    }
