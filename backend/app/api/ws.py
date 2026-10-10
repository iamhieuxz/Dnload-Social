from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.websocket_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def ws_job(websocket: WebSocket, job_id: int) -> None:
    channel = f"job:{job_id}"
    await ws_manager.connect(channel, websocket)
    try:
        while True:
            # We don't expect client messages, but keep the connection alive.
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(channel, websocket)
    except Exception:
        logger.exception("WS job connection error")
        await ws_manager.disconnect(channel, websocket)


@router.websocket("/ws/system")
async def ws_system(websocket: WebSocket) -> None:
    channel = "system"
    await ws_manager.connect(channel, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(channel, websocket)
    except Exception:
        logger.exception("WS system connection error")
        await ws_manager.disconnect(channel, websocket)
