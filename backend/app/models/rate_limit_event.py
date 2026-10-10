from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.job import Job


class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    cookie_used: Mapped[str | None] = mapped_column(String(255), nullable=True)
    keywords_matched: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_line: Mapped[str | None] = mapped_column(Text, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    job: Mapped["Job | None"] = relationship("Job", back_populates="rate_limit_events")
    account: Mapped["Account | None"] = relationship(
        "Account", back_populates="rate_limit_events"
    )
