"""
Job runner — reads from the `downloads` table and dispatches each row to
the correct platform service (InstagramService / TwitterService).

Pipeline:
  1. /api/downloads/batch  → creates Download rows (status=pending)
  2. /api/downloads/run-pending?platform=... → marks them status=downloading
                                               and triggers a Job
  3. JobRunner picks the Job up, fetches all status=downloading rows
     for the platform, runs each URL through the right service, and
     updates the row to status=completed/failed with file_path + size.

One job = one platform. Serialised by an asyncio lock so only one runs
at a time. The job finishes when all rows it claimed are done.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import WebSocketLogHandler, clear_job_logs
from app.core.websocket_manager import ws_manager
from app.database import session_scope
from app.models import (
    Account,
    Download,
    DownloadStatus,
    Job,
    JobStatus,
    Platform,
    SourceType,
)
from app.services.instagram import InstagramService
from app.services.tiktok import TikTokService
from app.services.twitter import TwitterService

logger = logging.getLogger(__name__)


class JobRunner:
    """Holds one service instance per platform for the currently running job.

    Keyed by the Platform value string so adding a platform is a one-line
    change here instead of another parallel `_current_xx` attribute.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._services: dict[str, InstagramService | TwitterService | TikTokService] = {}
        self._current_job_id: int | None = None

    @property
    def is_busy(self) -> bool:
        return self._lock.locked()

    @property
    def current_job_id(self) -> int | None:
        return self._current_job_id

    async def request_stop(self) -> None:
        """Signal the running services to stop and tear down the
        subprocess they're supervising so the generator unblocks.

        Every service exposes both `request_stop` (a sync flag setter) and
        `request_stop_async` (which also kills the subprocess). We use the
        async variant because without killing the subprocess, the runner can
        stay parked for minutes waiting on the next stdout line (especially
        when the download is in a long sleep / rate-limit cooldown)."""
        for name, svc in self._services.items():
            try:
                await svc.request_stop_async()
            except Exception:
                logger.exception("Error stopping %s service", name)
            else:
                # Keep the legacy sync flag in case any code path still
                # checks it (it does — there are several guard checks in
                # the service layer that look at `_stop_requested`).
                svc.request_stop()

    async def enqueue(self, job_id: int) -> None:
        """Run the job in the background.

        Before handing off to _run, sweep any stale `downloading` rows that
        might be left over from a previous run (e.g. the app crashed mid-
        download, or a stop was requested but the process was killed before
        the finally-block could fire). We re-stamp them as `pending` so
        the run-pending flow can re-pick them up on the next attempt.
        """
        from sqlalchemy import update as _update
        async with session_scope() as session:
            stale = _update(Download).where(
                Download.status == DownloadStatus.DOWNLOADING,
            ).values(status=DownloadStatus.PENDING)
            result = await session.execute(stale)
            if result.rowcount:
                logger.info(
                    "Startup sweep: reset %s stale `downloading` rows to `pending`",
                    result.rowcount,
                )
        asyncio.create_task(self._run(job_id))

    async def _run(self, job_id: int) -> None:
        logger.info("[JOB %s] _run called, lock.locked=%s", job_id, self._lock.locked())
        if self._lock.locked():
            logger.warning("Another job is already running, skipping enqueue of %s", job_id)
            # Mark the orphaned job as STOPPED so the UI doesn't show a
            # "queued" zombie forever. We can't actually run it because
            # the lock is held by a previous, still-running job.
            await self._orphan_job(job_id)
            return
        logger.info("[JOB %s] entering lock", job_id)

        async with self._lock:
            self._current_job_id = job_id
            try:
                await self._execute(job_id)
            finally:
                self._current_job_id = None
                self._services = {}
                clear_job_logs(job_id)

    async def _orphan_job(self, job_id: int) -> None:
        """Mark a job that could not start as STOPPED + detach any
        downloads still pointing at it. Used when enqueue is rejected
        because another job is currently running."""
        from sqlalchemy import update as _update
        try:
            async with session_scope() as session:
                job = await session.get(Job, job_id)
                if job is None:
                    return
                if job.status not in (JobStatus.QUEUED,):
                    return
                job.status = JobStatus.STOPPED
                job.finished_at = datetime.utcnow()
                job.error_message = "Another job was already running"
                # Release any rows we already attached to this job so the
                # next run-pending can re-pick them up.
                await session.execute(
                    _update(Download)
                    .where(Download.job_id == job_id,
                           Download.status == DownloadStatus.DOWNLOADING)
                    .values(status=DownloadStatus.PENDING, job_id=None)
                )
                await session.execute(
                    _update(Download)
                    .where(Download.job_id == job_id,
                           Download.status == DownloadStatus.PENDING)
                    .values(job_id=None)
                )
                await _emit_status(job_id, JobStatus.STOPPED,
                                   extra={"reason": "busy"})
                logger.info("Orphaned job %s marked as STOPPED", job_id)
        except Exception:
            logger.exception("Failed to orphan job %s", job_id)

    async def _execute(self, job_id: int) -> None:
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                logger.error("Job %s not found", job_id)
                return

            # Look at the linked Download row to determine the platform
            # (the job was created with a single platform target).
            stmt = select(Download).where(
                Download.job_id == job_id,
                Download.status.in_(
                    [DownloadStatus.DOWNLOADING, DownloadStatus.PENDING]
                ),
            )
            downloads = list((await session.execute(stmt)).scalars().all())

            if not downloads:
                # fallback: look at job's own platform via the most recent downloads it owns
                logger.warning("Job %s has no linked downloads; completing", job_id)
                job.status = JobStatus.COMPLETED
                job.finished_at = datetime.utcnow()
                await _emit_status(job_id, JobStatus.COMPLETED, extra={"processed": 0})
                return

            platform: Platform = Platform(downloads[0].platform)
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            await session.flush()
            # Commit immediately so the UI sees the job as RUNNING
            # without waiting for the whole loop to finish.
            await session.commit()
            await _emit_status(job_id, JobStatus.RUNNING, extra={"platform": platform.value, "total": len(downloads)})

            cookies = await _load_cookie_paths(session)
            services: dict = {
                Platform.INSTAGRAM.value: InstagramService(),
                Platform.TWITTER.value: TwitterService(),
                Platform.TIKTOK.value: TikTokService(),
            }
            self._services = services

            ws_handler = WebSocketLogHandler(job_id)
            ws_handler.setFormatter(logging.Formatter("%(message)s"))
            root = logging.getLogger()
            root.addHandler(ws_handler)

            try:
                processed = 0
                failed = 0
                for d in downloads:
                    if any(s.is_stopping for s in services.values()):
                        break
                    ok = await self._process_one(session, d, services, cookies)
                    if ok:
                        processed += 1
                    else:
                        failed += 1
                job.new_files_count = processed
                job.total_processed = processed + failed
            except Exception as e:
                logger.exception("Job %s failed", job_id)
                job.status = JobStatus.FAILED
                job.error_message = str(e)
            else:
                if any(s.is_stopping for s in services.values()):
                    job.status = JobStatus.STOPPED
                else:
                    job.status = JobStatus.COMPLETED
            finally:
                # "Perfect stop" — any rows that were marked `downloading`
                # when we exited (because the user pressed Stop) are
                # reverted to `pending` so the next run-pending call will
                # pick them up again. The instagram/tiktok services use
                # the gallery-dl --download-archive sqlite, so the actual
                # file download work is idempotent and safe to re-run.
                if any(s.is_stopping for s in services.values()):
                    from sqlalchemy import update as _update
                    reset_stmt = _update(Download).where(
                        Download.job_id == job_id,
                        Download.status == DownloadStatus.DOWNLOADING,
                    ).values(status=DownloadStatus.PENDING)
                    reset_result = await session.execute(reset_stmt)
                    if reset_result.rowcount:
                        logger.info(
                            "Job %s stopped — reset %s in-progress downloads back to pending",
                            job_id, reset_result.rowcount,
                        )
                        await session.flush()

                job.finished_at = datetime.utcnow()
                root.removeHandler(ws_handler)
                await _emit_status(
                    job_id, job.status,
                    extra={
                        "platform": platform.value,
                        "processed": job.total_processed,
                        "new_files": job.new_files_count,
                    },
                )

    async def _process_one(
        self,
        session: AsyncSession,
        d: Download,
        services: dict,
        cookies: dict[str, list[str]],
    ) -> bool:
        """Process a single Download row. Returns True on success."""
        try:
            logger.info(
                "Download #%s [%s] %s",
                d.id, d.platform, d.url,
            )
            d.status = DownloadStatus.DOWNLOADING
            await session.flush()
            await session.commit()  # make this status visible to the UI
            await ws_manager.broadcast(
                "system", "download_update",
                {"id": d.id, "status": d.status.value},
            )
            from app.core.logging_config import record_event
            record_event("download_update", {"id": d.id, "status": d.status.value})

            service = services[d.platform]
            target = self._build_target(d)
            # Pick the right cookie set for this platform (IG and X cookies
            # are stored in separate folders and have different formats).
            platform_cookies = cookies.get(d.platform, []) or []

            # If source is a database account, use that account's folder
            if d.source_type == SourceType.DATABASE and d.account_id:
                acc = await session.get(Account, d.account_id)
                if acc:
                    target = f"https://{_PLATFORM_HOST.get(d.platform, d.platform)}/{acc.username}/"

            events: list[dict] = []
            # Wrap with a watchdog: if no event for >90s AND the underlying
            # process has exited, finish up with whatever files we have.
            IDLE_TIMEOUT = 90.0
            last_event_at = asyncio.get_event_loop().time()
            gen = service.download(target, cookie_files=platform_cookies, content_type=d.content_type)
            while True:
                if any(s.is_stopping for s in services.values()):
                    break
                try:
                    ev = await asyncio.wait_for(gen.__anext__(), timeout=IDLE_TIMEOUT)
                    last_event_at = asyncio.get_event_loop().time()
                except (StopAsyncIteration, asyncio.TimeoutError) as e:
                    if isinstance(e, asyncio.TimeoutError):
                        runner_obj = service.runner
                        if runner_obj.is_running:
                            logger.info(
                                "Download #%s still running after %ss idle; continuing to wait",
                                d.id, IDLE_TIMEOUT,
                            )
                            continue
                        logger.info("Download #%s idle for %ss, runner exited, finishing", d.id, IDLE_TIMEOUT)
                    else:
                        logger.info("Download #%s generator finished (%s events)", d.id, len(events))
                    break
                events.append(ev)
                if ev.get("type") == "user_start":
                    logger.info("--> @%s", ev.get("user"))
                elif ev.get("type") == "media":
                    if d.file_path is None:
                        d.file_path = ev.get("path")
                        d.file_name = ev.get("filename")
                elif ev.get("type") == "user_done":
                    logger.info("done @%s", ev.get("user"))
                elif ev.get("type") == "error":
                    logger.warning("Error for #%s: %s", d.id, ev.get("message"))
                    d.error_message = ev.get("message")
                    break
                elif ev.get("type") == "warn":
                    logger.info("    warn: %s - %s", ev.get("code"), ev.get("line", "")[:120])

            # Pick the actual file from disk (gallery-dl/yt-dlp write to disk,
            # we just need to record where the file lives).
            file_path, file_size = self._find_output_file(d, events)
            if file_path:
                d.file_path = file_path
                d.file_name = os.path.basename(file_path)
                d.file_size_bytes = file_size
            else:
                # No file produced. If we have an error message, propagate
                # it; otherwise mark as failed with a generic explanation.
                if not d.error_message:
                    d.error_message = (
                        f"No output file found for {d.platform} URL "
                        f"(events={len(events)})"
                    )
                d.status = DownloadStatus.FAILED
                await session.flush()
                await session.commit()
                await ws_manager.broadcast(
                    "system", "download_update",
                    {"id": d.id, "status": d.status.value, "error": d.error_message},
                )
                return False

            d.status = DownloadStatus.COMPLETED
            d.completed_at = datetime.utcnow()
            await session.flush()
            await session.commit()
            await ws_manager.broadcast("system", "download_update",
                {"id": d.id, "status": d.status.value, "file_path": d.file_path})
            from app.core.logging_config import record_event
            record_event("download_update", {"id": d.id, "status": d.status.value, "file_path": d.file_path})
            return True

        except Exception as e:
            logger.exception("Download #%s crashed", d.id)
            d.status = DownloadStatus.FAILED
            d.error_message = str(e)
            await session.flush()
            try:
                await session.commit()
            except Exception:
                logger.exception("Failed to commit crash state for #%s", d.id)
            await ws_manager.broadcast("system", "download_update",
                {"id": d.id, "status": d.status.value, "error": str(e)})
            from app.core.logging_config import record_event
            record_event("download_update", {"id": d.id, "status": d.status.value, "error": str(e)})
            return False

    def _build_target(self, d: Download) -> str:
        """Convert a Download row into a URL the service can consume."""
        url = d.url.strip()
        if d.platform == Platform.TWITTER:
            # normalize to twitter.com
            for prefix in ("https://x.com/", "https://www.x.com/", "https://www.twitter.com/"):
                if url.startswith(prefix):
                    url = "https://twitter.com/" + url[len(prefix):]
                    break
        return url

    def _find_output_file(self, d: Download, events: list[dict]) -> tuple[str | None, int]:
        """Look on disk for the newest file under the expected output folder.

        Returns (path, size) or (None, 0).

        Strategy (in order of trust):
          1. Use the explicit path that came through a `media` event.
          2. Look in <base>/<author>/ (author inferred from URL).
          3. Last resort: scan <base> but only for files created AFTER the
             job started, so we don't pick up old files from previous jobs.
        """
        from app.config import get_settings

        base = {
            Platform.INSTAGRAM.value: get_settings().get_download_folder,
            Platform.TWITTER.value: get_settings().get_twitter_download_folder,
            Platform.TIKTOK.value: get_settings().get_tiktok_download_folder,
        }[d.platform]()

        # Try the explicit event-supplied path first
        for ev in events:
            if ev.get("type") == "media" and ev.get("path"):
                p = Path(ev["path"])
                if p.exists():
                    return str(p), p.stat().st_size
                # Try resolving relative to base
                if not p.is_absolute():
                    p2 = base / p
                    if p2.exists():
                        return str(p2), p2.stat().st_size

        # Fallback 1: scan the user's folder for the most recently modified file
        # younger than 5 minutes (so we don't pick up old files from the gallery).
        # Instagram posts are /p/<code> (no author in the path); X and TikTok
        # both put the author three segments up (/user/status/1, /@user/video/1).
        seg = 2 if d.platform == Platform.INSTAGRAM.value else 3
        author = (d.author or d.url.split("/")[-seg]).lstrip("@").strip()
        if author:
            user_dir = base / author
            if user_dir.exists():
                newest = self._newest_file(user_dir, max_age_seconds=600)
                if newest:
                    return str(newest), newest.stat().st_size

        # Fallback 2: last-resort scan of the entire base folder. Only used
        # when the service emitted at least one event (so we know it actually
        # ran) but the file wasn't found in the author folder either. This
        # happens when the URL is a post (no clean author) and gallery-dl
        # wrote a file but didn't yield a `media` event we could capture.
        # We restrict to a 2-minute window so old files from prior jobs
        # can't be picked up by mistake.
        if events:
            newest = self._newest_file(base, max_age_seconds=120)
            if newest:
                return str(newest), newest.stat().st_size

        return None, 0

    def _newest_file(self, folder: Path, max_age_seconds: int) -> Path | None:
        from time import time
        cutoff = time() - max_age_seconds
        best: tuple[float, Path] | None = None
        try:
            for p in folder.rglob("*"):
                if not p.is_file():
                    continue
                if p.name.startswith("."):
                    continue
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                if mtime < cutoff:
                    continue
                if best is None or mtime > best[0]:
                    best = (mtime, p)
        except OSError:
            return None
        return best[1] if best else None


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

# Host used when rebuilding a profile URL from a database account.
_PLATFORM_HOST = {
    Platform.INSTAGRAM.value: "instagram.com",
    Platform.TWITTER.value: "twitter.com",
    Platform.TIKTOK.value: "www.tiktok.com",
}


async def _load_cookie_paths(session: AsyncSession) -> dict[str, list[str]]:
    """Return cookie file paths per platform.

    Why a dict instead of a flat list:
      - IG and X have different cookie formats, so we must not mix them
      - The JobRunner now passes the right list to each service
      - TikTok needs none (public data), so its entry is empty and
        TikTokService.cookies_required = False lets it run cookie-less
    """
    from app.config import get_settings
    settings = get_settings()
    cookie_dir = settings.get_cookie_folder()

    ig_paths: list[str] = []
    if cookie_dir.exists():
        for name in ("cookie1.txt", "cookie2.txt"):
            p = cookie_dir / name
            if p.exists():
                ig_paths.append(str(p))

    tw_paths: list[str] = []
    tw_dir = cookie_dir / "twitter"
    if tw_dir.exists():
        for name in ("tw_cookie1.txt", "tw_cookie2.txt"):
            p = tw_dir / name
            if p.exists():
                tw_paths.append(str(p))

    return {"instagram": ig_paths, "twitter": tw_paths, "tiktok": []}


async def _emit_status(job_id: int, status: JobStatus, extra: dict | None = None) -> None:
    payload = {"status": status.value}
    if extra:
        payload.update(extra)
    await ws_manager.broadcast(f"job:{job_id}", "status", payload)
    await ws_manager.broadcast("system", "job_update", {"job_id": job_id, **payload})
    # Also append to the system-wide polling buffer for HTTP-only clients
    from app.core.logging_config import record_event
    record_event("job_update", {"job_id": job_id, **payload})


job_runner = JobRunner()
