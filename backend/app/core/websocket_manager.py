"""
WebSocket manager — broadcasts job logs / events to all connected clients.

Replaces the Tkinter queue-based log delivery. Clients subscribe via
WS endpoint /ws/jobs/{job_id} or /ws/system for global events.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


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
                "timestamp": datetime.utcnow().isoformat(),
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
        """
        message = json.dumps(
            {
                "type": event_type,
                "channel": channel,
                "timestamp": datetime.utcnow().isoformat(),
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


ws_manager = WebSocketManager()
