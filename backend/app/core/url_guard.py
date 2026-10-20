"""Validate URLs before they reach gallery-dl / yt-dlp.

Argv-injection guard: the URL is passed straight to `cmd.append(url)`
in every platform service, so an attacker-controlled string that starts
with `--config=...` or has a `file://` scheme would be interpreted by
the downstream tool. We pin scheme and host per platform here.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException

# Host whitelist per platform. Lowercased for case-insensitive compare.
_HOSTS: dict[str, set[str]] = {
    "instagram": {
        "instagram.com",
        "www.instagram.com",
    },
    "twitter": {
        "twitter.com",
        "www.twitter.com",
        "x.com",
        "www.x.com",
    },
    "tiktok": {
        "tiktok.com",
        "www.tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
    },
}

_SCHEMES = {"http", "https"}


def validate_url(url: str, platform: str) -> str:
    """Return the URL if it passes scheme+host check; else raise 400.

    Bare usernames / short codes are accepted for TikTok only (the
    `_normalize_target` step in tiktok.py turns `@user` into a real URL).
    """
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="empty url")
    raw = url.strip()
    # Bare username is a TikTok convention (`@foo` or `foo`) — let the
    # service normalize it; no host to check.
    if platform == "tiktok" and not raw.startswith(("http://", "https://")):
        if raw.lstrip("@").isidentifier() or _looks_like_username(raw.lstrip("@")):
            return raw
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unparseable url: {exc}") from exc
    if parsed.scheme not in _SCHEMES:
        raise HTTPException(status_code=400, detail=f"scheme not allowed: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    allowed = _HOSTS.get(platform)
    if allowed is None:
        raise HTTPException(status_code=400, detail=f"unknown platform: {platform!r}")
    if host not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"host {host!r} not allowed for platform {platform!r}",
        )
    return raw


def _looks_like_username(s: str) -> bool:
    """Cheap username sanity check: letters/digits/underscore/dot, ≤30 chars."""
    if not s or len(s) > 30:
        return False
    return all(c.isalnum() or c in "._-" for c in s)


def is_path_inside_any(child: str | Path, roots: list[Path]) -> bool:
    """True iff resolved `child` is inside at least one of `roots`.

    Used to gate FileResponse + os.remove in `app/api/media.py` so a
    row that points outside the configured download folders cannot
    be read or deleted by API callers.
    """
    try:
        c = Path(child).resolve(strict=False)
    except (OSError, RuntimeError):
        return False
    for r in roots:
        try:
            base = Path(r).resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        try:
            c.relative_to(base)
        except ValueError:
            continue
        return True
    return False
