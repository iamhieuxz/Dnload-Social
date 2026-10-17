from __future__ import annotations

from pydantic import BaseModel


class SettingsOut(BaseModel):
    download_folder: str
    twitter_download_folder: str = ""
    tiktok_download_folder: str = ""
    cookie_folder: str
    rate_limit_min_delay: int
    rate_limit_max_delay: int
    rate_limit_batch_size: int
    rate_limit_batch_cooldown: int
    rate_limit_limit_cooldown: int
    rate_limit_max_signals: int
    cookies_configured: bool


class SettingsUpdate(BaseModel):
    download_folder: str | None = None
    rate_limit_min_delay: int | None = None
    rate_limit_max_delay: int | None = None
    rate_limit_batch_size: int | None = None
    rate_limit_batch_cooldown: int | None = None
    rate_limit_limit_cooldown: int | None = None
    rate_limit_max_signals: int | None = None
