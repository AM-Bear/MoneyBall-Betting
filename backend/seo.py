"""Small, dependency-free SEO responses shared by MONEYLINE servers.

The frontend is intentionally still a client-rendered React app.  These
responses provide useful HTML to crawlers and link unfurlers before JavaScript
loads, while the normal React root takes over for interactive use.
"""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin


SITE_URL = os.getenv("MONEYLINE_SITE_URL", "https://money-ball-betting.replit.app").rstrip(
    "/"
)
# The marker the Vite template ships in place of route content. Exported
# because backend.serve_spa has to recognise an UNrendered shell, and two
# copies of this string would drift.
SEO_CONTENT_PLACEHOLDER = "<!-- server-seo-content -->"
SEO_STRUCTURED_DATA_PLACEHOLDER = "<!-- server-seo-structured-data -->"

SITEMAP_PATH = "/sitemap.xml"
SEO_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "artifacts" / "moneyline" / "seo-config.json"
)


@dataclass(frozen=True)
class RouteMetadata:
    title: str
    description: str
    canonical_path: str
    indexable: bool
    public: bool


def _load_route_metadata() -> tuple[
    dict[str, RouteMetadata], dict[str, str]
]:
    """Load the JSON metadata source consumed by every MONEYLINE renderer."""
    try:
        config = json.loads(SEO_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Unable to load the shared SEO config at {SEO_CONFIG_PATH}."
        ) from exc

    raw_routes = config.get("routes")
    raw_aliases = config.get("aliases")
    if not isinstance(raw_routes, dict) or not isinstance(raw_aliases, dict):
        raise RuntimeError("Shared SEO config must define object-valued routes and aliases.")

    required = {"title", "description", "canonicalPath", "indexable", "public"}
    routes: dict[str, RouteMetadata] = {}
    for path, raw_route in raw_routes.items():
        if not isinstance(path, str) or not path.startswith("/") or not isinstance(
            raw_route, dict
        ):
            raise RuntimeError("Shared SEO config contains an invalid route.")
        missing = required - raw_route.keys()
        if missing:
            raise RuntimeError(
                f"Shared SEO config route {path!r} is missing: {sorted(missing)!r}."
            )
        title = raw_route["title"]
        description = raw_route["description"]
        canonical_path = raw_route["canonicalPath"]
        indexable = raw_route["indexable"]
        public = raw_route["public"]
        if not (
            isinstance(title, str)
            and isinstance(description, str)
            and isinstance(canonical_path, str)
            and canonical_path.startswith("/")
            and type(indexable) is bool
            and type(public) is bool
        ):
            raise RuntimeError(f"Shared SEO config route {path!r} has invalid metadata.")
        routes[path] = RouteMetadata(
            title=title,
            description=description,
            canonical_path=canonical_path,
            indexable=indexable,
            public=public,
        )

    aliases: dict[str, str] = {}
    for alias, canonical in raw_aliases.items():
        if (
            not isinstance(alias, str)
            or not alias.startswith("/")
            or not isinstance(canonical, str)
            or canonical not in routes
        ):
            raise RuntimeError("Shared SEO config contains an invalid route alias.")
        aliases[alias] = canonical

    for path, metadata in routes.items():
        if metadata.canonical_path not in routes:
            raise RuntimeError(
                f"Shared SEO config route {path!r} has an unknown canonical path."
            )
    return routes, aliases


ROUTE_METADATA, ALIASED_CANONICAL_PATHS = _load_route_metadata()


@dataclass(frozen=True)
class RouteSeo:
    heading: str
    eyebrow: str
    intro: str
    sections: tuple[tuple[str, str], ...]
    links: tuple[tuple[str, str], ...]


COMMON_LINKS = (
    ("Research hub", "/research"),
    ("Baseball trading desk", "/desk"),
    ("Model track record", "/track-record"),
    ("Player research", "/research/players"),
    ("Matchup research", "/research/matchups"),
    ("Parlay research", "/research/parlay"),
    ("Season research", "/research/season"),
    ("Baseball wire", "/research/wire"),
)

# Keep these destinations aligned between the visible server copy and the
# research hub's server-rendered ItemList schema.
RESEARCH_DESTINATIONS = (
    (
        "/research/players",
        "Players",
        "Compare hitting and pitching profiles with live-season context.",
    ),
    (
        "/research/matchups",
        "Matchups",
        "Put two teams or players side by side and inspect the model inputs.",
    ),
    (
        "/research/season",
        "Season outlook",
        "Review projected wins, playoff odds, and remaining-schedule context.",
    ),
    (
        "/research/wire",
        "Wire",
        "Read injury, roster, and research context without treating it as a price input.",
    ),
)

RESEARCH_STRUCTURED_DATA_DESCRIPTION = (
    "Baseball research surfaces for players, matchups, season outlook, and wire context."
)
TRACK_RECORD_STRUCTURED_DATA_DESCRIPTION = (
    "A public MONEYLINE record showing live grading, starter-adjusted grading, "
    "paper parlays, and historical simulation as separate views."
)


ROUTE_SEO: dict[str, RouteSeo] = {
    "/": RouteSeo(
        heading="Baseball research, priced transparently",
        eyebrow="MONEYLINE / STATISTICAL RESEARCH DESK",
        intro=(
            "Explore model-based baseball research built from verified data, "
            "disclosed assumptions, and honest refusals instead of fake precision."
        ),
        sections=(
            (
                "A research desk, not a black box",
                "MONEYLINE translates historical team performance into readable "
                "prices and keeps the evidence behind each result visible.",
            ),
            (
                "Start with a public research page",
                "Review the research hub, inspect the model record, or open a "
                "focused player, matchup, parlay, season, or wire workspace.",
            ),
        ),
        links=COMMON_LINKS,
    ),
    "/research": RouteSeo(
        heading="Baseball research hub",
        eyebrow="MONEYLINE / RESEARCH",
        intro=(
            "A starting point for transparent baseball analysis, with each "
            "workspace focused on a distinct question."
        ),
        sections=(
            (
                "Research paths",
                "Compare player profiles, evaluate head-to-head matchups, test "
                "parlay math, inspect season outlooks, and read baseball news "
                "and transaction context.",
            ),
        ),
        links=tuple((label, href) for href, label, _ in RESEARCH_DESTINATIONS),
    ),
    "/track-record": RouteSeo(
        heading="Baseball model track record",
        eyebrow="MONEYLINE / TRACK RECORD",
        intro=(
            "See how the model's paper picks have performed, with the grading "
            "rules and limitations shown alongside the record."
        ),
        sections=(
            (
                "Receipts over hindsight",
                "The record separates model outputs from later game results so "
                "performance can be reviewed without rewriting the original pick.",
            ),
        ),
        links=(
            ("Research hub", "/research"),
            ("Today's slate", "/"),
            ("Season research", "/research/season"),
        ),
    ),
    "/research/players": RouteSeo(
        heading="Baseball player research",
        eyebrow="MONEYLINE / PLAYERS",
        intro=(
            "Search the live player pool and inspect the context behind a "
            "player's statistical profile."
        ),
        sections=(
            (
                "Player context",
                "Profiles use transparent statistical comparisons and disclose "
                "when a requested player or comparison is outside the supported "
                "research pool.",
            ),
        ),
        links=(
            ("Research hub", "/research"),
            ("Matchup research", "/research/matchups"),
            ("Season research", "/research/season"),
        ),
    ),
    "/research/matchups": RouteSeo(
        heading="Baseball matchup research",
        eyebrow="MONEYLINE / MATCHUPS",
        intro=(
            "Compare teams or players side by side and see the inputs that "
            "shape the matchup context."
        ),
        sections=(
            (
                "Compare the evidence",
                "Matchup views surface historical team inputs and player "
                "context without pretending that context alone changes a fair "
                "price.",
            ),
        ),
        links=(
            ("Research hub", "/research"),
            ("Player research", "/research/players"),
            ("Today's slate", "/"),
        ),
    ),
    "/research/parlay": RouteSeo(
        heading="Baseball parlay research",
        eyebrow="MONEYLINE / PARLAY LAB",
        intro=(
            "Build a paper parlay and inspect the probability, expected value, "
            "vig comparison, and staking math instead of chasing a headline."
        ),
        sections=(
            (
                "Math before marketing",
                "The parlay lab distinguishes model probability from a supplied "
                "book line and refuses to show an edge until the required price "
                "inputs are valid.",
            ),
        ),
        links=(
            ("Research hub", "/research"),
            ("Today's slate", "/"),
            ("Model track record", "/track-record"),
        ),
    ),
    "/research/season": RouteSeo(
        heading="MLB season research",
        eyebrow="MONEYLINE / SEASON DESK",
        intro=(
            "Review current-season team outlooks and the assumptions behind "
            "the remaining-schedule research."
        ),
        sections=(
            (
                "Outlooks with disclosed limits",
                "Season views use the current live season and show when inputs "
                "are unavailable rather than filling gaps with invented numbers.",
            ),
        ),
        links=(
            ("Research hub", "/research"),
            ("Today's slate", "/"),
            ("Baseball wire", "/research/wire"),
        ),
    ),
    "/research/wire": RouteSeo(
        heading="MLB baseball wire",
        eyebrow="MONEYLINE / WIRE",
        intro=(
            "Follow transactions, baseball news, and team context from a "
            "research-first view of the current MLB environment."
        ),
        sections=(
            (
                "Context, not hidden price inputs",
                "Wire notes and media pulse help explain what is happening "
                "around a team; they are disclosed context and do not silently "
                "move the model's price.",
            ),
        ),
        links=(
            ("Research hub", "/research"),
            ("Season research", "/research/season"),
            ("Today's slate", "/"),
        ),
    ),
    "/desk": RouteSeo(
        heading="Baseball trading desk",
        eyebrow="MONEYLINE / DESK",
        intro=(
            "Review model pricing and the data receipts behind a baseball "
            "team's current research profile."
        ),
        sections=(
            (
                "Model inputs in view",
                "The desk keeps the model's assumptions and evidence close to "
                "the price so a result can be inspected rather than accepted "
                "on trust.",
            ),
        ),
        links=(
            ("Research hub", "/research"),
            ("Today's slate", "/"),
            ("Model track record", "/track-record"),
        ),
    ),
    "/settings": RouteSeo(
        heading="MONEYLINE settings",
        eyebrow="MONEYLINE / SETTINGS",
        intro="Presentation controls for the MONEYLINE research desk.",
        sections=(),
        links=(("Return to research", "/research"),),
    ),
}

# The shared config is also the authority for public server routes and sitemap
# inclusion. Shortcut aliases are supported but intentionally remain absent
# from the sitemap.
PUBLIC_CLIENT_ROUTE_PATHS = frozenset(
    {
        *(
            path
            for path, metadata in ROUTE_METADATA.items()
            if metadata.public
        ),
        *ALIASED_CANONICAL_PATHS,
    }
)

CANONICAL_PUBLIC_RESEARCH_PATHS = tuple(
    path
    for path, metadata in ROUTE_METADATA.items()
    if metadata.public and metadata.indexable
)

def normalize_route_path(path: str) -> str:
    """Normalize clean client paths without accepting arbitrary URL shapes."""
    if not path or path == "/":
        return "/"
    return "/" + path.strip("/")


def canonical_path_for(path: str) -> str:
    normalized = normalize_route_path(path)
    return ALIASED_CANONICAL_PATHS.get(normalized, normalized)


def route_seo_for(path: str) -> RouteSeo | None:
    return ROUTE_SEO.get(canonical_path_for(path))


def route_metadata_for(path: str) -> RouteMetadata | None:
    return ROUTE_METADATA.get(canonical_path_for(path))


def is_public_client_route(path: str) -> bool:
    return normalize_route_path(path) in PUBLIC_CLIENT_ROUTE_PATHS


def absolute_url(path: str, site_url: str = SITE_URL) -> str:
    return urljoin(f"{site_url.rstrip('/')}/", path.lstrip("/"))


def sitemap_xml(site_url: str = SITE_URL) -> str:
    urls = "\n".join(
        f"  <url><loc>{html.escape(absolute_url(path, site_url))}</loc></url>"
        for path in CANONICAL_PUBLIC_RESEARCH_PATHS
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )


def _seo_content(route: RouteSeo) -> str:
    sections = "".join(
        f"<section><h2>{html.escape(title)}</h2><p>{html.escape(copy)}</p></section>"
        for title, copy in route.sections
    )
    links = "".join(
        f'<li><a href="{html.escape(path)}">{html.escape(label)}</a></li>'
        for label, path in route.links
    )
    return (
        '<main id="seo-content" class="seo-content" aria-label="MONEYLINE research page">'
        f'<p class="seo-eyebrow">{html.escape(route.eyebrow)}</p>'
        f"<h1>{html.escape(route.heading)}</h1>"
        f"<p>{html.escape(route.intro)}</p>"
        f"{sections}"
        '<nav aria-label="MONEYLINE research links"><h2>Explore MONEYLINE</h2>'
        f"<ul>{links}</ul></nav>"
        "</main>"
    )


def _set_seo_attribute(markup: str, marker: str, attribute: str, value: str) -> str:
    """Rewrite ``attribute`` on the first tag carrying ``marker``.

    Order-independent, deliberately. The previous implementation matched
    ``<tag ... marker ... attribute="...">`` in one regex, which required the
    marker to appear BEFORE the attribute in source order. The template writes
    them the other way round -- ``<meta name="description" content="..."
    data-seo="description" data-seo-description />`` -- so every description,
    og:*, twitter:*, robots and canonical substitution silently matched
    nothing and every route served the homepage's metadata. A no-op regex
    fails quietly, which is why this survived a commit explicitly about
    crawlability.
    """
    tag_pattern = re.compile(r"<[^>]*\b" + re.escape(marker) + r"\b[^>]*>")
    match = tag_pattern.search(markup)
    if not match:
        return markup
    escaped = html.escape(value, quote=True)
    new_tag, replaced = re.subn(
        rf'(\b{re.escape(attribute)}=")[^"]*(")',
        lambda inner: f"{inner.group(1)}{escaped}{inner.group(2)}",
        match.group(0),
        count=1,
    )
    if not replaced:
        return markup
    return markup[: match.start()] + new_tag + markup[match.end() :]


def _json_ld_script(data: dict[str, object]) -> str:
    """Serialize JSON-LD safely for an inline script element."""
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    # JSON is inside HTML rather than an isolated response. Escape characters
    # that could terminate the script even if metadata later becomes editable.
    payload = (
        payload.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return f'<script type="application/ld+json">{payload}</script>'


def _route_structured_data(path: str, site_url: str = SITE_URL) -> str:
    """Return schema for public routes that have a dedicated page entity."""
    metadata = route_metadata_for(path)
    if metadata is None:
        return ""

    canonical = metadata.canonical_path
    if canonical == "/research":
        data: dict[str, object] = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "@id": f"{absolute_url('/research', site_url)}#webpage",
            "url": absolute_url("/research", site_url),
            "name": "Research | MONEYLINE",
            "description": RESEARCH_STRUCTURED_DATA_DESCRIPTION,
            "isPartOf": {"@id": f"{absolute_url('/', site_url)}#website"},
            "publisher": {"@id": f"{absolute_url('/', site_url)}#organization"},
            "about": {
                "@type": "Thing",
                "name": "Baseball statistical research",
            },
            "mainEntity": {
                "@type": "ItemList",
                "name": "MONEYLINE research destinations",
                "itemListOrder": "https://schema.org/ItemListOrderAscending",
                "numberOfItems": len(RESEARCH_DESTINATIONS),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": index,
                        "name": label,
                        "description": description,
                        "url": absolute_url(href, site_url),
                    }
                    for index, (href, label, description) in enumerate(
                        RESEARCH_DESTINATIONS, start=1
                    )
                ],
            },
        }
        return _json_ld_script(data)

    if canonical == "/track-record":
        data = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "@id": f"{absolute_url('/track-record', site_url)}#webpage",
            "url": absolute_url("/track-record", site_url),
            "name": "Track record | MONEYLINE",
            "description": TRACK_RECORD_STRUCTURED_DATA_DESCRIPTION,
            "isPartOf": {"@id": f"{absolute_url('/', site_url)}#website"},
            "publisher": {"@id": f"{absolute_url('/', site_url)}#organization"},
            "about": {
                "@type": "Thing",
                "name": "Baseball model track record",
            },
        }
        return _json_ld_script(data)

    return ""


def render_index(index_html: str, path: str) -> str:
    """Inject route-specific head tags and readable content into index.html."""
    route = route_seo_for(path) or ROUTE_SEO["/"]
    metadata = route_metadata_for(path) or ROUTE_METADATA["/"]
    canonical = absolute_url(metadata.canonical_path)
    robots = "index, follow" if metadata.indexable else "noindex, follow"

    rendered = index_html
    rendered = re.sub(
        r"(<title\b[^>]*data-seo-title[^>]*>).*?(</title>)",
        lambda match: f"{match.group(1)}{html.escape(metadata.title)}{match.group(2)}",
        rendered,
        count=1,
        flags=re.DOTALL,
    )
    for marker, value in (
        ("data-seo-description", metadata.description),
        ("data-seo-og-title", metadata.title),
        ("data-seo-og-description", metadata.description),
        ("data-seo-og-url", canonical),
        ("data-seo-twitter-title", metadata.title),
        ("data-seo-twitter-description", metadata.description),
        ("data-seo-robots", robots),
    ):
        rendered = _set_seo_attribute(rendered, marker, "content", value)
    rendered = _set_seo_attribute(rendered, "data-seo-canonical", "href", canonical)

    content = _seo_content(route)
    if SEO_CONTENT_PLACEHOLDER in rendered:
        rendered = rendered.replace(SEO_CONTENT_PLACEHOLDER, content, 1)
    else:
        rendered = rendered.replace(
            '<div id="root"></div>', f'<div id="root">{content}</div>', 1
        )
    structured_data = _route_structured_data(path)
    if SEO_STRUCTURED_DATA_PLACEHOLDER in rendered:
        rendered = rendered.replace(SEO_STRUCTURED_DATA_PLACEHOLDER, structured_data, 1)
    elif structured_data:
        rendered = rendered.replace("</head>", f"    {structured_data}\n  </head>", 1)
    return rendered


def not_found_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="robots" content="noindex"><title>Page not found | MONEYLINE</title></head>
  <body><main><h1>Page not found</h1><p>The MONEYLINE page you requested does not exist.</p><p><a href="/">Return to MONEYLINE</a></p></main></body>
</html>
"""