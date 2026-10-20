"""Tests for WebSocket loopback guard (app/api/ws.py)."""
from __future__ import annotations

import pytest


def _make_ws_stub(client_host: str | None):
    """Build an object that mimics enough of the FastAPI WebSocket
    interface for `_client_is_loopback(ws)` to read `.client.host`.
    The real WebSocket class refuses to be instantiated outside a
    request scope, so we use a simple stand-in."""

    class _Client:
        def __init__(self, host: str | None):
            self.host = host

    class _Stub:
        pass

    stub = _Stub()
    stub.client = _Client(client_host)
    return stub


def test_loopback_v4_allowed(monkeypatch):
    monkeypatch.delenv("LOCAL_API_BEHIND_LOOPBACK_PROXY", raising=False)
    from app.api.ws import _client_is_loopback

    assert _client_is_loopback(_make_ws_stub("127.0.0.1")) is True


def test_loopback_v6_allowed(monkeypatch):
    monkeypatch.delenv("LOCAL_API_BEHIND_LOOPBACK_PROXY", raising=False)
    from app.api.ws import _client_is_loopback

    assert _client_is_loopback(_make_ws_stub("::1")) is True


def test_non_loopback_rejected(monkeypatch):
    monkeypatch.delenv("LOCAL_API_BEHIND_LOOPBACK_PROXY", raising=False)
    from app.api.ws import _client_is_loopback

    assert _client_is_loopback(_make_ws_stub("10.0.0.5")) is False
    assert _client_is_loopback(_make_ws_stub("192.168.1.1")) is False


def test_empty_client_rejected(monkeypatch):
    monkeypatch.delenv("LOCAL_API_BEHIND_LOOPBACK_PROXY", raising=False)
    from app.api.ws import _client_is_loopback

    assert _client_is_loopback(_make_ws_stub("")) is False
    assert _client_is_loopback(_make_ws_stub(None)) is False


def test_behind_loopback_proxy_bypasses(monkeypatch):
    monkeypatch.setenv("LOCAL_API_BEHIND_LOOPBACK_PROXY", "true")
    from app.api.ws import _client_is_loopback

    # Bypass mode allows any host (operator is opting in).
    assert _client_is_loopback(_make_ws_stub("10.0.0.5")) is True
    assert _client_is_loopback(_make_ws_stub("")) is True
