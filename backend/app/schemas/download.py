from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PlatformStr = Literal["instagram", "twitter", "tiktok"]
SourceStr = Literal["link", "list", "database"]
StatusStr = Literal["pending", "downloading", "completed", "failed", "skipped"]
ContentTypeStr = Literal["post", "story", "highlight", "tweet", "live", "tiktok"]


class DownloadOut(BaseModel):
    id: int
    job_id: int | None
    account_id: int | None
    platform: str
    source_type: str
    url: str
    shortcode: str | None
    media_type: str | None
    content_type: str | None
    title: str | None
    author: str | None
    file_path: str | None
    file_name: str | None
    file_size_bytes: int
    thumbnail_url: str | None
    status: str
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class DownloadListResponse(BaseModel):
    items: list[DownloadOut]
    total: int
    page: int
    page_size: int


class DownloadStats(BaseModel):
    total: int
    by_platform: dict[str, int]   # platform -> count
    by_status: dict[str, int]     # status -> count
    by_source: dict[str, int]     # source -> count
    total_size_bytes: int
    last_24h: int
    last_7d: int


class DownloadCreate(BaseModel):
    """Manual insert — for sources that don't go through the job runner."""
    platform: PlatformStr
    source_type: SourceStr
    url: str
    title: str | None = None
    author: str | None = None
    media_type: str | None = None
    content_type: ContentTypeStr | None = None
