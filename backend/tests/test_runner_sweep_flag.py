"""Regression test: JobRunner marks the startup sweep done ONLY after
the sweep commit succeeds. A sweep failure should leave the flag False
so the next enqueue retries it instead of silently skipping.

Bug B-22 from docs/BUGS.md.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.job_runner import JobRunner


def _locks_held(runner: JobRunner) -> bool:
    return any(lock.locked() for lock in runner._locks.values())


def test_sweep_failure_keeps_flag_false() -> None:
    """If the sweep's DB call raises, _startup_sweep_done must stay
    False so the next enqueue() retries it."""
    runner = JobRunner()
    assert runner._startup_sweep_done is False

    # Make session_scope raise so the sweep's DB write fails. The platform
    # lookup runs before it and needs its own answer, otherwise this would
    # be testing the lookup's failure path instead of the sweep's.
    orphan = AsyncMock()
    with patch.object(JobRunner, "_job_platform", new=AsyncMock(return_value="instagram")), \
            patch("app.services.job_runner.session_scope", side_effect=RuntimeError("db down")), \
            patch.object(JobRunner, "_orphan_job", new=orphan):
        asyncio.run(runner.enqueue(1234))

    # Lock should have been released since the sweep failed.
    assert _locks_held(runner) is False
    # And the sweep flag should still be False so the next enqueue retries.
    assert runner._startup_sweep_done is False
    assert orphan.await_count == 1
    assert orphan.await_args.args[0] == 1234


def test_sweep_success_marks_flag_true() -> None:
    """Happy path: sweep commits, flag flips True, second enqueue
    skips the sweep block entirely."""
    runner = JobRunner()
    # Stub session_scope to return a fake session whose execute()
    # behaves well enough for the platform lookup and the UPDATE
    # statement to commit.
    from contextlib import asynccontextmanager

    class _FakeResult:
        rowcount = 0

        def scalar_one_or_none(self):
            return "instagram"

    class _FakeSession:
        async def execute(self, stmt):
            return _FakeResult()

        async def __aenter__(self_inner):
            return self_inner

        async def __aexit__(self_inner, *args):
            return False

    @asynccontextmanager
    async def _fake_session_scope():
        yield _FakeSession()

    with patch("app.services.job_runner.session_scope", _fake_session_scope):
        with patch.object(JobRunner, "_orphan_job", new=AsyncMock()):
            with patch.object(JobRunner, "_run_with_lock", new=AsyncMock()):
                asyncio.run(runner.enqueue(1))
                assert runner._startup_sweep_done is True
