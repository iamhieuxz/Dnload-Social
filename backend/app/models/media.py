from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.account import Account


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    media_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # 'post' | 'story' | 'highlight'
    file_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    shortcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    instagram_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    account: Mapped["Account"] = relationship("Account", back_populates="media")
