"""Seeded rest-of-season Monte Carlo under the actual 2026 playoff format.

Fixed seed, N = 2,000. Cached; re-run only when the inputs (team rates,
standings, remaining schedule) actually refresh. Playoff odds come from the
simulated standings — top 6 per league: 3 division winners + 3 wild cards —
NOT from the historical Playoffs~W logistic, which was fit on 1962–2012
formats and stays in the historical panels.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from datetime import datetime
from typing import Any

from backend.feeds import (
    EASTERN,
    _team_inputs,
    current_season,
    get_remaining_schedule,
    get_standings,
)
from backend.inference import predict_from_inputs
from backend.odds import log5_probability, pythagorean_strength

SIM_SEED = 20261962
SIM_ITERATIONS = 2000
ASSUMPTIONS = [
    "Current team rates (2026 OBP/SLG and OBP/SLG-against) persist for every remaining game.",
    "No trade, injury, fatigue, or pitching-matchup modeling.",
    "Per-game win probability: RS/RA models → Pythagorean → log5, the desk's season chain.",
    "Playoff spots: top 6 per league from simulated standings — 3 division winners + 3 wild cards (the actual 2026 format).",
    "Ties for a spot are broken randomly inside each simulation.",
    f"N = {SIM_ITERATIONS} simulations, fixed seed {SIM_SEED}; the table only changes when the inputs refresh.",
]
NEXT_SEASON_REFUSAL = {
    "season": current_season() + 1,
    "status": "NOT PRICED",
    "reason": (
        "A season model needs an offseason roster model; this desk doesn't "
        "fake what it can't fit."
    ),
}

_sim_lock = asyncio.Lock()
_sim_cache: dict[str, Any] | None = None


def _input_signature(
    standings: list[dict[str, Any]],
    rates: dict[int, float],
    schedule: list[dict[str, Any]],
) -> str:
    payload = json.dumps(
        {
            "standings": [
                (t["team_id"], t["wins"], t["losses"], t["games_played"])
                for t in sorted(standings, key=lambda t: t["team_id"])
            ],
            "rates": sorted((k, round(v, 6)) for k, v in rates.items()),
            "schedule": len(schedule),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def simulate_season(
    standings: list[dict[str, Any]],
    strengths: dict[int, float],
    schedule: list[dict[str, Any]],
    seed: int = SIM_SEED,
    iterations: int = SIM_ITERATIONS,
) -> dict[int, dict[str, Any]]:
    """Deterministic Monte Carlo: same seed + same inputs → same table."""
    rng = random.Random(seed)
    team_ids = [t["team_id"] for t in standings]
    base_wins = {t["team_id"]: t["wins"] for t in standings}
    league_of = {t["team_id"]: t["league_id"] for t in standings}
    division_of = {t["team_id"]: t["division_id"] for t in standings}

    game_probabilities = [
        (
            game["home_id"],
            game["away_id"],
            log5_probability(strengths[game["home_id"]], strengths[game["away_id"]]),
        )
        for game in schedule
        if game["home_id"] in strengths and game["away_id"] in strengths
    ]

    win_totals: dict[int, list[int]] = {team_id: [] for team_id in team_ids}
    playoff_counts = {team_id: 0 for team_id in team_ids}
    division_counts = {team_id: 0 for team_id in team_ids}

    for _iteration in range(iterations):
        wins = dict(base_wins)
        for home_id, away_id, probability in game_probabilities:
            if rng.random() < probability:
                wins[home_id] += 1
            else:
                wins[away_id] += 1
        for team_id in team_ids:
            win_totals[team_id].append(wins[team_id])

        # Random tie-break: jitter never exceeds one scheduling quantum.
        jittered = {
            team_id: wins[team_id] + rng.random() * 1e-6 for team_id in team_ids
        }
        for league_id in {league_of[t] for t in team_ids}:
            league_teams = [t for t in team_ids if league_of[t] == league_id]
            division_winners: list[int] = []
            for division_id in {division_of[t] for t in league_teams}:
                division_teams = [
                    t for t in league_teams if division_of[t] == division_id
                ]
                winner = max(division_teams, key=lambda t: jittered[t])
                division_winners.append(winner)
                division_counts[winner] += 1
            wild_card_pool = [t for t in league_teams if t not in division_winners]
            wild_cards = sorted(wild_card_pool, key=lambda t: jittered[t], reverse=True)[:3]
            for team_id in [*division_winners, *wild_cards]:
                playoff_counts[team_id] += 1

    results: dict[int, dict[str, Any]] = {}
    for team_id in team_ids:
        totals = win_totals[team_id]
        totals_sorted = sorted(totals)
        minimum, maximum = totals_sorted[0], totals_sorted[-1]
        histogram: dict[int, int] = {}
        for value in totals:
            histogram[value] = histogram.get(value, 0) + 1
        results[team_id] = {
            "expected_wins": round(sum(totals) / len(totals), 1),
            "wins_p5": totals_sorted[int(0.05 * len(totals))],
            "wins_p95": totals_sorted[int(0.95 * len(totals)) - 1],
            "wins_min": minimum,
            "wins_max": maximum,
            "distribution": [
                {"wins": w, "count": histogram[w]} for w in sorted(histogram)
            ],
            "playoff_odds": round(playoff_counts[team_id] / iterations, 4),
            "division_odds": round(division_counts[team_id] / iterations, 4),
        }
    return results


async def get_season_sim() -> dict[str, Any]:
    """Cached simulation payload; recomputed only when inputs change."""
    global _sim_cache
    standings = await get_standings()
    season = current_season()
    inputs_by_team: dict[int, dict[str, float]] = {}

    semaphore = asyncio.Semaphore(5)

    async def one(team_id: int) -> None:
        async with semaphore:
            inputs, _cached = await _team_inputs(team_id, season)
            inputs_by_team[team_id] = inputs

    await asyncio.gather(*(one(t["team_id"]) for t in standings))
    schedule = await get_remaining_schedule()

    strengths: dict[int, float] = {}
    for team_id, inputs in inputs_by_team.items():
        model = predict_from_inputs(**inputs)
        strengths[team_id] = pythagorean_strength(
            model["predicted"]["rs"], model["predicted"]["ra"]
        )

    signature = _input_signature(
        standings, {k: v for k, v in strengths.items()}, schedule
    )
    async with _sim_lock:
        if _sim_cache is not None and _sim_cache["signature"] == signature:
            return _sim_cache["payload"]

        started = time.perf_counter()
        results = await asyncio.to_thread(
            simulate_season, standings, strengths, schedule
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000)

        remaining_by_team: dict[int, int] = {}
        for game in schedule:
            for team_id in (game["home_id"], game["away_id"]):
                remaining_by_team[team_id] = remaining_by_team.get(team_id, 0) + 1

        rows = []
        for team in sorted(standings, key=lambda t: t["code"]):
            team_id = team["team_id"]
            sim = results[team_id]
            games_played = team["games_played"]
            pace_wins = (
                round(team["wins"] / games_played * 162, 1) if games_played else None
            )
            rows.append(
                {
                    "team_id": team_id,
                    "team": team["code"],
                    "name": team["name"],
                    "league_id": team["league_id"],
                    "division_id": team["division_id"],
                    "wins": team["wins"],
                    "losses": team["losses"],
                    "games_played": games_played,
                    "games_remaining": remaining_by_team.get(team_id, 0),
                    "pace_wins": pace_wins,
                    "delta_vs_pace": (
                        round(sim["expected_wins"] - pace_wins, 1)
                        if pace_wins is not None
                        else None
                    ),
                    **sim,
                }
            )

        payload = {
            "season": season,
            "seed": SIM_SEED,
            "iterations": SIM_ITERATIONS,
            "input_signature": signature,
            "computed_at": datetime.now(EASTERN).isoformat(),
            "compute_ms": elapsed_ms,
            "sample_label": f"THRU {max(t['games_played'] for t in standings)} GP",
            "remaining_games_simulated": len(schedule),
            "rows": rows,
            "assumptions": ASSUMPTIONS,
            "playoff_format_note": (
                "Playoff odds are computed from simulated standings under the "
                "2026 format. The historical Playoffs~W logistic (fit on "
                "1962–2012 formats) stays in the historical panels only."
            ),
            "next_season": NEXT_SEASON_REFUSAL,
        }
        _sim_cache = {"signature": signature, "payload": payload}
        return payload
