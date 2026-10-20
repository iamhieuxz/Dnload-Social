from fastapi.testclient import TestClient
from pathlib import Path
from types import SimpleNamespace

from app.main import app
from app.api import gallery


def test_gallery_roots_follow_platform_settings(monkeypatch, tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("instagram", "twitter", "tiktok")]
    monkeypatch.setattr(
        gallery,
        "get_settings",
        lambda: SimpleNamespace(
            get_download_folder=lambda: roots[0],
            get_twitter_download_folder=lambda: roots[1],
            get_tiktok_download_folder=lambda: roots[2],
        ),
    )
    assert gallery._gallery_roots() == roots
    assert gallery._gallery_root() == tmp_path
    assert gallery._safe_path("instagram/user/file.mp4") == roots[0] / "user" / "file.mp4"
    assert gallery._safe_path("twitter/user/file.mp4") == roots[1] / "user" / "file.mp4"
    assert gallery._to_rel(roots[1] / "user" / "file.mp4") == "twitter/user/file.mp4"


def test_local_health_endpoint_remains_available() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200


def test_rejects_non_local_host() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"host": "attacker.example"})
    assert response.status_code == 400


def test_rejects_non_loopback_client() -> None:
    with TestClient(app, client=("203.0.113.10", 12345)) as client:
        response = client.get("/api/health")
    assert response.status_code == 403
