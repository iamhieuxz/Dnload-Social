"""Regression test: when no output file is produced for a Download, the
row gets a 1000-char-capped error_message and FAILED status.

Bug B-20 from docs/BUGS.md.

We test the extracted helper `_set_no_output_failure` directly because
the surrounding `_process_one` is a 200-line monster that drives a
subprocess; verifying the cap and status at the helper level is the
smallest regression that proves the rule.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models import DownloadStatus
from app.services.job_runner import _set_no_output_failure


def test_long_error_message_truncated() -> None:
    """A 5KB error_message must shrink to 1000 chars."""
    d = SimpleNamespace(
        platform="instagram",
        error_message="X" * 5000,
        status="pending",
    )
    _set_no_output_failure(d, events=[])
    assert len(d.error_message) <= 1000, (
        f"not truncated: length={len(d.error_message)}"
    )
    # Prefix survived (we did not accidentally null it out).
    assert d.error_message.startswith("X")
    assert d.status == DownloadStatus.FAILED


def test_short_error_message_untouched() -> None:
    """A short error_message must be preserved verbatim."""
    short = "rate limit hit on this URL"
    d = SimpleNamespace(
        platform="instagram",
        error_message=short,
        status="pending",
    )
    _set_no_output_failure(d, events=[])
    assert d.error_message == short
    assert d.status == DownloadStatus.FAILED


def test_empty_error_message_gets_generic_default() -> None:
    """If error_message is empty, a generic one is written and truncated
    (which is a no-op for short defaults)."""
    d = SimpleNamespace(
        platform="instagram",
        error_message="",
        status="pending",
    )
    _set_no_output_failure(d, events=[{"type": "user_start"}] * 3)
    assert d.error_message
    assert "No output file found" in d.error_message
    assert "events=3" in d.error_message
    assert d.status == DownloadStatus.FAILED


def test_50kb_stacktrace_becomes_1000_chars() -> None:
    """A 50KB stack trace (the case the rule exists for) must end at
    1000 chars exactly."""
    big = "Traceback (most recent call last):\n" + "  File\n" * 8000  # ~50KB
    assert len(big) > 50_000
    d = SimpleNamespace(
        platform="instagram",
        error_message=big,
        status="pending",
    )
    _set_no_output_failure(d, events=[])
    assert len(d.error_message) == 1000
