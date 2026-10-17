"""
Twitter / X service — runs gallery-dl for user/single tweet, yt-dlp for live.

Mirrors x_tool3.py approach for non-live paths:
- Uses gallery-dl so behavior matches the working standalone tool
- Writes to E:\\gallery-dl\\twitter\\<username>\\
- Accepts both twitter.com and x.com URLs
- Copies sleep / rate-limit settings from x_tool3.py

Live (Spaces / broadcasts):
- Uses yt-dlp because gallery-dl twitter extractor only fetches the
  per-tweet media, not Space audio / broadcast VOD. yt-dlp supports both.
- Resolves the real uploader from the page metadata BEFORE writing any
  file, so the destination folder is named after the actual host (not
  the spaces_<id> slug).
- Accepts both twitter.com and x.com URLs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from app.core.process_manager import (
    AsyncProcessRunner,
    resolve_gallery_dl_executable,
    resolve_ytdlp_executable,
)

logger = logging.getLogger(__name__)

TWITTER_MEDIA_EXTS = (".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".gif")


class TwitterService:
    """High-level orchestrator for Twitter / X downloads.

    Two backends behind one entry point:

    - gallery-dl for plain tweet / user / video URLs (default)
    - yt-dlp    for ended Spaces (`/i/spaces/<id>`) and ended broadcasts
                (`/i/broadcasts/<id>`) — gallery-dl can't fetch Space audio
                or broadcast VOD
    """

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
        author: str | None = None,
        run_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """Download a single tweet / video / user / ENDED live stream.

        Auto-detect rule (content_type is just a hint, the URL wins):
          - /i/spaces/<id>     → ended Space   (yt-dlp, resolved uploader)
          - /i/broadcasts/<id> → ended live    (yt-dlp, resolved uploader)
          - /status/<id>       → single tweet  (gallery-dl)
          - /<user>            → user timeline (gallery-dl)

        `author` is the row's stored username (passed in by JobRunner). It's
        used as a fallback for the destination folder when the URL itself
        doesn't carry a screen-name (live URLs).

        Yields dict events: user_start, media, warn, error, done.
        """
        normalized = self._normalize_url(url)
        live_kind = self._detect_live_url(normalized)
        if live_kind is not None:
            async for event in self._download_live(
                normalized, live_kind, cookie_files or [], author, run_id,
            ):
                yield event
            return

        # Plain tweet / user / video
        username = self._extract_username(normalized)
        dest = self._resolve_dest(username)
        os.makedirs(dest, exist_ok=True)

        yield {"type": "user_start", "user": username, "index": 1, "total": 1}
        async for event in self._download_with_fallback(normalized, dest, cookie_files or [], run_id=run_id):
            yield event
        yield {"type": "user_done", "user": username}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _resolve_live_uploader(
        self,
        url: str,
        cookie_files: list[str],
    ) -> str | None:
        """Resolve the real host screen-name for a live URL.

        Order (cheapest first):
          1. parse the URL — if the path has a non-special segment before
             `/i/`, use it. This catches tweets that happen to be live
             (e.g. a quoted broadcast, `https://x.com/alice/status/...`
             where yt-dlp is downloading the live VOD attached to it).
          2. fall back to `yt-dlp --print uploader_id` (cheap, single
             line of stdout, no JSON parsing). This is what x_tool3.py
             uses and works for both Spaces and broadcasts.

        Returns the bare handle (no leading @), or None if both fail.
        """
        from app.services.twitter import _LAY_USER_FROM_LIVE_URL as _parser
        parsed = _parser(url)
        if parsed:
            return parsed

        cmd = [
            *resolve_ytdlp_executable(),
            url,
            "--skip-download",
            "--print", "uploader_id",
            "--no-warnings",
            "--no-playlist",
        ]
        for cf in cookie_files:
            if cf and os.path.exists(cf):
                cmd.extend(["--cookies", os.path.normpath(cf)])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return None
            if proc.returncode != 0 or not stdout:
                return None
            # yt-dlp prints one value per line. Take the first non-empty.
            line = stdout.decode("utf-8", errors="ignore").strip().splitlines()[0].strip()
            line = line.lstrip("@")
            if line and line.lower() != "unknown":
                # `uploader_id` is a numeric id sometimes; treat numeric as
                # unresolved so we fall back to author/folder_name.
                if line.isdigit():
                    return None
                return line.split()[0] if line else None
            return None
        except Exception as e:
            logger.warning("yt-dlp --print uploader_id failed for %s: %s", url, e)
            return None

    async def _download_live(
        self,
        url: str,
        live_kind: str,
        cookie_files: list[str],
        author: str | None,
        run_id: str | None,
    ) -> AsyncIterator[dict]:
        """Spaces / broadcasts path — uses yt-dlp and lands in the right folder.

        Folder resolution order:
          1. uploader from yt-dlp metadata (best — matches what X shows)
          2. author from the Download row (if user pasted a handle)
          3. `<live_kind>_<id>` (so the file still lands somewhere)
        """
        resolved = await self._resolve_live_uploader(url, cookie_files)
        folder_name = (
            resolved
            or (author or "").lstrip("@").strip()
            or f"lives_{self._extract_username_from_live(url, live_kind)}"
        )
        dest = self._resolve_dest(folder_name)
        os.makedirs(dest, exist_ok=True)

        yield {"type": "user_start", "user": folder_name, "index": 1, "total": 1}
        async for event in self._download_with_fallback(
            url, dest, cookie_files, live=live_kind, run_id=run_id,
        ):
            yield event
        yield {"type": "user_done", "user": folder_name}

    async def _download_with_fallback(
        self,
        url: str,
        dest: str,
        cookie_files: list[str],
        *,
        live: str | None = None,
        run_id: str | None = None,
    ) -> AsyncIterator[dict]:
        if not cookie_files:
            cookie_files = []

        # Try each cookie file in order
        cookies_to_try = cookie_files or [None]
        for cookie_path in cookies_to_try:
            if self._stop_requested:
                return
            try:
                had_error = False
                async for event in self._execute_one(url, dest, cookie_path, live=live, run_id=run_id):
                    if event.get("type") == "error":
                        had_error = True
                    yield event
                if not had_error:
                    return
            except Exception as e:
                logger.exception("download run failed: %s", e)
                yield {"type": "error", "message": str(e)}
                return

    async def _execute_one(
        self,
        url: str,
        dest: str,
        cookie_file: str | None,
        *,
        live: str | None = None,
        run_id: str | None = None,
    ) -> AsyncIterator[dict]:
        import time as _time
        cmd = self._build_command(url, dest, cookie_file, live=live, run_id=run_id)
        is_ytdlp = live is not None
        # Count files before we start — both engines set mtime from the
        # original social-media post date, not download time, and the
        # SQLite archive persists across runs.  The only reliable signal is
        # "were there more files on disk after the run?".
        files_before = set(self._iter_files(dest))
        # Also track by count — if more files exist after the run,
        # those are the new ones (subprocesses write files atomically so we
        # won't see half-written files).
        count_before = len(files_before)
        await self.runner.start(cmd)
        try:
            downloaded_files: list[Path] = []
            error_seen: str | None = None
            rate_limited = False

            async for line in self.runner.stream_output():
                if self._stop_requested:
                    return
                stripped = line.strip()
                if not stripped:
                    continue
                lower = stripped.lower()

                # Detect rate-limit (same as x_tool3.py)
                if any(err in lower for err in ("429", "rate limit", "too many requests")):
                    rate_limited = True

                # Track new file downloads. yt-dlp emits several line
                # shapes; the working x_tool3.py parses by substring
                # ("destination:", "downloading", "merging", or a
                # bare path ending in a media extension). gallery-dl
                # prefixes paths with "gallery-dl:".
                path_candidate: str | None = None
                if is_ytdlp:
                    if "destination:" in lower or "downloading" in lower or "merging" in lower:
                        # Try "[X] Destination: /path" first (most reliable).
                        m = re.search(
                            r"\[(?:(?:MoveFiles|ExtractAudio|Download|Merger)\s*)?Destination\]:\s*(.+)",
                            stripped,
                        )
                        if m:
                            path_candidate = m.group(1).strip()
                    if not path_candidate and any(stripped.endswith(ext) for ext in TWITTER_MEDIA_EXTS + (".m4a", ".ts")):
                        # bare path line (rare but happens for some extractors)
                        path_candidate = stripped
                else:
                    stripped_for_media = stripped
                    if stripped_for_media.startswith("gallery-dl:"):
                        stripped_for_media = stripped_for_media[len("gallery-dl:") :].strip()
                    is_media = (
                        any(ext in lower for ext in (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm", ".gif"))
                        and not stripped.startswith("#")
                    )
                    if is_media and stripped_for_media:
                        path_candidate = stripped_for_media
                        if " " in path_candidate:
                            path_candidate = path_candidate.split()[-1]
                        # Remove any leading ".\" from gallery-dl output
                        path_candidate = path_candidate.lstrip(".\\")

                if path_candidate and any(path_candidate.endswith(ext) for ext in TWITTER_MEDIA_EXTS + (".m4a", ".ts")):
                    # Yield media event immediately so job_runner picks it up
                    # even if the rest of the run takes a long time
                    self._new_files_count += 1
                    self._total_processed += 1
                    yield {
                        "type": "media",
                        "new": True,
                        "path": path_candidate,
                        "filename": os.path.basename(path_candidate),
                    }

                # Capture errors (same as x_tool3.py)
                if any(err in lower for err in ("error", "unable", "private", "login", "not found")):
                    if not error_seen:
                        error_seen = stripped
                    # Only stop on real errors, not warnings
                    if "error" in lower or "unable" in lower or "private" in lower or "not found" in lower:
                        pass  # keep scanning for media files

                # Already-on-disk lines start with "#" (gallery-dl writes
                # them for archive hits). Don't log them — too noisy for
                # the user terminal, and the new-file count is what
                # matters.

            rc = await self.runner.wait()

            if rate_limited:
                yield {"type": "error", "message": "Rate limit exceeded (429). Cookie may be blocked by X. Wait 4-6 hours."}
                return

            if rc not in (0, None) and not error_seen:
                error_seen = f"{'yt-dlp' if is_ytdlp else 'gallery-dl'} exit code {rc}"

            # After process exits, find truly new files by comparing
            # the set of files before vs after the run.
            if not self._stop_requested:
                files_after = set(self._iter_files(dest))
                new_files = [Path(f) for f in (files_after - files_before)]
                if new_files:
                    # filter out any .part (incomplete) downloads
                    new_files = [f for f in new_files if not str(f).endswith(".part")]
                if new_files:
                    for f in sorted(new_files, key=lambda x: x.stat().st_mtime):
                        self._new_files_count += 1
                        self._total_processed += 1
                        yield {
                            "type": "media",
                            "new": True,
                            "path": str(f),
                            "filename": f.name,
                        }
                    return

                # Nothing fresh in dest.
                if error_seen:
                    yield {"type": "error", "message": error_seen}
                else:
                    yield {"type": "warn", "code": "no_output", "line": ""}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
            return

    def _iter_files(self, folder: str) -> list[str]:
        """Return a list of file names (basenames only) under `folder`.

        Excludes gallery-dl archive files (`.gallery-dl-archive*` and `.archive-*`)
        since those are metadata, not actual downloads.
        """
        p = Path(folder)
        if not p.exists():
            return []
        out: list[str] = []
        for f in p.rglob("*"):
            if not f.is_file():
                continue
            # skip all gallery-dl archive and metadata files
            if f.name.startswith(".") and "archive" in f.name.lower():
                continue
            out.append(f.name)
        return out

    def _build_command(
        self,
        url: str,
        destination: str,
        cookie_file: str | None,
        *,
        live: str | None = None,
        run_id: str | None = None,
    ) -> list[str]:
        dest_path = Path(destination).expanduser()

        # Live (Spaces / broadcasts) → yt-dlp. Plain tweet / user / video
        # → gallery-dl, which has better per-tweet metadata handling.
        if live is not None:
            return self._build_ytdlp_command(url, dest_path, cookie_file, live=live, run_id=run_id)

        cmd: list[str] = [
            *resolve_gallery_dl_executable(),
            url,
            "--destination", str(dest_path),
            "--sleep-request", "3-10",
            "--sleep", "1-5",
            "-o", "cache.file=none",
            "-o", 'directory=["."]',
        ]

        # Each run gets its own archive so the "files before vs after" comparison
        # always reflects this run's output, not a previous run's.
        if run_id:
            archive = dest_path / f".archive-{run_id}.sqlite"
        else:
            archive = dest_path / self.archive_name
        cmd.extend(["--download-archive", str(archive)])

        if cookie_file and os.path.exists(cookie_file):
            cmd.extend(["--cookies", os.path.normpath(cookie_file)])

        return cmd

    def _build_ytdlp_command(
        self,
        url: str,
        dest_path: Path,
        cookie_file: str | None,
        *,
        live: str,
        run_id: str | None,
    ) -> list[str]:
        """yt-dlp command for an ENDED Space or broadcast.

        Mirrors x_tool3.py `thuc_thi_yt_dlp`:
          - output template uses `%(title)s [%(id)s].%(ext)s` so the file
            name is recognisable on disk
          - `--merge-output-format mp4` so audio+video streams land in a
            single .mp4 (broadcasts only; Spaces are audio-only m4a)
          - `--no-part` avoids leaving `.part` files behind on crash
          - retries 5 / fragment-retries 5 to survive flaky network
        """
        if live == "spaces":
            # Spaces are audio-only; cap the title so we don't end up
            # with a 200-char filename.
            out_template = str(dest_path / "%(uploader,channel,creator,unknown)s - %(title).80s [%(id)s].%(ext)s")
        else:
            out_template = str(dest_path / "%(uploader,channel,creator,unknown)s - %(title).80s [%(id)s].%(ext)s")

        cmd: list[str] = [
            *resolve_ytdlp_executable(),
            url,
            "-o", out_template,
            "--merge-output-format", "mp4",
            "--no-part",
            "--no-progress",
            "--no-mtime",
            "--no-warnings",
            "--no-playlist",
            "--retries", "5",
            "--fragment-retries", "5",
        ]

        # Archive (skip if already downloaded). One archive per run, just
        # like the gallery-dl path, so "files before vs after" stays
        # scoped to this run.
        if run_id:
            archive = dest_path / f".yt-archive-{run_id}.txt"
        else:
            archive = dest_path / self.ytdlp_archive_name
        cmd.extend(["--download-archive", str(archive)])

        if cookie_file and os.path.exists(cookie_file):
            cmd.extend(["--cookies", os.path.normpath(cookie_file)])

        return cmd

    archive_name = ".gallery-dl-archive.sqlite"
    ytdlp_archive_name = ".yt-dlp-archive.txt"

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

    def _live_folder_name(self, url: str, live_kind: str, author: str | None) -> str:
        """Pick the destination folder for a Space/broadcast.

        Prefer the username the row was created against (author param).
        Fall back to `<live_kind>_<id>` so the file still lands somewhere
        when the user didn't tell us who they were downloading.
        """
        clean_author = (author or "").lstrip("@").strip()
        if clean_author:
            return clean_author
        return f"lives_{self._extract_username_from_live(url, live_kind)}"

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


# Module-level URL parser — mirrors x_tool3.py `lay_user_tu_link_live`
# so we resolve the host screen-name from a tweet/quote URL without
# shelling out to yt-dlp. Path segments like `i`, `intent`, `search`,
# `home`, `explore`, `hashtag` are non-personal and get skipped.
_LIVE_URL_PREFIXES = (
    "https://x.com/", "http://x.com/",
    "https://twitter.com/", "http://twitter.com/",
    "https://mobile.twitter.com/", "http://mobile.twitter.com/",
)
_LIVE_URL_NON_USER_SEGMENTS = frozenset({"i", "intent", "search", "home", "explore", "hashtag"})


def _LAY_USER_FROM_LIVE_URL(url: str) -> str:
    """Return the first path segment that looks like a screen-name, or ""."""
    if not url:
        return ""
    s = url.strip().replace('"', "")
    if "?" in s:
        s = s.split("?", 1)[0]
    if s.endswith("/"):
        s = s[:-1]
    lower = s.lower()
    for prefix in _LIVE_URL_PREFIXES:
        if not lower.startswith(prefix):
            continue
        parts = s[len(prefix):].split("/")
        if parts and parts[0] and parts[0] not in _LIVE_URL_NON_USER_SEGMENTS:
            return parts[0]
        return ""
    return ""
