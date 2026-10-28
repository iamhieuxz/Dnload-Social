from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging_config import get_job_logs
from app.database import get_db
from app.models import Job, JobStatus
from app.schemas import JobCreate, JobListResponse, JobLogsResponse, JobOut
from app.services.job_runner import job_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobOut, status_code=201)
async def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    # Platform-agnostic cap: this endpoint doesn't know which platform the job
    # will end up driving (that comes from its Download rows), so it can only
    # enforce the total. `JobRunner.enqueue` then rejects a job whose own
    # platform is already busy.
    if len(job_runner.active_job_ids) >= get_settings().max_concurrent_jobs:
        raise HTTPException(
            status_code=409,
            detail="The maximum number of concurrent jobs is already running. "
                   "Stop one first or raise `max_concurrent_jobs`.",
        )

    job = Job(
        job_type=payload.job_type,
        targets=json.dumps(payload.targets) if payload.targets else None,
        include_posts=payload.include_posts,
        include_stories=payload.include_stories,
        include_highlights=payload.include_highlights,
        disable_range=payload.disable_range,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Schedule the run
    background_tasks.add_task(job_runner.enqueue, job.id)
    return JobOut.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: JobStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    stmt = select(Job)
    count_stmt = select(func.count(Job.id))
    if status is not None:
        stmt = stmt.where(Job.status == status)
        count_stmt = count_stmt.where(Job.status == status)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return JobListResponse(
        items=[JobOut.model_validate(j) for j in items],
        total=total,
    )


@router.get("/active")
async def get_active_job(db: AsyncSession = Depends(get_db)) -> dict:
    """Returns the currently running job, if any. Used by the UI to show
    a global indicator when a job is in progress."""
    stmt = select(Job).where(Job.status == JobStatus.RUNNING).order_by(Job.started_at.desc())
    job = (await db.execute(stmt)).scalars().first()
    return {"job": JobOut.model_validate(job).model_dump() if job else None}


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)) -> JobOut:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut.model_validate(job)


@router.post("/{job_id}/stop")
async def stop_job(job_id: int) -> dict:
    if job_id not in job_runner.active_job_ids:
        raise HTTPException(status_code=409, detail="Job is not currently running")
    # Targeted: with Instagram and X running side by side, stopping one must
    # not kill the other's subprocess.
    await job_runner.request_stop(job_id)
    return {"stopping": job_id}


@router.get("/{job_id}/logs", response_model=JobLogsResponse)
async def get_job_logs_endpoint(job_id: int, limit: int = Query(500, ge=1, le=5000)) -> JobLogsResponse:
    lines = get_job_logs(job_id, limit=limit)
    return JobLogsResponse(job_id=job_id, lines=lines)


@router.delete("/{job_id}")
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    if job_id in job_runner.active_job_ids:
        raise HTTPException(status_code=409, detail="Cannot delete a running job")
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.delete(job)
    await db.commit()
    return {"deleted": job_id}
