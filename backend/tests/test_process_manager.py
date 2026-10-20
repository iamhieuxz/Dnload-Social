"""Tests for AsyncProcessRunner._redact_cmd."""
from __future__ import annotations

from app.core.process_manager import AsyncProcessRunner


def test_redact_cookies_path():
    cmd = ["gallery-dl", "https://example.com/p/1", "--cookies", "C:/secrets/ig/cookie1.txt"]
    out = AsyncProcessRunner()._redact_cmd(cmd)
    assert "cookie1.txt" not in out
    assert "<redacted>" in out


def test_redact_destination_path():
    cmd = ["gallery-dl", "--destination", "E:/gallery-dl/instagram", "url"]
    out = AsyncProcessRunner()._redact_cmd(cmd)
    assert "gallery-dl/instagram" not in out
    assert "<redacted>" in out


def test_redact_download_archive():
    cmd = ["gallery-dl", "--download-archive", ".archive.sqlite", "url"]
    out = AsyncProcessRunner()._redact_cmd(cmd)
    assert ".archive.sqlite" not in out


def test_no_flag_passthrough():
    cmd = ["gallery-dl", "https://example.com/p/1"]
    out = AsyncProcessRunner()._redact_cmd(cmd)
    assert out == "gallery-dl https://example.com/p/1"


def test_unknown_flag_unaffected():
    cmd = ["gallery-dl", "--sleep-request", "10-24", "url"]
    out = AsyncProcessRunner()._redact_cmd(cmd)
    # Unknown flags keep their next value intact.
    assert "10-24" in out


def test_flag_at_end_no_value():
    """Flag without a value after it must not crash; skip_next stays False."""
    cmd = ["gallery-dl", "url", "--cookies"]
    out = AsyncProcessRunner()._redact_cmd(cmd)
    assert out == "gallery-dl url --cookies"
