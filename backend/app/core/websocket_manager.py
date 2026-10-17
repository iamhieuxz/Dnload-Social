"""
WebSocket manager — broadcasts job logs / events to all connected clients.

Replaces the Tkinter queue-based log delivery. Clients subscribe via
WS endpoint /ws/jobs/{job_id} or /ws/system for global events.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# How many messages per second the "system" channel will accept from
# broadcast_sync (the noisy one fed by the log handler). Anything above
# this gets dropped at the manager, so the WebSocket send loop never
# gets swamped and the React UI stops stuttering. Per-job channels and
# the async broadcast() are NOT throttled — they're called by code
# paths that already produce one event per meaningful state change.
_SYSTEM_MAX_PER_SECOND = 20
_system_dropped_total: int = 0
_system_window_start: float = 0.0
_system_window_count: int = 0
_system_window_lock = threading.Lock()


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[channel].add(websocket)
        logger.info("WS connected to channel=%s, total=%s", channel, len(self._connections[channel]))

    async def disconnect(self, channel: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[channel].discard(websocket)
        logger.info("WS disconnected from channel=%s", channel)

    async def broadcast(self, channel: str, event_type: str, data: Any) -> None:
        message = json.dumps(
            {
                "type": event_type,
                "channel": channel,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            },
            default=str,
        )
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in list(self._connections[channel]):
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections[channel].discard(ws)

    def broadcast_sync(self, channel: str, event_type: str, data: Any) -> None:
        """Schedule a broadcast from non-async code (e.g. background job thread).

        Tries the running loop first; if there is none, we fall back to the
        global loop that uvicorn keeps alive, so logs from worker threads
        are never silently dropped.

        The "system" channel is throttled: gallery-dl / yt-dlp can print
        dozens of lines per second, and broadcasting every single one
        pushes hundreds of JSON-encoded messages per second at the React
        UI, which then re-renders the Live terminal panel and stutters.
        We cap the channel at _SYSTEM_MAX_PER_SECOND messages and drop
        the excess — the per-job channel is unaffected because users
        looking at a single job want every line, and the buffer in
        logging_config still keeps the full stream for the API endpoint.
        """
        if channel == "system" and event_type == "log":
            global _system_window_count, _system_window_start, _system_dropped_total
            with _system_window_lock:
                now = time.monotonic()
                if now - _system_window_start >= 1.0:
                    _system_window_start = now
                    _system_window_count = 0
                if _system_window_count >= _SYSTEM_MAX_PER_SECOND:
                    _system_dropped_total += 1
                    return
                _system_window_count += 1

        message = json.dumps(
            {
                "type": event_type,
                "channel": channel,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            },
            default=str,
        )

        async def _send_all() -> None:
            async with self._lock:
                dead: list[WebSocket] = []
                for ws in list(self._connections[channel]):
                    try:
                        await ws.send_text(message)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    self._connections[channel].discard(ws)

        # 1) Fast path — caller is on the same thread that owns a running loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_send_all())
            return
        except RuntimeError:
            pass

        # 2) Slow path — caller is on a worker thread (no loop here).
        # Hand the coroutine off to the loop uvicorn is running, if any.
        global _fastapi_loop
        loop = _fastapi_loop
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(asyncio.ensure_future, _send_all())
            except RuntimeError:
                pass


# Stored reference to the loop that uvicorn runs in, so worker threads can
# push events without losing them.
_fastapi_loop: asyncio.AbstractEventLoop | None = None


def bind_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Call this once from the FastAPI startup hook with the main loop."""
    global _fastapi_loop
    _fastapi_loop = loop


def get_throttle_stats() -> dict:
    """Diagnostic counter — how many messages were dropped by the system-
    channel throttle. Useful for checking the front-end isn't starving."""
    return {
        "dropped_total": _system_dropped_total,
        "max_per_second": _SYSTEM_MAX_PER_SECOND,
    }


def reset_throttle_stats() -> None:
    global _system_dropped_total, _system_window_count, _system_window_start
    with _system_window_lock:
        _system_dropped_total = 0
        _system_window_count = 0
        _system_window_start = 0.0


ws_manager = WebSocketManager()
