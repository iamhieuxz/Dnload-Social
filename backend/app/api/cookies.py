"""
Cookie management endpoints.

Three namespaces:
  - /api/cookies/...        → Instagram cookie slots (cookie1.txt / cookie2.txt)
                              stored on disk under <cookie_folder>/cookieN.txt
  - /api/cookies/twitter/.. → X / Twitter cookie slots
                              stored on disk under <cookie_folder>/twitter/tw_cookieN.txt
                              AND mirrored in the `twitter_cookies` DB table
  - /api/cookies/tiktok/... → TikTok cookie slots
                              stored on disk under <cookie_folder>/tiktok/tt_cookieN.txt
                              AND mirrored in the `tiktok_cookies` DB table

Why mirror to DB?
  - UI can list/replace slots without scanning the disk
  - Upload / last-used timestamps
  - Future-proof: easy to encrypt at rest, audit, etc.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import select

from app.config import get_settings
from app.core.cookie_vault import encrypt_cookie
from app.database import session_scope
from app.models import TikTokCookie, TikTokCookieSlot, TwitterCookie, TwitterCookieSlot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cookies", tags=["cookies"])


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write to `<path>.tmp` then `os.replace` for atomic swap on the
    same filesystem. Replaces the old `Path.write_bytes` which would
    leave a half-written file on disk if the process was killed
    mid-write, breaking subsequent decrypt attempts."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except Exception:
        # If replace never happened, clean up the half-written temp.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


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
    _atomic_write_bytes(target, encrypt_cookie(contents))
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
    _atomic_write_bytes(target, encrypt_cookie(contents))
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
            existing.uploaded_at = datetime.now(timezone.utc)

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


# ---------------------------------------------------------------------------
# TikTok slots (DB-mirrored)
#
# gallery-dl on TikTok without a `sessionid` cookie gets stuck in
# long rate-limit cooldowns (5-10 min between requests). Providing a
# logged-in cookie cuts that to a few seconds, which is why uploads
# from a fresh TikTok URL run for an hour when no cookie is set.
# ---------------------------------------------------------------------------

def _tiktok_cookie_path(slot: TikTokCookieSlot) -> Path:
    """Where the cookie file lives on disk for a given slot."""
    base = get_settings().get_cookie_folder() / "tiktok"
    base.mkdir(parents=True, exist_ok=True)
    suffix = "1" if slot == TikTokCookieSlot.PRIMARY else "2"
    return base / f"tt_cookie{suffix}.txt"


@router.get("/tiktok/list")
async def list_tiktok_cookies() -> dict:
    """List all TikTok cookie slots and their DB metadata."""
    async with session_scope() as session:
        rows = (await session.execute(
            select(TikTokCookie).order_by(TikTokCookie.slot)
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


@router.post("/tiktok/upload/{slot}")
async def upload_tiktok_cookie(slot: str, file: UploadFile = File(...)) -> dict:
    """
    Upload a TikTok cookie file.
    slot = 'primary' | 'backup'
    File is written to <cookie_folder>/tiktok/tt_cookie{1,2}.txt
    and the row in `tiktok_cookies` is upserted.
    """
    try:
        slot_enum = TikTokCookieSlot(slot)
    except ValueError:
        raise HTTPException(status_code=400, detail="slot must be 'primary' or 'backup'")
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are accepted")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Cookie file too large (>10MB)")

    target = _tiktok_cookie_path(slot_enum)
    _atomic_write_bytes(target, encrypt_cookie(contents))
    logger.info("TikTok cookie slot %s updated (%s bytes)", slot, len(contents))

    async with session_scope() as session:
        existing = (await session.execute(
            select(TikTokCookie).where(TikTokCookie.slot == slot_enum)
        )).scalar_one_or_none()
        if existing is None:
            existing = TikTokCookie(
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
            existing.uploaded_at = datetime.now(timezone.utc)

    return {
        "slot": slot_enum.value,
        "bytes": len(contents),
        "filename": target.name,
        "file_path": str(target),
    }


@router.delete("/tiktok/{slot}")
async def delete_tiktok_cookie(slot: str) -> dict:
    """Delete a TikTok cookie slot (file + DB row)."""
    try:
        slot_enum = TikTokCookieSlot(slot)
    except ValueError:
        raise HTTPException(status_code=400, detail="slot must be 'primary' or 'backup'")
    target = _tiktok_cookie_path(slot_enum)
    if target.exists():
        target.unlink()
    async with session_scope() as session:
        row = (await session.execute(
            select(TikTokCookie).where(TikTokCookie.slot == slot_enum)
        )).scalar_one_or_none()
        if row is not None:
            await session.delete(row)
    return {"deleted": slot_enum.value}
