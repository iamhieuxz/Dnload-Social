from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Download, DownloadStatus
from app.schemas import DownloadListResponse, DownloadOut, DownloadStats

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


class BatchCreateItem(BaseModel):
    url: str
    title: str | None = None
    author: str | None = None
    media_type: str | None = None
    account_id: int | None = None
    content_type: str | None = None  # post|story|highlight|tweet|live — drives layer routing


class BatchCreateRequest(BaseModel):
    platform: Literal["instagram", "twitter", "tiktok"]
    source_type: Literal["link", "list", "database"]
    items: list[BatchCreateItem] = Field(..., min_length=1, max_length=1000)


class BatchCreateResponse(BaseModel):
    created: int
    ids: list[int]


# ---- Literal paths MUST be declared before /{download_id} catch-all ----

@router.get("/pending-summary")
async def pending_summary(
    platform: str = Query(..., description="instagram | twitter | tiktok"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the number of pending / in-progress downloads for a platform.

    Used by the UI to decide whether to show "Resume pending (N items)"
    next to "Run pending". Anything in `downloading` is *also* counted as
    resumable — the runner's startup sweep will reset those back to
    `pending` on the next run, so a single count is fine for UX purposes.
    """
    from sqlalchemy import and_, or_
    rows = (await db.execute(
        select(Download.status, func.count(Download.id))
        .where(
            Download.platform == platform,
            or_(
                Download.status == DownloadStatus.PENDING,
                Download.status == DownloadStatus.DOWNLOADING,
            ),
        )
        .group_by(Download.status)
    )).all()
    pending = 0
    in_flight = 0
    for stat, cnt in rows:
        if stat == DownloadStatus.PENDING:
            pending = cnt
        elif stat == DownloadStatus.DOWNLOADING:
            in_flight = cnt
    return {
        "platform": platform,
        "pending": pending,
        "in_flight": in_flight,
        "resumable": pending + in_flight,
    }


@router.get("", response_model=DownloadListResponse)
async def list_downloads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    platform: str | None = Query(None, description="instagram | twitter | tiktok"),
    status: str | None = Query(None, description="pending|downloading|completed|failed|skipped"),
    source_type: str | None = Query(None, description="link|list|database"),
    search: str | None = Query(None, description="search title/file_name/author/url"),
    job_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> DownloadListResponse:
    stmt = select(Download)
    count_stmt = select(func.count(Download.id))

    if platform:
        stmt = stmt.where(Download.platform == platform)
        count_stmt = count_stmt.where(Download.platform == platform)
    if status:
        stmt = stmt.where(Download.status == status)
        count_stmt = count_stmt.where(Download.status == status)
    if source_type:
        stmt = stmt.where(Download.source_type == source_type)
        count_stmt = count_stmt.where(Download.source_type == source_type)
    if job_id is not None:
        stmt = stmt.where(Download.job_id == job_id)
        count_stmt = count_stmt.where(Download.job_id == job_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            (Download.title.ilike(like))
            | (Download.file_name.ilike(like))
            | (Download.author.ilike(like))
            | (Download.url.ilike(like))
        )
        count_stmt = count_stmt.where(
            (Download.title.ilike(like))
            | (Download.file_name.ilike(like))
            | (Download.author.ilike(like))
            | (Download.url.ilike(like))
        )

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Download.created_at.desc(), Download.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return DownloadListResponse(
        items=[DownloadOut.model_validate(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DownloadStats)
async def get_download_stats(db: AsyncSession = Depends(get_db)) -> DownloadStats:
    rows = (await db.execute(
        select(Download.platform, Download.status, Download.source_type, Download.file_size_bytes, Download.created_at)
    )).all()

    by_platform: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
    total_size = 0
    last_24h = 0
    last_7d = 0
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    total = len(rows)

    for plat, stat, src, size, created in rows:
        by_platform[plat] = by_platform.get(plat, 0) + 1
        by_status[stat] = by_status.get(stat, 0) + 1
        by_source[src] = by_source.get(src, 0) + 1
        if size:
            total_size += size
        if created and created >= day_ago:
            last_24h += 1
        if created and created >= week_ago:
            last_7d += 1

    return DownloadStats(
        total=total,
        by_platform=by_platform,
        by_status=by_status,
        by_source=by_source,
        total_size_bytes=total_size,
        last_24h=last_24h,
        last_7d=last_7d,
    )


@router.post("/batch", response_model=BatchCreateResponse, status_code=201)
async def batch_create(req: BatchCreateRequest, db: AsyncSession = Depends(get_db)) -> BatchCreateResponse:
    """Create many Download rows at once — used by the UI 'Add to queue' flow."""
    ids: list[int] = []
    for item in req.items:
        url = item.url.strip()
        if not url:
            continue
        # Default: IG → post, X → tweet, TikTok → tiktok. Per-item content_type overrides.
        if item.content_type:
            ct = item.content_type
        elif req.platform == "instagram":
            ct = "post"
        elif req.platform == "twitter":
            ct = "tweet"
        else:
            ct = "tiktok"
        d = Download(
            platform=req.platform,
            source_type=req.source_type,
            url=url,
            title=item.title,
            author=item.author,
            media_type=item.media_type,
            content_type=ct,
            account_id=item.account_id,
            status=DownloadStatus.PENDING,
        )
        db.add(d)
    await db.commit()
    # Recompute: count the newest N rows of this platform
    res = await db.execute(
        select(Download.id).where(Download.platform == req.platform).order_by(Download.id.desc()).limit(len(req.items))
    )
    ids = list(res.scalars().all())
    return BatchCreateResponse(created=len(ids), ids=ids)


@router.post("/run-pending", status_code=201)
async def run_pending(
    platform: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Take all pending downloads of a platform, create a Job, attach the
    downloads to it, and hand off to the JobRunner.

    This is the only entry point the UI uses to actually start a download.
    """
    from app.models import Job, JobStatus, JobType, Platform as Plat
    from app.services.job_runner import job_runner

    try:
        plat_enum = Plat(platform)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    if job_runner.is_busy:
        raise HTTPException(
            status_code=409,
            detail="Another job is currently running. Wait for it to finish or stop it first.",
        )

    # 1. Pick up all pending rows
    rows = (await db.execute(
        select(Download).where(
            Download.platform == plat_enum.value,
            Download.status == DownloadStatus.PENDING,
        ).order_by(Download.id.asc())
    )).scalars().all()

    if not rows:
        return {"marked": 0, "job_id": None, "items": []}

    # 2. Create a Job row to own the run
    job = Job(
        job_type=JobType.UPDATE_LIST,
        status=JobStatus.QUEUED,
        targets=json.dumps([d.url for d in rows]),
    )
    db.add(job)
    await db.flush()  # get job.id

    # 3. Attach downloads to the job and mark them as downloading
    items: list[dict] = []
    for d in rows:
        d.status = DownloadStatus.DOWNLOADING
        d.job_id = job.id
        items.append({"id": d.id, "url": d.url, "author": d.author, "title": d.title})

    await db.commit()

    # 4. Hand off to the runner (background)
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.create_task(job_runner.enqueue(job.id))

    return {"marked": len(items), "job_id": job.id, "items": items}


# ---- Per-id routes (must come AFTER literal paths) ----

@router.get("/{download_id}", response_model=DownloadOut)
async def get_download(download_id: int, db: AsyncSession = Depends(get_db)) -> DownloadOut:
    d = await db.get(Download, download_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Download not found")
    return DownloadOut.model_validate(d)


@router.delete("/{download_id}")
async def delete_download(download_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    d = await db.get(Download, download_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Download not found")
    await db.delete(d)
    await db.commit()
    return {"deleted": download_id}


@router.post("/{download_id}/retry", response_model=DownloadOut)
async def retry_download(download_id: int, db: AsyncSession = Depends(get_db)) -> DownloadOut:
    d = await db.get(Download, download_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Download not found")
    if d.status not in (DownloadStatus.FAILED, DownloadStatus.SKIPPED, DownloadStatus.COMPLETED):
        raise HTTPException(status_code=400, detail="Only failed/skipped/completed downloads can be retried")
    d.status = DownloadStatus.PENDING
    d.error_message = None
    d.completed_at = None
    await db.commit()
    await db.refresh(d)
    return DownloadOut.model_validate(d)
