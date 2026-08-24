"""The MLB.com RSS headline feed, and ESPN's silent-skip contract.

``get_news()`` referenced three module names — ``RSS_URL``, ``ESPN_NEWS_URL``
and ``_espn_dead`` — that were never defined, so every call raised
``NameError``. ``wire.py``'s per-source ``safe()`` wrapper swallowed it, so the
only symptom was ``sources_up.news == false`` and a wire with no headlines.
These tests pin the contract that failure hid: the MLB feed parses, and the
optional ESPN source degrades silently without taking MLB down with it.
"""

from __future__ import annotations

from typing import Any

import pytest

import backend.feeds as feeds
from backend.feeds import get_news

RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>MLB News</title>
  <item>
    <title>Little Leaguers begged for a HR, and he delivered</title>
    <link>https://www.mlb.com/news/little-league-classic-2026</link>
    <pubDate>Mon, 24 Aug 2026 03:43:00 GMT</pubDate>
  </item>
  <item>
    <title>30 big questions for the stretch run</title>
    <link>https://www.mlb.com/news/big-questions-2026</link>
    <pubDate>Thu, 20 Aug 2026 15:30:00 GMT</pubDate>
  </item>
  <item>
    <title></title>
    <link>https://www.mlb.com/news/untitled</link>
  </item>
</channel></rss>
"""

ESPN_FIXTURE = {
    "articles": [
        {
            "headline": "2026 MLB ABS challenge system tracker",
            "dataSourceIdentifier": "5191d0555e510",
            "published": "2026-08-24T02:36:07Z",
            "links": {"web": {"href": "https://www.espn.com/mlb/story/_/id/48305211"}},
        }
    ]
}


class _FakeResponse:
    def __init__(self, text: str = "", payload: Any = None) -> None:
        self.text = text
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    """Stands in for the shared httpx client; records what was requested."""

    def __init__(self, rss: Any, espn: Any) -> None:
        self._rss = rss
        self._espn = espn
        self.requested: list[str] = []

    async def get(self, url: str, headers: dict[str, str] | None = None) -> Any:
        self.requested.append(url)
        source = self._rss if url == feeds.RSS_URL else self._espn
        if isinstance(source, Exception):
            raise source
        return source


@pytest.fixture(autouse=True)
def clean_news_state():
    """The news cache and the ESPN latch are module state — reset both."""
    feeds.wire_source_cache._items.pop("news", None)
    feeds._espn_dead = False
    yield
    feeds.wire_source_cache._items.pop("news", None)
    feeds._espn_dead = False


def _install(monkeypatch: pytest.MonkeyPatch, rss: Any, espn: Any) -> _FakeClient:
    client = _FakeClient(rss, espn)
    monkeypatch.setattr(feeds, "_get_client", lambda: client)
    return client


def test_news_source_constants_are_defined() -> None:
    """The regression guard: these three names were referenced but never defined."""
    assert feeds.RSS_URL == "https://www.mlb.com/feeds/news/rss.xml"
    assert feeds.ESPN_NEWS_URL.startswith("https://site.api.espn.com/")
    assert feeds._espn_dead is False


async def test_get_news_parses_mlb_rss(monkeypatch: pytest.MonkeyPatch) -> None:
    """Titled RSS items become wire rows; untitled ones are skipped."""
    _install(monkeypatch, _FakeResponse(text=RSS_FIXTURE), _FakeResponse(payload={"articles": []}))
    items = await get_news()

    mlb = [item for item in items if item["source"] == "MLB.COM"]
    assert len(mlb) == 2, "the untitled third <item> must be skipped"
    first = mlb[0]
    assert first["type"] == "NEWS"
    assert first["text"] == "Little Leaguers begged for a HR, and he delivered"
    assert first["link"] == "https://www.mlb.com/news/little-league-classic-2026"
    assert first["date"].startswith("2026-08-23"), "pubDate is converted to ET"
    assert first["id"] == f"rss-{first['link']}"


async def test_get_news_includes_espn_when_it_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """ESPN is a bonus second source when reachable."""
    _install(monkeypatch, _FakeResponse(text=RSS_FIXTURE), _FakeResponse(payload=ESPN_FIXTURE))
    items = await get_news()

    espn = [item for item in items if item["source"] == "ESPN"]
    assert len(espn) == 1
    assert espn[0]["text"] == "2026 MLB ABS challenge system tracker"
    assert espn[0]["link"] == "https://www.espn.com/mlb/story/_/id/48305211"
    assert feeds._espn_dead is False


async def test_dead_espn_does_not_break_the_mlb_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing ESPN fetch is skipped silently; MLB headlines still arrive."""
    _install(monkeypatch, _FakeResponse(text=RSS_FIXTURE), RuntimeError("ESPN 403"))
    items = await get_news()

    assert items, "a dead optional source must not empty the wire"
    assert {item["source"] for item in items} == {"MLB.COM"}
    assert feeds._espn_dead is True, "the optional source latches off after one failure"


async def test_espn_is_not_retried_once_latched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tried once per process, per spec — no retry storm against a dead source."""
    _install(monkeypatch, _FakeResponse(text=RSS_FIXTURE), RuntimeError("ESPN 403"))
    await get_news()

    feeds.wire_source_cache._items.pop("news", None)
    client = _install(monkeypatch, _FakeResponse(text=RSS_FIXTURE), RuntimeError("ESPN 403"))
    items = await get_news()

    assert feeds.ESPN_NEWS_URL not in client.requested
    assert client.requested == [feeds.RSS_URL]
    assert {item["source"] for item in items} == {"MLB.COM"}


async def test_a_dead_mlb_feed_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """MLB.com is the required source: wire.py's safe() decides how to degrade."""
    _install(monkeypatch, RuntimeError("MLB RSS 503"), _FakeResponse(payload=ESPN_FIXTURE))
    with pytest.raises(RuntimeError):
        await get_news()
