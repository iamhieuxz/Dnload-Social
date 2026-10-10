from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus, JobType


class JobCreate(BaseModel):
    job_type: JobType
    targets: list[str] = Field(default_factory=list)
    include_posts: bool = True
    include_stories: bool = True
    include_highlights: bool = False
    disable_range: bool = True


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_type: JobType
    status: JobStatus
    targets: str | None
    include_posts: bool
    include_stories: bool
    include_highlights: bool
    disable_range: bool
    started_at: datetime | None
    finished_at: datetime | None
    new_files_count: int
    total_processed: int
    error_message: str | None
    duration_seconds: int | None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobOut]
    total: int


class JobLogsResponse(BaseModel):
    job_id: int
    lines: list[str]
