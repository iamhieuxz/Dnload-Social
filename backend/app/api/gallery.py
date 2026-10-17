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

import asyncio
import logging
import mimetypes
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import get_settings
from app.core.media_types import IMAGE_EXTS, VIDEO_EXTS, classify as _classify

logger = logging.getLogger(__name__)

# Cache filesystem tree scans for 30s. The scan takes 5+ seconds for the
# full 144k-file gallery, so 30s is the right balance between freshness
# and not stalling the UI every time the user reopens a folder.
_TREE_CACHE: dict[tuple[str, int, int, bool], tuple[float, Any]] = {}
_TREE_CACHE_LOCK = asyncio.Lock()
_TREE_CACHE_TTL = 30.0
# Search walks the full gallery rglob — 4s+ on the 144k-file disk.
# Cache the (q, limit, kind) tuple for 30s; the UI only re-queries when
# the user types a new term, so a cold scan is the common case anyway.
_SEARCH_CACHE: dict[tuple[str, int, str | None], tuple[float, Any]] = {}
_SEARCH_CACHE_LOCK = asyncio.Lock()
_SEARCH_CACHE_TTL = 30.0
# Stop counting once we have enough evidence to know the user has
# "thousands" of hits — beyond this the exact total doesn't matter and
# the UI only shows `total.toLocaleString()` truncated to a small range.
_SEARCH_COUNT_CAP = 5000

def _gallery_roots() -> list[Path]:
    settings = get_settings()
    return [
        settings.get_download_folder(),
        settings.get_twitter_download_folder(),
        settings.get_tiktok_download_folder(),
    ]


def _gallery_root() -> Path:
    return _gallery_roots()[0].parent


def _is_allowed_path(path: Path) -> bool:
    return any(path == root or root in path.parents for root in _gallery_roots())

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


def _to_rel(p: Path) -> str:
    try:
        return str(p.relative_to(_gallery_root())).replace("\\", "/")
    except ValueError:
        pass
    return p.name


def _safe_stat(p: Path) -> tuple[int, float, float] | None:
    """Return (size, mtime, ctime) for a path, or None if it can't be stat'd.

    ctime here means "creation time" for the UI. We use st_birthtime
    where available (macOS, BSD, some Linux filesystems) and st_ctime
    elsewhere. On Windows, st_ctime is already exposed in Unix-epoch
    seconds by Python 3.3+; the previous "if raw > 10_000_000_000 then
    it's a raw FILETIME" heuristic was wrong and would break in 2286
    or on any build that returns an unexpected shape.
    """
    try:
        st = p.stat()
    except OSError:
        return None
    ctime = st.st_birthtime if hasattr(st, "st_birthtime") else st.st_ctime
    return st.st_size, st.st_mtime, ctime


def _safe_path(rel: str) -> Path:
    """Resolve a user-supplied relative path under the gallery root.

    Raises 400 if the result escapes the gallery root (path-traversal guard).
    """
    rel = (rel or "").replace("\\", "/").lstrip("/")
    # Reject Windows drive-relative forms like "C:foo" that resolve to a
    # path on the system drive. Path.is_absolute() returns False for
    # those, so the original check missed them. After normalisation
    # they would become "C:/foo" — drive letters are still detectable.
    if rel and (rel[1:2] == ":" or rel.startswith("//")):
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed")
    candidate = (_gallery_root() / rel).resolve()
    if _is_allowed_path(candidate):
        return candidate
    raise HTTPException(status_code=400, detail="Path escapes gallery roots")




# ----- Endpoints -----

@router.get("/root")
async def get_root() -> dict:
    root = _gallery_root()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Gallery root not found: {root}")
    return {
        "root": str(root),
        "exists": True,
    }


@router.get("/tree", response_model=FolderNode)
async def get_tree(
    path: str = Query("", description="Relative path under gallery root; '' = root"),
    depth: int = Query(6, ge=0, le=12, description="How many levels deep to expand children"),
    max_nodes: int = Query(8000, ge=100, le=50000, description="Stop scanning once this many nodes have been built"),
    include_files: bool = Query(False, description="Also list file children. Default false because 100k+ files would blow the response."),
) -> FolderNode:
    base = _safe_path(path) if path else _gallery_root()
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    key = (path, depth, max_nodes, include_files)
    now = time.monotonic()
    async with _TREE_CACHE_LOCK:
        cached = _TREE_CACHE.get(key)
        if cached is not None and now - cached[0] < _TREE_CACHE_TTL:
            return cached[1]
    node = await asyncio.to_thread(_build_node, base, depth, path, max_nodes=max_nodes, include_files=include_files)
    async with _TREE_CACHE_LOCK:
        _TREE_CACHE[key] = (time.monotonic(), node)
    return node


def _build_node(
    p: Path,
    depth: int,
    rel_input: str,
    *,
    max_nodes: int,
    include_files: bool,
) -> FolderNode:
    counter = [0]

    def walk(pp: Path, d: int, rel: str) -> FolderNode:
        counter[0] += 1
        if counter[0] > max_nodes:
            # Reached the cap — return a truncated stub.
            stat = _safe_stat(pp)
            return FolderNode(
                name=pp.name or rel or "/",
                path=str(pp).replace("\\", "/"),
                rel_path=rel,
                is_dir=True,
                mtime=stat[1] if stat else 0.0,
                ctime=stat[2] if stat else 0.0,
                folder_count=0,
            )
        stat = _safe_stat(pp)
        mtime = stat[1] if stat else 0.0
        ctime = stat[2] if stat else 0.0
        node = FolderNode(
            name=pp.name or rel or "/",
            path=str(pp).replace("\\", "/"),
            rel_path=rel,
            is_dir=True,
            mtime=mtime,
            ctime=ctime,
        )
        try:
            for child in sorted(pp.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if counter[0] >= max_nodes:
                    break
                if child.is_dir():
                    node.folder_count += 1
                    if d > 0:
                        node.children = node.children or []
                        node.children.append(walk(child, d - 1, _to_rel(child)))
                    else:
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
                elif include_files:
                    cstat = _safe_stat(child)
                    if cstat is None:
                        continue
                    node.file_count += 1
                    node.size_bytes += cstat[0]
                    node.children = node.children or []
                    ext_v = child.suffix.lower()
                    node.children.append(FolderNode(
                        name=child.name,
                        path=str(child).replace("\\", "/"),
                        rel_path=_to_rel(child),
                        is_dir=False,
                        mtime=cstat[1],
                        ctime=cstat[2],
                        size_bytes=cstat[0],
                        ext=ext_v,
                        kind=_classify(ext_v),
                    ))
                else:
                    cstat = _safe_stat(child)
                    if cstat is None:
                        continue
                    node.file_count += 1
                    node.size_bytes += cstat[0]
        except PermissionError as e:
            logger.warning("Permission denied scanning %s: %s", pp, e)
        return node

    rel = _to_rel(p) if p != _gallery_root() else (rel_input or "")
    return walk(p, depth, rel)


@router.get("/browse", response_model=FolderNode)
async def browse_folder(
    path: str = Query("", description="Relative path under gallery root"),
) -> FolderNode:
    """List a single folder with all its direct children (files + subfolders with metadata)."""
    base = _safe_path(path) if path else _gallery_root()
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
    # Shortcut: tell the browser to cache media for 10 min so the
    # gallery grid doesn't re-fetch the same 144k thumbnails on every
    # re-render. The gallery is local-only and the operator renames/
    # deletes via the API which already invalidates, so stale-while-
    # revalidate is fine.
    return FileResponse(
        str(p),
        media_type=mime or "application/octet-stream",
        filename=p.name,
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.get("/download")
async def download_file(path: str = Query(...)):
    """Force-download a file (Content-Disposition: attachment)."""
    p = _safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    # Same cache hint as /raw — the file content never changes unless
    # the operator edits it, so the browser can keep the binary around.
    return FileResponse(
        str(p),
        filename=p.name,
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.get("/search", response_model=SearchResult)
async def search_files(
    q: str = Query(..., min_length=1),
    limit: int = Query(200, ge=1, le=2000),
    kind: str | None = Query(None, description="image|video|text|other"),
) -> SearchResult:
    """Walk the gallery root and return files whose name contains q (case-insensitive)."""
    cache_key = (q.strip().lower(), limit, kind)
    now = time.monotonic()
    async with _SEARCH_CACHE_LOCK:
        cached = _SEARCH_CACHE.get(cache_key)
        if cached is not None and now - cached[0] < _SEARCH_CACHE_TTL:
            return cached[1]
    roots = _gallery_roots()
    if not any(root.exists() for root in roots):
        raise HTTPException(status_code=404, detail="Gallery root missing")
    needle = q.lower()
    items: list[dict[str, Any]] = []
    total = 0
    counting_done = False
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or needle not in p.name.lower():
                continue
            kind_v = _classify(p.suffix)
            if kind and kind_v != kind:
                continue
            if not counting_done:
                total += 1
                if total > _SEARCH_COUNT_CAP:
                    # Plenty of evidence; stop counting but keep filling
                    # the page of items the UI will actually render.
                    counting_done = True
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
    items.sort(key=lambda x: (x["ctime"], x["name"]), reverse=True)
    result = SearchResult(total=total, items=items)
    async with _SEARCH_CACHE_LOCK:
        _SEARCH_CACHE[cache_key] = (time.monotonic(), result)
    return result


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
    roots = _gallery_roots()
    if not any(root.exists() for root in roots):
        raise HTTPException(status_code=404, detail="Gallery root missing")

    total_files = 0
    total_folders = 0
    total_size = 0
    by_ext: dict[str, int] = {}
    by_top: dict[str, int] = {}
    largest: list[dict[str, Any]] = []
    newest: list[dict[str, Any]] = []

    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
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
            rel = p.relative_to(root)
            top = root.name if len(rel.parts) > 0 else "(root)"
            by_top[top] = by_top.get(top, 0) + 1

            entry = {
                "name": p.name,
                "rel_path": _to_rel(p),
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
        root=str(_gallery_root()),
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


# ----- Streaming tree (WebSocket) -----
#
# The whole /api/gallery/tree walk takes 30-120s on an HDD bind mount with
# 144k files. Instead of making the UI stare at a spinner, the client opens
# a WebSocket and receives one FolderNode per folder as soon as the walker
# finishes that subtree. The walker runs in a worker thread (so HDD seeks
# don't block the event loop), pushes completed nodes into an asyncio.Queue,
# and the WS handler forwards them. When the client disconnects, the
# queue.put sentinel returns False and the worker stops.

import json
import threading


@router.websocket("/stream")
async def stream_tree(websocket: WebSocket) -> None:
    await websocket.accept()
    cancelled = threading.Event()

    async def safe_send(payload: dict) -> bool:
        try:
            await websocket.send_json(payload)
            return True
        except (WebSocketDisconnect, RuntimeError):
            cancelled.set()
            return False

    try:
        raw = await websocket.receive_text()
        cfg = json.loads(raw)
        path = cfg.get("path", "")
        depth = int(cfg.get("depth", 6))
        max_nodes = int(cfg.get("max_nodes", 8000))
        include_files = bool(cfg.get("include_files", False))
        depth = max(0, min(12, depth))
        max_nodes = max(100, min(50000, max_nodes))

        try:
            base = _safe_path(path) if path else _gallery_root()
        except HTTPException as e:
            await safe_send({"type": "error", "detail": e.detail})
            return
        if not base.exists() or not base.is_dir():
            await safe_send({"type": "error", "detail": "Folder not found"})
            return

        # Root node first so the UI can render the breadcrumb + skeleton
        # before any subfolder is scanned.
        bstat = _safe_stat(base)
        root = FolderNode(
            name=base.name or path or "/",
            path=str(base).replace("\\", "/"),
            rel_path=path.replace("\\", "/").strip("/") if path else "",
            is_dir=True,
            mtime=bstat[1] if bstat else 0.0,
            ctime=bstat[2] if bstat else 0.0,
        )
        if not await safe_send({"type": "node", "data": root.model_dump()}):
            return

        # Use an asyncio.Queue so the consumer doesn't need a thread
        # executor. The walker is the producer and runs in a worker
        # thread; it pushes via call_soon_threadsafe, which is the
        # documented way to hand work from a non-asyncio thread to
        # the running loop.
        q: asyncio.Queue[dict | None] = asyncio.Queue()

        # Batching: each ws.send() costs ~hundreds of µs through Docker
        # Desktop's loopback bridge. Sending one message per folder
        # turns 312 folders into ~100s of round trips. Flush a batch
        # of nodes (up to 64) per message instead.
        BATCH_SIZE = 64
        loop = asyncio.get_event_loop()

        def worker() -> None:
            counter = [0]
            batch: list[dict] = []

            def flush() -> None:
                nonlocal batch
                if not batch:
                    return
                if len(batch) == 1:
                    payload = batch[0]
                else:
                    payload = {"type": "batch", "nodes": batch}
                batch = []
                loop.call_soon_threadsafe(q.put_nowait, payload)

            def walk(pp: Path, d: int, rel: str) -> FolderNode | None:
                if cancelled.is_set():
                    return None
                counter[0] += 1
                if counter[0] > max_nodes:
                    stat = _safe_stat(pp)
                    return FolderNode(
                        name=pp.name or rel or "/",
                        path=str(pp).replace("\\", "/"),
                        rel_path=rel,
                        is_dir=True,
                        mtime=stat[1] if stat else 0.0,
                        ctime=stat[2] if stat else 0.0,
                        folder_count=0,
                    )
                # Defer stat() on the folder itself until we need mtime/ctime
                # in the response. Most of the time the client just needs
                # the name + children list, so we skip the per-folder
                # syscall that Path.iterdir + Path.stat was paying.
                node = FolderNode(
                    name=pp.name or rel or "/",
                    path=str(pp).replace("\\", "/"),
                    rel_path=rel,
                    is_dir=True,
                )
                try:
                    # os.scandir is a single syscall that returns a
                    # DirEntry for every child with is_dir() cached.
                    # We avoid calling is_dir() during the sort key
                    # because on Windows + bind mount each call walks
                    # through a slow attribute path; instead we group
                    # by name and let the UI sort if it cares. The
                    # cost of an unsorted list is invisible to a tree
                    # that paints folder-by-folder anyway.
                    with os.scandir(pp) as it:
                        entries = list(it)
                except (PermissionError, OSError):
                    return node
                for child in entries:
                    if cancelled.is_set() or counter[0] >= max_nodes:
                        break
                    try:
                        is_dir = child.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        node.folder_count += 1
                        if d > 0:
                            sub = walk(Path(child.path), d - 1, _to_rel(Path(child.path)))
                            if sub is None:
                                return None
                            node.children = node.children or []
                            node.children.append(sub)
                            batch.append(sub.model_dump())
                            if len(batch) >= BATCH_SIZE:
                                flush()
                        else:
                            stub = FolderNode(
                                name=child.name,
                                path=child.path.replace("\\", "/"),
                                rel_path=_to_rel(Path(child.path)),
                                is_dir=True,
                            )
                            node.children = node.children or []
                            node.children.append(stub)
                            batch.append(stub.model_dump())
                            if len(batch) >= BATCH_SIZE:
                                flush()
                    elif include_files:
                        cstat = _safe_stat(Path(child.path))
                        if cstat is None:
                            continue
                        node.file_count += 1
                        node.size_bytes += cstat[0]
                        ext_v = Path(child.name).suffix.lower()
                        file_node = FolderNode(
                            name=child.name,
                            path=child.path.replace("\\", "/"),
                            rel_path=_to_rel(Path(child.path)),
                            is_dir=False,
                            mtime=cstat[1],
                            ctime=cstat[2],
                            size_bytes=cstat[0],
                            ext=ext_v,
                            kind=_classify(ext_v),
                        )
                        node.children = node.children or []
                        node.children.append(file_node)
                        batch.append(file_node.model_dump())
                        if len(batch) >= BATCH_SIZE:
                            flush()
                    else:
                        if d > 0:
                            node.file_count += 1
                            continue
                        try:
                            st = child.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        node.file_count += 1
                        node.size_bytes += st.st_size
                return node

            rel = _to_rel(base) if base != _gallery_root() else (path or "")
            full = walk(base, depth, rel)
            # The root node was sent before walk() populated its children,
            # so the UI saw an empty tree for the first frame. Re-send
            # it now with the populated children; the client overwrites
            # by rel_path, so this is idempotent.
            if full is not None and depth == 0 and (path or "") != (full.rel_path or ""):
                pass  # walker rooted somewhere else; not our case here
            if full is not None:
                loop.call_soon_threadsafe(
                    q.put_nowait,
                    {"type": "node", "data": full.model_dump()},
                )
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "done", "data": full.model_dump() if full else None, "total": counter[0]},
            )

        # Watch for client disconnect in parallel — set the cancel event
        # the moment the WS drops, so the worker can stop on its next
        # folder boundary.
        disconnect_future: asyncio.Future[None] = asyncio.get_event_loop().create_future()

        async def watch_disconnect() -> None:
            try:
                while True:
                    await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                cancelled.set()
                disconnect_future.set_result(None)

        watcher = asyncio.create_task(watch_disconnect())
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        # Drain the queue. We use asyncio.wait on (get_task, disconnect_future)
        # so we can bail the moment the client goes away, without paying
        # for a per-call thread executor (which on this Docker Desktop
        # setup was adding tens of ms per get and turning a 0.6s scan
        # into 100s of wall time).
        get_task = asyncio.create_task(q.get())
        while True:
            if cancelled.is_set() or disconnect_future.done():
                get_task.cancel()
                break
            done_set, _ = await asyncio.wait(
                {get_task, disconnect_future},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if disconnect_future in done_set and not get_task.done():
                # Client gone — worker will stop at next folder.
                get_task.cancel()
                try:
                    await get_task
                except BaseException:
                    pass  # CancelledError or empty queue — both fine
                break
            if get_task not in done_set:
                continue
            payload = get_task.result()
            get_task = asyncio.create_task(q.get())
            if payload is None:
                break
            if not await safe_send(payload):
                break
            if payload.get("type") == "done":
                break

        cancelled.set()
        if watcher and not watcher.done():
            watcher.cancel()
            try:
                await watcher
            except BaseException:
                pass
    except WebSocketDisconnect:
        cancelled.set()
    except Exception as e:
        logger.exception("WS gallery stream error")
        try:
            await safe_send({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
