"""
FastAPI application entry point.
"""
from __future__ import annotations

import logging
import ipaddress
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# Reconfigure stdout/stderr to UTF-8 so logger.info with non-ASCII
# (e.g. "→", emoji) doesn't crash on Windows cp1252 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.api import accounts, cookies, downloads, gallery, jobs, logs, media, settings, stats, ws
from app.core.logging_config import configure_logging
from app.config import get_settings
from app.database import session_scope
from app.models import Download, DownloadStatus, Job, JobStatus


async def _reset_stale_jobs() -> None:
    """On startup, mark any RUNNING/QUEUED job from a previous process as FAILED
    and detach its downloads so the next run-pending can re-pick them up.

    Without this, a kill-9 or container restart leaves the job row in
    'running' forever — dashboard reports a phantom active job and
    JobRunner rejects new work via _lock until restart.
    """
    logger = logging.getLogger(__name__)
    try:
        async with session_scope() as session:
            # Jobs: any RUNNING/QUEUED from a previous process → FAILED
            jobs_result = await session.execute(
                update(Job)
                .where(Job.status.in_([JobStatus.RUNNING, JobStatus.QUEUED]))
                .values(
                    status=JobStatus.FAILED,
                    finished_at=datetime.now(timezone.utc),
                    error_message="Backend restarted while job was active",
                )
            )
            if jobs_result.rowcount:
                logger.warning(
                    "Startup sweep: marked %s stale jobs as FAILED",
                    jobs_result.rowcount,
                )

            # Downloads: any DOWNLOADING → PENDING so the next run-pending picks them up
            dl_result = await session.execute(
                update(Download)
                .where(Download.status == DownloadStatus.DOWNLOADING)
                .values(status=DownloadStatus.PENDING, job_id=None)
            )
            if dl_result.rowcount:
                logger.warning(
                    "Startup sweep: reset %s stuck DOWNLOADING rows to PENDING",
                    dl_result.rowcount,
                )
    except Exception:
        logger.exception("Startup sweep failed; continuing anyway")


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
    await _reset_stale_jobs()
    logger.info("Starting backend; download_folder=%s", settings.download_folder)
    yield
    logger.info("Shutting down backend")


app = FastAPI(
    title="Instagram Downloader API",
    version="7.0.0",
    description="Local server + DB manager for Instagram media downloading",
    lifespan=lifespan,
)


@app.middleware("http")
async def restrict_to_local_clients(request: Request, call_next):
    """Protect this local file-management API from remote browser requests."""
    behind_loopback_proxy = os.getenv("LOCAL_API_BEHIND_LOOPBACK_PROXY", "false").lower() == "true"
    forwarded_host = request.headers.get("x-forwarded-host") if behind_loopback_proxy else None
    host_header = (forwarded_host or request.headers.get("host", "")).split(":", 1)[0].strip("[]").lower()
    if host_header not in {"localhost", "127.0.0.1", "::1", "testserver"}:
        return JSONResponse({"detail": "Invalid Host header"}, status_code=400)

    client_host = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(client_host)
        is_local = ip.is_loopback
    except ValueError:
        # Non-IP clients (unix socket in tests, etc.) — only allowed
        # via the explicit proxy bypass.
        is_local = behind_loopback_proxy or client_host.lower() == "testclient"
    if not is_local:
        return JSONResponse({"detail": "Local access only"}, status_code=403)
    return await call_next(request)

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
    # Cheap DB ping — catches the case where the SQLite file moved or
    # the Postgres connection died since startup. We don't fail the
    # health check on this; the operator dashboard surfaces it.
    db_ok = True
    try:
        async with session_scope() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    # Cheap Fernet key check — same failure mode the BUGS.md
    # "stale-jobs-running" item was logging silently.
    fernet_ok = True
    try:
        from app.core.cookie_vault import _fernet  # type: ignore[attr-defined]
        _fernet()
    except Exception:
        fernet_ok = False
    return {
        "status": "ok" if (db_ok and fernet_ok) else "degraded",
        "db": db_ok,
        "fernet": fernet_ok,
    }


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
