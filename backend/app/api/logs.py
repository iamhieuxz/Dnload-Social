"""HTTP polling endpoint for system-wide events (fallback when the
browser cannot open WebSocket connections)."""
from __future__ import annotations

import time

from fastapi import APIRouter, Query

from app.core.logging_config import get_system_events

router = APIRouter(prefix="/api/logs", tags=["logs"])

# Cache the response for 500ms so 10 clients polling at 1Hz share a single
# DB read instead of stampeding the event buffer.
_CACHE_TTL_SECONDS = 0.5
_cache: dict[tuple[int, int], tuple[float, dict]] = {}


def _cache_get(since: int, limit: int) -> dict | None:
    key = (since, limit)
    hit = _cache.get(key)
    if hit is None:
        return None
    cached_at, payload = hit
    if time.monotonic() - cached_at > _CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return payload


def _cache_put(since: int, limit: int, payload: dict) -> None:
    _cache[(since, limit)] = (time.monotonic(), payload)


@router.get("/system")
async def get_system_logs(
    since: int = Query(0, ge=0, description="Return events with id > since"),
    limit: int = Query(200, ge=1, le=2000),
) -> dict:
    cached = _cache_get(since, limit)
    if cached is not None:
        return cached
    events, latest = get_system_events(since_id=since, limit=limit)
    payload = {"events": events, "latest": latest, "count": len(events)}
    _cache_put(since, limit, payload)
    return payload