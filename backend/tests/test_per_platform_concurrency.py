"""One job per platform, not one job per process.

The runner used to hold a single global lock, so a Twitter job started while
Instagram was downloading was orphaned immediately: the queue advanced one
platform at a time even though the two have separate cookies, separate
download archives and separate rate-limit budgets.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.job_runner import JobRunner

PLATFORMS = {1: "instagram", 2: "twitter", 3: "instagram"}


@asynccontextmanager
async def _scenario(*, cap: int = 2):
    runner = JobRunner()
    release = asyncio.Event()
    started: list[int] = []

    async def fake_run(_runner: JobRunner, job_id: int) -> None:
        started.append(job_id)
        await release.wait()

    with patch.object(
        JobRunner, "_job_platform", new=AsyncMock(side_effect=lambda job_id: PLATFORMS[job_id])
    ), patch.object(JobRunner, "_run", new=fake_run), patch.object(
        JobRunner, "_startup_sweep", new=AsyncMock()
    ), patch.object(
        JobRunner, "_orphan_job", new=AsyncMock()
    ) as orphan, patch("app.config.get_settings", return_value=SimpleNamespace(max_concurrent_jobs=cap)):
        yield runner, started, release, orphan


@pytest.mark.asyncio
async def test_two_platforms_run_at_the_same_time() -> None:
    async with _scenario() as (runner, started, release, orphan):
        await runner.enqueue(1)
        await runner.enqueue(2)
        await asyncio.sleep(0.05)

        assert sorted(started) == [1, 2]
        assert sorted(runner.active_job_ids) == [1, 2]
        assert orphan.await_count == 0, "Instagram and X must not block each other"

        release.set()
        await asyncio.sleep(0.05)
        assert runner.is_busy is False


@pytest.mark.asyncio
async def test_second_job_on_the_same_platform_is_rejected() -> None:
    """Two Instagram jobs would double the request rate on one cookie — the
    sibling must be refused, with a reason the UI can show."""
    async with _scenario() as (runner, _started, release, orphan):
        await runner.enqueue(1)
        await runner.enqueue(3)

        assert orphan.await_count == 1
        assert orphan.await_args.args[0] == 3
        assert "instagram" in orphan.await_args.args[1]
        assert runner.active_job_ids == [1]

        release.set()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_total_cap_still_applies_across_platforms() -> None:
    async with _scenario(cap=1) as (runner, _started, release, orphan):
        await runner.enqueue(1)
        await runner.enqueue(2)

        assert orphan.await_count == 1
        assert orphan.await_args.args[0] == 2
        assert "1 jobs" in orphan.await_args.args[1]

        release.set()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_stop_targets_one_job_only() -> None:
    """Stop on the X job must leave Instagram's subprocess running."""
    class _Svc:
        def __init__(self) -> None:
            self._stop_requested = False

        @property
        def is_stopping(self) -> bool:
            return self._stop_requested

        async def request_stop_async(self) -> None:
            self._stop_requested = True

        def request_stop(self) -> None:
            self._stop_requested = True

    runner = JobRunner()
    ig, x = _Svc(), _Svc()
    runner._active[1] = SimpleNamespace(job_id=1, services={"instagram": ig})  # type: ignore[arg-type]
    runner._active[2] = SimpleNamespace(job_id=2, services={"twitter": x})  # type: ignore[arg-type]

    await runner.request_stop(2)

    assert x.is_stopping is True
    assert ig.is_stopping is False
