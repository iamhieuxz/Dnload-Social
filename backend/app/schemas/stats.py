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

    # ----- Per-platform breakdown (all three platforms) -----
    by_platform: dict[str, int] = {}          # platform -> completed downloads
    size_by_platform: dict[str, int] = {}     # platform -> bytes
    pending_count: int = 0                    # pending + in-flight, all platforms
    downloads_24h: int = 0
    downloads_7d: int = 0


class StorageBreakdown(BaseModel):
    """Per-platform on-disk usage, measured from the real folders."""
    platform: str
    path: str
    exists: bool
    file_count: int
    folder_count: int
    size_bytes: int


class StorageStats(BaseModel):
    total_size_bytes: int
    total_files: int
    total_folders: int
    free_bytes: int
    total_disk_bytes: int
    by_platform: list[StorageBreakdown]


class TimelineBucket(BaseModel):
    date: str
    count: int


class TimelineResponse(BaseModel):
    buckets: list[TimelineBucket]
