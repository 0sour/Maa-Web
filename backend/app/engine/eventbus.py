"""In-process pub/sub for task log streaming (S-05).

WebSocket handlers subscribe per device; the task runner publishes log lines
as they are produced. Async-only — run inside the event loop (no thread sync).
"""
from __future__ import annotations

import asyncio

# device_id → set of subscriber queues (one per connected WS client)
_subscribers: dict[int, set[asyncio.Queue]] = {}


def subscribe(device_id: int) -> asyncio.Queue:
    """Register a new subscriber queue for a device; returns the queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    _subscribers.setdefault(device_id, set()).add(q)
    return q


def unsubscribe(device_id: int, q: asyncio.Queue) -> None:
    """Remove a subscriber queue (WS disconnect)."""
    subs = _subscribers.get(device_id)
    if subs is None:
        return
    subs.discard(q)
    if not subs:
        _subscribers.pop(device_id, None)


def publish(device_id: int, payload: dict) -> None:
    """Broadcast a log payload to all WS subscribers of a device."""
    subs = _subscribers.get(device_id)
    if not subs:
        return
    for q in list(subs):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Slow consumer — drop the oldest line to keep the stream live.
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


def subscriber_count(device_id: int) -> int:
    return len(_subscribers.get(device_id, ()))
