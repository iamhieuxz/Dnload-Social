from pathlib import Path
from types import SimpleNamespace

from app.models.download import Platform
from app.services.job_runner import JobRunner


def test_output_resolution_uses_explicit_media_event(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "expected.mp4"
    output.write_bytes(b"media")
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(
            get_download_folder=lambda: tmp_path,
            get_twitter_download_folder=lambda: tmp_path,
            get_tiktok_download_folder=lambda: tmp_path,
        ),
    )
    download = SimpleNamespace(platform=Platform.INSTAGRAM.value)

    assert JobRunner()._find_output_file(
        download, [{"type": "media", "path": str(output)}]
    ) == (str(output), 5)


def test_output_resolution_never_guesses_newest_file(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "unrelated.mp4").write_bytes(b"unrelated")
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(
            get_download_folder=lambda: tmp_path,
            get_twitter_download_folder=lambda: tmp_path,
            get_tiktok_download_folder=lambda: tmp_path,
        ),
    )
    download = SimpleNamespace(platform=Platform.INSTAGRAM.value)

    assert JobRunner()._find_output_file(download, [{"type": "user_done"}]) == (None, 0)
