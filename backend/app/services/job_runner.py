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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        # _lock guards BOTH the "is a job running?" state AND the critical
        # section that picks up work. Holding it across enqueue prevents
        # the classic double-click race: two `Run pending` clicks fired
        # 200ms apart used to both pass the is_busy check (because the
        # lock was only held once _run was already executing) and create
        # two Jobs, with the second one immediately getting orphaned to
        # STOPPED. The lock is now acquired BEFORE any DB work.
        self._lock = asyncio.Lock()
        # Recovery runs ONCE per process, at the first enqueue() after
        # the runner wakes up. Running it on every enqueue would reset
        # downloads owned by a *different* in-flight job (e.g. another
        # process holding the same job_id), which is the
        # runner-global-stale-reset bug.
        self._startup_sweep_done = False
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
            if svc.is_stopping:
                continue
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

        Lock semantics: we acquire `_lock` BEFORE doing any DB work. This
        means the second `enqueue` of a double-click blocks here until the
        first job releases. While blocked, the second call also reads the
        current job state to decide whether to run or orphan — and since
        it blocks on the lock, by the time it gets the lock the first
        job is either still running (in which case we orphan) or has
        finished cleanly.
        """
        from sqlalchemy import update as _update
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=0.05)
        except asyncio.TimeoutError:
            # First job is still busy. Orphan this one immediately so it
            # doesn't sit in QUEUED forever and the UI doesn't think
            # nothing's happening.
            logger.warning("Job %s rejected at enqueue (busy)", job_id)
            await self._orphan_job(job_id)
            return

        # We hold the lock for the lifetime of the job. _run will release
        # it in its finally block. Pass the lock through so the finally
        # block can release it (avoids us having to store state here).
        # Recovery: only sweep stale `downloading` rows on the FIRST
        # enqueue of this process lifetime, and only reset rows that
        # aren't owned by the job we're about to run. Without the
        # `job_id != :id` filter we would clobber a perfectly valid
        # download owned by a sibling job in another process.
        if not self._startup_sweep_done:
            try:
                async with session_scope() as session:
                    stale = _update(Download).where(
                        Download.status == DownloadStatus.DOWNLOADING,
                        Download.job_id != job_id,
                    ).values(status=DownloadStatus.PENDING, job_id=None)
                    result = await session.execute(stale)
                    if result.rowcount:
                        logger.info(
                            "Startup sweep: reset %s stale `downloading` rows to `pending`",
                            result.rowcount,
                        )
                # Only mark the sweep done AFTER it commits successfully.
                # A failure here leaves the flag False so the next enqueue
                # gets a fresh attempt, instead of silently skipping it.
                self._startup_sweep_done = True
            except Exception:
                logger.exception("Startup sweep failed for job %s; releasing lock", job_id)
                self._lock.release()
                await self._orphan_job(job_id)
                return

        asyncio.create_task(self._run_with_lock(job_id))

    async def _run_with_lock(self, job_id: int) -> None:
        """Wrapper that releases `_lock` after _run finishes. _run used to
        do `async with self._lock:` which acquired AND released in the same
        statement; we now keep the lock held across enqueue so a second
        enqueue call can be rejected immediately."""
        try:
            await self._run(job_id)
        finally:
            if self._lock.locked():
                self._lock.release()

    async def _run(self, job_id: int) -> None:
        logger.info("[JOB %s] _run called", job_id)
        # Lock is already held by enqueue; don't re-acquire (we'd deadlock).
        # Just set state and execute.
        self._current_job_id = job_id
        try:
            await self._execute(job_id)
        except Exception as e:
            # Shortcut: any uncaught error from _execute (cookie key
            # missing, DB unavailable, OOM, etc.) used to leave the job
            # row stuck in RUNNING forever — the UI showed a phantom
            # active job, the run button was locked, and the job page
            # was empty. Mark it FAILED with the error message so the
            # operator can see what happened, and detach its downloads
            # so the next run-pending can re-pick them up.
            logger.exception("[JOB %s] _execute crashed", job_id)
            await self._mark_job_failed(job_id, repr(e))
        finally:
            self._current_job_id = None
            self._services = {}
            # Shortcut: keep the log buffer around on failure so the UI
            # can show what went wrong. We only clear on success — see
            # the call site below. This is symmetric with how the buffer
            # is filled: if a job runs to completion, the logs are stale
            # anyway; if it crashes, they're the only diagnostic.
            pass

    async def _mark_job_failed(self, job_id: int, error_message: str) -> None:
        """Mark a job as FAILED (with error) and detach its downloads so
        the queue can recover. Used by _run's exception path."""
        from sqlalchemy import update as _update
        try:
            async with session_scope() as session:
                job = await session.get(Job, job_id)
                if job is not None and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    job.status = JobStatus.FAILED
                    job.finished_at = datetime.now(timezone.utc)
                    job.error_message = error_message[:500]
                # Detach downloads so they go back to PENDING and the
                # next run-pending picks them up.
                await session.execute(
                    _update(Download)
                    .where(Download.job_id == job_id,
                           Download.status.in_([
                               DownloadStatus.DOWNLOADING,
                               DownloadStatus.PENDING,
                           ]))
                    .values(status=DownloadStatus.PENDING, job_id=None)
                )
                await _emit_status(job_id, JobStatus.FAILED,
                                   extra={"reason": "exception"})
        except Exception:
            logger.exception("Failed to mark job %s as FAILED", job_id)

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
                job.finished_at = datetime.now(timezone.utc)
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
                job.finished_at = datetime.now(timezone.utc)
                await _emit_status(job_id, JobStatus.COMPLETED, extra={"processed": 0})
                return

            platform: Platform = Platform(downloads[0].platform)
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
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
                for cookie_paths in cookies.values():
                    for cookie_path in cookie_paths:
                        try:
                            os.remove(cookie_path)
                        except OSError:
                            logger.warning("Could not remove temporary cookie file %s", cookie_path)
                # "Perfect stop" — any rows that were marked `downloading`
                # when we exited (because the user pressed Stop) are
                # reverted to `pending` so the next run-pending call will
                # pick them up again. The instagram/tiktok services use
                # the gallery-dl --download-archive sqlite, so the actual
                # file download work is idempotent and safe to re-run.
                # Use a separate transaction so a rollback earlier in the
                # outer session_scope doesn't drop this reset.
                if any(s.is_stopping for s in services.values()):
                    try:
                        from sqlalchemy import update as _update
                        async with session_scope() as reset_session:
                            reset_stmt = _update(Download).where(
                                Download.job_id == job_id,
                                Download.status == DownloadStatus.DOWNLOADING,
                            ).values(status=DownloadStatus.PENDING)
                            reset_result = await reset_session.execute(reset_stmt)
                            if reset_result.rowcount:
                                logger.info(
                                    "Job %s stopped — reset %s in-progress downloads back to pending",
                                    job_id, reset_result.rowcount,
                                )
                    except Exception:
                        logger.exception("Failed to reset in-progress rows for job %s", job_id)

                job.finished_at = datetime.now(timezone.utc)
                root.removeHandler(ws_handler)
                await _emit_status(
                    job_id, job.status,
                    extra={
                        "platform": platform.value,
                        "processed": job.total_processed,
                        "new_files": job.new_files_count,
                    },
                )
                # Only clear the log buffer when the job was stopped by
                # the user. COMPLETED jobs keep their logs so the operator
                # can scroll back and see what each download did. The
                # buffer is capped at 5000 lines so memory cost is bounded.
                if job.status == JobStatus.STOPPED:
                    clear_job_logs(job_id)

    async def _process_one(
        self,
        session: AsyncSession,
        d: Download,
        services: dict,
        cookies: dict[str, list[str]],
    ) -> bool:
        """Process a single Download row. Returns True on success."""
        try:
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
            # Hard cap so a hung subprocess (gallery-dl sleeping in
            # --sleep-request) can't pin a download row forever. After
            # this many seconds we ask the service to stop, break the
            # loop, and let the outer JobRunner mark the row failed.
            TOTAL_DEADLINE = float(os.getenv("DOWNLOAD_TOTAL_DEADLINE_SECONDS", "1800"))
            last_event_at = asyncio.get_event_loop().time()
            started_at = last_event_at
            gen = service.download(target, cookie_files=platform_cookies, content_type=d.content_type, author=d.author, run_id=str(d.id))
            try:
                while True:
                    if any(s.is_stopping for s in services.values()):
                        break
                    elapsed = asyncio.get_event_loop().time() - started_at
                    if elapsed >= TOTAL_DEADLINE:
                        logger.warning("[ERR] timeout after %ss", int(elapsed))
                        d.error_message = f"timeout after {int(elapsed)}s (total deadline)"
                        for s in services.values():
                            await s.request_stop_async()
                        break
                    try:
                        remaining = max(0.1, min(IDLE_TIMEOUT, TOTAL_DEADLINE - elapsed))
                        ev = await asyncio.wait_for(gen.__anext__(), timeout=remaining)
                        last_event_at = asyncio.get_event_loop().time()
                    except (StopAsyncIteration, asyncio.TimeoutError) as e:
                        if isinstance(e, asyncio.TimeoutError):
                            runner_obj = service.runner
                            if runner_obj.is_running:
                                # Subprocess is still alive but silent — keep
                                # waiting; this is normal during rate-limit
                                # sleeps and long HTTP calls.
                                continue
                            # Process exited but no event surfaced — nothing
                            # more to do.
                        break
                    events.append(ev)
                    if ev.get("type") == "user_start":
                        # Internal event; surfaced as part of the URL line so
                        # the UI doesn't need to see "starting @user" twice.
                        pass
                    elif ev.get("type") == "media":
                        if d.file_path is None:
                            d.file_path = ev.get("path")
                            d.file_name = ev.get("filename")
                        # UI-facing: only the first media event per row is
                        # worth showing (subsequent ones are parts of the
                        # same tweet / carousel / Space chunk).
                        if ev.get("new"):
                            logger.info("[NEW] %s", ev.get("filename") or os.path.basename(ev.get("path", "")))
                    elif ev.get("type") == "user_done":
                        pass
                    elif ev.get("type") == "error":
                        # Trim to a short, user-readable name. Full trace
                        # stays in the backend log; the user just sees
                        # "ERR: rate limit exceeded" or similar.
                        err_name = (ev.get("message") or "unknown").splitlines()[0][:200].rstrip()
                        logger.warning("[ERR] %s", err_name)
                        d.error_message = ev.get("message")
                        break
                    elif ev.get("type") == "warn":
                        # gallery-dl prints a line per already-on-disk file
                        # ("# <path>"); surface the count as a single
                        # [SKIP] so the terminal doesn't drown in skipped
                        # archive entries.
                        code = ev.get("code")
                        if code == "no_output":
                            logger.info("[ERR] no_output")
                        else:
                            # Internal warn — no UI tag → filtered out.
                            pass
            finally:
                # Always close the generator so its `finally` runs — that is
                # what tears down the subprocess and removes the temp cookie
                # file. Breaking out of the loop (timeout / stop / error)
                # without this left an orphaned gallery-dl per aborted row.
                try:
                    await gen.aclose()
                except Exception:
                    logger.exception("Error closing download generator")

            # Pick the actual file from disk (gallery-dl/yt-dlp write to disk,
            # we just need to record where the file lives).
            file_path, file_size = self._find_output_file(d, events)
            if file_path:
                d.file_path = file_path
                d.file_name = os.path.basename(file_path)
                d.file_size_bytes = file_size
            else:
                # Truncate to 1000 chars so a 50KB stack trace from a
                # gallery-dl crash doesn't bloat the row.
                _set_no_output_failure(d, events)
                # Skip logging here if the service already surfaced an
                # [ERR] for this row — the no_output message is just
                # the same condition reported twice, and we don't want
                # the terminal to show two lines for one failure.
                if d.status == DownloadStatus.FAILED:
                    if d.error_message is None:
                        logger.info("[ERR] %s", (d.error_message or "no output").splitlines()[0][:200])
                    await session.flush()
                    await session.commit()
                    await ws_manager.broadcast(
                        "system", "download_update",
                        {"id": d.id, "status": d.status.value, "error": d.error_message},
                    )
                    return False

                # SKIPPED — nothing new to fetch. Counts as a processed
                # row for job progress, but never as a failure.
                await session.flush()
                await session.commit()
                await ws_manager.broadcast(
                    "system", "download_update",
                    {"id": d.id, "status": d.status.value},
                )
                return True

            d.status = DownloadStatus.COMPLETED
            d.completed_at = datetime.now(timezone.utc)
            await session.flush()
            await session.commit()
            await ws_manager.broadcast("system", "download_update",
                {"id": d.id, "status": d.status.value, "file_path": d.file_path})
            from app.core.logging_config import record_event
            record_event("download_update", {"id": d.id, "status": d.status.value, "file_path": d.file_path})
            return True

        except Exception as e:
            # Truncate so a noisy crash trace doesn't bloat the row.
            d.status = DownloadStatus.FAILED
            d.error_message = str(e)[:1000]
            err_name = str(e).splitlines()[0][:200] or "crashed"
            logger.warning("[ERR] %s", err_name)
            await session.flush()
            try:
                await session.commit()
            except Exception:
                pass
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
        """Resolve only an explicit media event path; never guess from recency."""
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

        return None, 0


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
      - IG, X and TikTok all have different cookie formats, so we must
        not mix them — JobRunner passes the right list to each service.
      - TikTok without a sessionid cookie is throttled to ~1 req / 5-10
        min (causing the 12-min stall we saw in C1). Once a primary
        cookie is uploaded it goes from "stuck" to "snappy" so the
        empty-list default is a no-op fallback, not the steady state.

    Also stamps `last_used_at` on the matching DB row for each loaded
    cookie so the Settings page can show the user which slot was actually
    used in the most recent job.
    """
    from app.config import get_settings
    settings = get_settings()
    cookie_dir = settings.get_cookie_folder()

    from app.core.cookie_vault import decrypt_cookie_file
    from app.models import TikTokCookie, TwitterCookie

    paths: dict[str, list[str]] = {"instagram": [], "twitter": [], "tiktok": []}
    cookie_slots = {
        "instagram": (cookie_dir, ("cookie1.txt", "cookie2.txt"), None),
        "twitter": (cookie_dir / "twitter", ("tw_cookie1.txt", "tw_cookie2.txt"), TwitterCookie),
        "tiktok": (cookie_dir / "tiktok", ("tt_cookie1.txt", "tt_cookie2.txt"), TikTokCookie),
    }
    # Slots we successfully decrypted — stamped with last_used_at after the
    # call returns so a cookie error doesn't claim the slot was just used.
    from sqlalchemy import update as _sa_update
    used_slots: list[tuple[Any, Any]] = []  # (model_cls, slot_value_str)
    try:
        for platform, (folder, names, model_cls) in cookie_slots.items():
            if not folder.exists():
                continue
            for name in names:
                path = folder / name
                if not path.exists():
                    continue
                paths[platform].append(decrypt_cookie_file(path))
                if model_cls is not None:
                    slot_value = "primary" if name.endswith("1.txt") else "backup"
                    used_slots.append((model_cls, slot_value))
    except Exception:
        for platform_paths in paths.values():
            for temp_path in platform_paths:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        raise

    # Stamp last_used_at in a separate transaction so a DB failure doesn't
    # abort the in-flight job.
    if used_slots:
        try:
            async with session_scope() as stamp_session:
                for model_cls, slot_value in used_slots:
                    await stamp_session.execute(
                        _sa_update(model_cls)
                        .where(model_cls.slot == slot_value)
                        .values(last_used_at=datetime.now(timezone.utc))
                    )
        except Exception:
            logger.exception("Failed to stamp last_used_at on cookie rows")

    return paths


async def _emit_status(job_id: int, status: JobStatus, extra: dict | None = None) -> None:
    payload = {"status": status.value}
    if extra:
        payload.update(extra)
    await ws_manager.broadcast(f"job:{job_id}", "status", payload)
    await ws_manager.broadcast("system", "job_update", {"job_id": job_id, **payload})
    # Also append to the system-wide polling buffer for HTTP-only clients
    from app.core.logging_config import record_event
    record_event("job_update", {"job_id": job_id, **payload})


def _set_no_output_failure(d, events: list[dict]) -> None:
    """Classify a Download row that produced no output file.

    "No output" is ambiguous: it can mean the download genuinely failed
    (bad cookie, network) OR that there was simply nothing left to
    fetch (profile already archived via --download-archive, empty
    highlight, private account). Reporting the latter as `failed` made
    every re-run of an up-to-date profile look like an error in the UI.

    So: if the service surfaced no `error` event and at least one
    benign "nothing to do" signal (`skip` / `no_output` / `user_done`),
    the row is SKIPPED. Otherwise it's a real FAILED.

    Keeps any prior error_message, otherwise writes a generic one, and
    truncates to 1000 chars so a 50KB gallery-dl stack trace doesn't
    bloat the row (B-20).
    """
    benign = not any(ev.get("type") == "error" for ev in events)
    already_done = any(
        ev.get("type") == "skip"
        or (ev.get("type") == "warn" and ev.get("code") == "no_output")
        for ev in events
    )
    if benign and already_done:
        d.status = DownloadStatus.SKIPPED
        d.error_message = None
        return
    if not d.error_message:
        d.error_message = (
            f"No output file found for {d.platform} URL "
            f"(events={len(events)})"
        )
    d.error_message = d.error_message[:1000]
    d.status = DownloadStatus.FAILED


job_runner = JobRunner()
