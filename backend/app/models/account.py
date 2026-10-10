from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.media import Media
    from app.models.rate_limit_event import RateLimitEvent
    from app.models.download import Download


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    destination_folder: Mapped[str] = mapped_column(String(1024), nullable=False)

    first_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    total_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_stories: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_highlights: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_dead: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    media: Mapped[list["Media"]] = relationship(
        "Media", back_populates="account", cascade="all, delete-orphan"
    )
    rate_limit_events: Mapped[list["RateLimitEvent"]] = relationship(
        "RateLimitEvent", back_populates="account"
    )
    downloads: Mapped[list["Download"]] = relationship(
        "Download", back_populates="account"
    )

    def __repr__(self) -> str:
        return f"<Account id={self.id} username={self.username!r}>"
