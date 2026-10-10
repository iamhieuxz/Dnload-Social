"""
TikTok service — runs gallery-dl and parses output.

Reuses InstagramService's gallery-dl pipeline (same runner, archive, sleep
tuning, output parsing) and only changes three things:
  - URL shapes   : tiktok.com/@user  (profile) | /@user/video/123 (one post)
                   | vm.tiktok.com/XXXXXX (short share link)
  - destination  : E:\\gallery-dl\\tiktok\\<username>\\
  - no cookies   : TikTok public profiles / posts work logged-out

A profile URL downloads the whole video feed; a post URL downloads just that
video. Both land in the same per-user folder, so the tree is:
    E:/gallery-dl/tiktok/<username>/<videos>
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

from app.services.instagram import InstagramService

logger = logging.getLogger(__name__)


class TikTokService(InstagramService):
    archive_name = ".tiktok_download_archive.sqlite"
    cookies_required = False
    # TikTok items have no shortcode/num — {id} is the video ID and {date}
    # keeps files in the same shape as the other platforms.
    filename_template = "{date:%Y-%m-%d}_{id}.{extension}"

    async def download(
        self,
        target: str,
        cookie_files: list[str] | None = None,
        content_type: str | None = None,
    ) -> AsyncIterator[dict]:
        """Download one TikTok target.

        content_type is accepted for signature parity with the other services
        but TikTok has a single kind of media (video), so it is ignored —
        the URL shape decides whether we grab one post or the whole profile.
        """
        normalized = self._normalize_target(target)
        username = self._derive_dest_name(normalized)
        dest = self._resolve_dest(username)
        os.makedirs(dest, exist_ok=True)

        yield {"type": "user_start", "user": username, "index": 1, "total": 1}
        async for event in self._download_with_fallback(
            normalized, dest, cookie_files or [],
            limit_range=None, disable_range=True, prefix="",
        ):
            yield event
        yield {"type": "user_done", "user": username}

    # ------------------------------------------------------------------
    # TikTok-specific URL handling (overrides the Instagram versions)
    # ------------------------------------------------------------------

    def _normalize_target(self, target: str) -> str:
        cleaned = target.strip().split("?")[0].split("#")[0].rstrip("/")
        lowered = cleaned.lower()

        # vm.tiktok.com short links (with or without scheme) — pass through,
        # the gallery-dl VmpostExtractor follows the redirect itself.
        if re.match(r"^(?:https?://)?(?:vm|vt)\.tiktok\.com/", cleaned, re.IGNORECASE):
            return cleaned if cleaned.lower().startswith("http") else "https://" + cleaned
        # Any other absolute URL: only strip the host prefix, never a path one.
        for prefix in (
            "https://www.tiktok.com/", "http://www.tiktok.com/",
            "https://m.tiktok.com/", "http://m.tiktok.com/",
            "https://tiktok.com/", "http://tiktok.com/",
        ):
            if lowered.startswith(prefix):
                return "https://www.tiktok.com/" + cleaned[len(prefix):]
        # Bare host or bare @user — gallery-dl's USER_PATTERN needs the "@".
        cleaned = re.sub(r"^(?:https?://)?(?:www\.|m\.)?tiktok\.com/", "", cleaned, flags=re.IGNORECASE)
        if cleaned.startswith(("http://", "https://")):
            return cleaned
        cleaned = cleaned.lstrip("/")
        # gallery-dl's USER_PATTERN requires the "@" prefix; restore it when
        # the user typed a bare username.
        if cleaned and not cleaned.startswith("@"):
            cleaned = "@" + cleaned
        return f"https://www.tiktok.com/{cleaned}"

    def _derive_dest_name(self, target: str) -> str:
        """Folder name = the @username, for both profile and post URLs.

        `vm.tiktok.com/<code>` has no username until the redirect resolves, so
        fall back to the short code — the real username is not worth a second
        HEAD request for a folder name.
        """
        cleaned = target.strip().rstrip("/")
        m = re.search(r"tiktok\.com/@([\w_.-]+)", cleaned, re.IGNORECASE)
        if m:
            return m.group(1)
        vm = re.search(r"vm\.tiktok\.com/([\w-]+)", cleaned, re.IGNORECASE)
        if vm:
            return vm.group(1)
        path = cleaned.replace("https://", "").replace("http://", "").strip("/")
        return path.split("/")[0] or "tiktok"

    def _resolve_dest(self, name: str) -> str:
        from app.config import get_settings
        base = get_settings().get_tiktok_download_folder()
        return str(base / name)