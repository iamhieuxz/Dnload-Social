"""
Application settings — loaded from environment variables.

Replaces the old hardcoded config.py. All paths and secrets come from
.env / environment, so the app is portable across machines.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- Database -----
    # Defaults to SQLite (no Docker needed). Override via .env or DATABASE_URL env var.
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/igdownloader.db",
        description="SQLAlchemy async URL. SQLite (aiosqlite) or PostgreSQL (asyncpg).",
    )

    # ----- Storage -----
    # Per-platform roots. Each platform writes into its own subfolder under
    # E:\gallery-dl so the layout matches what gallery-dl already produces.
    download_folder: str = Field(
        default="E:/gallery-dl/instagram",
        description="Where gallery-dl writes Instagram media files",
    )
    twitter_download_folder: str = Field(
        default="E:/gallery-dl/twitter",
        description="Where yt-dlp writes Twitter / X media files",
    )
    tiktok_download_folder: str = Field(
        default="E:/gallery-dl/tiktok",
        description="Where gallery-dl writes TikTok media files",
    )
    cookie_folder: str = Field(
        default="./secrets/cookies",
        description="Where cookie files are stored (encrypted)",
    )

    # ----- Server -----
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # ----- Security -----
    cookie_encryption_key: str = Field(
        default="",
        description="Fernet key for encrypting cookie files at rest. "
        "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"",
    )

    # ----- Rate limit policy -----
    rate_limit_min_delay: int = 18
    rate_limit_max_delay: int = 45
    rate_limit_batch_size: int = 8
    rate_limit_batch_cooldown: int = 240
    rate_limit_limit_cooldown: int = 900
    rate_limit_max_signals: int = 2

    # ----- Job runner -----
    max_concurrent_jobs: int = 1  # Critical fix C1: only 1 job at a time
    job_lock_timeout_seconds: int = 5

    def get_download_folder(self) -> Path:
        return Path(self.download_folder).expanduser().resolve()

    def get_twitter_download_folder(self) -> Path:
        return Path(self.twitter_download_folder).expanduser().resolve()

    def get_tiktok_download_folder(self) -> Path:
        return Path(self.tiktok_download_folder).expanduser().resolve()

    def get_cookie_folder(self) -> Path:
        return Path(self.cookie_folder).expanduser().resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
