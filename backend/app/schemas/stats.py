from __future__ import annotations

from pydantic import BaseModel


class OverviewStats(BaseModel):
    total_accounts: int
    total_media: int
    total_size_bytes: int
    total_posts: int
    total_stories: int
    total_highlights: int
    jobs_running: int
    jobs_completed_24h: int
    jobs_failed_24h: int


class TimelineBucket(BaseModel):
    date: str
    count: int


class TimelineResponse(BaseModel):
    buckets: list[TimelineBucket]
