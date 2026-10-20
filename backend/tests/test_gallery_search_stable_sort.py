"""Regression test: gallery search results sort by (ctime desc, name asc)
so the order is deterministic when two files share a ctime.

Bug B-41 from docs/BUGS.md.

On Windows, ctime = birthtime so we can't easily force a tie using
os.utime. The test instead uses THREE files: two of them created
within the same wall-clock second (which yields the same ctime on
most filesystems), and one created later. The newest ctime must
come first, and the two with tied ctime must come back sorted by
name (a..z).
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import gallery
from app.main import app


def test_search_sort_is_stable_on_ctime_ties(monkeypatch, tmp_path) -> None:
    root = tmp_path / "insta"
    root.mkdir()
    sub = root / "user1"
    sub.mkdir()

    # Create zebra.jpg first, then apple.jpg in the same second, then
    # middle.jpg 2s later. apple and zebra have the same wall-clock
    # second → same ctime on Windows (birthtime resolution = 100ns but
    # filesystem mtime resolution is often 1s).
    (sub / "zebra.jpg").write_bytes(b"z")
    time.sleep(0.05)  # ensure file system can record distinct timestamps
    apple_path = sub / "apple.jpg"
    apple_path.write_bytes(b"a")
    zebra_path = sub / "zebra.jpg"
    # Force zebra and apple to share ctime/mtime exactly.
    fixed = 1_700_000_000
    os.utime(zebra_path, (fixed, fixed))
    os.utime(apple_path, (fixed, fixed))
    # middle.jpg is later.
    middle_path = sub / "middle.jpg"
    middle_path.write_bytes(b"m")
    os.utime(middle_path, (fixed + 100, fixed + 100))

    monkeypatch.setattr(
        gallery,
        "get_settings",
        lambda: SimpleNamespace(
            get_download_folder=lambda: root,
            get_twitter_download_folder=lambda: tmp_path / "tw",
            get_tiktok_download_folder=lambda: tmp_path / "tt",
        ),
    )

    with TestClient(app) as client:
        r = client.get("/api/gallery/search", params={"q": ".jpg"})
    assert r.status_code == 200
    data = r.json()
    names = [item["name"] for item in data["items"]]

    # middle.jpg has the newest ctime, must be first.
    assert names[0] == "middle.jpg", f"newest should be first, got {names}"
    # apple.jpg and zebra.jpg tie on ctime — secondary key must be
    # name asc, so apple before zebra.
    tied = sorted(names[1:])
    assert tied == ["apple.jpg", "zebra.jpg"], (
        f"tied-cfile order is not stable: got {tied}"
    )
