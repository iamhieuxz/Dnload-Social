"""
Async Instagram service — runs gallery-dl and parses output.

Fixes vs original services.py:
- C1: Job is owned by JobRunner; only one job runs at a time.
- C4: We do NOT scan the file tree before/after every account. Instead
      we use the file_count delta and a per-account media table for stats.
- C5: Cookie fallback aborts on first rate-limit signal instead of yielding
      all lines first.
- M6: Cache sets are now DB-backed (Job table), not in-memory sets that
      reset on restart.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.process_manager import (
    AsyncProcessRunner,
    resolve_gallery_dl_executable,
    resolve_ytdlp_executable,
)
from app.core.rate_limit import RateLimitGuard, RateLimitPolicy

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".m4v", ".heic", ".avif")


@dataclass(slots=True)
class GalleryDlTuning:
    sleep_request: str = "10-24"
    sleep: str = "5-12"
    retries: int = 8
    retry_sleep: str = "60-180"
    request_timeout: int = 60


class InstagramService:
    """
    High-level orchestrator. Pure business logic — no DB access here.
    The JobRunner persists state; this service just runs gallery-dl and
    yields parsed events.

    Subclasses (e.g. TikTokService) reuse the whole gallery-dl pipeline and
    only override the three class hooks below plus URL/dest derivation.
    """

    # --- class hooks: what a subclass needs to change ---
    archive_name = ".instagram_download_archive.sqlite"
    cookies_required = True
    filename_template = "{date:%Y-%m-%d}_{shortcode|id}_{num:04}.{extension}"

    def __init__(
        self,
        policy: RateLimitPolicy | None = None,
        tuning: GalleryDlTuning | None = None,
    ) -> None:
        self.policy = policy or RateLimitPolicy()
        self.guard = RateLimitGuard(self.policy)
        self.tuning = tuning or GalleryDlTuning()
        self.runner = AsyncProcessRunner()
        self._stop_requested = False
        self._new_files_count = 0
        self._total_processed = 0

    @property
    def is_stopping(self) -> bool:
        return self._stop_requested

    @property
    def is_running(self) -> bool:
        return self.runner.is_running

    @property
    def current_pid(self) -> int | None:
        return self.runner.pid

    async def request_stop_async(self) -> None:
        """Set the stop flag AND terminate any subprocess the runner is
        currently supervising. Without killing the subprocess, the
        generator would block waiting for the next stdout line, which
        can take minutes if the download is paused / rate-limited."""
        self._stop_requested = True
        await self.runner.stop(grace_seconds=2.0)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "new_files": self._new_files_count,
            "total_processed": self._total_processed,
            "limit_signals": self.guard.limit_signals,
        }

    def request_stop(self) -> None:
        self._stop_requested = True

    # ------------------------------------------------------------------
    # Public job methods — each corresponds to a button in the original GUI
    # ------------------------------------------------------------------

    async def download(
        self,
        target: str,
        cookie_files: list[str] | None = None,
        content_type: str | None = None,
        author: str | None = None,
        run_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """JobRunner entry point — download one URL / username.

        `content_type` is the per-row tag set when the Download was created:
          - "post"      → grab timeline posts (Layer 1)
          - "story"     → grab active 24h stories (Layer 2)
          - "highlight" → grab highlights (Layer 3)
          - None        → legacy callers, treat as posts

        `author` is the username the row was created against (for highlight
        rows the user gave us at /from-highlight-ids time). It is only used
        by the highlight branch to pick a destination folder; the other
        branches ignore it and keep deriving the folder from the URL.

        Yields events: user_start, media, warn, error, user_done.
        """
        layer = (content_type or "post").lower()
        if layer == "story":
            async for event in self.add_stories(target, cookie_files or []):
                yield event
            return
        if layer == "highlight":
            async for event in self.add_highlights(target, cookie_files or [], author=author):
                yield event
            return
        # default → posts
        async for event in self.add_new(target, cookie_files or [], disable_range=True):
            yield event

    async def add_new(
        self,
        target: str,
        cookie_files: list[str],
        *,
        disable_range: bool = True,
    ) -> AsyncIterator[dict]:
        """Download a single new account or single post (Layer 1)."""
        normalized = self._normalize_target(target)
        dest_name = self._derive_dest_name(normalized)
        dest = self._resolve_dest(dest_name)

        os.makedirs(dest, exist_ok=True)
        is_post = self._is_single_post(normalized)
        limit_range = None if (disable_range or not is_post) else "1-4"

        async for event in self._download_with_fallback(
            normalized, dest, cookie_files,
            limit_range=limit_range, disable_range=disable_range, prefix="",
        ):
            yield event

    async def add_stories(
        self,
        target: str,
        cookie_files: list[str],
    ) -> AsyncIterator[dict]:
        """Download only the active 24h stories of a user (Layer 2).

        Writes under <base>/<user>/STORY_* so the file tree is self-documenting.
        """
        normalized = self._normalize_target(target)
        username = self._derive_dest_name(normalized)
        dest = self._resolve_dest(username)
        os.makedirs(dest, exist_ok=True)
        stories_url = f"https://www.instagram.com/stories/{username}/"

        async for event in self._download_with_fallback(
            stories_url, dest, cookie_files,
            limit_range=None, disable_range=True, prefix="STORY_",
        ):
            yield event

    async def add_highlights(
        self,
        target: str,
        cookie_files: list[str],
        author: str | None = None,
    ) -> AsyncIterator[dict]:
        """Download all highlights of a user (Layer 3).

        Writes under <base>/<user>/HL_* so the file tree is self-documenting.

        Supports two URL shapes:
          - https://www.instagram.com/<user>/highlights/  (broken: IG API
            now requires follow + browser; kept for fallback)
          - https://www.instagram.com/stories/highlights/<id>/  (works:
            a single known highlight reel ID)

        For the second shape, the URL itself has no username — we either use
        the `author` the caller passes (the user that was attached to the
        row when the highlight IDs were imported) or fall back to the reel
        id so files still go somewhere instead of leaking into the base.
        """
        # If target is a direct /stories/highlights/<id> URL, use it as-is.
        if "/stories/highlights/" in target:
            normalized = self._normalize_target(target)
            parts = [p for p in normalized.rstrip("/").split("/") if p]
            # parts = ["stories", "highlights", "<id>"]
            reel_id = parts[-1] if parts else "highlight"
            # Prefer the username the row was created against; otherwise
            # the reel id (better than dumping files at the base).
            folder_name = (author or "").lstrip("@").strip() or reel_id
            dest = self._resolve_dest(folder_name)
            os.makedirs(dest, exist_ok=True)
            url = target.split("?")[0].split("#")[0]
            if not url.endswith("/"):
                url = url + "/"
            async for event in self._download_with_fallback(
                url, dest, cookie_files,
                limit_range=None, disable_range=True, prefix="HL_",
            ):
                yield event
            return

        normalized = self._normalize_target(target)
        username = self._derive_dest_name(normalized)
        dest = self._resolve_dest(username)
        os.makedirs(dest, exist_ok=True)
        hl_url = f"https://www.instagram.com/{username}/highlights/"

        async for event in self._download_with_fallback(
            hl_url, dest, cookie_files,
            limit_range=None, disable_range=True, prefix="HL_",
        ):
            yield event

    async def update_list(
        self,
        users: list[str],
        cookie_files: list[str],
        *,
        disable_range: bool = True,
        include_posts: bool = True,
        include_stories: bool = True,
        include_highlights: bool = False,
        is_already_done: Callable[[str], bool] | None = None,
    ) -> AsyncIterator[dict]:
        """Update an explicit list of accounts (from .txt file).

        When the UI selects individual layers (post / story / highlight) this
        method runs only the selected layer per user, instead of always
        running all 3.
        """
        for index, user in enumerate(users, start=1):
            if self._stop_requested:
                break
            if is_already_done and is_already_done(user):
                yield {"type": "skip", "user": user, "reason": "cached"}
                continue

            yield {"type": "user_start", "user": user, "index": index, "total": len(users)}
            normalized = self._normalize_target(user)
            dest = self._resolve_dest(self._derive_dest_name(normalized))
            os.makedirs(dest, exist_ok=True)

            if include_posts:
                await self._run_layered_sync(
                    target=normalized,
                    dest=dest,
                    cookie_files=cookie_files,
                    disable_range=disable_range,
                    include_posts=True,
                    include_stories=False,
                    include_highlights=False,
                    event_callback=lambda e: self._reemit(e, user=user),
                )
            if include_stories and not self._stop_requested:
                stories_url = f"https://www.instagram.com/stories/{self._derive_dest_name(normalized)}/"
                await self._run_one(
                    stories_url, dest, cookie_files, disable_range=True, prefix="STORY_",
                )
            if include_highlights and not self._stop_requested:
                hl_url = f"{normalized.rstrip('/')}/highlights/"
                await self._run_one(
                    hl_url, dest, cookie_files, disable_range=True, prefix="HL_",
                )

            if not self._stop_requested:
                yield {"type": "user_done", "user": user}
                await self.guard.wait_after_account(stop_requested=lambda: self._stop_requested)

    async def _run_one(
        self,
        url: str,
        dest: str,
        cookie_files: list[str],
        *,
        disable_range: bool,
        prefix: str,
    ) -> None:
        """Sync wrapper: drain a single _download_with_fallback generator
        so callers don't have to nest async-for. Used by update_list when the
        user pre-selected only a single layer (story/highlight)."""
        async for _ in self._download_with_fallback(
            url, dest, cookie_files,
            limit_range=None, disable_range=disable_range, prefix=prefix,
        ):
            if self._stop_requested:
                return

    async def update_all_local(
        self,
        subfolders: list[str],
        cookie_files: list[str],
        *,
        is_already_done: Callable[[str], bool] | None = None,
    ) -> AsyncIterator[dict]:
        """Update every subfolder found under the download root."""
        for index, folder in enumerate(subfolders, start=1):
            if self._stop_requested:
                break
            if is_already_done and is_already_done(folder):
                yield {"type": "skip", "user": folder, "reason": "cached"}
                continue

            username = folder.lstrip("@")
            dest = self._resolve_dest(folder)
            yield {"type": "user_start", "user": username, "index": index, "total": len(subfolders)}

            try:
                async for event in self._download_with_fallback(
                    f"https://www.instagram.com/{username}/",
                    dest, cookie_files,
                    limit_range=None, disable_range=True, prefix="",
                ):
                    yield event
                if not self._stop_requested:
                    async for event in self._download_with_fallback(
                        f"https://www.instagram.com/stories/{username}/",
                        dest, cookie_files,
                        limit_range=None, disable_range=True, prefix="STORY_",
                    ):
                        yield event
                if not self._stop_requested:
                    async for event in self._download_with_fallback(
                        f"https://www.instagram.com/{username}/highlights",
                        dest, cookie_files,
                        limit_range=None, disable_range=True, prefix="HL_",
                    ):
                        yield event
            except Exception:
                logger.exception("Error processing %s", username)
                yield {"type": "error", "user": username}

            if not self._stop_requested:
                yield {"type": "user_done", "user": username}
                await self.guard.wait_after_account(stop_requested=lambda: self._stop_requested)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_layered_sync(
        self,
        *,
        target: str,
        dest: str,
        cookie_files: list[str],
        disable_range: bool,
        include_posts: bool,
        include_stories: bool,
        include_highlights: bool,
        event_callback: Callable[[dict], None] | None = None,
    ) -> None:
        is_post = self._is_single_post(target)

        if include_posts:
            logger.info("Layer 1: posts (timeline feed)")
            async for event in self._download_with_fallback(
                target, dest, cookie_files,
                limit_range=None, disable_range=disable_range, prefix="",
            ):
                if event_callback:
                    event_callback(event)
                if self._stop_requested:
                    return

        if self._stop_requested or is_post:
            return

        if include_stories:
            logger.info("Layer 2: stories (24h)")
            stories_url = self._stories_url(target)
            async for event in self._download_with_fallback(
                stories_url, dest, cookie_files,
                limit_range=None, disable_range=True, prefix="STORY_",
            ):
                if event_callback:
                    event_callback(event)
                if self._stop_requested:
                    return

        if self._stop_requested:
            return

        if include_highlights:
            logger.info("Layer 3: highlights")
            hl_url = f"{target.rstrip('/')}/highlights/"
            async for event in self._download_with_fallback(
                hl_url, dest, cookie_files,
                limit_range=None, disable_range=True, prefix="HL_",
            ):
                if event_callback:
                    event_callback(event)
                if self._stop_requested:
                    return

    async def _reemit(self, event: dict, *, user: str) -> None:
        """Forward an event tagged with the user — no-op placeholder if
        caller wants a no-yield sync variant."""
        # The async generator in update_list handles forwarding inline;
        # this exists so _run_layered_sync can be used sync-style if needed.
        return None

    async def _download_with_fallback(
        self,
        url: str,
        dest: str,
        cookie_files: list[str],
        *,
        limit_range: str | None,
        disable_range: bool,
        prefix: str = "",
    ) -> AsyncIterator[dict]:
        if not cookie_files:
            if self.cookies_required:
                yield {"type": "error", "message": "No cookie files configured"}
                return
            cookie_files = [None]  # type: ignore[list-item]

        for index, cookie_path in enumerate(cookie_files, start=1):
            saw_limit = False
            async for event in self._execute_one(
                url, dest, cookie_path,
                limit_range=limit_range,
                disable_range=disable_range,
                prefix=prefix,
            ):
                if event.get("type") == "limit_signal":
                    saw_limit = True
                    # FIX C5: Abort fallback to next cookie IMMEDIATELY;
                    # do not yield further media events from the throttled cookie.
                    break
                yield event
                if self._stop_requested:
                    return

            if not saw_limit:
                return
            if index < len(cookie_files) and not self._stop_requested:
                logger.warning("Cookie #%s hit a rate limit; trying backup cookie...", index)
                await self.guard.wait_after_limit_signal(stop_requested=lambda: self._stop_requested)

    async def _execute_one(
        self,
        url: str,
        dest: str,
        cookie_file: str | None,
        *,
        limit_range: str | None,
        disable_range: bool,
        prefix: str,
    ) -> AsyncIterator[dict]:
        temp_cookie = None
        actual_cookie = cookie_file
        if cookie_file and Path(cookie_file).exists():
            try:
                # Cookie files on disk are Fernet-encrypted at rest (see
                # `core.cookie_vault.encrypt_cookie`). gallery-dl needs the
                # plaintext Netscape file, so decrypt into a temp file the
                # process owns; the OS will reap it on exit.
                from app.core.cookie_vault import decrypt_cookie_file
                temp_cookie = decrypt_cookie_file(Path(cookie_file))
                actual_cookie = temp_cookie
            except Exception:
                logger.warning("Could not stage decrypted temp cookie; using original", exc_info=True)
                temp_cookie = None

        try:
            cmd = self._build_command(url, dest, actual_cookie, limit_range, disable_range, prefix)
            await self.runner.start(cmd)
            saw_meaningful_output = False
            saw_media = False

            async for line in self.runner.stream_output():
                if self._stop_requested:
                    break
                stripped = line.strip()
                lower = stripped.lower()
                if not stripped:
                    continue

                # gallery-dl progress lines stay in stdout (root logger
                # handler) but never reach the UI terminal.

                if self.guard.detect_limit_signal(stripped):
                    yield {"type": "limit_signal", "line": stripped}
                    return

                if "http redirect to home page" in lower or "login required" in lower:
                    yield {"type": "warn", "code": "cookie_rejected", "line": stripped}
                    continue

                if any(t in lower for t in ("time out", "timeout", "connection reset", "network unreachable", "10054")):
                    yield {"type": "warn", "code": "network", "line": stripped}
                    continue

                # TikTok 403 / Forbidden: gallery-dl prints this when the
                # public CDN rejects the IP. Check BEFORE the generic
                # engine_error branch so the more specific code wins.
                if "403" in stripped or "forbidden" in lower:
                    yield {"type": "warn", "code": "forbidden", "line": stripped}
                    continue

                if any(t in lower for t in ("[error]", "error:", "exception", "failed", "404 not found", "permission")):
                    yield {"type": "warn", "code": "engine_error", "line": stripped}
                    continue

                if not any(ext in lower for ext in IMAGE_EXTENSIONS):
                    continue

                saw_media = True
                self._total_processed += 1
                is_new = not stripped.startswith("#")
                clean_path = stripped.lstrip("#").strip()
                filename = os.path.basename(clean_path)
                # Some gallery-dl extractors (notably TikTok when the
                # response is rate-limited) emit a file path whose filename
                # starts with "None_" because the {id} field was unavailable.
                # Treat those as failures: they are zero-byte placeholder
                # files and would otherwise count as a successful download.
                if filename.startswith("None_") or filename.lower() == "none":
                    logger.warning("Discarding empty/None-named file from gallery-dl: %s", filename)
                    saw_media = False
                    self._total_processed -= 1
                    yield {"type": "warn", "code": "empty_file", "line": filename}
                    continue

                marker = "[NEW]" if is_new else "[SKIP]"
                logger.info("%s %s", marker, filename)
                if is_new:
                    self._new_files_count += 1
                yield {
                    "type": "media",
                    "new": is_new,
                    "path": clean_path,
                    "filename": filename,
                }

            rc = await self.runner.wait()
            if rc not in (0, None):
                yield {"type": "warn", "code": "non_zero_exit", "code_value": rc}
            if not saw_media and not saw_meaningful_output and not self._stop_requested:
                yield {"type": "warn", "code": "no_output", "line": ""}
        finally:
            if temp_cookie and os.path.exists(temp_cookie):
                try:
                    os.remove(temp_cookie)
                except OSError:
                    pass

    def _build_command(
        self,
        url: str,
        destination: str,
        cookie_file: str,
        limit_range: str | None,
        disable_range: bool,
        prefix: str,
    ) -> list[str]:
        dest_path = Path(destination).expanduser()
        filename_template = f"{prefix}{self.filename_template}"

        cmd: list[str] = [
            *resolve_gallery_dl_executable(),
            url,
            "--destination", str(dest_path),
            "--sleep-request", self.tuning.sleep_request,
            "--sleep", self.tuning.sleep,
            "--retries", str(self.tuning.retries),
            "--http-timeout", str(self.tuning.request_timeout),
            "-o", "cache.file=none",
            "-o", 'directory=["."]',
            "-o", f"filename={filename_template}",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        ]
        if cookie_file and os.path.exists(cookie_file):
            cmd.extend(["--cookies", os.path.normpath(cookie_file)])

        archive = dest_path / self.archive_name
        cmd.extend(["--download-archive", str(archive), "--abort", "20"])

        if limit_range and not disable_range:
            cmd.extend(["--range", limit_range])
        return cmd

    def _normalize_target(self, target: str) -> str:
        cleaned = target.strip()
        for prefix in ("https://www.instagram.com/", "https://instagram.com/"):
            cleaned = cleaned.replace(prefix, "")
        cleaned = cleaned.split("?")[0].split("#")[0].strip("/")
        if cleaned.startswith(("http://", "https://")):
            return cleaned.rstrip("/") + "/"
        return f"https://www.instagram.com/{cleaned}/"

    def _is_single_post(self, target: str) -> bool:
        path = target.replace("https://www.instagram.com/", "").replace("https://instagram.com/", "").strip("/")
        return path.startswith(("p/", "reel/", "reels/", "tv/")) or any(
            m in path for m in ("/p/", "/reel/", "/reels/", "/tv/")
        )

    def _derive_dest_name(self, target: str) -> str:
        parts = [p for p in target.rstrip("/").split("/") if p]
        if not parts:
            return "instagram"
        if parts[-1] in {"stories", "highlights"} and len(parts) >= 2:
            return parts[-2]
        if len(parts) >= 2 and parts[-2] == "stories":
            return parts[-1]
        return parts[-1]

    def _stories_url(self, target: str) -> str:
        username = self._derive_dest_name(self._normalize_target(target))
        return f"https://www.instagram.com/stories/{username}/"

    def _resolve_dest(self, name: str) -> str:
        from app.config import get_settings
        base = get_settings().get_download_folder()
        return str(base / name)
