"""
Centralised logging configuration.

Sets up:
- stdout handler (full debug log, always)
- per-job memory buffer (so logs can be retrieved via API)
- broadcast to WebSocket clients in real-time, but ONLY for events the
  UI cares about: [NEW] file downloaded, [SKIP] file already on disk,
  [ERR] error name. Everything else stays in the file/stdout log and
  never reaches the user.
"""
from __future__ import annotations

import logging
import sys
from collections import deque
from threading import Lock
from typing import Deque

from app.core.websocket_manager import ws_manager


_buffers: dict[int, Deque[str]] = {}
# System-wide event stream (for the dashboard "Live terminal" panel and
# for HTTP-polling clients whose browsers can't open WebSocket connections).
# Only UI-facing events land here; internal logs go to stdout only.
_system_events: Deque[dict] = deque(maxlen=2000)
_system_cursor: int = 0  # monotonically increasing id; clients poll since id
_buffer_lock = Lock()
_BUFFER_SIZE = 5000  # keep last N lines per job in memory

# Message prefixes that are allowed through to the WebSocket / system
# event stream. Anything without one of these tags is treated as an
# internal log line and dropped from the broadcast path (still visible
# in the backend's own stdout).
_UI_LOG_PREFIXES = ("[NEW] ", "[SKIP] ", "[ERR] ", "[OK] ", "[RATE] ")


def _is_ui_visible(message: str) -> bool:
    return message.startswith(_UI_LOG_PREFIXES)


class WebSocketLogHandler(logging.Handler):
    """Pushes a filtered subset of log records to the WS manager.

    Only records whose formatted message carries a UI tag prefix
    ([NEW], [SKIP], [ERR], [OK], [RATE]) reach the WebSocket / polling
    stream. All other records still flow to stdout via the root logger
    but never leave the process — keeps the user-facing terminal
    focused on what actually changed (files, errors, rate-limits).
    """

    def __init__(self, job_id: int) -> None:
        super().__init__()
        self.job_id = job_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if not _is_ui_visible(msg):
                # Internal log line — keep in stdout (root logger
                # handler), skip the WS / system event stream entirely.
                return
            with _buffer_lock:
                buf = _buffers.setdefault(self.job_id, deque(maxlen=_BUFFER_SIZE))
                buf.append(msg)
                # also append to the system-wide stream (so polling clients
                # can read it via /api/logs/system)
                global _system_cursor
                _system_cursor += 1
                _system_events.append(
                    {
                        "id": _system_cursor,
                        "type": "log",
                        "ts": record.created,
                        "level": record.levelname,
                        "message": msg,
                        "job_id": self.job_id,
                    }
                )
            payload = {"job_id": self.job_id, "level": record.levelname, "message": msg}
            # 1) per-job channel (for the dedicated job log page)
            ws_manager.broadcast_sync(
                channel=f"job:{self.job_id}",
                event_type="log",
                data=payload,
            )
            # 2) global system channel (for the dashboard "Live terminal" panel)
            ws_manager.broadcast_sync(
                channel="system",
                event_type="log",
                data=payload,
            )
        except Exception:
            self.handleError(record)


def record_event(event_type: str, data: dict) -> None:
    """Append a non-log event (job_update, download_update, status) to the
    system-wide stream so HTTP-polling clients can receive it.

    Also broadcasts the same event over WebSocket so WS clients (the
    common case) see it in real time without waiting for the next poll.
    Without the broadcast the two transports drift: polling clients
    get every event, WS clients only get log lines.
    """
    global _system_cursor
    with _buffer_lock:
        _system_cursor += 1
        _system_events.append(
            {
                "id": _system_cursor,
                "type": event_type,
                "ts": __import__("time").time(),
                **data,
            }
        )
    # Best-effort broadcast — if no loop is bound yet (early startup)
    # or the channel has no listeners, just skip silently. The polling
    # path above still delivers the event.
    try:
        ws_manager.broadcast_sync("system", event_type, data)
    except Exception:
        pass


def get_job_logs(job_id: int, limit: int = 500) -> list[str]:
    with _buffer_lock:
        buf = _buffers.get(job_id, deque())
        return list(buf)[-limit:]


def get_system_events(since_id: int = 0, limit: int = 500) -> tuple[list[dict], int]:
    """Return system events with id > since_id (newest last), plus the latest
    id seen so the caller can use it for the next poll."""
    with _buffer_lock:
        items = [e for e in _system_events if e["id"] > since_id]
    if len(items) > limit:
        items = items[-limit:]
    latest = _system_cursor
    return items, latest


def clear_job_logs(job_id: int) -> None:
    with _buffer_lock:
        _buffers.pop(job_id, None)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)

    # Reset existing handlers (avoid duplicate logs on reload)
    for h in list(root.handlers):
        root.removeHandler(h)

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(stdout)
