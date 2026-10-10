"""
Media scanner — walks the download folder and reconciles with the DB.

Fixes:
- C4: This is the ONLY place that does an expensive rglob. Called only
  on manual rescan, not during downloads. Cached counts live in
  accounts.total_posts/total_stories/total_highlights during runs.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import session_scope
from app.models import Account, Media

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov")


def _is_post_filename(name: str) -> str:
    if name.startswith("STORY_"):
        return "story"
    if name.startswith("HL_"):
        return "highlight"
    return "post"


def _parse_date_from_filename(name: str) -> date | None:
    # Format: {prefix}YYYY-MM-DD_{shortcode}_{num}.{ext}
    parts = name.split("_")
    for part in parts:
        if len(part) >= 10 and part[4] == "-" and part[7] == "-":
            try:
                return date.fromisoformat(part[:10])
            except ValueError:
                continue
    return None


def _parse_shortcode(name: str) -> str | None:
    # The piece between the first two underscores (after prefix) is the shortcode
    parts = name.split("_")
    # drop extension from last part
    if parts:
        parts[-1] = parts[-1].rsplit(".", 1)[0]
    # find a token that looks like a shortcode (alphanumeric, 8+ chars)
    for p in parts:
        if p.isalnum() and 8 <= len(p) <= 32:
            return p
    return None


def _safe_stat(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


class MediaScanner:
    """
    Two responsibilities:
    1. full_scan() — index the entire download folder into Media + Account tables.
    2. The result is then used by the Stats API to render the dashboard.
    """

    async def full_scan(self) -> dict[str, int]:
        settings = get_settings()
        root = settings.get_download_folder()
        if not root.exists():
            return {"scanned": 0, "accounts": 0, "media": 0}

        scanned = 0
        account_count = 0
        media_count = 0

        # Walk all account directories
        for account_dir in root.iterdir():
            if not account_dir.is_dir() or account_dir.name.endswith("._DEAD"):
                continue
            username = account_dir.name.lstrip("@")
            await self._scan_account(account_dir, username)
            account_count += 1
            media_count += await self._count_media_for(username)
            scanned += 1

        return {"scanned": scanned, "accounts": account_count, "media": media_count}

    async def rescan_account(self, username: str) -> int:
        settings = get_settings()
        account_dir = settings.get_download_folder() / username
        if not account_dir.exists():
            return 0
        await self._scan_account(account_dir, username)
        return await self._count_media_for(username)

    async def _scan_account(self, account_dir: Path, username: str) -> None:
        files: list[dict] = []
        for path in account_dir.rglob("*"):
            if not path.is_file():
                continue
            if not path.suffix.lower() in IMAGE_EXTENSIONS:
                continue
            files.append({
                "file_path": str(path),
                "file_name": path.name,
                "media_type": _is_post_filename(path.name),
                "instagram_date": _parse_date_from_filename(path.name),
                "shortcode": _parse_shortcode(path.name),
                "file_size_bytes": _safe_stat(path),
            })

        if not files:
            # ensure account exists even if empty
            await self._upsert_account(username, account_dir, count_payload=None)
            return

        # Upsert account first
        total_posts = sum(1 for f in files if f["media_type"] == "post")
        total_stories = sum(1 for f in files if f["media_type"] == "story")
        total_highlights = sum(1 for f in files if f["media_type"] == "highlight")
        total_size = sum(f["file_size_bytes"] for f in files)
        await self._upsert_account(
            username, account_dir,
            count_payload={
                "total_posts": total_posts,
                "total_stories": total_stories,
                "total_highlights": total_highlights,
                "total_size_bytes": total_size,
            },
        )

        # Upsert media — use ON CONFLICT on file_path
        async with session_scope() as session:
            account = await self._get_account(session, username)
            if account is None:
                return
            for f in files:
                stmt = pg_insert(Media).values(
                    account_id=account.id,
                    media_type=f["media_type"],
                    file_path=f["file_path"],
                    file_name=f["file_name"],
                    shortcode=f["shortcode"],
                    instagram_date=f["instagram_date"],
                    file_size_bytes=f["file_size_bytes"],
                ).on_conflict_do_nothing(index_elements=["file_path"])
                await session.execute(stmt)

    async def _upsert_account(
        self,
        username: str,
        account_dir: Path,
        count_payload: dict | None,
    ) -> None:
        async with session_scope() as session:
            account = await self._get_account(session, username)
            if account is None:
                account = Account(
                    username=username,
                    destination_folder=str(account_dir),
                    first_scanned_at=datetime.utcnow(),
                    last_scanned_at=datetime.utcnow(),
                )
                session.add(account)
                await session.flush()
            else:
                account.last_scanned_at = datetime.utcnow()
            if count_payload:
                account.total_posts = count_payload["total_posts"]
                account.total_stories = count_payload["total_stories"]
                account.total_highlights = count_payload["total_highlights"]
                account.total_size_bytes = count_payload["total_size_bytes"]

    async def _get_account(self, session: AsyncSession, username: str) -> Account | None:
        stmt = select(Account).where(Account.username == username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _count_media_for(self, username: str) -> int:
        async with session_scope() as session:
            account = await self._get_account(session, username)
            if not account:
                return 0
            from sqlalchemy import func as sa_func
            stmt = select(sa_func.count(Media.id)).where(Media.account_id == account.id)
            return (await session.execute(stmt)).scalar_one()


media_scanner = MediaScanner()
