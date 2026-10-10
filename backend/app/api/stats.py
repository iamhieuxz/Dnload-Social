from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, Job, JobStatus, Media
from app.schemas import OverviewStats, TimelineBucket, TimelineResponse

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewStats)
async def get_overview(db: AsyncSession = Depends(get_db)) -> OverviewStats:
    total_accounts = (await db.execute(select(func.count(Account.id)))).scalar_one()
    total_media = (await db.execute(select(func.count(Media.id)))).scalar_one()
    total_size = (await db.execute(select(func.coalesce(func.sum(Account.total_size_bytes), 0)))).scalar_one()
    total_posts = (await db.execute(select(func.coalesce(func.sum(Account.total_posts), 0)))).scalar_one()
    total_stories = (await db.execute(select(func.coalesce(func.sum(Account.total_stories), 0)))).scalar_one()
    total_highlights = (await db.execute(select(func.coalesce(func.sum(Account.total_highlights), 0)))).scalar_one()

    jobs_running = (
        await db.execute(select(func.count(Job.id)).where(Job.status == JobStatus.RUNNING))
    ).scalar_one()

    cutoff = datetime.utcnow() - timedelta(hours=24)
    jobs_completed_24h = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.status == JobStatus.COMPLETED, Job.finished_at >= cutoff
            )
        )
    ).scalar_one()
    jobs_failed_24h = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.status == JobStatus.FAILED, Job.finished_at >= cutoff
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
    )


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
