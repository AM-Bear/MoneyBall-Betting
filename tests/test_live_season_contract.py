"""The live-season contract: the backend clock is the single source of truth.

The frontend never hardcodes the live year — it reads ``season`` from
``/api/teams-live`` and derives labels, screener availability, and omnisearch
navigation from it. Backend payloads, error copy, simulation assumptions, and
cache keys must likewise derive from ``current_season()`` at request time.
These tests pin that contract, including the case where the server calendar
year advances.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

import backend.feeds as feeds
import backend.main as main
import backend.season_sim as season_sim
from backend.feeds import current_season
from backend.season_sim import assumptions, next_season_refusal


def _client() -> TestClient:
    return TestClient(main.app)


def _fake_directory(**overrides: Any):
    team = {
        "team_id": 147,
        "code": "NYY",
        "name": "New York Yankees",
        "wins": 71,
        "losses": 55,
        "games_played": 126,
    }
    team.update(overrides)

    async def loader() -> dict[int, dict[str, Any]]:
        return {147: team}

    return loader


# ---- /api/teams-live ----


def test_teams_live_reports_current_season(monkeypatch) -> None:
    """/api/teams-live carries the season and labels every team with it."""
    monkeypatch.setattr(main, "get_team_directory", _fake_directory())
    resp = _client().get("/api/teams-live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["season"] == current_season()
    assert body["teams"][0]["label"] == f"NYY {current_season()}"


def test_teams_live_season_tracks_server_clock(monkeypatch) -> None:
    """If the server clock rolls into a new season, the label rolls with it —
    the client must not assume any particular year."""
    future = current_season() + 1
    monkeypatch.setattr(main, "get_team_directory", _fake_directory(wins=0, losses=0, games_played=0))
    monkeypatch.setattr(main, "current_season", lambda: future)
    resp = _client().get("/api/teams-live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["season"] == future
    assert body["teams"][0]["label"] == f"NYY {future}"


# ---- /api/screener ----


def test_screener_accepts_the_live_season_year(monkeypatch) -> None:
    """year == current_season() routes to the live screener path."""
    sentinel = {"season_so_far": True, "year": current_season()}

    async def fake_live(season: int) -> dict[str, Any]:
        assert season == current_season()
        return sentinel

    monkeypatch.setattr(main, "_screener_live", fake_live)
    resp = _client().get(f"/api/screener?year={current_season()}")
    assert resp.status_code == 200
    assert resp.json() == sentinel


def test_screener_rejects_stale_live_year_when_clock_advances(monkeypatch) -> None:
    """Once the server clock says a new season, last season's year is no
    longer 'live' and gets the honest refusal, naming the new live year."""
    old_live = current_season()
    future = old_live + 1
    monkeypatch.setattr(main, "current_season", lambda: future)

    resp = _client().get(f"/api/screener?year={old_live}")
    assert resp.status_code == 400
    text = str(resp.json())
    assert "bad_year" in text
    assert str(future) in text  # the refusal advertises the actual live year


def test_screener_rejects_arbitrary_post_2012_year() -> None:
    resp = _client().get("/api/screener?year=2019")
    assert resp.status_code == 400
    assert "bad_year" in str(resp.json())


# ---- player pool / card error copy ----


def test_player_pool_error_copy_tracks_clock(monkeypatch) -> None:
    """503/404 copy names the live season derived at request time."""

    async def boom(*args: Any, **kwargs: Any):
        raise RuntimeError("feed down")

    future = current_season() + 2
    monkeypatch.setattr(main, "search_players", boom)
    monkeypatch.setattr(main, "current_season", lambda: future)
    resp = _client().get("/api/players?group=hitting")
    assert resp.status_code == 503
    assert str(future) in str(resp.json())


def test_player_card_not_found_copy_tracks_clock(monkeypatch) -> None:
    async def missing(player_id: int):
        return None

    future = current_season() + 2
    monkeypatch.setattr(main, "build_player_card", missing)
    monkeypatch.setattr(main, "current_season", lambda: future)
    resp = _client().get("/api/player/999999")
    assert resp.status_code == 404
    body = str(resp.json())
    assert str(future) in body
    assert "2026" not in body or str(future) == "2026"


# ---- season simulation ----


def test_sim_assumptions_and_refusal_track_season() -> None:
    """Assumption copy and the next-season refusal are built per request from
    the season argument — no import-time year baked in."""
    text = " ".join(assumptions(2031))
    assert "2031" in text
    # No stale year outside the fixed literal seed value.
    assert "2026" not in text.replace(str(season_sim.SIM_SEED), "")
    refusal = next_season_refusal(2031)
    assert refusal["season"] == 2032
    assert refusal["status"] == "NOT PRICED"


def test_season_sim_payload_and_cache_roll_with_clock(monkeypatch) -> None:
    """A cached sim payload from one season must not survive a clock advance:
    the signature is season-scoped, and the payload text tracks the season."""
    standings = [
        {
            "team_id": 147,
            "code": "NYY",
            "name": "New York Yankees",
            "league_id": 103,
            "division_id": 201,
            "wins": 71,
            "losses": 55,
            "games_played": 126,
        }
    ]

    async def fake_standings():
        return standings

    async def fake_inputs(team_id: int, season: int):
        return {"obp": 0.330, "slg": 0.420, "oobp": 0.310, "oslg": 0.390}, True

    async def fake_schedule():
        return []

    def fake_simulate(st: Any, strengths: Any, schedule: Any):
        return {
            147: {
                "expected_wins": 95.0,
                "playoff_odds": 0.9,
                "division_odds": 0.6,
                "win_distribution": [],
            }
        }

    monkeypatch.setattr(season_sim, "get_standings", fake_standings)
    monkeypatch.setattr(season_sim, "_team_inputs", fake_inputs)
    monkeypatch.setattr(season_sim, "get_remaining_schedule", fake_schedule)
    monkeypatch.setattr(season_sim, "simulate_season", fake_simulate)
    monkeypatch.setattr(season_sim, "_sim_cache", None)

    year_a = current_season()
    payload_a = asyncio.run(season_sim.get_season_sim())
    assert payload_a["season"] == year_a
    assert str(year_a) in " ".join(payload_a["assumptions"])
    assert payload_a["next_season"]["season"] == year_a + 1
    assert payload_a["input_signature"].startswith(f"{year_a}:")

    # Advance the clock: identical inputs, but the season-scoped signature
    # must force a recompute with the new season everywhere in the payload.
    year_b = year_a + 1
    monkeypatch.setattr(season_sim, "current_season", lambda: year_b)
    payload_b = asyncio.run(season_sim.get_season_sim())
    assert payload_b["season"] == year_b
    assert str(year_b) in " ".join(payload_b["assumptions"])
    assert payload_b["next_season"]["season"] == year_b + 1
    assert payload_b["input_signature"].startswith(f"{year_b}:")
    assert payload_b is not payload_a


# ---- live-feed cache isolation ----


def test_player_pool_cache_is_season_scoped(monkeypatch) -> None:
    """The pool cache key embeds the season: after a clock advance the loader
    refetches instead of serving the prior season's cached pool."""
    calls: list[int] = []

    def split(season: int) -> dict[str, Any]:
        return {
            "player": {"id": 1000 + season, "fullName": f"Pool Player {season}"},
            "team": {"id": 147, "name": "New York Yankees"},
            "position": {"abbreviation": "1B"},
            "stat": {
                "plateAppearances": 500,
                "gamesPlayed": 120,
                "avg": 0.280,
                "obp": 0.350,
                "slg": 0.450,
                "homeRuns": 20,
                "baseOnBalls": 50,
                "strikeOuts": 90,
            },
        }

    async def fake_fetch(path: str, params: dict[str, Any] | None = None):
        season = params["season"] if params else -1
        calls.append(season)
        return {"stats": [{"splits": [split(season)]}]}

    monkeypatch.setattr(feeds, "_fetch_json", fake_fetch)
    monkeypatch.setattr(feeds, "pool_cache", feeds.AsyncTTLCache(3600))

    year_a = current_season()
    asyncio.run(feeds.get_player_pool("hitting", "qualified"))
    assert calls and calls[-1] == year_a
    fetches_after_first = len(calls)

    # Same season again: served from cache, no new fetch.
    asyncio.run(feeds.get_player_pool("hitting", "qualified"))
    assert len(calls) == fetches_after_first

    # Clock advances: the season-scoped key misses and refetches for year_b.
    year_b = year_a + 1
    monkeypatch.setattr(feeds, "current_season", lambda: year_b)
    asyncio.run(feeds.get_player_pool("hitting", "qualified"))
    assert len(calls) > fetches_after_first
    assert calls[-1] == year_b


def test_standings_cache_is_season_scoped(monkeypatch) -> None:
    """get_standings() (the source behind /api/teams-live and the directory)
    must refetch after a clock advance instead of relabeling cached
    prior-season standings with the new year."""
    calls: list[tuple[str, Any]] = []

    def standings_payload(season: int) -> dict[str, Any]:
        return {
            "records": [
                {
                    "division": {"id": 200},
                    "league": {"id": 103},
                    "teamRecords": [
                        {
                            "team": {"id": 100 + i, "name": f"Team {i}"},
                            "wins": season % 1000,
                            "losses": i,
                            "gamesPlayed": 10,
                            "runsScored": 40,
                            "runsAllowed": 38,
                            "divisionRank": "1",
                        }
                        for i in range(30)
                    ],
                }
            ]
        }

    async def fake_fetch(path: str, params: dict[str, Any] | None = None):
        season = (params or {}).get("season")
        calls.append((path, season))
        if path == "/api/v1/standings":
            return standings_payload(season)
        return {"teams": [{"id": 100 + i, "name": f"Team {i}"} for i in range(30)]}

    monkeypatch.setattr(feeds, "_fetch_json", fake_fetch)
    monkeypatch.setattr(feeds, "_team_code", lambda name: "TST")
    monkeypatch.setattr(feeds, "cache", feeds.AsyncTTLCache(3600))

    year_a = current_season()
    rows_a = asyncio.run(feeds.get_standings())
    assert rows_a[0]["wins"] == year_a % 1000  # data really came from year A
    fetches = len(calls)

    # Same season: served from cache, no new upstream call.
    asyncio.run(feeds.get_standings())
    assert len(calls) == fetches

    # Clock advances: the season-scoped key misses and refetches for year B —
    # the old rows are never relabeled as the new season.
    year_b = year_a + 1
    monkeypatch.setattr(feeds, "current_season", lambda: year_b)
    rows_b = asyncio.run(feeds.get_standings())
    assert len(calls) > fetches
    assert rows_b[0]["wins"] == year_b % 1000
