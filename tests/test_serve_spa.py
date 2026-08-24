"""Tests for the lightweight production SPA server."""

import xml.etree.ElementTree as ET

from starlette.testclient import TestClient

from backend.serve_spa import DIST_DIR, app
from backend.seo import CANONICAL_PUBLIC_RESEARCH_PATHS

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


def test_research_route_includes_pre_javascript_content_and_metadata() -> None:
    response = client.get("/research/players")
    assert response.status_code == 200
    assert "<h1>Baseball player research</h1>" in response.text
    assert '<a href="/research/matchups">Matchup research</a>' in response.text
    assert "<title data-seo-title>Baseball Player Research | MONEYLINE</title>" in response.text
    assert (
        'href="https://money-ball-betting.replit.app/research/players"'
        in response.text
    )


def test_sitemap_lists_only_canonical_public_routes() -> None:
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(response.text)
    namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locations = [
        element.text
        for element in root.findall("sitemap:url/sitemap:loc", namespace)
    ]
    expected = {
        f"https://money-ball-betting.replit.app{path}"
        for path in CANONICAL_PUBLIC_RESEARCH_PATHS
    }
    assert set(locations) == expected
    assert "https://money-ball-betting.replit.app/players" not in locations


def test_robots_advertises_the_sitemap() -> None:
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Sitemap: https://money-ball-betting.replit.app/sitemap.xml" in response.text


def test_unknown_clean_url_is_a_real_404() -> None:
    response = client.get("/not-a-real-page")
    assert response.status_code == 404
    assert "<h1>Page not found</h1>" in response.text


def test_api_root_is_a_json_404_not_an_spa_response() -> None:
    response = client.get("/api")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "API route not found."}
    }


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
