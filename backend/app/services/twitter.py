"""
Twitter / X service — runs yt-dlp and parses output.

Mirrors InstagramService but:
- Uses yt-dlp instead of gallery-dl
- Writes to E:\\gallery-dl\\twitter\\<username>\\
- No Instagram-specific rate-limit patterns (yt-dlp is generally friendlier)
- Accepts both twitter.com and x.com URLs
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from app.core.process_manager import (
    AsyncProcessRunner,
    resolve_ytdlp_executable,
)

logger = logging.getLogger(__name__)

TWITTER_MEDIA_EXTS = (".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".gif")


class TwitterService:
    """High-level orchestrator for Twitter / X downloads via yt-dlp."""

    def __init__(self) -> None:
        self.runner = AsyncProcessRunner()
        self._stop_requested = False
        self._new_files_count = 0
        self._total_processed = 0

    @property
    def is_stopping(self) -> bool:
        return self._stop_requested

    @property
    def stats(self) -> dict[str, int]:
        return {
            "new_files": self._new_files_count,
            "total_processed": self._total_processed,
        }

    def request_stop(self) -> None:
        self._stop_requested = True

    async def request_stop_async(self) -> None:
        """Async version — also kills the yt-dlp subprocess so the
        generator unblocks instead of waiting for the next stdout line."""
        self._stop_requested = True
        await self.runner.stop(grace_seconds=2.0)

    @property
    def is_running(self) -> bool:
        return self.runner.is_running

    @property
    def current_pid(self) -> int | None:
        return self.runner.pid

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def download(
        self,
        url: str,
        cookie_files: list[str] | None = None,
        content_type: str | None = None,
    ) -> AsyncIterator[dict]:
        """Download a single tweet / video / user / ENDED live stream.

        Auto-detect rule (content_type is just a hint, the URL wins):
          - /i/spaces/<id>     → ended Space   (yt-dlp --live-from-start)
          - /i/broadcasts/<id> → ended live    (yt-dlp)
          - /status/<id>       → single tweet  (yt-dlp)
          - /<user>            → user timeline (yt-dlp)

        Yields dict events: user_start, media, warn, error, done.
        """
        normalized = self._normalize_url(url)
        live_kind = self._detect_live_url(normalized)
        if live_kind is not None:
            username = self._extract_username_from_live(normalized, live_kind)
            dest = self._resolve_dest(f"lives_{live_kind}_{username}")
            os.makedirs(dest, exist_ok=True)
            yield {"type": "user_start", "user": username, "index": 1, "total": 1}
            async for event in self._download_with_fallback(
                normalized, dest, cookie_files or [], live=live_kind,
            ):
                yield event
            yield {"type": "user_done", "user": username}
            return

        # Plain tweet / user / video
        username = self._extract_username(normalized)
        dest = self._resolve_dest(username)
        os.makedirs(dest, exist_ok=True)

        yield {"type": "user_start", "user": username, "index": 1, "total": 1}
        async for event in self._download_with_fallback(normalized, dest, cookie_files or []):
            yield event
        yield {"type": "user_done", "user": username}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _download_with_fallback(
        self,
        url: str,
        dest: str,
        cookie_files: list[str],
        *,
        live: str | None = None,
    ) -> AsyncIterator[dict]:
        if not cookie_files:
            # yt-dlp works without cookies for public tweets
            cookie_files = []

        # Try each cookie file in order
        cookies_to_try = cookie_files or [None]
        for cookie_path in cookies_to_try:
            if self._stop_requested:
                return
            try:
                had_error = False
                async for event in self._execute_one(url, dest, cookie_path, live=live):
                    if event.get("type") == "error":
                        had_error = True
                        yield event
                if not had_error:
                    return
            except Exception as e:
                logger.exception("yt-dlp run failed: %s", e)
                yield {"type": "error", "message": str(e)}
                return

    async def _execute_one(
        self,
        url: str,
        dest: str,
        cookie_file: str | None,
        *,
        live: str | None = None,
    ) -> AsyncIterator[dict]:
        cmd = self._build_command(url, dest, cookie_file, live=live)
        logger.info("yt-dlp cmd: %s", " ".join(cmd))
        await self.runner.start(cmd)
        try:
            error_seen: str | None = None
            async for line in self.runner.stream_output():
                if self._stop_requested:
                    return
                stripped = line.strip()
                if not stripped:
                    continue
                lower = stripped.lower()
                # Always log yt-dlp output for visibility
                if any(t in lower for t in ("[twitter]", "[x]", "extracting", "downloading", "[info]", "[debug]")):
                    logger.info("yt-dlp: %s", stripped)
                    continue
                if any(t in lower for t in ("error", "unable", "failed", "private", "warning", "http error")):
                    logger.warning("yt-dlp: %s", stripped)
                    if "private" in lower or "unable" in lower or "error" in lower:
                        error_seen = stripped
                    continue
                # Log other lines at debug to keep noise down
                logger.debug("yt-dlp: %s", stripped)

            rc = await self.runner.wait()
            if rc not in (0, None):
                error_seen = f"yt-dlp exit code {rc}"

            # After process exits, scan dest folder for newest file
            if not self._stop_requested:
                found = self._newest_in(dest, max_age_seconds=600)
                if found:
                    self._new_files_count += 1
                    self._total_processed += 1
                    yield {
                        "type": "media",
                        "new": True,
                        "path": str(found),
                        "filename": found.name,
                    }
                elif error_seen:
                    yield {"type": "error", "message": error_seen}
                else:
                    yield {"type": "warn", "code": "no_output", "line": ""}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
            return

    def _newest_in(self, folder: str, max_age_seconds: int) -> Path | None:
        from time import time
        p = Path(folder)
        if not p.exists():
            return None
        cutoff = time() - max_age_seconds
        best: tuple[float, Path] | None = None
        try:
            for f in p.rglob("*"):
                if not f.is_file() or f.name.startswith("."):
                    continue
                try:
                    mtime = f.stat().st_mtime
                except OSError:
                    continue
                if mtime < cutoff:
                    continue
                if best is None or mtime > best[0]:
                    best = (mtime, f)
        except OSError:
            return None
        return best[1] if best else None

    def _build_command(
        self,
        url: str,
        destination: str,
        cookie_file: str | None,
        *,
        live: str | None = None,
    ) -> list[str]:
        dest_path = Path(destination).expanduser()
        # Filename template keeps tweets identifiable
        filename_template = "%(uploader)s_%(id)s_%(timestamp)s.%(ext)s"

        cmd: list[str] = [
            *resolve_ytdlp_executable(),
            url,
            "-P", f"{dest_path}",
            "-o", filename_template,
            "--no-playlist",
            "--restrict-filenames",
            "--no-warnings",
            "--no-progress",
            "--no-mtime",
            "--retries", "5",
            "--fragment-retries", "5",
            # Don't redownload already-seen files (id-based)
            "--download-archive", str(dest_path / ".yt-dlp-archive.txt"),
        ]

        # Ended live (Spaces / broadcasts) needs the live-from-start flag
        # so yt-dlp pulls the full replay rather than just the live tail.
        if live == "spaces":
            cmd.extend(["--live-from-start"])
        elif live == "broadcasts":
            # broadcasts: still use live-from-start if available, plus write
            # the metadata sidecar for post-processing.
            cmd.extend(["--live-from-start", "--write-info-json"])

        if cookie_file and os.path.exists(cookie_file):
            cmd.extend(["--cookies", os.path.normpath(cookie_file)])

        return cmd

    def _detect_live_url(self, url: str) -> str | None:
        """Return 'spaces' | 'broadcasts' | None based on the URL path.

        We only support ENDED live streams. The UI shouldn't submit a live URL
        that's still airing — yt-dlp will fail and the row will be marked
        failed with a clear error message.
        """
        path = url.replace("https://twitter.com/", "").replace("https://x.com/", "")
        path = path.strip("/")
        # both /i/spaces/<id> and /i/spaces/1yoJMAjAlXyKQ (hash form)
        if path.startswith("i/spaces/") or "/i/spaces/" in path:
            return "spaces"
        if path.startswith("i/broadcasts/") or "/i/broadcasts/" in path:
            return "broadcasts"
        return None

    def _extract_username_from_live(self, url: str, live_kind: str) -> str:
        # For Spaces the ID lives in /i/spaces/<id>; for broadcasts in
        # /i/broadcasts/<id>. The "username" we use for the destination
        # folder is just the ID — there's no stable screen-name for a Space.
        path = url.replace("https://twitter.com/", "").replace("https://x.com/", "")
        parts = [p for p in path.split("/") if p]
        # find the segment after "spaces" or "broadcasts"
        try:
            idx = parts.index("i")
            kind = parts[idx + 1]  # 'spaces' or 'broadcasts'
            sid = parts[idx + 2] if idx + 2 < len(parts) else "unknown"
            return f"{kind}_{sid}"
        except (ValueError, IndexError):
            return f"{live_kind}_unknown"

    def _normalize_url(self, url: str) -> str:
        cleaned = url.strip()
        # Strip query and fragment
        cleaned = cleaned.split("?")[0].split("#")[0].rstrip("/")
        # Accept any of: https://twitter.com/..., https://x.com/..., https://www.x.com/...
        for prefix in (
            "https://www.twitter.com/",
            "https://twitter.com/",
            "https://www.x.com/",
            "https://x.com/",
        ):
            if cleaned.startswith(prefix):
                return "https://twitter.com/" + cleaned[len(prefix):]
        if cleaned.startswith(("http://", "https://")):
            return cleaned
        return f"https://twitter.com/{cleaned.lstrip('@/')}"

    def _extract_username(self, url: str) -> str:
        # url is normalized to https://twitter.com/...
        path = url.replace("https://twitter.com/", "").strip("/")
        if not path:
            return "unknown"
        # /status/<id> → take the first path segment
        return path.split("/")[0].split("?")[0] or "unknown"

    def _resolve_dest(self, name: str) -> str:
        from app.config import get_settings
        base = get_settings().get_twitter_download_folder()
        return str(base / name)
