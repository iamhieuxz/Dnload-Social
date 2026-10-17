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


# =========================================================================
# Dashboard — single endpoint that powers the StatCards row
# =========================================================================

class MediaByType(BaseModel):
    posts: int = 0
    stories: int = 0
    highlights: int = 0


class PlatformCount(BaseModel):
    """All counts and sizes for a single platform, used in the
    'Storage by platform' and platform filter breakdowns."""
    platform: str
    accounts: int = 0
    pending: int = 0
    in_flight: int = 0
    completed: int = 0
    failed: int = 0
    completed_24h: int = 0
    bytes_total: int = 0
    files_on_disk: int = 0
    folders_on_disk: int = 0
    last_download_at: str | None = None


class TopAccount(BaseModel):
    id: int
    username: str
    platform: str
    total_posts: int
    total_stories: int
    total_highlights: int
    total_size_bytes: int
    is_dead: bool
    last_scanned_at: str | None = None


class DashboardStats(BaseModel):
    """Everything the dashboard needs in a single round-trip.

    Keeps the StatCards row cheap: the breakdown tables (top accounts,
    per-platform details) are pulled once and re-rendered client-side
    on the 5s poll cycle. The disk-walk StorageStats is still served
    by /api/stats/storage so its 30s cache stays effective.
    """
    # ----- Media (DB rows) -----
    total_accounts: int
    total_media: int
    media_by_type: MediaByType
    total_size_bytes: int                       # sum of account.total_size_bytes

    # ----- On-disk (from the storage endpoint, denormalized) -----
    disk_total_bytes: int
    disk_used_bytes: int
    disk_free_bytes: int
    files_on_disk: int
    folders_on_disk: int

    # ----- Queue -----
    pending_count: int
    in_flight_count: int
    downloads_24h: int
    downloads_7d: int
    last_download_at: str | None = None

    # ----- Jobs -----
    jobs_running: int
    jobs_completed_24h: int
    jobs_failed_24h: int
    jobs_stopped_24h: int
    success_rate_24h: float                      # 0.0 – 1.0; -1 if no jobs in window

    # ----- Rate limit -----
    rate_limit_events_24h: int
    last_rate_limit_at: str | None = None

    # ----- Per-platform -----
    by_platform: list[PlatformCount]

    # ----- Top accounts (top 5 by size) -----
    top_accounts_by_size: list[TopAccount]
