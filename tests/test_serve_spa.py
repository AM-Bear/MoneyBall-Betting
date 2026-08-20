"""Tests for the lightweight production SPA server."""

from starlette.testclient import TestClient

from backend.serve_spa import DIST_DIR, app

client = TestClient(app)


def _first_asset() -> str | None:
    assets = DIST_DIR / "assets"
    if not assets.is_dir():
        return None
    for entry in sorted(assets.iterdir()):
        if entry.suffix == ".js":
            return f"assets/{entry.name}"
    return None


def test_root_serves_index() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"


def test_deep_link_falls_back_to_index() -> None:
    response = client.get("/players")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_hashed_asset_is_immutable() -> None:
    asset = _first_asset()
    assert asset is not None, "frontend build output missing; run the vite build first"
    response = client.get(f"/{asset}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "javascript" in response.headers["content-type"]


def test_missing_asset_is_404_not_index() -> None:
    response = client.get("/assets/does-not-exist-abc123.js")
    assert response.status_code == 404


def test_missing_file_like_path_is_404() -> None:
    response = client.get("/favicon-nope.ico")
    assert response.status_code == 404


def test_traversal_is_not_served() -> None:
    response = client.get("/%2e%2e/%2e%2e/backend/main.py")
    assert response.status_code in (200, 404)
    assert "backend.precompute" not in response.text
    assert "FastAPI" not in response.text
