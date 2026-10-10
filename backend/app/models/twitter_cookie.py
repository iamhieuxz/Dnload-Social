"""
Twitter / X cookie slots — DB-backed record of uploaded cookie files.

Mirrors the IG cookie upload (cookie1/cookie2.txt on disk) but persists
metadata to the database so the UI can list / replace / delete slots
without having to scan the secrets/cookies folder.

Files still live on disk under <cookie_folder>/twitter/tw_cookie1.txt
etc. — the DB row points to the path and tracks upload / last-used time.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TwitterCookieSlot(str, enum.Enum):
    PRIMARY = "primary"   # maps to tw_cookie1.txt
    BACKUP = "backup"     # maps to tw_cookie2.txt


class TwitterCookie(Base):
    __tablename__ = "twitter_cookies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot: Mapped[TwitterCookieSlot] = mapped_column(
        Enum(TwitterCookieSlot, native_enum=False, length=16),
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
        return f"<TwitterCookie slot={self.slot.value} file={self.file_name!r}>"
