"""Shared media classification (extension sets + classify function).

Kept tiny on purpose: a single import site avoids drift between the
API routers (gallery, accounts) and the WS handlers that all need
the same "is this an image / video / text" answer.
"""
from __future__ import annotations

IMAGE_EXTS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".avif", ".tiff",
})
VIDEO_EXTS: frozenset[str] = frozenset({
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".flv", ".m4v", ".3gp",
})
TEXT_EXTS: frozenset[str] = frozenset({
    ".txt", ".json", ".xml", ".csv", ".log", ".md",
})


def classify(ext: str | None) -> str:
    """Return 'image' | 'video' | 'text' | 'other' for a file extension.

    The leading dot is optional — both '.jpg' and 'jpg' work. None or
    an unknown extension returns 'other'.
    """
    if not ext:
        return "other"
    e = ext.lower()
    if not e.startswith("."):
        e = "." + e
    if e in IMAGE_EXTS:
        return "image"
    if e in VIDEO_EXTS:
        return "video"
    if e in TEXT_EXTS:
        return "text"
    return "other"
