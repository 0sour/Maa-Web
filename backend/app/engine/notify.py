"""外部通知服务（M6，对齐 MAA 客户端 ExternalNotification）。

触发事件：complete（任务完成）/ error（任务出错）/ test（手动测试）。
渠道：serverchan（Server酱）/ dingtalk（钉钉群机器人，加签）/ custom（自定义 Webhook）。
配置存 Setting 表 notify.* 组：enabled_complete/enabled_error/enabled_stalled/details
+ channels（JSON 数组，含 enabled 开关）。每次发送逐渠道记录 notify_logs。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import quote_plus

import httpx
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.notify import NotifyLog
from app.models.setting import Setting

log = logging.getLogger(__name__)

_TIMEOUT = 10.0

# 事件 → 配置开关键（默认对齐 MAA 客户端：完成/出错默认开，卡住默认关）
_EVENT_SWITCH = {
    "complete": "enabled_complete",
    "error": "enabled_error",
    "stalled": "enabled_stalled",
    "test": None,
}
_SWITCH_DEFAULTS = {"enabled_complete": True, "enabled_error": True, "enabled_stalled": False}


async def _notify_settings() -> dict[str, Any]:
    """读取 notify.* 设置组（key 去前缀，JSON 反序列化）。"""
    out: dict[str, Any] = {}
    try:
        async with get_sessionmaker()() as s:
            rows = (
                (
                    await s.execute(
                        select(Setting).where(Setting.key.like("notify.%"))
                    )
                )
                .scalars()
                .all()
            )
        for row in rows:
            key = row.key.removeprefix("notify.")
            try:
                out[key] = json.loads(row.value)
            except (TypeError, json.JSONDecodeError):
                out[key] = row.value
    except Exception:  # noqa: BLE001 - 配置读取失败按空配置处理
        log.warning("notify settings read failed")
    return out


async def _record(
    channel: str, event: str, title: str, content: str, ok: bool, error: str | None
) -> None:
    try:
        async with get_sessionmaker()() as s:
            s.add(
                NotifyLog(
                    channel=channel, event=event, title=title,
                    content=content, ok=ok, error=error,
                )
            )
            await s.commit()
    except Exception:  # noqa: BLE001 - 记录失败不阻塞发送
        log.warning("notify log persist failed")


# ── 渠道消息构造 ─────────────────────────────────────────────

def _serverchan(ch: dict, title: str, content: str) -> tuple[str, dict, dict]:
    """Server酱：POST https://sctapi.ftqq.com/{key}.send，form 表单。"""
    url = f"https://sctapi.ftqq.com/{ch.get('send_key', '')}.send"
    return url, {"title": title, "desp": content}, {}


def _dingtalk(ch: dict, title: str, content: str) -> tuple[str, dict, dict]:
    """钉钉群机器人：access_token + 加签（HMAC-SHA256(secret, ts\\nsecret)）。"""
    ts = str(round(time.time() * 1000))
    secret = str(ch.get("secret", ""))
    sign = ""
    if secret:
        string_to_sign = f"{ts}\n{secret}"
        digest = hmac.new(
            secret.encode(), string_to_sign.encode(), digestmod=hashlib.sha256
        ).digest()
        sign = quote_plus(base64.b64encode(digest))
    url = (
        "https://oapi.dingtalk.com/robot/send"
        f"?access_token={ch.get('access_token', '')}&timestamp={ts}&sign={sign}"
    )
    body = {"msgtype": "text", "text": {"content": f"{title}\n{content}"}}
    return url, body, {}


def _custom(ch: dict, title: str, content: str) -> tuple[str, str, dict]:
    """自定义 Webhook：URL + Headers（每行 K: V）+ Body 模板（{title}/{content} 占位）。"""
    url = str(ch.get("url", ""))
    template = str(ch.get("body", "")).strip()
    headers: dict[str, str] = {}
    for line in str(ch.get("headers", "")).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    if template:
        body = template.replace("{title}", title).replace("{content}", content)
        headers.setdefault(
            "Content-Type",
            "application/json" if body.lstrip().startswith(("{", "[")) else "text/plain",
        )
    else:
        body = json.dumps({"title": title, "content": content}, ensure_ascii=False)
        headers.setdefault("Content-Type", "application/json")
    return url, body, headers


async def send(
    event: str, title: str, content: str
) -> list[dict[str, Any]]:
    """按配置渠道发送通知；逐渠道返回 {channel, ok, error}。失败不抛出。"""
    results: list[dict[str, Any]] = []
    try:
        cfg = await _notify_settings()
        switch = _EVENT_SWITCH.get(event)
        if switch and not cfg.get(switch, _SWITCH_DEFAULTS.get(switch, True)):
            return results
        channels = cfg.get("channels") or []
        if not isinstance(channels, list) or not channels:
            return results
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for ch in channels:
                if not isinstance(ch, dict) or not ch.get("enabled", True):
                    continue
                ch_type = str(ch.get("type", ""))
                ok, err = False, None
                try:
                    if ch_type == "serverchan":
                        url, payload, headers = _serverchan(ch, title, content)
                        resp = await client.post(url, data=payload, headers=headers)
                    elif ch_type == "dingtalk":
                        url, payload, headers = _dingtalk(ch, title, content)
                        resp = await client.post(url, json=payload, headers=headers)
                    elif ch_type == "custom":
                        url, payload, headers = _custom(ch, title, content)
                        resp = await client.post(url, content=payload, headers=headers)
                    else:
                        continue
                    ok = resp.status_code < 400
                    err = None if ok else f"HTTP {resp.status_code}: {resp.text[:200]}"
                except Exception as exc:  # noqa: BLE001 - 单渠道失败不影响其他
                    err = str(exc)[:300]
                await _record(ch_type, event, title, content, ok, err)
                results.append({"channel": ch_type, "ok": ok, "error": err})
    except Exception:  # noqa: BLE001 - 通知失败绝不冒泡
        log.exception("notify send failed event=%s", event)
    return results
