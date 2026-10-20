"""Regression test: decrypt_cookie_file wraps read errors in RuntimeError
instead of leaking OSError + a possibly half-decrypted tempfile.

Bug B-01 from docs/BUGS.md.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.core import cookie_vault


def test_missing_file_raises_runtimeerror(monkeypatch, tmp_path: Path) -> None:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        cookie_vault,
        "get_settings",
        lambda: SimpleNamespace(cookie_encryption_key=key),
    )
    missing = tmp_path / "does-not-exist.txt"
    with pytest.raises(RuntimeError) as exc:
        cookie_vault.decrypt_cookie_file(missing)
    assert "does-not-exist.txt" in str(exc.value)


def test_garbage_file_does_not_leave_tempfile(monkeypatch, tmp_path: Path) -> None:
    """Random bytes that don't decrypt to anything must fail cleanly
    and not leave a stray tempfile under %TEMP%."""
    import os
    import tempfile

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        cookie_vault,
        "get_settings",
        lambda: SimpleNamespace(cookie_encryption_key=key),
    )
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"not encrypted, not netscape")

    # Snapshot temp dir before — we expect zero new dnload_cookie_* files.
    tmp_dir = tempfile.gettempdir()
    before = set(os.listdir(tmp_dir))
    with pytest.raises(Exception):
        cookie_vault.decrypt_cookie_file(bad)
    after = set(os.listdir(tmp_dir))
    leaked = (after - before) & {n for n in after if n.startswith("dnload_cookie_")}
    assert not leaked, f"Stray tempfile left behind: {leaked}"
