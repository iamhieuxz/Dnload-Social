"""
Stats endpoints — overview, storage breakdown, and media timeline.

Heavy disk walks are cached in-process for `_STORAGE_CACHE_TTL` so the
30-second dashboard poll doesn't re-stat every file. The cache is
best-effort: a stat is only an approximation of disk usage, and 30s of
staleness is harmless.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Account, Download, DownloadStatus, Job, JobStatus, Media
from app.schemas import (
    OverviewStats,
    StorageBreakdown,
    StorageStats,
    TimelineBucket,
    TimelineResponse,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])

settings = get_settings()

# 30 seconds — matches the frontend's poll cadence.
_STORAGE_CACHE_TTL = 30.0
_storage_cache: dict[str, tuple[float, StorageStats]] = {}

# Skip the gallery-dl/yt-dlp archive files — they grow but are not media.
_SKIP_BASENAMES = frozenset({
    ".instagram_download_archive.sqlite",
    ".tiktok_download_archive.sqlite",
    ".yt-dlp-archive.txt",
    "desktop.ini",
    "thumbs.db",
})


# =========================================================================
# Helpers — measured against the real folders, not the DB
# =========================================================================

async def _measure_folder(path: Path) -> tuple[int, int, int]:
    """Return (size_bytes, file_count, folder_count) for a path.

    Uses os.scandir to do one syscall per entry (no extra stat for the
    name) and walks the tree in a thread so the request stays async.
    Symlinks and archive bookkeeping files are skipped.
    """
    def _walk() -> tuple[int, int, int]:
        if not path.exists():
            return 0, 0, 0
        size = 0
        files = 0
        folders = 0
        try:
            stack = [path]
            while stack:
                current = stack.pop()
                try:
                    with os.scandir(current) as it:
                        for entry in it:
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    folders += 1
                                    stack.append(entry.path)
                                elif entry.is_file(follow_symlinks=False):
                                    if entry.name.lower() in _SKIP_BASENAMES:
                                        continue
                                    try:
                                        size += entry.stat(follow_symlinks=False).st_size
                                        files += 1
                                    except OSError:
                                        continue
                            except OSError:
                                continue
                except OSError:
                    continue
        except OSError:
            return size, files, folders
        return size, files, folders

    return await asyncio.to_thread(_walk)


async def _build_storage_breakdown(platform: str, path_str: str) -> StorageBreakdown:
    path = Path(path_str).expanduser()
    if not path.exists():
        return StorageBreakdown(
            platform=platform, path=str(path), exists=False,
            file_count=0, folder_count=0, size_bytes=0,
        )
    size, files, folders = await _measure_folder(path)
    return StorageBreakdown(
        platform=platform, path=str(path), exists=True,
        file_count=files, folder_count=folders, size_bytes=size,
    )


def _disk_usage(path: Path) -> tuple[int, int, int]:
    """Return (total_bytes, free_bytes, used_bytes) for the volume holding `path`.

    Falls back to zeros on platforms / paths where statfs is unavailable
    (e.g. some sandboxed network shares).
    """
    try:
        usage = shutil.disk_usage(path if path.exists() else path.parent)
        return usage.total, usage.free, usage.used
    except OSError:
        return 0, 0, 0


# =========================================================================
# Routes
# =========================================================================

@router.get("/overview", response_model=OverviewStats)
async def get_overview(db: AsyncSession = Depends(get_db)) -> OverviewStats:
    total_accounts = (await db.execute(select(func.count(Account.id)))).scalar_one()
    total_media = (await db.execute(select(func.count(Media.id)))).scalar_one()
    total_size = (await db.execute(
        select(func.coalesce(func.sum(Account.total_size_bytes), 0))
    )).scalar_one()
    total_posts = (await db.execute(
        select(func.coalesce(func.sum(Account.total_posts), 0))
    )).scalar_one()
    total_stories = (await db.execute(
        select(func.coalesce(func.sum(Account.total_stories), 0))
    )).scalar_one()
    total_highlights = (await db.execute(
        select(func.coalesce(func.sum(Account.total_highlights), 0))
    )).scalar_one()

    jobs_running = (
        await db.execute(select(func.count(Job.id)).where(Job.status == JobStatus.RUNNING))
    ).scalar_one()

    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    cutoff_7d = datetime.utcnow() - timedelta(days=7)
    jobs_completed_24h = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.status == JobStatus.COMPLETED, Job.finished_at >= cutoff_24h
            )
        )
    ).scalar_one()
    jobs_failed_24h = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.status == JobStatus.FAILED, Job.finished_at >= cutoff_24h
            )
        )
    ).scalar_one()

    # ----- Per-platform download counts (queue + completed) -----
    plat_rows = (await db.execute(
        select(Download.platform, func.count(Download.id))
        .where(Download.status.in_([DownloadStatus.COMPLETED, DownloadStatus.SKIPPED]))
        .group_by(Download.platform)
    )).all()
    by_platform: dict[str, int] = {p: c for p, c in plat_rows}

    size_rows = (await db.execute(
        select(Download.platform, func.coalesce(func.sum(Download.file_size_bytes), 0))
        .where(Download.status == DownloadStatus.COMPLETED)
        .group_by(Download.platform)
    )).all()
    size_by_platform: dict[str, int] = {p: int(s) for p, s in size_rows}

    pending_count = (
        await db.execute(
            select(func.count(Download.id)).where(
                Download.status.in_([DownloadStatus.PENDING, DownloadStatus.DOWNLOADING])
            )
        )
    ).scalar_one()

    downloads_24h = (
        await db.execute(
            select(func.count(Download.id)).where(
                Download.status == DownloadStatus.COMPLETED,
                Download.completed_at >= cutoff_24h,
            )
        )
    ).scalar_one()
    downloads_7d = (
        await db.execute(
            select(func.count(Download.id)).where(
                Download.status == DownloadStatus.COMPLETED,
                Download.completed_at >= cutoff_7d,
            )
        )
    ).scalar_one()

    return OverviewStats(
        total_accounts=total_accounts,
        total_media=total_media,
        total_size_bytes=total_size,
        total_posts=total_posts,
        total_stories=total_stories,
        total_highlights=total_highlights,
        jobs_running=jobs_running,
        jobs_completed_24h=jobs_completed_24h,
        jobs_failed_24h=jobs_failed_24h,
        by_platform=by_platform,
        size_by_platform=size_by_platform,
        pending_count=pending_count,
        downloads_24h=downloads_24h,
        downloads_7d=downloads_7d,
    )


@router.get("/storage", response_model=StorageStats)
async def get_storage() -> StorageStats:
    """Per-platform on-disk usage + free space on the volume holding it.

    Cached for `_STORAGE_CACHE_TTL` seconds so the dashboard's 30-second
    poll doesn't re-stat every file when nothing has changed.
    """
    cached = _storage_cache.get("v1")
    if cached and (time.monotonic() - cached[0]) < _STORAGE_CACHE_TTL:
        return cached[1]

    breakdowns = await asyncio.gather(
        _build_storage_breakdown("instagram", settings.download_folder),
        _build_storage_breakdown("twitter", settings.twitter_download_folder),
        _build_storage_breakdown("tiktok", settings.tiktok_download_folder),
    )

    # Disk usage — measure against the first existing folder; if none exist,
    # fall back to the cwd (which always has a volume).
    anchor = next(
        (Path(b.path) for b in breakdowns if b.exists),
        Path(settings.download_folder).expanduser(),
    )
    total_disk, free_disk, _ = _disk_usage(anchor)

    total_size = sum(b.size_bytes for b in breakdowns)
    total_files = sum(b.file_count for b in breakdowns)
    total_folders = sum(b.folder_count for b in breakdowns)

    result = StorageStats(
        total_size_bytes=total_size,
        total_files=total_files,
        total_folders=total_folders,
        free_bytes=free_disk,
        total_disk_bytes=total_disk,
        by_platform=list(breakdowns),
    )
    _storage_cache["v1"] = (time.monotonic(), result)
    return result


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """Media added per day for the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(
            func.date(Media.downloaded_at).label("d"),
            func.count(Media.id).label("c"),
        )
        .where(Media.downloaded_at >= cutoff)
        .group_by("d")
        .order_by("d")
    )
    rows = (await db.execute(stmt)).all()
    buckets = [TimelineBucket(date=str(r.d), count=r.c) for r in rows]
    return TimelineResponse(buckets=buckets)
