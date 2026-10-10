from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    media_type: str
    file_path: str
    file_name: str
    shortcode: str | None
    instagram_date: date | None
    file_size_bytes: int
    downloaded_at: datetime


class MediaListResponse(BaseModel):
    items: list[MediaOut]
    total: int
    page: int
    page_size: int
