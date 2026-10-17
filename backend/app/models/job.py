from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.rate_limit_event import RateLimitEvent
    from app.models.download import Download


class JobType(str, enum.Enum):
    ADD_NEW = "add_new"
    UPDATE_LIST = "update_list"
    UPDATE_ALL = "update_all"
    SINGLE = "single"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, native_enum=False, length=32), nullable=False, index=True
    )
    targets: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of usernames
    include_posts: Mapped[bool] = mapped_column(default=True, nullable=False)
    include_stories: Mapped[bool] = mapped_column(default=True, nullable=False)
    include_highlights: Mapped[bool] = mapped_column(default=False, nullable=False)
    disable_range: Mapped[bool] = mapped_column(default=True, nullable=False)

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    new_files_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_output: Mapped[str | None] = mapped_column(Text, nullable=True)  # full log captured

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    rate_limit_events: Mapped[list["RateLimitEvent"]] = relationship(
        "RateLimitEvent", back_populates="job"
    )
    downloads: Mapped[list["Download"]] = relationship(
        "Download", back_populates="job"
    )

    @property
    def duration_seconds(self) -> int | None:
        if not self.started_at or not self.finished_at:
            return None
        return int((self.finished_at - self.started_at).total_seconds())
