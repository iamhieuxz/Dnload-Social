"""Regression tests for queue pacing and partial-download status.

Two bugs made a bulk run silently lose data:

1. Every row shared one flat 1800s deadline. A profile with a few thousand
   posts cannot finish in 30 minutes, and because the deadline called
   `request_stop_async` the whole job ended as STOPPED — so a queue of
   hundreds of accounts got through one account per button press.
2. The aborted row had already recorded a file path, so it fell into the
   success branch and was stored as `completed`. The missing tail was never
   queued again.

Both were invisible in the UI; the only symptom was accounts that looked
finished but held a fraction of their media.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.rate_limit import RateLimitGuard, RateLimitPolicy
from app.models.download import DownloadStatus
from app.services.job_runner import JobRunner, _JobState


class _FakeService:
    """Yields one media event, then stalls — the shape of a profile that
    needs longer than the deadline allows."""

    def __init__(self, output) -> None:
        self.output = str(output)
        self.runner = SimpleNamespace(is_running=True)
        self.aborted = False
        self._stop_requested = False

    @property
    def is_stopping(self) -> bool:
        return self._stop_requested

    async def download(self, *args, **kwargs):
        yield {"type": "media", "new": True, "path": self.output, "filename": "a.jpg"}
        await asyncio.sleep(0.05)
        yield {"type": "user_done", "user": "creator"}

    async def abort_current(self) -> None:
        self.aborted = True

    async def request_stop_async(self) -> None:
        self._stop_requested = True


class _StoppingService(_FakeService):
    """Yields one media event, then the user presses Stop."""

    async def download(self, *args, **kwargs):
        yield {"type": "media", "new": True, "path": self.output, "filename": "a.jpg"}
        self._stop_requested = True
        yield {"type": "user_done", "user": "creator"}


def _row(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        platform="instagram",
        source_type="database",
        account_id=None,
        url="https://www.instagram.com/creator/",
        content_type="post",
        author="creator",
        status=DownloadStatus.PENDING,
        file_path=None,
        file_name=None,
        file_size_bytes=0,
        error_message=None,
        completed_at=None,
    )


class _FakeSession:
    async def flush(self): ...
    async def commit(self): ...
    async def get(self, *args): return None


def _run_row(service: _FakeService, row: SimpleNamespace, monkeypatch):
    monkeypatch.setenv("DOWNLOAD_PROFILE_TOTAL_DEADLINE_SECONDS", "0.02")
    monkeypatch.setenv("DOWNLOAD_TOTAL_DEADLINE_SECONDS", "0.02")
    runner = JobRunner()
    with patch("app.services.job_runner.ws_manager.broadcast", new=AsyncMock()):
        with patch("app.core.logging_config.record_event"):
            ok = asyncio.run(
                runner._process_one(
                    _FakeSession(), row, {"instagram": service}, {"instagram": []}
                )
            )
    return ok, runner


def _process_row(service, row: SimpleNamespace) -> bool:
    """Same as `_run_row`, but leaves the deadlines alone."""
    runner = JobRunner()
    with patch("app.services.job_runner.ws_manager.broadcast", new=AsyncMock()):
        with patch("app.core.logging_config.record_event"):
            return asyncio.run(
                runner._process_one(
                    _FakeSession(), row, {"instagram": service}, {"instagram": []}
                )
            )


def _quiet_policy() -> RateLimitPolicy:
    return RateLimitPolicy(
        min_delay_seconds=0,
        max_delay_seconds=0,
        batch_size=999,
        batch_cooldown_seconds=0,
        suspected_limit_cooldown_seconds=0,
        jitter_seconds=0,
    )


class _RecordingGuard(RateLimitGuard):
    def __init__(self) -> None:
        super().__init__(_quiet_policy())
        self.account_waits = 0
        self.limit_waits = 0

    async def wait_after_account(self, *, stop_requested):
        self.account_waits += 1

    async def wait_after_limit_signal(self, *, stop_requested):
        self.limit_waits += 1


def test_partial_profile_hit_is_failed_not_completed(tmp_path, monkeypatch) -> None:
    output = tmp_path / "a.jpg"
    output.write_bytes(b"media")
    service = _FakeService(output)
    row = _row(tmp_path)

    ok, _runner = _run_row(service, row, monkeypatch)

    assert ok is False
    # The media event put a real file on disk; that must not flip the row to
    # `completed` while thousands of its siblings are still missing.
    assert row.status == DownloadStatus.FAILED
    assert "timeout" in (row.error_message or "")


def test_deadline_abandons_only_the_row_and_keeps_the_job(tmp_path, monkeypatch) -> None:
    output = tmp_path / "a.jpg"
    output.write_bytes(b"media")
    service = _FakeService(output)
    row = _row(tmp_path)

    _run_row(service, row, monkeypatch)

    assert service.aborted is True, "row should be abandoned via abort_current()"
    # Sticky stop would mark the whole job STOPPED and strand the queue.
    assert service.is_stopping is False


def test_stopped_row_goes_back_to_pending_not_completed(tmp_path) -> None:
    """Stop pressed after the first file landed. The row had a real path on
    disk, which used to be read as success — so the rest of the profile was
    never queued again."""
    output = tmp_path / "a.jpg"
    output.write_bytes(b"media")
    service = _StoppingService(output)
    row = _row(tmp_path)

    ok = _process_row(service, row)

    assert ok is False
    assert row.status == DownloadStatus.PENDING


def test_profile_rows_get_the_long_deadline(monkeypatch) -> None:
    monkeypatch.setenv("DOWNLOAD_PROFILE_TOTAL_DEADLINE_SECONDS", "14400")
    monkeypatch.setenv("DOWNLOAD_TOTAL_DEADLINE_SECONDS", "1800")
    runner = JobRunner()

    profile = SimpleNamespace(url="https://www.instagram.com/creator/")
    post = SimpleNamespace(url="https://www.instagram.com/creator/p/AbCdEf/")

    assert runner._row_deadline(profile) == 14400
    assert runner._row_deadline(post) == 1800


def _state(services: dict, guard: RateLimitGuard) -> _JobState:
    return _JobState(job_id=1, platform="instagram", services=services, guard=guard)


@pytest.mark.asyncio
async def test_healthy_profile_gets_inter_account_spacing() -> None:
    runner = JobRunner()
    guard = _RecordingGuard()
    state = _state({"instagram": _FakeService("x")}, guard)

    reason = await runner._pace_after_row(
        SimpleNamespace(url="https://www.instagram.com/creator/"), state,
    )

    assert reason is None
    assert guard.account_waits == 1
    assert guard.limit_waits == 0


@pytest.mark.asyncio
async def test_single_post_row_is_not_account_paced() -> None:
    """One-off links are not an account switch — spacing each of them would
    make a 20-link paste crawl without protecting anything."""
    runner = JobRunner()
    guard = _RecordingGuard()
    state = _state({"instagram": _FakeService("x")}, guard)

    await runner._pace_after_row(
        SimpleNamespace(url="https://www.instagram.com/creator/p/AbCdEf/"), state,
    )

    assert guard.account_waits == 0


@pytest.mark.asyncio
async def test_repeated_limit_signals_stop_the_job() -> None:
    """One throttle = cool down and continue. Two back to back = the session
    itself is flagged; continuing is how a block becomes a checkpoint."""
    runner = JobRunner()
    guard = _RecordingGuard()
    state = _state({"instagram": _FakeService("x")}, guard)
    row = SimpleNamespace(url="https://www.instagram.com/creator/")

    state.row_saw_limit = True
    first = await runner._pace_after_row(row, state)
    state.row_saw_limit = True
    second = await runner._pace_after_row(row, state)

    assert first is None
    assert guard.limit_waits == 1
    assert second and "rate limit signals" in second


@pytest.mark.asyncio
async def test_healthy_row_resets_the_limit_streak() -> None:
    runner = JobRunner()
    guard = _RecordingGuard()
    state = _state({"instagram": _FakeService("x")}, guard)
    row = SimpleNamespace(url="https://www.instagram.com/creator/")

    state.row_saw_limit = True
    await runner._pace_after_row(row, state)
    state.row_saw_limit = False
    await runner._pace_after_row(row, state)
    state.row_saw_limit = True
    reason = await runner._pace_after_row(row, state)

    assert reason is None, "streak was broken by a clean account, so no stop"


@pytest.mark.asyncio
async def test_each_running_job_keeps_its_own_pace_history() -> None:
    """Instagram and X now run side by side, so one job's throttle streak must
    not stop the other. These counters lived on the runner itself, where the
    last job to start overwrote them for everybody."""
    runner = JobRunner()
    ig_guard = _RecordingGuard()
    x_guard = _RecordingGuard()
    ig = _state({"instagram": _FakeService("x")}, ig_guard)
    x = _state({"twitter": _FakeService("x")}, x_guard)
    row = SimpleNamespace(url="https://www.instagram.com/creator/")

    ig.row_saw_limit = True
    await runner._pace_after_row(row, ig)
    ig.row_saw_limit = True
    ig_stop = await runner._pace_after_row(row, ig)
    x_stop = await runner._pace_after_row(row, x)

    assert ig_stop and "rate limit signals" in ig_stop
    assert x_stop is None, "a clean X job must not inherit Instagram's streak"
    assert x_guard.limit_waits == 0
    assert x_guard.account_waits == 1


def test_profile_command_does_not_use_abort() -> None:
    """gallery-dl's -A counts consecutive *skips*, not errors. With `-A 20`
    a resume run stopped as soon as the newest 20 files were already archived:
    1.6 seconds, rc=0, and a row recorded `completed` with most of the account
    missing."""
    from app.services.instagram import InstagramService

    service = InstagramService(policy=_quiet_policy())
    cmd = service._build_command(
        "https://www.instagram.com/creator/", "dest", None, None, True, ""
    )

    assert "--abort" not in cmd
    assert "--download-archive" in cmd
