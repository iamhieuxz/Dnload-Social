"""
FastAPI application entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, cookies, downloads, gallery, jobs, logs, media, settings, stats, ws
from app.core.logging_config import configure_logging
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    # Capture the running loop so log handlers running on background threads
    # can broadcast WebSocket events back to the browser.
    import asyncio as _asyncio
    from app.core.websocket_manager import bind_event_loop
    bind_event_loop(_asyncio.get_running_loop())
    logger.info("Starting backend; download_folder=%s", settings.download_folder)
    yield
    logger.info("Shutting down backend")


app = FastAPI(
    title="Instagram Downloader API",
    version="7.0.0",
    description="Local server + DB manager for Instagram media downloading",
    lifespan=lifespan,
)

# CORS — allow the Next.js dev server (port 3000) to talk to us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


app.include_router(accounts.router)
app.include_router(jobs.router)
app.include_router(media.router)
app.include_router(stats.router)
app.include_router(settings.router)
app.include_router(cookies.router)
app.include_router(ws.router)
app.include_router(gallery.router)
app.include_router(downloads.router)
app.include_router(logs.router)
