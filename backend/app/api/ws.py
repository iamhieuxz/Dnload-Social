from __future__ import annotations

import ipaddress
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.websocket_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter()


def _client_is_loopback(websocket: WebSocket) -> bool:
    """Reject WS clients whose peer address is not loopback. Backend is
    local-first; broadcast channels (system logs, job events) leak
    usernames + error messages, so a remote connection is never expected.
    Bypass only when LOCAL_API_BEHIND_LOOPBACK_PROXY=true is set
    explicitly."""
    if os.getenv("LOCAL_API_BEHIND_LOOPBACK_PROXY", "false").lower() == "true":
        return True
    client = websocket.client
    if client is None or not client.host:
        return False
    try:
        return ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        return False


@router.websocket("/ws/jobs/{job_id}")
async def ws_job(websocket: WebSocket, job_id: int) -> None:
    if not _client_is_loopback(websocket):
        await websocket.close(code=1008, reason="local access only")
        return
    channel = f"job:{job_id}"
    await ws_manager.connect(channel, websocket)
    try:
        while True:
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
    if not _client_is_loopback(websocket):
        await websocket.close(code=1008, reason="local access only")
        return
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
