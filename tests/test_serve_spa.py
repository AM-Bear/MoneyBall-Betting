"""Tests for the lightweight production SPA server."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from backend.serve_spa import DIST_DIR, app
from backend.seo import (
    ALIASED_CANONICAL_PATHS,
    CANONICAL_PUBLIC_RESEARCH_PATHS,
    ROUTE_METADATA,
    SEO_CONFIG_PATH,
    absolute_url,
    render_index,
)

client = TestClient(app)

# The tests marked below read the built frontend. `dist/` is gitignored, and it cannot be
# built on every machine (the workspace's pnpm overrides ship esbuild for linux-x64 only),
# so without it they skip with the reason -- the same convention the schema-backed tests
# use without DATABASE_URL. With a dist present they still fail loudly when it is stale,
# which is their job. Everything else in this file runs against the template and the
# routing rules and needs no build.
requires_dist = pytest.mark.skipif(
    not (DIST_DIR / "index.html").is_file(),
    reason="frontend build output missing (artifacts/moneyline/dist/public); run the vite build",
)


def _first_asset() -> str | None:
    assets = DIST_DIR / "assets"
    if not assets.is_dir():
        return None
    for entry in sorted(assets.iterdir()):
        if entry.suffix == ".js":
            return f"assets/{entry.name}"
    return None


@requires_dist
def test_root_serves_index() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"


@requires_dist
def test_deep_link_falls_back_to_index() -> None:
    response = client.get("/players")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@requires_dist
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

def test_server_metadata_matches_the_shared_route_source_for_all_public_urls() -> None:
    """Aliases and canonical pages must render the same source-defined metadata."""
    config = json.loads(SEO_CONFIG_PATH.read_text(encoding="utf-8"))
    template = (Path("artifacts/moneyline") / "index.html").read_text(encoding="utf-8")

    assert config["aliases"] == ALIASED_CANONICAL_PATHS
    for canonical_path, expected in config["routes"].items():
        metadata = ROUTE_METADATA[canonical_path]
        assert metadata.title == expected["title"]
        assert metadata.description == expected["description"]
        assert metadata.canonical_path == expected["canonicalPath"]
        assert metadata.indexable is expected["indexable"]
        assert metadata.public is expected["public"]

    public_paths = [
        path for path, metadata in ROUTE_METADATA.items() if metadata.public
    ]
    for path in [*public_paths, *ALIASED_CANONICAL_PATHS]:
        metadata = ROUTE_METADATA[ALIASED_CANONICAL_PATHS.get(path, path)]
        rendered = render_index(template, path)
        canonical = absolute_url(metadata.canonical_path)
        robots = "index, follow" if metadata.indexable else "noindex, follow"
        assert f"<title data-seo=\"title\" data-seo-title>{metadata.title}</title>" in rendered
        assert f'content="{metadata.description}"' in rendered
        assert f'content="{canonical}"' in rendered
        assert f'href="{canonical}"' in rendered
        assert f'content="{robots}"' in rendered


def _json_ld_documents(markup: str) -> list[dict[str, object]]:
    return [
        json.loads(payload)
        for payload in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            markup,
            flags=re.DOTALL,
        )
    ]


@requires_dist
def test_research_route_includes_its_collection_schema_before_javascript() -> None:
    response = client.get("/research")
    assert response.status_code == 200

    collection = next(
        document
        for document in _json_ld_documents(response.text)
        if document.get("@type") == "CollectionPage"
    )
    assert collection["url"] == "https://money-ball-betting.replit.app/research"
    assert collection["name"] == "Research | MONEYLINE"
    assert collection["isPartOf"] == {
        "@id": "https://money-ball-betting.replit.app/#website"
    }
    items = collection["mainEntity"]["itemListElement"]
    assert collection["mainEntity"]["numberOfItems"] == 4
    assert [item["name"] for item in items] == [
        "Players",
        "Matchups",
        "Season outlook",
        "Wire",
    ]
    assert [item["url"] for item in items] == [
        "https://money-ball-betting.replit.app/research/players",
        "https://money-ball-betting.replit.app/research/matchups",
        "https://money-ball-betting.replit.app/research/season",
        "https://money-ball-betting.replit.app/research/wire",
    ]


@requires_dist
def test_track_record_route_includes_its_page_schema_before_javascript() -> None:
    response = client.get("/track-record")
    assert response.status_code == 200

    page = next(
        document
        for document in _json_ld_documents(response.text)
        if document.get("@type") == "WebPage"
    )
    assert page == {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "@id": "https://money-ball-betting.replit.app/track-record#webpage",
        "url": "https://money-ball-betting.replit.app/track-record",
        "name": "Track record | MONEYLINE",
        "description": (
            "A public MONEYLINE record showing live grading, starter-adjusted grading, "
            "paper parlays, and historical simulation as separate views."
        ),
        "isPartOf": {"@id": "https://money-ball-betting.replit.app/#website"},
        "publisher": {"@id": "https://money-ball-betting.replit.app/#organization"},
        "about": {"@type": "Thing", "name": "Baseball model track record"},
    }


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


@requires_dist
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


@requires_dist
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


@requires_dist
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
