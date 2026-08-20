"""Player Desk assembly: cards, percentiles, run values, comparisons.

Composition layer between feeds.py (live pools) and analytics.py (pure math).
"""

from __future__ import annotations

import asyncio
from typing import Any

from backend.analytics import (
    mwaa_label,
    beane_badge,
    hitter_run_value,
    percentile,
    pitcher_run_value,
    runs_per_win_receipt,
)
from backend.feeds import (
    current_season,
    get_league_pool_context,
    get_player_pool,
    get_standings,
)
from backend.odds import probability_to_moneyline


def salary_note() -> str:
    """Built per request — the season is the backend clock, never a literal."""
    return (
        f"No {current_season()} salary data exists on keyless endpoints, so the "
        "desk shows no salary figures. The Player Desk may accept a "
        "USER-SUPPLIED number for $/mWAA math on the user's own responsibility."
    )


async def search_players(
    group: str, pool: str, query: str | None, limit: int = 25
) -> list[dict[str, Any]]:
    players = await get_player_pool(group, pool)
    if query:
        needle = query.strip().lower()
        players = [p for p in players if needle in p["name"].lower()]
    keyed = "pa" if group == "hitting" else "ip"
    players = sorted(players, key=lambda p: p[keyed], reverse=True)
    return players[: max(1, min(limit, 100))]


async def _league_baseline_runs() -> float:
    standings = await get_standings()
    return sum(t["runs_scored"] for t in standings) / len(standings)


def _reprice_line(strength: float) -> int:
    return probability_to_moneyline(strength)


async def build_player_card(player_id: int) -> dict[str, Any] | None:
    """Card with stat line, percentiles, ΔRS/ΔRA, mWAA, receipts, badges."""
    (
        hitters_all,
        pitchers_all,
        hitters_qualified,
        pitchers_qualified,
        context,
        baseline_runs,
    ) = await asyncio.gather(
        get_player_pool("hitting", "all"),
        get_player_pool("pitching", "all"),
        get_player_pool("hitting", "qualified"),
        get_player_pool("pitching", "qualified"),
        get_league_pool_context(),
        _league_baseline_runs(),
    )
    hitter = next((p for p in hitters_all if p["player_id"] == player_id), None)
    pitcher = next((p for p in pitchers_all if p["player_id"] == player_id), None)
    if hitter is None and pitcher is None:
        return None

    card: dict[str, Any] = {
        "player_id": player_id,
        "name": (hitter or pitcher)["name"],
        "team": (hitter or pitcher)["team_name"],
        "position": (hitter or pitcher)["position"],
        "salary": {"available": False, "note": salary_note()},
        "runs_per_win_receipt": runs_per_win_receipt(),
        "metric_label": mwaa_label(current_season()),
    }

    if hitter is not None:
        qualified_ids = {p["player_id"] for p in hitters_qualified}
        percentiles = {
            "ba": percentile(hitter["ba"], [p["ba"] for p in hitters_qualified]),
            "obp": percentile(hitter["obp"], [p["obp"] for p in hitters_qualified]),
            "slg": percentile(hitter["slg"], [p["slg"] for p in hitters_qualified]),
            "hr": percentile(float(hitter["hr"]), [float(p["hr"]) for p in hitters_qualified]),
            "bb_rate": percentile(
                hitter["bb_rate"] or 0.0,
                [p["bb_rate"] or 0.0 for p in hitters_qualified],
            ),
            "k_rate": round(
                100
                - percentile(
                    hitter["k_rate"] or 0.0,
                    [p["k_rate"] or 0.0 for p in hitters_qualified],
                ),
                1,
            ),
        }
        value = hitter_run_value(
            hitter["obp"],
            hitter["slg"],
            hitter["pa"],
            context["league_obp"],
            context["league_slg"],
            context["league_team_pa"],
            current_season(),
        )
        strength_with = (baseline_runs + value["delta_rs"]) ** 2 / (
            (baseline_runs + value["delta_rs"]) ** 2 + baseline_runs**2
        )
        badge = beane_badge(percentiles["obp"], percentiles["ba"])
        card["hitting"] = {
            "stat_line": {
                key: hitter[key]
                for key in ("games", "pa", "ba", "obp", "slg", "hr", "bb", "so", "bb_rate", "k_rate")
            },
            "qualified": player_id in qualified_ids,
            "percentiles": percentiles,
            "percentile_note": (
                f"Percentiles are computed live vs the {current_season()} qualified pool; "
                "K% is inverted so higher is always better."
            ),
            "model": value,
            "fair_odds_framing": (
                f"Adding this bat to an average team reprices it from -100 to "
                f"{_reprice_line(strength_with):+d} vs average."
            ),
            "would_beane_buy": badge,
            "badge_caption": (
                "Lit when OBP percentile beats BA percentile by 20+ points — the "
                "2002-style walk-heavy profile the market historically underpaid. "
                "See the BA Paradox panel for why."
            )
            if badge
            else None,
        }

    if pitcher is not None:
        qualified_ids = {p["player_id"] for p in pitchers_qualified}
        percentiles = {
            "era": round(
                100 - percentile(pitcher["era"], [p["era"] for p in pitchers_qualified]), 1
            ),
            "whip": round(
                100 - percentile(pitcher["whip"], [p["whip"] for p in pitchers_qualified]), 1
            ),
            "obp_against": round(
                100
                - percentile(
                    pitcher["obp_against"],
                    [p["obp_against"] for p in pitchers_qualified],
                ),
                1,
            ),
            "slg_against": round(
                100
                - percentile(
                    pitcher["slg_against"],
                    [p["slg_against"] for p in pitchers_qualified],
                ),
                1,
            ),
            "so": percentile(
                float(pitcher["so"]), [float(p["so"]) for p in pitchers_qualified]
            ),
        }
        value = pitcher_run_value(
            pitcher["obp_against"],
            pitcher["slg_against"],
            pitcher["ip"],
            context["league_obp_against"],
            context["league_slg_against"],
            context["league_team_ip"],
            current_season(),
        )
        strength_with = baseline_runs**2 / (
            baseline_runs**2 + (baseline_runs + (value["delta_ra"] or 0.0)) ** 2
        )
        card["pitching"] = {
            "stat_line": {
                key: pitcher[key]
                for key in (
                    "games", "games_started", "ip_display", "era", "whip", "so",
                    "bb", "obp_against", "slg_against",
                )
            },
            "qualified": player_id in qualified_ids,
            "percentiles": percentiles,
            "percentile_note": (
                f"Percentiles are computed live vs the {current_season()} qualified pool; rate "
                "stats are inverted so higher is always better."
            ),
            "model": value,
            "fair_odds_framing": (
                f"Adding this arm to an average team reprices it from -100 to "
                f"{_reprice_line(strength_with):+d} vs average."
            ),
        }

    card["pool_context"] = {
        "qualified_hitters": context["qualified_hitters"],
        "qualified_pitchers": context["qualified_pitchers"],
        "mean_definition": context["mean_definition"],
    }
    return card


def _primary_kind(card: dict[str, Any]) -> str | None:
    if "hitting" in card and "pitching" in card:
        # Two-way player: rank by playing-time share of each role.
        hitting_share = card["hitting"]["model"]["share"]
        pitching_share = card["pitching"]["model"]["share"]
        return "hitting" if hitting_share >= pitching_share else "pitching"
    if "hitting" in card:
        return "hitting"
    if "pitching" in card:
        return "pitching"
    return None


async def compare_players(a: int, b: int) -> dict[str, Any] | None:
    card_a, card_b = await asyncio.gather(build_player_card(a), build_player_card(b))
    if card_a is None or card_b is None:
        return None
    kind_a = _primary_kind(card_a)
    kind_b = _primary_kind(card_b)

    if kind_a != kind_b:
        return {
            "mode": "boundary",
            "a": card_a,
            "b": card_b,
            "verdict": None,
            "boundary": (
                "HITTER VS PITCHER: NOT PRICED — different y-variables; the model "
                "cannot stage a duel it never fit. Each player's own run impact "
                "is shown side by side instead."
            ),
        }

    section_a = card_a[kind_a]
    section_b = card_b[kind_b]
    mwaa_a = section_a["model"]["mwaa"]
    mwaa_b = section_b["model"]["mwaa"]
    margin = round(mwaa_a - mwaa_b, 2)
    leader = card_a if margin >= 0 else card_b
    deltas = {
        key: round(
            float(section_a["stat_line"].get(key) or 0)
            - float(section_b["stat_line"].get(key) or 0),
            3,
        )
        for key in section_a["stat_line"]
        if isinstance(section_a["stat_line"].get(key), (int, float))
        and isinstance(section_b["stat_line"].get(key), (int, float))
    }
    return {
        "mode": kind_a,
        "a": card_a,
        "b": card_b,
        "deltas": deltas,
        "percentile_pairs": {
            key: [section_a["percentiles"].get(key), section_b["percentiles"].get(key)]
            for key in section_a["percentiles"]
        },
        "verdict": {
            "leader": leader["name"],
            "margin_mwaa": abs(margin),
            "line": (
                f"{leader['name'].split(' ')[-1].upper()} "
                f"{'+' if abs(margin) >= 0 else ''}{abs(margin)} mWAA — but check "
                "the receipts before you quote it."
            ),
        },
    }
