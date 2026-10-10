"""
Gallery manager — read-only view over a hardcoded local folder.

This module is separate from the Instagram downloader pipeline.
It scans a fixed root directory (E:\\gallery-dl) and exposes:
  - folder tree (lazy)
  - search across filenames
  - file metadata (size, mtime, mime)
  - rename / delete / serve files

No data is persisted to DB. All responses are derived from the live filesystem.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Hardcoded root per project requirement
GALLERY_ROOT = Path("E:/gallery-dl").resolve()

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


# ----- Schemas -----

class FolderNode(BaseModel):
    name: str
    path: str           # absolute, forward-slash
    rel_path: str       # relative to GALLERY_ROOT
    is_dir: bool
    size_bytes: int = 0
    file_count: int = 0
    folder_count: int = 0
    mtime: float = 0.0   # last modified
    ctime: float = 0.0   # created
    ext: str = ""        # only set for file nodes
    kind: str = "other"  # image|video|text|other — only set for file nodes
    children: list["FolderNode"] | None = None  # None = not expanded


class GalleryStats(BaseModel):
    root: str
    total_files: int
    total_folders: int
    total_size_bytes: int
    by_extension: dict[str, int]      # ext -> count
    by_top_folder: dict[str, int]     # top-level folder -> file count
    largest_files: list[dict[str, Any]]
    newest_files: list[dict[str, Any]]


class SearchResult(BaseModel):
    total: int
    items: list[dict[str, Any]]


class RenameRequest(BaseModel):
    new_name: str


# ----- Helpers -----

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".avif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".flv", ".m4v", ".3gp"}


def _to_rel(p: Path) -> str:
    try:
        return str(p.relative_to(GALLERY_ROOT)).replace("\\", "/")
    except ValueError:
        return p.name


def _safe_stat(p: Path) -> tuple[int, float, float] | None:
    """Return (size, mtime, ctime) for a path, or None if it can't be stat'd.

    On Windows, st_ctime is *creation* time but stored as a Windows FILETIME
    (100-ns ticks since 1601-01-01), and Python's stat() on Windows exposes
    it as st_ctime in seconds since the *Unix* epoch — which would make any
    value look like 1657-ish.  We therefore normalise the platform-specific
    creation time to a Unix-seconds float before returning.
    """
    try:
        st = p.stat()
    except OSError:
        return None
    import os
    if hasattr(st, "st_birthtime"):
        # macOS and *some* Linux filesystems expose real birth time
        ctime = st.st_birthtime
    else:
        # Windows: st_ctime is FILETIME, but Python's stat() already converts
        # it to a Unix-style seconds value on modern Windows.  However on
        # older builds / network shares it can be a raw FILETIME.  The
        # difference between FILETIME and Unix-epoch seconds is
        # 11644473600 — and we'll detect that by sanity-checking the value
        # (real Windows creation time is always after 2001-01-01).
        raw = st.st_ctime
        if raw > 10_000_000_000:  # way too big for a Unix timestamp
            # treat as Windows FILETIME ticks (100-ns since 1601)
            ctime = (raw - 11_644_473_600_000_000) / 10_000_000
        else:
            ctime = raw
    return st.st_size, st.st_mtime, ctime


def _safe_path(rel: str) -> Path:
    """Resolve a user-supplied relative path under the gallery root.

    Raises 400 if the result escapes the gallery root (path-traversal guard).
    """
    if not rel or rel.startswith("/") or "\\" in rel and "/" not in rel:
        # accept both separator styles but reject absolute paths
        if Path(rel).is_absolute():
            raise HTTPException(status_code=400, detail="Absolute paths are not allowed")
    rel = rel.replace("\\", "/").lstrip("/")
    candidate = (GALLERY_ROOT / rel).resolve()
    try:
        candidate.relative_to(GALLERY_ROOT)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path escapes gallery root")
    return candidate


def _classify(ext: str) -> str:
    e = ext.lower()
    if e in IMAGE_EXTS:
        return "image"
    if e in VIDEO_EXTS:
        return "video"
    if e in {".txt", ".json", ".xml", ".csv", ".log", ".md"}:
        return "text"
    return "other"


# ----- Endpoints -----

@router.get("/root")
async def get_root() -> dict:
    if not GALLERY_ROOT.exists():
        raise HTTPException(status_code=404, detail=f"Gallery root not found: {GALLERY_ROOT}")
    return {
        "root": str(GALLERY_ROOT),
        "exists": True,
    }


@router.get("/tree", response_model=FolderNode)
async def get_tree(
    path: str = Query("", description="Relative path under gallery root; '' = root"),
    depth: int = Query(2, ge=0, le=6, description="How many levels deep to expand children"),
) -> FolderNode:
    base = _safe_path(path) if path else GALLERY_ROOT
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    return _build_node(base, depth, path)


def _build_node(p: Path, depth: int, rel_input: str) -> FolderNode:
    rel = _to_rel(p) if p != GALLERY_ROOT else (rel_input or "")
    stat = _safe_stat(p)
    mtime = stat[1] if stat else 0.0
    ctime = stat[2] if stat else 0.0
    node = FolderNode(
        name=p.name or rel or "/",
        path=str(p).replace("\\", "/"),
        rel_path=rel,
        is_dir=True,
        mtime=mtime,
        ctime=ctime,
    )
    try:
        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if child.is_dir():
                node.folder_count += 1
                if depth > 0:
                    node.children = node.children or []
                    node.children.append(_build_node(child, depth - 1, ""))
                else:
                    # Show folder name only as placeholder
                    cstat = _safe_stat(child)
                    node.children = node.children or []
                    node.children.append(FolderNode(
                        name=child.name,
                        path=str(child).replace("\\", "/"),
                        rel_path=_to_rel(child),
                        is_dir=True,
                        mtime=cstat[1] if cstat else 0.0,
                        ctime=cstat[2] if cstat else 0.0,
                    ))
            else:
                cstat = _safe_stat(child)
                if cstat is None:
                    continue
                node.file_count += 1
                node.size_bytes += cstat[0]
                if node.children is None and depth == 0:
                    pass
    except PermissionError as e:
        logger.warning("Permission denied scanning %s: %s", p, e)
    return node


@router.get("/browse", response_model=FolderNode)
async def browse_folder(
    path: str = Query("", description="Relative path under gallery root"),
) -> FolderNode:
    """List a single folder with all its direct children (files + subfolders with metadata)."""
    base = _safe_path(path) if path else GALLERY_ROOT
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    bstat = _safe_stat(base)
    node = FolderNode(
        name=base.name or path or "/",
        path=str(base).replace("\\", "/"),
        rel_path=path.replace("\\", "/").strip("/") if path else "",
        is_dir=True,
        mtime=bstat[1] if bstat else 0.0,
        ctime=bstat[2] if bstat else 0.0,
    )
    try:
        for child in sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            cstat = _safe_stat(child)
            if cstat is None:
                continue
            size_v, mtime_v, ctime_v = cstat
            if child.is_dir():
                # Count immediate children for folder metadata
                fc = 0
                ff = 0
                size = 0
                try:
                    for sub in child.iterdir():
                        if sub.is_dir():
                            ff += 1
                        else:
                            try:
                                sub_st = sub.stat()
                                size += sub_st.st_size
                                fc += 1
                            except OSError:
                                pass
                except PermissionError:
                    pass
                node.folder_count += 1
                node.children = node.children or []
                node.children.append(FolderNode(
                    name=child.name,
                    path=str(child).replace("\\", "/"),
                    rel_path=_to_rel(child),
                    is_dir=True,
                    mtime=mtime_v,
                    ctime=ctime_v,
                    file_count=fc,
                    folder_count=ff,
                    size_bytes=size,
                ))
            else:
                node.file_count += 1
                node.size_bytes += size_v
                node.children = node.children or []
                ext_v = child.suffix.lower()
                kind_v = _classify(ext_v)
                node.children.append(FolderNode(
                    name=child.name,
                    path=str(child).replace("\\", "/"),
                    rel_path=_to_rel(child),
                    is_dir=False,
                    mtime=mtime_v,
                    ctime=ctime_v,
                    size_bytes=size_v,
                    ext=ext_v,
                    kind=kind_v,
                ))
    except PermissionError as e:
        logger.warning("Permission denied browsing %s: %s", base, e)
    return node


@router.get("/file")
async def get_file_info(
    path: str = Query(..., description="Relative path to file"),
) -> dict:
    p = _safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    stat = _safe_stat(p)
    mime, _ = mimetypes.guess_type(p.name)
    mtime = stat[1] if stat else 0.0
    ctime = stat[2] if stat else 0.0
    return {
        "name": p.name,
        "path": str(p).replace("\\", "/"),
        "rel_path": _to_rel(p),
        "size_bytes": stat[0] if stat else 0,
        "mtime": mtime,
        "ctime": ctime,
        "mtime_iso": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        "ctime_iso": datetime.fromtimestamp(ctime).isoformat(timespec="seconds"),
        "mime": mime or "application/octet-stream",
        "kind": _classify(p.suffix),
        "ext": p.suffix.lower(),
    }


@router.get("/raw")
async def get_file_raw(path: str = Query(...)):
    """Stream a file with appropriate content-type (for <img>, <video>, preview)."""
    p = _safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    mime, _ = mimetypes.guess_type(p.name)
    return FileResponse(str(p), media_type=mime or "application/octet-stream", filename=p.name)


@router.get("/download")
async def download_file(path: str = Query(...)):
    """Force-download a file (Content-Disposition: attachment)."""
    p = _safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(p), filename=p.name, media_type="application/octet-stream")


@router.get("/search", response_model=SearchResult)
async def search_files(
    q: str = Query(..., min_length=1),
    limit: int = Query(200, ge=1, le=2000),
    kind: str | None = Query(None, description="image|video|text|other"),
) -> SearchResult:
    """Walk the gallery root and return files whose name contains q (case-insensitive)."""
    if not GALLERY_ROOT.exists():
        raise HTTPException(status_code=404, detail="Gallery root missing")
    needle = q.lower()
    items: list[dict[str, Any]] = []
    total = 0
    for p in GALLERY_ROOT.rglob("*"):
        if not p.is_file():
            continue
        if needle not in p.name.lower():
            continue
        kind_v = _classify(p.suffix)
        if kind and kind_v != kind:
            continue
        total += 1
        if len(items) >= limit:
            continue
        stat = _safe_stat(p)
        if stat is None:
            continue
        items.append({
            "name": p.name,
            "rel_path": _to_rel(p),
            "path": str(p).replace("\\", "/"),
            "size_bytes": stat[0],
            "mtime": stat[1],
            "ctime": stat[2],
            "kind": kind_v,
            "ext": p.suffix.lower(),
        })
    items.sort(key=lambda x: x["ctime"], reverse=True)
    return SearchResult(total=total, items=items)


@router.post("/rename")
async def rename_item(payload: RenameRequest, path: str = Query(...)) -> dict:
    p = _safe_path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if "/" in payload.new_name or "\\" in payload.new_name or payload.new_name.strip() == "":
        raise HTTPException(status_code=400, detail="Invalid name")
    new_path = p.parent / payload.new_name
    if new_path.exists():
        raise HTTPException(status_code=409, detail="Target already exists")
    p.rename(new_path)
    return {
        "old_path": str(p).replace("\\", "/"),
        "new_path": str(new_path).replace("\\", "/"),
        "new_rel_path": _to_rel(new_path),
    }


@router.delete("")
async def delete_item(
    path: str = Query(...),
    confirm: bool = Query(False, description="Must be true to actually delete"),
) -> dict:
    if not confirm:
        raise HTTPException(status_code=400, detail="Pass confirm=true to delete")
    p = _safe_path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    rel = _to_rel(p)
    if p.is_dir():
        try:
            shutil.rmtree(p)
        except OSError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"deleted": rel, "kind": "folder"}
    else:
        try:
            p.unlink()
        except OSError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"deleted": rel, "kind": "file"}


@router.get("/stats", response_model=GalleryStats)
async def get_stats() -> GalleryStats:
    """Walk the entire gallery root once. May take a while on big trees."""
    if not GALLERY_ROOT.exists():
        raise HTTPException(status_code=404, detail="Gallery root missing")

    total_files = 0
    total_folders = 0
    total_size = 0
    by_ext: dict[str, int] = {}
    by_top: dict[str, int] = {}
    largest: list[dict[str, Any]] = []
    newest: list[dict[str, Any]] = []

    for p in GALLERY_ROOT.rglob("*"):
        stat = _safe_stat(p)
        if stat is None:
            continue
        size_v, mtime_v, ctime_v = stat
        if p.is_dir():
            total_folders += 1
            continue
        total_files += 1
        total_size += size_v
        ext = p.suffix.lower() or "(none)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
        rel = p.relative_to(GALLERY_ROOT)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        by_top[top] = by_top.get(top, 0) + 1

        entry = {
            "name": p.name,
            "rel_path": str(rel).replace("\\", "/"),
            "size_bytes": size_v,
            "mtime": mtime_v,
            "ctime": ctime_v,
            "kind": _classify(p.suffix),
        }
        largest.append(entry)
        newest.append(entry)

    largest.sort(key=lambda x: x["size_bytes"], reverse=True)
    newest.sort(key=lambda x: x["ctime"], reverse=True)

    return GalleryStats(
        root=str(GALLERY_ROOT),
        total_files=total_files,
        total_folders=total_folders,
        total_size_bytes=total_size,
        by_extension=dict(sorted(by_ext.items(), key=lambda x: x[1], reverse=True)[:20]),
        by_top_folder=dict(sorted(by_top.items(), key=lambda x: x[1], reverse=True)),
        largest_files=largest[:25],
        newest_files=newest[:25],
    )


# ----- HEAD probe for thumbnail availability -----
@router.head("/raw")
async def head_raw(path: str = Query(...)) -> Response:
    p = _safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404)
    return Response(headers={"Content-Length": str(p.stat().st_size)})
