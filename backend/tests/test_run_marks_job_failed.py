"""Smoke test: when _execute raises, the job gets marked FAILED (not stuck RUNNING)."""
import asyncio
import pytest
from unittest.mock import patch

from app.services.job_runner import JobRunner


def test_run_marks_job_failed_on_exception():
    """If _execute raises any uncaught exception, the job should transition
    to FAILED with an error message — not stay stuck in RUNNING."""
    runner = JobRunner()
    captured = {}

    async def fake_execute(self, job_id):
        raise RuntimeError("simulated crash: cookie key missing")

    async def fake_mark(self, job_id, msg):
        captured["job_id"] = job_id
        captured["msg"] = msg

    with patch.object(JobRunner, "_execute", fake_execute), \
         patch.object(JobRunner, "_mark_job_failed", fake_mark):
        asyncio.run(runner._run(9999))

    assert captured["job_id"] == 9999
    assert "cookie key missing" in captured["msg"]
