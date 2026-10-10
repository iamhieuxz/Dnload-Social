from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Account
from app.schemas import (
    AccountListResponse,
    AccountOut,
    AccountRescanResponse,
    AccountUpdate,
)
from app.services.media_scanner import media_scanner

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# ----- Disk-based account scan -----
# Walks the gallery root recursively and groups folders by the first path
# segment (instagram/<username>/... or twitter/<username>/...). Each entry
# has full stats so the Accounts page can render a card per account without
# hitting /api/gallery/browse (which would be too slow for big trees).

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".avif", ".tiff", ".svg"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".flv", ".m4v", ".3gp"}


def _classify(ext: str) -> str:
    e = ext.lower()
    if e in _IMAGE_EXTS:
        return "image"
    if e in _VIDEO_EXTS:
        return "video"
    return "other"


@router.get("/scan-from-disk")
async def scan_accounts_from_disk(
    platforms: str = Query("instagram,twitter", description="Comma-separated platform folders to scan"),
) -> dict:
    """Walk `<gallery_root>/<platform>/<account>/...` recursively and return
    one entry per account folder with full stats. The result is sorted
    alphabetically by (platform, username) so the UI can render the
    accounts in a predictable order."""
    settings = get_settings()
    # The "gallery root" is the parent of the Instagram download folder
    # (default E:/gallery-dl/instagram → E:/gallery-dl), so we can scan
    # both instagram/ and twitter/ side by side.
    root = Path(settings.download_folder).resolve().parent
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Gallery root not found: {root}")

    wanted = [p.strip().lower() for p in platforms.split(",") if p.strip()]
    accounts: list[dict[str, Any]] = []

    for platform in wanted:
        plat_dir = root / platform
        if not plat_dir.exists() or not plat_dir.is_dir():
            continue
        try:
            account_dirs = [c for c in plat_dir.iterdir() if c.is_dir()]
        except PermissionError:
            continue
        for acc_dir in account_dirs:
            stats = {
                "username": acc_dir.name,
                "platform": platform,
                "rel_path": f"{platform}/{acc_dir.name}".replace("\\", "/"),
                "size_bytes": 0,
                "file_count": 0,
                "folder_count": 0,
                "image_count": 0,
                "video_count": 0,
                "mtime": 0.0,
                "ctime": 0.0,
                "newest_file": None,
            }
            for dirpath, dirnames, filenames in os.walk(acc_dir):
                stats["folder_count"] += len(dirnames)
                for fn in filenames:
                    p = Path(dirpath) / fn
                    try:
                        st = p.stat()
                    except OSError:
                        continue
                    stats["file_count"] += 1
                    stats["size_bytes"] += st.st_size
                    if st.st_mtime > stats["mtime"]:
                        stats["mtime"] = st.st_mtime
                    ext = p.suffix.lower()
                    kind = _classify(ext)
                    if kind == "image":
                        stats["image_count"] += 1
                    elif kind == "video":
                        stats["video_count"] += 1
                    if (
                        stats["newest_file"] is None
                        or st.st_mtime > stats["newest_file"]["mtime"]
                    ):
                        stats["newest_file"] = {
                            "name": fn,
                            "mtime": st.st_mtime,
                            "size_bytes": st.st_size,
                        }
            # ctime (creation time of the account folder itself)
            try:
                st_acc = acc_dir.stat()
                stats["ctime"] = st_acc.st_ctime
            except OSError:
                pass
            stats["mtime_iso"] = (
                datetime.utcfromtimestamp(stats["mtime"]).isoformat(timespec="seconds")
                if stats["mtime"]
                else None
            )
            accounts.append(stats)

    # Predictable ordering: by platform then username
    accounts.sort(key=lambda a: (a["platform"], a["username"].lower()))
    return {
        "total": len(accounts),
        "platforms": wanted,
        "accounts": accounts,
    }


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = None,
    is_dead: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> AccountListResponse:
    stmt = select(Account)
    count_stmt = select(func.count(Account.id))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Account.username.ilike(like))
        count_stmt = count_stmt.where(Account.username.ilike(like))
    if is_dead is not None:
        stmt = stmt.where(Account.is_dead == is_dead)
        count_stmt = count_stmt.where(Account.is_dead == is_dead)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Account.last_scanned_at.desc().nullslast(), Account.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return AccountListResponse(
        items=[AccountOut.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{account_id}", response_model=AccountOut)
async def get_account(account_id: int, db: AsyncSession = Depends(get_db)) -> AccountOut:
    account = await db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountOut.model_validate(account)


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    account = await db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if payload.is_dead is not None:
        account.is_dead = payload.is_dead
    if payload.notes is not None:
        account.notes = payload.notes
    await db.commit()
    await db.refresh(account)
    return AccountOut.model_validate(account)


@router.delete("/{account_id}")
async def delete_account(account_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Delete the account row and all its media records. Does NOT delete files on disk."""
    account = await db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    username = account.username
    await db.delete(account)
    await db.commit()
    return {"deleted": username}


@router.post("/{account_id}/rescan", response_model=AccountRescanResponse)
async def rescan_account(account_id: int, db: AsyncSession = Depends(get_db)) -> AccountRescanResponse:
    account = await db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    count = await media_scanner.rescan_account(account.username)
    return AccountRescanResponse(username=account.username, indexed_files=count)
