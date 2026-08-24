"""Tests for the lightweight production SPA server."""

import re
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
    # Asserted on the marker and the text, not on an exact attribute string.
    # The template carries both `data-seo="title"` and `data-seo-title`; the
    # old literal listed only the second and so failed against correct output.
    title = re.search(r"<title\b[^>]*\bdata-seo-title\b[^>]*>(.*?)</title>", response.text)
    assert title is not None, "the SEO title tag must survive rendering"
    assert title.group(1) == "Baseball Player Research | MONEYLINE"
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


def test_route_metadata_is_actually_rewritten_not_left_at_the_homepage_default() -> None:
    """Regression: the SEO rewrites used to silently match nothing.

    Each substitution was a single regex of the form
    `<tag ... marker ... content="...">`, which requires the marker to appear
    BEFORE the attribute in source order. The template writes them the other
    way round, so description, og:*, twitter:*, robots and canonical all
    no-opped and every route served the homepage's metadata. A regex that
    matches nothing fails silently, which is how this survived a commit
    explicitly about crawlability.
    """
    response = client.get("/research/players")
    assert response.status_code == 200
    body = response.text

    canonical = re.search(r'<link\b[^>]*\bdata-seo-canonical\b[^>]*>', body)
    assert canonical is not None
    assert "/research/players" in canonical.group(0), (
        "canonical must point at this route, not the site root"
    )

    for marker in ("data-seo-og-url", "data-seo-description", "data-seo-og-description"):
        tag = re.search(rf'<[^>]*\b{marker}\b[^>]*>', body)
        assert tag is not None, f"{marker} tag missing"
        content = re.search(r'content="([^"]*)"', tag.group(0))
        assert content is not None and content.group(1), f"{marker} has no content"

    og_url = re.search(r'<[^>]*\bdata-seo-og-url\b[^>]*>', body).group(0)
    assert "/research/players" in og_url

    # The homepage description must not leak onto a research route.
    home = client.get("/").text
    home_desc = re.search(
        r'<[^>]*\bdata-seo-description\b[^>]*>', home
    ).group(0)
    route_desc = re.search(
        r'<[^>]*\bdata-seo-description\b[^>]*>', body
    ).group(0)
    assert home_desc != route_desc, (
        "a route must not serve the homepage description"
    )
