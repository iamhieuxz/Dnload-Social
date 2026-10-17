from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Download, DownloadStatus
from app.schemas import DownloadListResponse, DownloadOut, DownloadStats
from app.core.url_guard import validate_url as _validate_download_url

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
    """Return the number of pending / in-progress / failed downloads for a
    platform.

    Used by the UI to decide whether to show "Resume pending (N items)"
    next to "Run pending". Anything in `downloading` is *also* counted as
    resumable — the runner's startup sweep will reset those back to
    `pending` on the next run, so a single count is fine for UX purposes.
    The `failed` count is exposed so the Resume button can also show how
    many rows are eligible for one-click retry.
    """
    from sqlalchemy import and_, or_
    rows = (await db.execute(
        select(Download.status, func.count(Download.id))
        .where(
            Download.platform == platform,
            Download.status.in_([
                DownloadStatus.PENDING,
                DownloadStatus.DOWNLOADING,
                DownloadStatus.FAILED,
            ]),
        )
        .group_by(Download.status)
    )).all()
    pending = 0
    in_flight = 0
    failed = 0
    for stat, cnt in rows:
        if stat == DownloadStatus.PENDING:
            pending = cnt
        elif stat == DownloadStatus.DOWNLOADING:
            in_flight = cnt
        elif stat == DownloadStatus.FAILED:
            failed = cnt
    return {
        "platform": platform,
        "pending": pending,
        "in_flight": in_flight,
        "failed": failed,
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
    # SQL aggregates — avoid loading 144k+ rows into memory just to
    # count them in Python. Each GROUP BY runs as a single query.
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    async def _group_count(column):
        return dict((await db.execute(
            select(column, func.count(Download.id)).group_by(column)
        )).all())

    by_platform = await _group_count(Download.platform)
    by_status = await _group_count(Download.status)
    by_source = await _group_count(Download.source_type)

    # Total + size sum + 24h/7d buckets in one query.
    total = (await db.execute(select(func.count(Download.id)))).scalar_one()
    total_size = (await db.execute(
        select(func.coalesce(func.sum(Download.file_size_bytes), 0))
    )).scalar_one()
    last_24h = (await db.execute(
        select(func.count(Download.id)).where(Download.created_at >= day_ago)
    )).scalar_one()
    last_7d = (await db.execute(
        select(func.count(Download.id)).where(Download.created_at >= week_ago)
    )).scalar_one()

    return DownloadStats(
        total=total,
        by_platform=by_platform,
        by_status=by_status,
        by_source=by_source,
        total_size_bytes=int(total_size),
        last_24h=last_24h,
        last_7d=last_7d,
    )


@router.post("/batch", response_model=BatchCreateResponse, status_code=201)
async def batch_create(req: BatchCreateRequest, db: AsyncSession = Depends(get_db)) -> BatchCreateResponse:
    """Create many Download rows at once — used by the UI 'Add to queue' flow."""
    ids: list[int] = []
    for item in req.items:
        url = _validate_download_url(item.url, req.platform)
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


class FromHighlightIdsRequest(BaseModel):
    user: str = Field(..., description="Instagram username (e.g. 'hienthuc.27')")
    ids: list[str] = Field(..., min_length=1, max_length=500,
                           description="Highlight reel IDs (15-22 digits each)")


class FromHighlightIdsResponse(BaseModel):
    created: int
    skipped: int
    ids: list[int]


@router.post("/from-highlight-ids", response_model=FromHighlightIdsResponse, status_code=201)
async def from_highlight_ids(
    req: FromHighlightIdsRequest, db: AsyncSession = Depends(get_db)
) -> FromHighlightIdsResponse:
    """Create one Download row per highlight reel ID.

    gallery-dl's */highlights/ GraphQL endpoint now requires following
    the user AND a browser context. As a workaround, the user can paste
    the highlight reel IDs (visible in the URL when they click a
    highlight in their browser) and we hit the working
    /stories/highlights/<id>/ pattern directly.
    """
    user = req.user.strip().lstrip("@")
    if not user or "/" in user:
        raise HTTPException(status_code=400, detail="invalid username")

    seen: set[str] = set()
    created_ids: list[int] = []
    skipped = 0
    # Shortcut: query the URL set ONCE so we can dedup across the whole
    # request in a single round trip instead of N lookups below. This
    # also makes the endpoint idempotent — re-pasting the same reel IDs
    # after a partial failure no longer creates duplicate Download rows.
    candidate_urls: list[str] = []
    for raw in req.ids:
        hid = raw.strip()
        if not hid or not hid.isdigit() or not (15 <= len(hid) <= 22):
            skipped += 1
            continue
        candidate_urls.append(f"https://www.instagram.com/stories/highlights/{hid}/")
    if candidate_urls:
        existing_rows = (await db.execute(
            select(Download.url).where(Download.url.in_(candidate_urls))
        )).scalars().all()
        existing_urls: set[str] = set(existing_rows)
    else:
        existing_urls = set()

    for raw in req.ids:
        hid = raw.strip()
        if not hid or not hid.isdigit() or not (15 <= len(hid) <= 22):
            continue
        if hid in seen:
            skipped += 1
            continue
        url = f"https://www.instagram.com/stories/highlights/{hid}/"
        if url in existing_urls:
            skipped += 1
            continue
        seen.add(hid)
        url = f"https://www.instagram.com/stories/highlights/{hid}/"
        d = Download(
            platform="instagram",
            source_type="link",
            url=url,
            title=f"HL {hid}",
            author=user,
            content_type="highlight",
            status=DownloadStatus.PENDING,
        )
        db.add(d)
        await db.flush()
        created_ids.append(d.id)
    await db.commit()
    return FromHighlightIdsResponse(created=len(created_ids), skipped=skipped, ids=created_ids)


@router.post("/run-pending", status_code=201)
async def run_pending(
    platform: str = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
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

    # Serialize claims in the database, including across API worker processes.
    from sqlalchemy import text
    if db.bind and db.bind.dialect.name == "sqlite":
        await db.execute(text("BEGIN IMMEDIATE"))
    else:
        await db.execute(text("SELECT pg_advisory_xact_lock(731204881)"))
        active = (await db.execute(
            select(Job.id).where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])).limit(1)
        )).scalar_one_or_none()
        if active is not None:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Another job is currently running")

    if job_runner.is_busy:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Another job is currently running")

    rows = (await db.execute(
        select(Download).where(
            Download.platform == plat_enum.value,
            Download.status == DownloadStatus.PENDING,
        ).order_by(Download.id.asc())
    )).scalars().all()

    if not rows:
        await db.commit()
        return {"marked": 0, "job_id": None, "items": []}

    job = Job(
        job_type=JobType.UPDATE_LIST,
        status=JobStatus.QUEUED,
        targets=json.dumps([d.url for d in rows]),
    )
    db.add(job)
    await db.flush()  # get job.id

    # Attach rows inside the same transaction as job creation.
    items: list[dict] = []
    for d in rows:
        d.status = DownloadStatus.DOWNLOADING
        d.job_id = job.id
        items.append({"id": d.id, "url": d.url, "author": d.author, "title": d.title})

    await db.commit()

    # 4. Hand off to the runner via BackgroundTasks so exceptions are
    # surfaced to the task system (and logged) instead of being silently
    # dropped by a fire-and-forget create_task.
    background_tasks.add_task(job_runner.enqueue, job.id)

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
