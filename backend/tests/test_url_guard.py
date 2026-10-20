"""Tests for app.core.url_guard — argv-injection guard."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.url_guard import validate_url


def test_https_instagram_ok():
    url = "https://www.instagram.com/p/ABC123/"
    assert validate_url(url, "instagram") == url


def test_https_twitter_ok():
    url = "https://x.com/user/status/123"
    assert validate_url(url, "twitter") == url


def test_https_tiktok_ok():
    url = "https://www.tiktok.com/@user/video/123"
    assert validate_url(url, "tiktok") == url


def test_vm_tiktok_short_url_ok():
    url = "https://vm.tiktok.com/ZMabc123/"
    assert validate_url(url, "tiktok") == url


def test_bare_username_tiktok_ok():
    assert validate_url("@username", "tiktok") == "@username"
    assert validate_url("username", "tiktok") == "username"


def test_rejects_argv_injection_instagram():
    """`--config=...` starts with `--` and is a relative path, not a URL.
    urlparse returns scheme='' and hostname=None, so it must 400."""
    with pytest.raises(HTTPException) as exc:
        validate_url("--config=/etc/passwd", "instagram")
    assert exc.value.status_code == 400


def test_rejects_file_scheme():
    with pytest.raises(HTTPException) as exc:
        validate_url("file:///etc/passwd", "instagram")
    assert exc.value.status_code == 400


def test_rejects_javascript_scheme():
    with pytest.raises(HTTPException) as exc:
        validate_url("javascript:alert(1)", "twitter")
    assert exc.value.status_code == 400


def test_rejects_unknown_host():
    with pytest.raises(HTTPException) as exc:
        validate_url("https://evil.example.com/p/123", "instagram")
    assert exc.value.status_code == 400
    assert "evil.example.com" in str(exc.value.detail)


def test_rejects_empty_url():
    with pytest.raises(HTTPException) as exc:
        validate_url("", "instagram")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        validate_url("   ", "instagram")
    assert exc.value.status_code == 400


def test_rejects_unknown_platform():
    with pytest.raises(HTTPException) as exc:
        validate_url("https://www.instagram.com/p/123", "facebook")
    assert exc.value.status_code == 400


def test_bare_username_outside_tiktok_rejected():
    """Username-only inputs are TikTok-specific; other platforms require
    a real URL."""
    with pytest.raises(HTTPException) as exc:
        validate_url("just_a_name", "instagram")
    assert exc.value.status_code == 400
