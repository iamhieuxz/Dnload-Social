"""Every UI log line must say which stream produced it — and only once.

Instagram and X run at the same time and both emit plain "[NEW] <file>"
lines. One handler is attached per running job, so a record has to carry the
job it belongs to (`extra={"job_id": …}`) or it gets broadcast once per job,
each copy tagged with the wrong platform.
"""
from __future__ import annotations

import logging

from app.core.logging_config import WebSocketLogHandler, get_system_events


def _emit(handler: WebSocketLogHandler, message: str, job_id: int | None) -> None:
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord("x", logging.INFO, __file__, 1, message, None, None)
    if job_id is not None:
        record.job_id = job_id
    handler.emit(record)


def _events_for(job_id: int) -> list[dict]:
    events, _cursor = get_system_events(0)
    return [e for e in events if e.get("job_id") == job_id]


def test_log_handler_stamps_platform_on_the_system_event() -> None:
    handler = WebSocketLogHandler(987_654, platform="twitter")
    _emit(handler, "[NEW] 123_1.jpg", job_id=987_654)

    mine = _events_for(987_654)

    assert mine, "log line did not reach the system event stream"
    assert mine[-1]["platform"] == "twitter"
    assert "ts" in mine[-1], "clients dedupe the WS/polling copies by ts"


def test_other_jobs_records_are_not_republished() -> None:
    """The X job's handler must ignore a line produced by the Instagram job."""
    x_handler = WebSocketLogHandler(987_656, platform="twitter")
    _emit(x_handler, "[NEW] ig_file.jpg", job_id=987_655)

    assert _events_for(987_656) == []


def test_records_without_a_job_id_stay_internal() -> None:
    handler = WebSocketLogHandler(987_657, platform="instagram")
    _emit(handler, "[NEW] stray.jpg", job_id=None)

    assert _events_for(987_657) == []


def test_internal_lines_stay_out_of_the_stream() -> None:
    handler = WebSocketLogHandler(987_658, platform="instagram")
    _emit(handler, "starting up", job_id=987_658)

    assert _events_for(987_658) == []
