from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Media
from app.schemas import MediaListResponse, MediaOut

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("", response_model=MediaListResponse)
async def list_media(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    account_id: int | None = None,
    media_type: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> MediaListResponse:
    stmt = select(Media)
    count_stmt = select(func.count(Media.id))
    if account_id is not None:
        stmt = stmt.where(Media.account_id == account_id)
        count_stmt = count_stmt.where(Media.account_id == account_id)
    if media_type:
        stmt = stmt.where(Media.media_type == media_type)
        count_stmt = count_stmt.where(Media.media_type == media_type)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Media.file_name.ilike(like))
        count_stmt = count_stmt.where(Media.file_name.ilike(like))

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Media.downloaded_at.desc(), Media.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return MediaListResponse(
        items=[MediaOut.model_validate(m) for m in result.scalars().all()],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{media_id}/file")
async def get_media_file(media_id: int, db: AsyncSession = Depends(get_db)) -> FileResponse:
    media = await db.get(Media, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    if not os.path.exists(media.file_path):
        raise HTTPException(status_code=410, detail="File missing on disk")
    return FileResponse(media.file_path, filename=media.file_name)


@router.delete("/{media_id}")
async def delete_media(media_id: int, db: AsyncSession = Depends(get_db), delete_file: bool = False) -> dict:
    media = await db.get(Media, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    file_path = media.file_path
    await db.delete(media)
    await db.commit()
    if delete_file:
        try:
            os.remove(file_path)
        except OSError:
            pass
    return {"deleted": media_id}
