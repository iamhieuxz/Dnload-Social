"""HTTP polling endpoint for system-wide events (fallback when the
browser cannot open WebSocket connections)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.logging_config import get_system_events

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/system")
async def get_system_logs(
    since: int = Query(0, ge=0, description="Return events with id > since"),
    limit: int = Query(200, ge=1, le=2000),
) -> dict:
    events, latest = get_system_events(since_id=since, limit=limit)
    return {"events": events, "latest": latest, "count": len(events)}
