"""A download that produced no output is not automatically a failure.

A profile whose files are already on disk (gallery-dl --download-archive
short-circuits), an empty highlight, or a private profile all finish with
zero output events. Reporting those as `failed` made every re-run of an
up-to-date profile look like an error in the UI.
"""
from types import SimpleNamespace

from app.models.download import DownloadStatus
from app.services.job_runner import _set_no_output_failure


def _row() -> SimpleNamespace:
    return SimpleNamespace(
        platform="instagram",
        status=None,
        error_message=None,
    )


def test_cached_profile_is_skipped_not_failed() -> None:
    d = _row()
    _set_no_output_failure(d, [
        {"type": "user_start", "user": "creator"},
        {"type": "skip", "user": "creator", "reason": "cached"},
        {"type": "user_done", "user": "creator"},
    ])
    assert d.status == DownloadStatus.SKIPPED
    assert d.error_message is None


def test_no_output_warn_without_error_is_skipped() -> None:
    d = _row()
    _set_no_output_failure(d, [
        {"type": "warn", "code": "no_output", "line": ""},
    ])
    assert d.status == DownloadStatus.SKIPPED
    assert d.error_message is None


def test_service_error_event_still_fails() -> None:
    d = _row()
    _set_no_output_failure(d, [
        {"type": "user_start", "user": "creator"},
        {"type": "error", "message": "login required"},
    ])
    assert d.status == DownloadStatus.FAILED
    assert d.error_message


def test_timeout_message_is_preserved_and_fails() -> None:
    d = _row()
    d.error_message = "timeout after 1800s (total deadline)"
    _set_no_output_failure(d, [{"type": "user_start", "user": "creator"}])
    assert d.status == DownloadStatus.FAILED
    assert d.error_message == "timeout after 1800s (total deadline)"


def test_error_message_is_truncated_to_1000_chars() -> None:
    d = _row()
    d.error_message = "x" * 5000
    _set_no_output_failure(d, [{"type": "error", "message": "boom"}])
    assert d.status == DownloadStatus.FAILED
    assert len(d.error_message) == 1000