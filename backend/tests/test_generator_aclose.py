"""Regression test: the download generator is always closed.

`_process_one` drives an async generator wrapping a gallery-dl
subprocess. When the loop breaks early — user pressed Stop, or an
`error` event arrived — the generator was dropped without `aclose()`.
Its `finally` block is what tears the subprocess down and removes the
temp cookie file, so every aborted row leaked a process until GC ran.

Both tests below drive a generator that has already yielded at least
one event, because that is the only state where the subprocess exists
and `aclose()` actually has work to do.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.download import DownloadStatus
from app.services.job_runner import JobRunner


class _FakeService:
    """Service that stops when `stop_after` polling checks have passed."""

    def __init__(self, stop_after: int = 99) -> None:
        self.closed = False
        self._checks = 0
        self._stop_after = stop_after
        self.runner = SimpleNamespace(is_running=False)

    async def download(self, *a, **kw):
        # async generator: `finally` runs on aclose() (or GC).
        self.closed = False
        try:
            for ev in _EVENTS:
                yield ev
            await asyncio.sleep(3600)  # pragma: no cover - never reached
        finally:
            self.closed = True

    async def request_stop_async(self) -> None: ...

    @property
    def is_stopping(self) -> bool:
        self._checks += 1
        return self._checks > self._stop_after


# First event is normal (loop continues); second is the early exit
# under test.
_EVENTS: list[dict] = [
    {"type": "user_start", "user": "creator"},
    {"type": "error", "message": "login required"},
]


class _FakeSession:
    async def flush(self): ...
    async def commit(self): ...
    async def get(self, *a): return None


def _download_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        platform="instagram",
        source_type="link",
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


def _process(service: _FakeService, row: SimpleNamespace, monkeypatch) -> bool:
    monkeypatch.setenv("DOWNLOAD_TOTAL_DEADLINE_SECONDS", "1800")
    runner = JobRunner()
    with patch("app.services.job_runner.ws_manager.broadcast", new=AsyncMock()):
        with patch("app.core.logging_config.record_event"):
            return asyncio.run(
                runner._process_one(
                    _FakeSession(), row, {"instagram": service}, {"instagram": []}
                )
            )


def _process_capture_closed(service: _FakeService, row: SimpleNamespace, monkeypatch):
    """Run _process_one and read `service.closed` *inside* the loop.

    `asyncio.run` calls `loop.shutdown_asyncgens()` on teardown, which
    finalizes any surviving generator and runs its `finally` — that would
    make every assertion here pass regardless of whether `aclose()` ran.
    In production the loop lives for the whole job, so the only thing that
    closes the generator is our explicit call. Sampling before teardown is
    what makes this test meaningful.
    """
    monkeypatch.setenv("DOWNLOAD_TOTAL_DEADLINE_SECONDS", "1800")
    runner = JobRunner()

    async def _run():
        ok = await runner._process_one(
            _FakeSession(), row, {"instagram": service}, {"instagram": []}
        )
        return ok, service.closed

    with patch("app.services.job_manager", create=True):
        with patch("app.services.job_runner.ws_manager.broadcast", new=AsyncMock()):
            with patch("app.core.logging_config.record_event"):
                return asyncio.run(_run())


def test_generator_closed_when_user_stops_midstream(monkeypatch) -> None:
    # stop_after=1 ⇒ loop check #2 reports stopping, after the first
    # event was already pulled (so the generator is suspended, not
    # finished — exactly the state that used to leak a subprocess).
    #
    # We stash the generator so it stays alive past the call. CPython
    # would otherwise finalize it on refcount zero, which runs the same
    # `finally` and hides the bug. Holding a reference models the real
    # case: `gen` stays bound until the next row rebinds it, and we
    # cannot rely on collection timing for a 30-minute job.
    service = _FakeService(stop_after=1)
    row = _download_row()

    original_download = service.download
    stash: list = []

    def _tracking_download(*a, **kw):
        gen = original_download(*a, **kw)
        stash.append(gen)
        return gen

    service.download = _tracking_download  # type: ignore[assignment]
    ok, closed = _process_capture_closed(service, row, monkeypatch)

    assert stash, "expected _process_one to create a generator"
    assert closed is True, "aclose() was not called — subprocess leaks"
    assert ok is False


def test_generator_closed_when_error_event_breaks_the_loop(monkeypatch) -> None:
    service = _FakeService()
    row = _download_row()

    original_download = service.download
    stash: list = []

    def _tracking_download(*a, **kw):
        gen = original_download(*a, **kw)
        stash.append(gen)
        return gen

    service.download = _tracking_download  # type: ignore[assignment]
    _ok, closed = _process_capture_closed(service, row, monkeypatch)

    assert stash, "expected _process_one to create a generator"
    assert closed is True, "aclose() was not called — subprocess leaks"
    assert row.status == DownloadStatus.FAILED
    assert row.error_message == "login required"


def test_generator_closed_when_no_output_after_real_run(monkeypatch) -> None:
    """A run that finished with only benign events is SKIPPED, not
    FAILED — and the generator is still closed on the way out."""
    service = _FakeService()

    async def _run(*a, **kw):
        try:
            yield {"type": "skip", "user": "creator", "reason": "cached"}
            yield {"type": "user_done", "user": "creator"}
        finally:
            service.closed = True

    service.download = _run  # type: ignore[assignment]
    row = _download_row()

    ok = _process(service, row, monkeypatch)

    assert service.closed is True
    assert row.status == DownloadStatus.SKIPPED
    assert row.error_message is None
    assert ok is True