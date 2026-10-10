from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.job import Job


class Platform(str, enum.Enum):
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    TIKTOK = "tiktok"


class DownloadStatus(str, enum.Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SourceType(str, enum.Enum):
    LINK = "link"          # single URL pasted by user
    LIST = "list"          # multi-line list uploaded
    DATABASE = "database"  # account pulled from DB (gallery-dl profile)


class ContentType(str, enum.Enum):
    """What KIND of media this Download row represents.

    For Instagram: 'post' | 'story' | 'highlight'
    For Twitter / X: 'tweet' | 'live'   (live = ended Spaces/broadcast)
    The enum is platform-agnostic so the same column can carry both.
    """
    POST = "post"
    STORY = "story"
    HIGHLIGHT = "highlight"
    TWEET = "tweet"
    LIVE = "live"


class Download(Base):
    """A single media item that was (or will be) downloaded.

    One Download = one file. Many Downloads can belong to one Job.
    Created by the job runner when a file is successfully written to disk
    (or when a known target fails).
    """
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    platform: Mapped[Platform] = mapped_column(
        String(16), nullable=False, index=True
    )  # 'instagram' | 'twitter' | 'tiktok'
    source_type: Mapped[SourceType] = mapped_column(
        String(16), nullable=False, index=True
    )  # 'link' | 'list' | 'database'

    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    shortcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # post|story|highlight|tweet|video
    content_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True,
    )  # post|story|highlight|tweet|live — drives which sub-run handles the row
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    file_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    status: Mapped[DownloadStatus] = mapped_column(
        String(16), default=DownloadStatus.PENDING, nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    job: Mapped["Job | None"] = relationship("Job", back_populates="downloads")
    account: Mapped["Account | None"] = relationship("Account", back_populates="downloads")
