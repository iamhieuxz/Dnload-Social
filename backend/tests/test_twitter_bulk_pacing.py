"""X bulk runs must pace themselves and resume.

Two things made a large Twitter queue unsafe to start:

1. `--download-archive` was scoped to the *run* (`.archive-<row id>.sqlite`),
   so re-running a stopped account re-walked its whole timeline from zero and
   left one sqlite file per row in the folder.
2. A 429 surfaced as a plain row error, so the runner never cooled the session
   down and kept pointing fresh accounts at a blocked cookie.
"""
from __future__ import annotations

import asyncio

from app.services.twitter import TwitterService


def test_archive_is_per_account_not_per_run(tmp_path) -> None:
    service = TwitterService()
    cmd = service._build_command(
        "https://twitter.com/creator/", str(tmp_path / "creator"), None, live=None,
    )

    archive = cmd[cmd.index("--download-archive") + 1]
    assert archive.endswith(TwitterService.archive_name)
    assert ".archive-" not in archive


def test_timeline_pacing_flags_are_present(tmp_path) -> None:
    service = TwitterService()
    cmd = service._build_command(
        "https://twitter.com/creator/", str(tmp_path / "creator"), None, live=None,
    )

    assert cmd[cmd.index("--sleep-request") + 1] == "5-12"
    assert cmd[cmd.index("--retries") + 1] == "6"
    assert cmd[cmd.index("--http-timeout") + 1] == "60"


def test_throttle_stops_the_cookie_rotation(monkeypatch, tmp_path) -> None:
    """A second cookie shares the throttled IP, so the row must end on the
    signal instead of cycling the set."""
    service = TwitterService()
    calls: list[str | None] = []

    async def fake_execute(url, dest, cookie_file, *, live=None):
        calls.append(cookie_file)
        yield {"type": "rate_limited", "line": "429 Too Many Requests"}

    monkeypatch.setattr(service, "_execute_one", fake_execute)
    events = asyncio.run(_collect(service, tmp_path))

    assert calls == ["cookie-a"], "must not try the next cookie after a 429"
    assert [e["type"] for e in events] == ["rate_limited"]


async def _collect(service: TwitterService, tmp_path) -> list[dict]:
    return [
        event
        async for event in service._download_with_fallback(
            "https://twitter.com/creator/", str(tmp_path / "creator"),
            ["cookie-a", "cookie-b"],
        )
    ]


def test_tweet_id_filenames_are_not_throttle_signals() -> None:
    """X filenames are 19-digit tweet ids, and gallery-dl echoes the path as
    it writes. A bare "429" substring would abort a healthy run every few
    hundred files."""
    from app.core.rate_limit import detect_limit_signal

    assert detect_limit_signal(r"F:\x\2084846996897304904_1.jpg") is False
    assert detect_limit_signal("2102808587072602604_429.mp4") is False
    assert detect_limit_signal(
        "[twitter][error] HttpError: 'HTTP Error 429: Too Many Requests'"
    ) is True
