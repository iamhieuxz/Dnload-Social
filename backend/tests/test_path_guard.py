"""Tests for path-allow-list guard in app.core.url_guard."""
from __future__ import annotations

from pathlib import Path  # noqa: F401  (pytest tmp_path uses it transitively)

from app.core.url_guard import is_path_inside_any


def test_child_inside_root(tmp_path: Path):
    root = tmp_path / "downloads"
    root.mkdir()
    child = root / "instagram" / "user" / "post.jpg"
    child.parent.mkdir(parents=True)
    child.write_bytes(b"x")
    assert is_path_inside_any(child, [root]) is True


def test_child_outside_root(tmp_path: Path):
    root = tmp_path / "downloads"
    root.mkdir()
    outside = tmp_path / "secrets" / "cookie.txt"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"x")
    assert is_path_inside_any(outside, [root]) is False


def test_traversal_blocked(tmp_path: Path):
    """A path that lexically looks inside but resolves outside must fail."""
    root = tmp_path / "downloads"
    root.mkdir()
    sibling = tmp_path / "etc"
    sibling.mkdir()
    tricky = root / ".." / "etc" / "passwd"
    # On Windows, `..` from root resolves into the parent; not inside root.
    assert is_path_inside_any(tricky, [root]) is False


def test_relative_path_string_resolved(tmp_path: Path):
    """A bare relative string is resolved against cwd, not the root —
    unless it happens to land inside. Keep the test deterministic by
    giving a path that resolves to the tmp dir which is NOT the root.
    """
    root = tmp_path / "downloads"
    root.mkdir()
    assert is_path_inside_any("not-relative.txt", [root]) is False


def test_multiple_roots_first_match(tmp_path: Path):
    a = tmp_path / "ig"
    b = tmp_path / "tw"
    a.mkdir()
    b.mkdir()
    target = b / "user" / "file.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    assert is_path_inside_any(target, [a, b]) is True
