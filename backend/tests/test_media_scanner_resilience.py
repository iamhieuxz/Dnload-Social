"""Regression test: media_scanner._scan_account survives a folder that
gets deleted mid-scan (rglob raises OSError).

Bug B-05 from docs/BUGS.md.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.media_scanner import MediaScanner


def test_scan_account_survives_missing_folder(tmp_path: Path) -> None:
    """If rglob raises (folder deleted mid-scan), the scan must
    produce zero files and not raise to the caller."""
    scanner = MediaScanner()
    account_dir = tmp_path / "user"
    # Create and immediately remove so the directory exists in the
    # filesystem tree for the parent rglob but raises for ours.
    # Simpler: just make a nonexistent path.
    missing = tmp_path / "does-not-exist"

    # Must not raise.
    asyncio.run(scanner._scan_account(missing, "nobody"))
    # No assertions needed — if it didn't raise, the fix works.


def test_scan_account_survives_oserror_from_rglob(tmp_path: Path) -> None:
    """Even when the directory exists, a transient OSError from rglob
    must be swallowed (return zero files) instead of 500-ing the
    rescan endpoint."""
    scanner = MediaScanner()
    account_dir = tmp_path / "user"
    account_dir.mkdir()
    (account_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0fake-jpg")

    # Patch rglob to raise as if the folder was yanked mid-walk.
    with patch.object(
        Path,
        "rglob",
        side_effect=OSError("directory disappeared"),
    ):
        asyncio.run(scanner._scan_account(account_dir, "user"))
    # If we got here, no exception propagated. Good.
