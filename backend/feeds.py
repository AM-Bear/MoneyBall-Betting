"""Keyless MLB Stats API client with bounded concurrency and resilient fallbacks."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import httpx

from backend.inference import predict_from_inputs, predict_team
from backend.odds import (
    log5_probability,
    moneyline_to_probability,
    probability_to_moneyline,
    pythagorean_strength,
)


MLB_BASE_URL = "https://statsapi.mlb.com"
EASTERN = ZoneInfo("America/New_York")
USER_AGENT = "MONEYLINE/1.0 (statistical research terminal)"
TEAM_CODES = {
    "Arizona Diamondbacks": "ARI",
    "Athletics": "ATH",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SDP",
    "San Francisco Giants": "SFG",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TBR",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSN",
}
HISTORICAL_TEAMS = [
    ("OAK", 2002, "FOUNDING EXAMPLE"),
    ("NYY", 1998, "114-WIN POWERHOUSE"),
    ("SEA", 2001, "116-WIN RECORD"),
    ("BOS", 2004, "CURSE REVERSED"),
    ("NYM", 1962, "THE MODEL FLOOR"),
]


class FeedUnavailable(RuntimeError):
    """Raised when an MLB feed cannot be used after one retry."""


class AsyncTTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_set(
        self, key: str, loader: Callable[[], Awaitable[Any]]
    ) -> tuple[Any, bool]:
        cached = self._items.get(key)
        if cached and time.monotonic() - cached[0] < self.ttl_seconds:
            return cached[1], True
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._items.get(key)
            if cached and time.monotonic() - cached[0] < self.ttl_seconds:
                return cached[1], True
            value = await loader()
            self._items[key] = (time.monotonic(), value)
            return value, False


cache = AsyncTTLCache(int(os.getenv("CACHE_TTL_SECONDS", "600")))
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        timeout = float(os.getenv("FEED_TIMEOUT_SECONDS", "10"))
        _client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _fetch_json(path: str, params: dict[str, Any] | None = None) -> Any:
    client = _get_client()
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = await client.get(f"{MLB_BASE_URL}{path}", params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
            if attempt == 0:
                await asyncio.sleep(0.25)
    raise FeedUnavailable("MLB Stats API did not return usable data.") from last_error


async def _schedule(schedule_date: date) -> tuple[dict[str, Any], bool]:
    key = f"schedule:{schedule_date.isoformat()}"
    return await cache.get_or_set(
        key,
        lambda: _fetch_json(
            "/api/v1/schedule",
            {"sportId": 1, "date": schedule_date.isoformat()},
        ),
    )


async def _team_group_stats(
    team_id: int, season: int, group: str
) -> tuple[dict[str, Any], bool]:
    key = f"team:{team_id}:{season}:{group}"
    return await cache.get_or_set(
        key,
        lambda: _fetch_json(
            f"/api/v1/teams/{team_id}/stats",
            {"stats": "season", "group": group, "season": season},
        ),
    )


def _extract_stat(payload: dict[str, Any]) -> dict[str, Any]:
    stats = payload.get("stats", [])
    if not stats or not stats[0].get("splits"):
        raise FeedUnavailable("MLB team statistics are not available.")
    return stats[0]["splits"][0]["stat"]


async def _team_inputs(team_id: int, season: int) -> tuple[dict[str, float], bool]:
    (hitting, hit_cached), (pitching, pitch_cached) = await asyncio.gather(
        _team_group_stats(team_id, season, "hitting"),
        _team_group_stats(team_id, season, "pitching"),
    )
    hitting_stat = _extract_stat(hitting)
    pitching_stat = _extract_stat(pitching)
    return (
        {
            "obp": float(hitting_stat["obp"]),
            "slg": float(hitting_stat["slg"]),
            "oobp": float(pitching_stat["obp"]),
            "oslg": float(pitching_stat["slg"]),
        },
        hit_cached and pitch_cached,
    )


def _team_code(name: str) -> str:
    return TEAM_CODES.get(name, "".join(word[0] for word in name.split()).upper()[:3])


def _game_time_et(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(EASTERN).strftime("%-I:%M %p ET")


async def _price_game(game: dict[str, Any], season: int) -> dict[str, Any]:
    away_info = game["teams"]["away"]["team"]
    home_info = game["teams"]["home"]["team"]
    (away_inputs, away_cached), (home_inputs, home_cached) = await asyncio.gather(
        _team_inputs(int(away_info["id"]), season),
        _team_inputs(int(home_info["id"]), season),
    )
    away_model = predict_from_inputs(**away_inputs)
    home_model = predict_from_inputs(**home_inputs)
    away_strength = pythagorean_strength(
        away_model["predicted"]["rs"], away_model["predicted"]["ra"]
    )
    home_strength = pythagorean_strength(
        home_model["predicted"]["rs"], home_model["predicted"]["ra"]
    )
    model_prob_home = log5_probability(home_strength, away_strength)
    away_name = str(away_info["name"])
    home_name = str(home_info["name"])
    detailed_state = str(game.get("status", {}).get("detailedState", "Scheduled"))
    return {
        "game_pk": str(game["gamePk"]),
        "game_date": game["gameDate"][:10],
        "time_et": _game_time_et(game["gameDate"]),
        "status": detailed_state,
        "away": _team_code(away_name),
        "away_name": away_name,
        "home": _team_code(home_name),
        "home_name": home_name,
        "model_prob_home": round(model_prob_home, 4),
        "fair_lines": {
            "home": probability_to_moneyline(model_prob_home),
            "away": probability_to_moneyline(1 - model_prob_home),
        },
        "away_inputs": away_inputs,
        "home_inputs": home_inputs,
        "badges": ["LIVE"] if detailed_state.lower() not in {"scheduled", "pre-game"} else [],
        "cache_hit": away_cached and home_cached,
    }


def historical_slate(reason: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for team, year, label in HISTORICAL_TEAMS:
        priced = predict_team(team, year)
        fair_line = priced["fair_line"]
        away_probability = (
            moneyline_to_probability(fair_line) if fair_line is not None else None
        )
        rows.append(
            {
                "game_pk": f"historical-{team}-{year}",
                "team": team,
                "year": year,
                "game_date": None,
                "time_et": "HISTORICAL",
                "status": label,
                "away": team,
                "away_name": f"{team} {year}",
                "home": "AVG",
                "home_name": "League-average baseline",
                "model_prob_home": (
                    round(1 - away_probability, 4)
                    if away_probability is not None
                    else None
                ),
                "fair_lines": {
                    "away": fair_line,
                    "home": (
                        probability_to_moneyline(1 - away_probability)
                        if away_probability is not None
                        else None
                    ),
                },
                "away_inputs": priced["inputs"],
                "offense_only": priced["offense_only"],
                "badges": [
                    "HISTORICAL",
                    *(["OFFENSE ONLY"] if priced["offense_only"] else []),
                ],
                "cache_hit": True,
            }
        )
    return {
        "mode": "historical",
        "feed_up": False,
        "date": datetime.now(EASTERN).date().isoformat(),
        "updated_at": datetime.now(EASTERN).isoformat(),
        "reason": reason,
        "games": rows,
        "cache": "fallback",
    }


async def get_slate(schedule_date: date | None = None) -> dict[str, Any]:
    target_date = schedule_date or datetime.now(EASTERN).date()
    try:
        payload, schedule_cached = await _schedule(target_date)
        dates = payload.get("dates", [])
        games = dates[0].get("games", []) if dates else []
        if not games:
            return historical_slate("No MLB games are scheduled for this date.")

        semaphore = asyncio.Semaphore(3)

        async def bounded_price(game: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                try:
                    return await _price_game(game, target_date.year)
                except Exception:
                    away = game["teams"]["away"]["team"]
                    home = game["teams"]["home"]["team"]
                    return {
                        "game_pk": str(game["gamePk"]),
                        "game_date": game["gameDate"][:10],
                        "time_et": _game_time_et(game["gameDate"]),
                        "away": _team_code(str(away["name"])),
                        "home": _team_code(str(home["name"])),
                        "status": str(game.get("status", {}).get("detailedState", "Scheduled")),
                        "pricing_error": True,
                        "badges": ["FEED PARTIAL"],
                    }

        priced_games = await asyncio.gather(*(bounded_price(game) for game in games))
        successful = [game for game in priced_games if not game.get("pricing_error")]
        if not successful:
            return historical_slate("Live schedule loaded, but team statistics were unavailable.")
        return {
            "mode": "live",
            "feed_up": True,
            "date": target_date.isoformat(),
            "updated_at": datetime.now(EASTERN).isoformat(),
            "games": priced_games,
            "cache": "hit"
            if schedule_cached and all(game.get("cache_hit") for game in successful)
            else "miss",
        }
    except FeedUnavailable:
        return historical_slate("MLB Stats API is temporarily unavailable.")


async def get_final_score(game_pk: str) -> dict[str, Any] | None:
    payload = await _fetch_json(f"/api/v1.1/game/{game_pk}/feed/live")
    state = payload.get("gameData", {}).get("status", {}).get("abstractGameState")
    if state != "Final":
        return None
    teams = payload["gameData"]["teams"]
    linescore = payload["liveData"]["linescore"]["teams"]
    return {
        "game_pk": game_pk,
        "away": _team_code(str(teams["away"]["name"])),
        "home": _team_code(str(teams["home"]["name"])),
        "final_away": int(linescore["away"]["runs"]),
        "final_home": int(linescore["home"]["runs"]),
    }