from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    destination_folder: str
    first_scanned_at: datetime | None
    last_scanned_at: datetime | None
    total_posts: int
    total_stories: int
    total_highlights: int
    total_size_bytes: int
    is_dead: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AccountUpdate(BaseModel):
    is_dead: bool | None = None
    notes: str | None = None


class AccountListResponse(BaseModel):
    items: list[AccountOut]
    total: int
    page: int
    page_size: int


class AccountRescanResponse(BaseModel):
    username: str
    indexed_files: int
