"""
Cookie management endpoints.

Two namespaces:
  - /api/cookies/...        → Instagram cookie slots (cookie1.txt / cookie2.txt)
                              stored on disk under <cookie_folder>/cookieN.txt
  - /api/cookies/twitter/.. → X / Twitter cookie slots
                              stored on disk under <cookie_folder>/twitter/tw_cookieN.txt
                              AND mirrored in the `twitter_cookies` DB table

Why mirror to DB?
  - UI can list/replace slots without scanning the disk
  - Upload / last-used timestamps
  - Future-proof: easy to encrypt at rest, audit, etc.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope
from app.models import TwitterCookie, TwitterCookieSlot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cookies", tags=["cookies"])


# ---------------------------------------------------------------------------
# Instagram slots (existing behavior — kept for backwards compat)
# ---------------------------------------------------------------------------

@router.post("/upload/{slot}")
async def upload_cookie(slot: int, file: UploadFile = File(...)) -> dict:
    """
    Upload an Instagram cookie file. slot=1 (primary) or slot=2 (backup).
    """
    if slot not in (1, 2):
        raise HTTPException(status_code=400, detail="slot must be 1 or 2")
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are accepted")

    settings = get_settings()
    cookie_dir = settings.get_cookie_folder()
    cookie_dir.mkdir(parents=True, exist_ok=True)

    target = cookie_dir / f"cookie{slot}.txt"
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Cookie file too large (>10MB)")
    target.write_bytes(contents)
    logger.info("IG cookie slot %s updated (%s bytes)", slot, len(contents))
    return {"slot": slot, "bytes": len(contents), "filename": target.name}


@router.delete("/{slot}")
async def delete_cookie(slot: int) -> dict:
    """Delete an Instagram cookie slot (1 or 2)."""
    if slot not in (1, 2):
        raise HTTPException(status_code=400, detail="slot must be 1 or 2")
    settings = get_settings()
    target = settings.get_cookie_folder() / f"cookie{slot}.txt"
    if target.exists():
        target.unlink()
    return {"deleted": slot}


# ---------------------------------------------------------------------------
# Twitter / X slots (DB-mirrored)
# ---------------------------------------------------------------------------

def _twitter_cookie_path(slot: TwitterCookieSlot) -> Path:
    """Where the cookie file lives on disk for a given slot."""
    base = get_settings().get_cookie_folder() / "twitter"
    base.mkdir(parents=True, exist_ok=True)
    suffix = "1" if slot == TwitterCookieSlot.PRIMARY else "2"
    return base / f"tw_cookie{suffix}.txt"


@router.get("/twitter/list")
async def list_twitter_cookies() -> dict:
    """List all X / Twitter cookie slots and their DB metadata."""
    async with session_scope() as session:
        rows = (await session.execute(
            select(TwitterCookie).order_by(TwitterCookie.slot)
        )).scalars().all()
        return {
            "items": [
                {
                    "slot": r.slot.value,
                    "file_name": r.file_name,
                    "file_path": r.file_path,
                    "size_bytes": r.size_bytes,
                    "exists_on_disk": Path(r.file_path).exists() if r.file_path else False,
                    "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                    "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                }
                for r in rows
            ],
            "total": len(rows),
        }


@router.post("/twitter/upload/{slot}")
async def upload_twitter_cookie(slot: str, file: UploadFile = File(...)) -> dict:
    """
    Upload an X / Twitter cookie file.
    slot = 'primary' | 'backup'
    File is written to <cookie_folder>/twitter/tw_cookie{1,2}.txt
    and the row in `twitter_cookies` is upserted.
    """
    try:
        slot_enum = TwitterCookieSlot(slot)
    except ValueError:
        raise HTTPException(status_code=400, detail="slot must be 'primary' or 'backup'")
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are accepted")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Cookie file too large (>10MB)")

    target = _twitter_cookie_path(slot_enum)
    target.write_bytes(contents)
    logger.info("Twitter cookie slot %s updated (%s bytes)", slot, len(contents))

    async with session_scope() as session:
        existing = (await session.execute(
            select(TwitterCookie).where(TwitterCookie.slot == slot_enum)
        )).scalar_one_or_none()
        if existing is None:
            existing = TwitterCookie(
                slot=slot_enum,
                file_name=target.name,
                file_path=str(target),
                size_bytes=len(contents),
            )
            session.add(existing)
        else:
            existing.file_name = target.name
            existing.file_path = str(target)
            existing.size_bytes = len(contents)
            existing.uploaded_at = datetime.utcnow()

    return {
        "slot": slot_enum.value,
        "bytes": len(contents),
        "filename": target.name,
        "file_path": str(target),
    }


@router.delete("/twitter/{slot}")
async def delete_twitter_cookie(slot: str) -> dict:
    """Delete an X cookie slot (file + DB row)."""
    try:
        slot_enum = TwitterCookieSlot(slot)
    except ValueError:
        raise HTTPException(status_code=400, detail="slot must be 'primary' or 'backup'")
    target = _twitter_cookie_path(slot_enum)
    if target.exists():
        target.unlink()
    async with session_scope() as session:
        row = (await session.execute(
            select(TwitterCookie).where(TwitterCookie.slot == slot_enum)
        )).scalar_one_or_none()
        if row is not None:
            await session.delete(row)
    return {"deleted": slot_enum.value}
