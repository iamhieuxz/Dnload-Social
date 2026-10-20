"""Regression test: record_event broadcasts to the WebSocket manager in
addition to appending to the polling buffer.

Bug B-38 from docs/BUGS.md.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.core import logging_config


def test_record_event_broadcasts_to_ws() -> None:
    """A single record_event call must invoke ws_manager.broadcast_sync
    so WS clients see the event in real time, not just polling clients."""
    captured: list[tuple] = []
    fake_manager = MagicMock()
    fake_manager.broadcast_sync.side_effect = lambda *a, **k: captured.append((a, k))
    logging_config.ws_manager = fake_manager

    logging_config.record_event("download_update", {"id": 7, "status": "completed"})

    # The polling path was hit (the event is in the system stream).
    events, latest = logging_config.get_system_events(since_id=0, limit=10)
    assert any(e.get("type") == "download_update" for e in events)

    # AND the WS path was hit.
    assert len(captured) == 1, f"expected 1 WS broadcast, got {len(captured)}"
    args, kwargs = captured[0]
    # broadcast_sync(channel, event_type, data)
    assert args[0] == "system"
    assert args[1] == "download_update"
    assert args[2]["id"] == 7
    assert args[2]["status"] == "completed"

    # Cleanup — restore the real manager so other tests aren't affected.
    from app.core.websocket_manager import ws_manager
    logging_config.ws_manager = ws_manager
