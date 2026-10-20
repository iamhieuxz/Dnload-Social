"""
TikTok cookie slots — DB-backed record of uploaded cookie files.

Mirrors the Twitter cookie upload (tw_cookie1/2.txt on disk) so the UI
can list / replace / delete slots without scanning the secrets/cookies
folder. Without cookies, gallery-dl hits TikTok's anonymous rate-limit
very quickly and stalls for minutes between requests, which is why
C1-style "run everything" can hang for an hour on a single account.

Files live on disk under <cookie_folder>/tiktok/tt_cookie1.txt etc. —
the DB row points to the path and tracks upload / last-used time.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TikTokCookieSlot(str, enum.Enum):
    PRIMARY = "primary"   # maps to tt_cookie1.txt
    BACKUP = "backup"     # maps to tt_cookie2.txt


class TikTokCookie(Base):
    __tablename__ = "tiktok_cookies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot: Mapped[TikTokCookieSlot] = mapped_column(
        Enum(TikTokCookieSlot, native_enum=False, length=16),
        unique=True,
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TikTokCookie slot={self.slot.value} file={self.file_name!r}>"
