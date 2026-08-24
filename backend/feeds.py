"""Keyless MLB Stats API client with bounded concurrency and resilient fallbacks."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import logging

import httpx

from backend.analytics import (
    blend_defense_inputs,
    parse_innings,
    starter_innings_share,
)
from backend.inference import predict_from_inputs, predict_team
from backend.odds import (
    log5_probability,
    moneyline_to_probability,
    probability_to_moneyline,
    pythagorean_strength,
)


logger = logging.getLogger("moneyline")
MLB_BASE_URL = "https://statsapi.mlb.com"
EASTERN = ZoneInfo("America/New_York")
USER_AGENT = "MONEYLINE/1.0 (statistical research terminal)"
# Merged-wire headline sources. MLB.com RSS is the required feed; ESPN is the
# optional second source the spec allows and must never be a dependency.
# Dated curl transcripts for both live in notes/mlb_api_transcripts.md §8, §9.
RSS_URL = "https://www.mlb.com/feeds/news/rss.xml"
# site.web.api.espn.com, not site.api.espn.com. The latter sits behind an
# Akamai edge that 403s our identifying User-Agent; the former is served from
# ESPN's AWS origins and answers it with a byte-identical payload (34207 bytes,
# same 6 articles, verified 2026-08-24 -- see notes/decision-espn-user-agent.md).
# This is the honest fix: the alternative was presenting a browser User-Agent to
# get around the block, and USER_AGENT is shared with every statsapi.mlb.com
# call, so faking it there would have been both a lie and a wider blast radius.
# Still optional and still latched off by _espn_dead on any failure.
ESPN_NEWS_URL = "https://site.web.api.espn.com/apis/site/v2/sports/baseball/mlb/news"
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
# The `all` player pool floor: below this a sample is too small to assess.
POOL_FLOOR_PA = 100
POOL_FLOOR_IP = 30.0
HISTORICAL_TEAMS = [
    ("OAK", 2002, "FOUNDING EXAMPLE"),
    ("NYY", 1998, "114-WIN POWERHOUSE"),
    ("SEA", 2001, "116-WIN RECORD"),
    ("BOS", 2004, "CURSE REVERSED"),
    ("NYM", 1962, "THE MODEL FLOOR"),
]


class FeedUnavailable(RuntimeError):
    """Raised when an MLB feed cannot be used after one retry."""


class GameNotFound(FeedUnavailable):
    """Raised when the MLB feed no longer recognizes a game_pk (404)."""


class AsyncTTLCache:
    """Single-flight TTL cache with a bounded wait.

    Only one loader runs per key — without that, a cold ``/api/slate`` would let
    every concurrent request fan out its own 30-call roster sweep. But a caller
    must never be pinned to however long the upstream takes: ``FEED_TIMEOUT_SECONDS``
    (10s) applies per HTTP request, and a logical fetch retries once, so a slow
    (not dead) MLB API can stack up past two minutes behind one loader. A dead API
    degrades cleanly via ``historical_slate``; a slow one used to hang the app.

    So the loader runs as a shared task and callers wait on it with a deadline:

    * The task is **shielded**, so a caller giving up does not cancel work the
      next caller would benefit from — it keeps running and populates the cache.
    * On deadline, stale data is served if any exists (better a slightly old
      slate than none), otherwise ``FeedUnavailable`` propagates and the existing
      ``historical_slate`` fallback takes over.
    """

    def __init__(self, ttl_seconds: int, deadline_seconds: float | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self.deadline_seconds = (
            deadline_seconds
            if deadline_seconds is not None
            else float(os.getenv("FEED_DEADLINE_SECONDS", "25"))
        )
        self._items: dict[str, tuple[float, Any]] = {}
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    def _fresh(self, key: str) -> tuple[Any, bool] | None:
        cached = self._items.get(key)
        if cached and time.monotonic() - cached[0] < self.ttl_seconds:
            return cached[1], True
        return None

    async def _load(self, key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        try:
            value = await loader()
            self._items[key] = (time.monotonic(), value)
            return value
        finally:
            self._inflight.pop(key, None)

    async def get_or_set(
        self, key: str, loader: Callable[[], Awaitable[Any]]
    ) -> tuple[Any, bool]:
        hit = self._fresh(key)
        if hit is not None:
            return hit

        task = self._inflight.get(key)
        if task is None or task.done():
            # Re-check under no await: whoever gets here first owns the load.
            hit = self._fresh(key)
            if hit is not None:
                return hit
            task = asyncio.ensure_future(self._load(key, loader))
            self._inflight[key] = task

        try:
            value = await asyncio.wait_for(
                asyncio.shield(task), timeout=self.deadline_seconds
            )
            return value, False
        except asyncio.TimeoutError:
            stale = self._items.get(key)
            if stale is not None:
                logger.warning(
                    "feed_deadline_serving_stale key=%s deadline=%.1fs age=%.1fs",
                    key,
                    self.deadline_seconds,
                    time.monotonic() - stale[0],
                )
                return stale[1], True
            logger.warning(
                "feed_deadline_no_stale key=%s deadline=%.1fs — degrading",
                key,
                self.deadline_seconds,
            )
            raise FeedUnavailable(
                f"{key} exceeded the {self.deadline_seconds:.0f}s feed deadline"
            ) from None


cache = AsyncTTLCache(int(os.getenv("CACHE_TTL_SECONDS", "600")))
pool_cache = AsyncTTLCache(int(os.getenv("POOL_CACHE_TTL_SECONDS", "21600")))
wire_source_cache = AsyncTTLCache(int(os.getenv("WIRE_CACHE_TTL_SECONDS", "1800")))
_client: httpx.AsyncClient | None = None
# One-shot latch for the optional ESPN source: it is tried once per process and,
# once it fails, skipped for the rest of that process's life. Keyless, optional,
# and silent — MLB.com RSS is the only headline source the wire depends on.
_espn_dead = False


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
            if (
                isinstance(error, httpx.HTTPStatusError)
                and error.response.status_code == 404
            ):
                raise GameNotFound(
                    f"MLB Stats API has no resource at {path}."
                ) from error
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
            {
                "sportId": 1,
                "date": schedule_date.isoformat(),
                "hydrate": "probablePitcher,linescore",
            },
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


_TEAM_CODE_FALLBACKS_SEEN: set[str] = set()


def _team_code(name: str) -> str:
    code = TEAM_CODES.get(name)
    if code is not None:
        return code
    fallback = "".join(word[0] for word in name.split()).upper()[:3]
    if name not in _TEAM_CODE_FALLBACKS_SEEN:
        _TEAM_CODE_FALLBACKS_SEEN.add(name)
        logger.warning(
            "team_code_fallback name=%r code=%s — not in TEAM_CODES. "
            "If this is an MLB club (a rename?), stored and freshly derived codes "
            "will diverge and every affected pick grades LOSS. Add it to TEAM_CODES.",
            name,
            fallback,
        )
    return fallback


def _game_time_et(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(EASTERN).strftime("%-I:%M %p ET")

def _chain_probability(
    away_inputs: dict[str, float], home_inputs: dict[str, float]
) -> float:
    """Season chain: inputs → RS/RA models → Pythagorean → log5 (home prob)."""
    away_model = predict_from_inputs(**away_inputs)
    home_model = predict_from_inputs(**home_inputs)
    away_strength = pythagorean_strength(
        away_model["predicted"]["rs"], away_model["predicted"]["ra"]
    )
    home_strength = pythagorean_strength(
        home_model["predicted"]["rs"], home_model["predicted"]["ra"]
    )
    return log5_probability(home_strength, away_strength)
async def _price_game(
    game: dict[str, Any],
    season: int,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    away_info = game["teams"]["away"]["team"]
    home_info = game["teams"]["home"]["team"]
    (away_inputs, away_cached), (home_inputs, home_cached) = await asyncio.gather(
        _team_inputs(int(away_info["id"]), season),
        _team_inputs(int(home_info["id"]), season),
    )
    model_prob_home = _chain_probability(away_inputs, home_inputs)
    away_name = str(away_info["name"])
    home_name = str(home_info["name"])
    detailed_state = str(game.get("status", {}).get("detailedState", "Scheduled"))

    probables = {
        "away": _probable(game["teams"]["away"]),
        "home": _probable(game["teams"]["home"]),
    }
    adj_prob_home = None
    adj_fair_lines = None
    adj_detail = None
    flags: list[dict[str, Any]] = []
    if context is not None:
        away_blend, away_detail = _blended_side(
            probables["away"], away_inputs, context["pitchers_by_id"]
        )
        home_blend, home_detail = _blended_side(
            probables["home"], home_inputs, context["pitchers_by_id"]
        )
        if away_detail or home_detail:
            adj_prob_home = round(_chain_probability(away_blend, home_blend), 4)
            adj_fair_lines = {
                "home": probability_to_moneyline(adj_prob_home),
                "away": probability_to_moneyline(1 - adj_prob_home),
            }
            adj_detail = {
                "away": away_detail,
                "home": home_detail,
                "method": (
                    "ADJ blends each probable starter's OBP/SLG-against over his "
                    "innings share (capped 0.4–0.8) with the team rate as the "
                    "bullpen proxy, then reruns the same RA → Pythagorean → log5 "
                    "chain. SEASON stays unchanged; the Live Record grades both."
                ),
            }
        flags = [
            *context["flags"].get(int(away_info["id"]), []),
            *context["flags"].get(int(home_info["id"]), []),
        ]
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
        "probables": probables,
        "adj_prob": adj_prob_home,
        "adj_fair_lines": adj_fair_lines,
        "adj_detail": adj_detail,
        "flags": flags,
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

        context = await _slate_context(target_date.year)
        semaphore = asyncio.Semaphore(3)

        async def bounded_price(game: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                try:
                    return await _price_game(game, target_date.year, context)
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

def current_season() -> int:
    return datetime.now(EASTERN).year
async def get_final_score(game_pk: str) -> dict[str, Any] | None:
    """Resolve one game: a final score, a cancellation marker, or None (still pending).

    Cancelled games report abstractGameState "Final" with no played innings, so
    the cancellation check must run before the Final check — otherwise a 0–0
    "final" would keep the pick pending forever.
    """
    payload = await _fetch_json(f"/api/v1.1/game/{game_pk}/feed/live")
    status = payload.get("gameData", {}).get("status", {})
    detailed_state = str(status.get("detailedState", ""))
    coded_state = str(status.get("codedGameState", ""))
    if coded_state == "C" or detailed_state.lower().startswith("cancel"):
        return {"game_pk": game_pk, "status": "cancelled"}
    if status.get("abstractGameState") != "Final":
        return None
    teams = payload["gameData"]["teams"]
    linescore = payload["liveData"]["linescore"]["teams"]
    return {
        "game_pk": game_pk,
        "status": "final",
        "away": _team_code(str(teams["away"]["name"])),
        "home": _team_code(str(teams["home"]["name"])),
        "final_away": int(linescore["away"]["runs"]),
        "final_home": int(linescore["home"]["runs"]),
    }

async def get_player_pool(group: str, pool: str = "qualified") -> list[dict[str, Any]]:
    """League-wide current-season player pool, identity by player.id, cached ~6h.

    The `all` pool is floored app-side to ≥100 PA (hitters) / ≥30 IP
    (pitchers) so tiny samples never masquerade as assessable players.
    """
    if group not in {"hitting", "pitching"}:
        raise ValueError("group must be hitting or pitching")
    if pool not in {"qualified", "all"}:
        raise ValueError("pool must be qualified or all")

    async def loader() -> list[dict[str, Any]]:
        splits: list[dict[str, Any]] = []
        offset = 0
        for _page in range(5):
            payload = await _fetch_json(
                "/api/v1/stats",
                {
                    "stats": "season",
                    "group": group,
                    "season": current_season(),
                    "sportId": 1,
                    "playerPool": pool,
                    "limit": 2000,
                    "offset": offset,
                },
            )
            stats = payload.get("stats", [])
            page = stats[0].get("splits", []) if stats else []
            splits.extend(page)
            if len(page) < 2000:
                break
            offset += 2000
        normalize = _normalize_hitter if group == "hitting" else _normalize_pitcher
        players = [entry for entry in (normalize(split) for split in splits) if entry]
        if pool == "all":
            if group == "hitting":
                players = [p for p in players if p["pa"] >= POOL_FLOOR_PA]
            else:
                players = [p for p in players if p["ip"] >= POOL_FLOOR_IP]
        if not players:
            raise FeedUnavailable("The MLB player pool returned no usable rows.")
        return players

    value, _ = await pool_cache.get_or_set(f"pool:{current_season()}:{group}:{pool}", loader)
    return value

async def get_news() -> list[dict[str, Any]]:
    """MLB.com RSS headlines (+ ESPN when reachable), cached ~30m."""

    async def loader() -> list[dict[str, Any]]:
        import xml.etree.ElementTree as ElementTree

        client = _get_client()
        items: list[dict[str, Any]] = []
        response = await client.get(RSS_URL, headers={"Accept": "application/xml"})
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        for item in root.findall(".//item"):
            title = item.findtext("title")
            if not title:
                continue
            items.append(
                {
                    "id": f"rss-{item.findtext('link') or title}",
                    "type": "NEWS",
                    "text": title.strip(),
                    "team": None,
                    "date": _rss_date(item.findtext("pubDate")),
                    "source": "MLB.COM",
                    "link": item.findtext("link"),
                }
            )
        global _espn_dead
        if not _espn_dead:
            try:
                espn = await client.get(ESPN_NEWS_URL)
                espn.raise_for_status()
                for article in espn.json().get("articles", []):
                    headline = article.get("headline")
                    if not headline:
                        continue
                    items.append(
                        {
                            "id": f"espn-{article.get('dataSourceIdentifier', headline)}",
                            "type": "NEWS",
                            "text": str(headline).strip(),
                            "team": None,
                            "date": str(article.get("published", ""))[:19],
                            "source": "ESPN",
                            "link": article.get("links", {})
                            .get("web", {})
                            .get("href"),
                        }
                    )
            except Exception:
                # Optional source: skip silently per spec, never a dependency.
                # Latched off for this process; MLB.com RSS carries the wire.
                _espn_dead = True
                logger.debug("espn_news_unavailable — optional source latched off")
        return items

    value, _ = await wire_source_cache.get_or_set("news", loader)
    return value

async def get_rosters() -> dict[int, list[dict[str, Any]]]:
    """40-man rosters with status for all 30 teams, cached ~6h."""

    async def loader() -> dict[int, list[dict[str, Any]]]:
        directory = await get_team_directory()
        semaphore = asyncio.Semaphore(5)

        async def one(team_id: int) -> tuple[int, list[dict[str, Any]]]:
            async with semaphore:
                payload = await _fetch_json(
                    f"/api/v1/teams/{team_id}/roster",
                    {"rosterType": "40Man", "season": current_season()},
                )
                return team_id, [
                    {
                        "player_id": int(entry["person"]["id"]),
                        "name": str(entry["person"]["fullName"]),
                        "position": entry.get("position", {}).get("abbreviation"),
                        "status": str(entry.get("status", {}).get("description", "")),
                    }
                    for entry in payload.get("roster", [])
                ]

        pairs = await asyncio.gather(*(one(team_id) for team_id in directory))
        return dict(pairs)

    value, _ = await pool_cache.get_or_set(f"rosters:{current_season()}", loader)
    return value

async def get_season_dates() -> dict[str, str]:
    async def loader() -> dict[str, str]:
        payload = await _fetch_json(
            "/api/v1/seasons", {"season": current_season(), "sportId": 1}
        )
        seasons = payload.get("seasons", [])
        if not seasons:
            raise FeedUnavailable("MLB seasons metadata is unavailable.")
        return {
            "start": str(seasons[0]["regularSeasonStartDate"]),
            "end": str(seasons[0]["regularSeasonEndDate"]),
        }

    value, _ = await pool_cache.get_or_set(f"season_dates:{current_season()}", loader)
    return value

def _rss_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(raw).astimezone(EASTERN).isoformat()
    except Exception:
        return raw

async def get_standings() -> list[dict[str, Any]]:
    """Live standings — one row per team with W/L, RS/RA, GP, division."""

    async def loader() -> list[dict[str, Any]]:
        payload, teams_payload = await asyncio.gather(
            _fetch_json(
                "/api/v1/standings",
                {
                    "leagueId": "103,104",
                    "season": current_season(),
                    "standingsTypes": "regularSeason",
                },
            ),
            _fetch_json(
                "/api/v1/teams", {"sportId": 1, "season": current_season()}
            ),
        )
        # Standings carry short names ("Mets"); the teams endpoint owns the
        # full name, which maps through TEAM_CODES so every code in the app
        # (slate, record, wire, standings) stays identical.
        team_meta = {
            int(team["id"]): {"full_name": str(team.get("name", ""))}
            for team in teams_payload.get("teams", [])
        }
        teams: list[dict[str, Any]] = []
        for record in payload.get("records", []):
            division_id = record.get("division", {}).get("id")
            league_id = record.get("league", {}).get("id")
            for team_record in record.get("teamRecords", []):
                team_id = int(team_record["team"]["id"])
                meta = team_meta.get(team_id, {})
                name = meta.get("full_name") or str(team_record["team"]["name"])
                teams.append(
                    {
                        "team_id": team_id,
                        "name": name,
                        "code": _team_code(name),
                        "league_id": league_id,
                        "division_id": division_id,
                        "wins": int(team_record["wins"]),
                        "losses": int(team_record["losses"]),
                        "games_played": int(team_record["gamesPlayed"]),
                        "runs_scored": int(team_record.get("runsScored", 0)),
                        "runs_allowed": int(team_record.get("runsAllowed", 0)),
                        "division_rank": team_record.get("divisionRank"),
                    }
                )
        if len(teams) != 30:
            raise FeedUnavailable("Standings did not return all 30 teams.")
        return teams

    value, _ = await cache.get_or_set(f"standings:{current_season()}", loader)
    return value

async def get_prior_season_wins() -> dict[str, Any]:
    """Final regular-season wins for the prior season, keyed by team_id.

    The live screener's naive preseason prior. A finished season never
    changes, so this rides the long pool cache.
    """
    season = current_season() - 1

    async def loader() -> dict[str, Any]:
        payload = await _fetch_json(
            "/api/v1/standings",
            {
                "leagueId": "103,104",
                "season": season,
                "standingsTypes": "regularSeason",
            },
        )
        wins: dict[int, int] = {}
        for record in payload.get("records", []):
            for team_record in record.get("teamRecords", []):
                wins[int(team_record["team"]["id"])] = int(team_record["wins"])
        if len(wins) < 30:
            raise FeedUnavailable(f"{season} final standings are incomplete.")
        return {"season": season, "wins": wins}

    value, _ = await pool_cache.get_or_set(f"standings:final:{season}", loader)
    return value

def _majors_side(entry: dict[str, Any]) -> str | None:
    """Attribute a transaction to its major-league club.

    Even scoped to sportId=1, one end of a move is often an affiliate: an
    option-down has ``toTeam`` = "Buffalo Bisons" and ``fromTeam`` = "Toronto
    Blue Jays". Preferring ``toTeam`` unconditionally attributed the move to the
    affiliate, and ``_team_code`` then coined a phantom code from its initials.
    Whichever side is a real MLB club is the one the wire means.
    """
    to_name = (entry.get("toTeam") or {}).get("name")
    from_name = (entry.get("fromTeam") or {}).get("name")
    for name in (to_name, from_name):
        if name and name in TEAM_CODES:
            return str(name)
    return str(to_name or from_name) if (to_name or from_name) else None


async def get_transactions(days: int = 7) -> list[dict[str, Any]]:
    """Majors-relevant transactions from the last N days, cached ~30m."""

    async def loader() -> list[dict[str, Any]]:
        end = datetime.now(EASTERN).date()
        start = date.fromordinal(end.toordinal() - days)
        payload = await _fetch_json(
            "/api/v1/transactions",
            # sportId=1 scopes this to MLB. Without it the feed returns every
            # affiliated league -- Mexican League, Arizona Complex League, the
            # lot -- roughly 4x the rows, none of them majors-relevant.
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "sportId": 1,
            },
        )
        items: list[dict[str, Any]] = []
        for entry in payload.get("transactions", []):
            description = str(entry.get("description", "") or "")
            type_desc = str(entry.get("typeDesc", "") or "")
            wire_type = _classify_transaction(type_desc, description)
            if wire_type is None or not description:
                continue
            team_name = _majors_side(entry)
            items.append(
                {
                    "id": f"txn-{entry.get('id')}",
                    "type": wire_type,
                    "text": description,
                    "team": _team_code(str(team_name)) if team_name else None,
                    "date": str(entry.get("date", start.isoformat())),
                    "source": "TRANSACTION",
                    "link": None,
                }
            )
        return items

    value, _ = await wire_source_cache.get_or_set(f"transactions:{days}", loader)
    return value

async def get_remaining_schedule() -> list[dict[str, Any]]:
    """Remaining regular-season games (today → season end), cached ~6h."""

    async def loader() -> list[dict[str, Any]]:
        season_dates = await get_season_dates()
        today = datetime.now(EASTERN).date()
        payload = await _fetch_json(
            "/api/v1/schedule",
            {
                "sportId": 1,
                "startDate": today.isoformat(),
                "endDate": season_dates["end"],
                "gameType": "R",
            },
        )
        games: list[dict[str, Any]] = []
        for day in payload.get("dates", []):
            for game in day.get("games", []):
                state = game.get("status", {}).get("abstractGameState")
                if state == "Final":
                    continue
                games.append(
                    {
                        "game_pk": int(game["gamePk"]),
                        "date": str(game.get("officialDate", day.get("date"))),
                        "away_id": int(game["teams"]["away"]["team"]["id"]),
                        "home_id": int(game["teams"]["home"]["team"]["id"]),
                    }
                )
        return games

    value, _ = await pool_cache.get_or_set(f"remaining_schedule:{current_season()}", loader)
    return value

def _blended_side(
    probable: dict[str, Any] | None,
    team_inputs: dict[str, float],
    pitchers_by_id: dict[int, dict[str, Any]],
) -> tuple[dict[str, float], dict[str, Any] | None]:
    """Blend a team's defense inputs with its probable starter when possible."""
    if probable is None:
        return team_inputs, None
    starter = pitchers_by_id.get(probable["player_id"])
    if not starter or not starter["obp_against"] or not starter["slg_against"]:
        return team_inputs, None
    share = starter_innings_share(starter["ip"], starter["games_started"])
    if share is None:
        return team_inputs, None
    blend = blend_defense_inputs(
        starter["obp_against"],
        starter["slg_against"],
        team_inputs["oobp"],
        team_inputs["oslg"],
        share,
    )
    blended = {**team_inputs, "oobp": blend["oobp"], "oslg": blend["oslg"]}
    detail = {
        "starter": starter["name"],
        "player_id": starter["player_id"],
        "innings_share": share,
        "starter_obp_against": starter["obp_against"],
        "starter_slg_against": starter["slg_against"],
        "note": "Team rate is the bullpen proxy for the non-starter innings.",
    }
    return blended, detail

def _classify_transaction(type_desc: str, description: str) -> str | None:
    lowered_type = type_desc.lower()
    lowered_description = description.lower()
    if lowered_type == "trade":
        return "TRADE"
    if lowered_type in {"signed as free agent", "free agency"}:
        return "SIGNING" if "minor league" not in lowered_description else None
    if lowered_type == "released":
        return "SIGNING"
    if "injured list" in lowered_description or "il" in lowered_description.split():
        if "activated" in lowered_description or "reinstated" in lowered_description:
            return "ACTIVATED"
        if "placed" in lowered_description:
            return "IL"
    if lowered_type == "recalled" and "recalled" in lowered_description:
        return "ACTIVATED"
    return None

async def get_league_pool_context() -> dict[str, Any]:
    """League means and average team PA/IP, derived from the live pools."""

    async def loader() -> dict[str, Any]:
        qualified_hitters, qualified_pitchers, team_hitting, team_pitching = (
            await asyncio.gather(
                get_player_pool("hitting", "qualified"),
                get_player_pool("pitching", "qualified"),
                _league_team_stats("hitting"),
                _league_team_stats("pitching"),
            )
        )
        team_pa = [
            int(split["stat"].get("plateAppearances", 0)) for split in team_hitting
        ]
        team_ip = [
            parse_innings(split["stat"].get("inningsPitched")) for split in team_pitching
        ]
        return {
            "league_obp": _mean([p["obp"] for p in qualified_hitters]),
            "league_slg": _mean([p["slg"] for p in qualified_hitters]),
            "league_obp_against": _mean([p["obp_against"] for p in qualified_pitchers]),
            "league_slg_against": _mean([p["slg_against"] for p in qualified_pitchers]),
            "league_team_pa": _mean([float(v) for v in team_pa]),
            "league_team_ip": _mean(team_ip),
            "qualified_hitters": len(qualified_hitters),
            "qualified_pitchers": len(qualified_pitchers),
            "mean_definition": (
                f"League means are unweighted averages over the {current_season()} qualified pool; "
                "team PA/IP are league averages over all 30 teams."
            ),
        }

    value, _ = await pool_cache.get_or_set(f"pool:context:{current_season()}", loader)
    return value

async def get_team_live(team_id: int) -> dict[str, Any]:
    """Live current-season inputs + record for one team, from the same cached feeds."""
    directory = await get_team_directory()
    if team_id not in directory:
        raise FeedUnavailable("Unknown MLB team id.")
    inputs, _cached = await _team_inputs(team_id, current_season())
    return {
        **directory[team_id],
        "inputs": inputs,
        "sample_label": f"THRU {directory[team_id]['games_played']} GP",
    }

def _probable(game_side: dict[str, Any]) -> dict[str, Any] | None:
    probable = game_side.get("probablePitcher")
    if not probable:
        return None
    return {"player_id": int(probable["id"]), "name": str(probable["fullName"])}

def _normalize_hitter(split: dict[str, Any]) -> dict[str, Any] | None:
    stat = split.get("stat", {})
    player = split.get("player", {})
    try:
        pa = int(stat.get("plateAppearances", 0))
        return {
            "player_id": int(player["id"]),
            "name": str(player["fullName"]),
            "team_id": int(split.get("team", {}).get("id", 0)) or None,
            "team_name": split.get("team", {}).get("name"),
            "position": split.get("position", {}).get("abbreviation"),
            "games": int(stat.get("gamesPlayed", 0)),
            "pa": pa,
            "ba": float(stat.get("avg", 0) or 0),
            "obp": float(stat.get("obp", 0) or 0),
            "slg": float(stat.get("slg", 0) or 0),
            "hr": int(stat.get("homeRuns", 0)),
            "bb": int(stat.get("baseOnBalls", 0)),
            "so": int(stat.get("strikeOuts", 0)),
            "bb_rate": round(int(stat.get("baseOnBalls", 0)) / pa, 3) if pa else None,
            "k_rate": round(int(stat.get("strikeOuts", 0)) / pa, 3) if pa else None,
        }
    except (KeyError, TypeError, ValueError):
        return None

async def _slate_context(season: int) -> dict[str, Any] | None:
    """Pools + rosters context used to enrich slate rows; None degrades."""
    try:
        pitchers, flags, directory = await asyncio.gather(
            get_player_pool("pitching", "all"),
            get_injury_flags(),
            get_team_directory(),
        )
        return {
            "pitchers_by_id": {p["player_id"]: p for p in pitchers},
            "flags": flags,
            "directory": directory,
        }
    except Exception:
        logger.warning("slate_context_unavailable — rows degrade gracefully")
        return None

def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0

async def get_team_directory() -> dict[int, dict[str, Any]]:
    return {team["team_id"]: team for team in await get_standings()}

async def get_injury_flags() -> dict[int, list[dict[str, Any]]]:
    """IL players who rank top-5 on their team by playing time (PA or IP)."""

    async def loader() -> dict[int, list[dict[str, Any]]]:
        rosters, hitters, pitchers, directory = await asyncio.gather(
            get_rosters(),
            get_player_pool("hitting", "all"),
            get_player_pool("pitching", "all"),
            get_team_directory(),
        )
        top_by_team: dict[int, set[int]] = {}
        rank_context: dict[int, dict[str, Any]] = {}
        for pool, key in ((hitters, "pa"), (pitchers, "ip")):
            by_team: dict[int, list[dict[str, Any]]] = {}
            for player in pool:
                if player["team_id"]:
                    by_team.setdefault(player["team_id"], []).append(player)
            for team_id, players in by_team.items():
                ranked = sorted(players, key=lambda p: p[key], reverse=True)[:5]
                for rank, player in enumerate(ranked, start=1):
                    top_by_team.setdefault(team_id, set()).add(player["player_id"])
                    rank_context[player["player_id"]] = {
                        "metric": key.upper(),
                        "value": player[key],
                        "rank": rank,
                    }
        flags: dict[int, list[dict[str, Any]]] = {}
        for team_id, roster in rosters.items():
            code = directory.get(team_id, {}).get("code", "???")
            for entry in roster:
                if not _is_il_status(entry["status"]):
                    continue
                if entry["player_id"] not in top_by_team.get(team_id, set()):
                    continue
                context = rank_context[entry["player_id"]]
                flags.setdefault(team_id, []).append(
                    {
                        "team": code,
                        "player_id": entry["player_id"],
                        "player": entry["name"],
                        "status": entry["status"].upper().replace("INJURED", "").strip() + " IL"
                        if "injured" in entry["status"].lower()
                        else entry["status"].upper(),
                        "playing_time_rank": context,
                        "source": "MLB 40-man roster status",
                        "tooltip": (
                            "The season model prices the roster's season-to-date "
                            "average, including games this player missed and played. "
                            "It cannot see tomorrow's lineup — you can."
                        ),
                    }
                )
        return flags

    value, _ = await pool_cache.get_or_set(f"injury_flags:{current_season()}", loader)
    return value

def _is_il_status(status: str) -> bool:
    lowered = status.lower()
    return "injured" in lowered or lowered.endswith(" il") or "il-" in lowered

def _normalize_pitcher(split: dict[str, Any]) -> dict[str, Any] | None:
    stat = split.get("stat", {})
    player = split.get("player", {})
    try:
        return {
            "player_id": int(player["id"]),
            "name": str(player["fullName"]),
            "team_id": int(split.get("team", {}).get("id", 0)) or None,
            "team_name": split.get("team", {}).get("name"),
            "position": split.get("position", {}).get("abbreviation"),
            "games": int(stat.get("gamesPlayed", 0)),
            "games_started": int(stat.get("gamesStarted", 0)),
            "ip": round(parse_innings(stat.get("inningsPitched")), 1),
            "ip_display": str(stat.get("inningsPitched", "0.0")),
            "era": float(stat.get("era", 0) or 0),
            "whip": float(stat.get("whip", 0) or 0),
            "so": int(stat.get("strikeOuts", 0)),
            "bb": int(stat.get("baseOnBalls", 0)),
            "obp_against": float(stat.get("obp", 0) or 0),
            "slg_against": float(stat.get("slg", 0) or 0),
        }
    except (KeyError, TypeError, ValueError):
        return None

async def _league_team_stats(group: str) -> list[dict[str, Any]]:
    payload = await _fetch_json(
        "/api/v1/teams/stats",
        {"season": current_season(), "group": group, "stats": "season", "sportId": 1},
    )
    stats = payload.get("stats", [])
    splits = stats[0].get("splits", []) if stats else []
    if len(splits) < 30:
        raise FeedUnavailable("League team statistics are incomplete.")
    return splits
