"""v2 desk math: player run values, mWAA, blended pricing, percentiles, pulse.

Every formula here cashes out a consequence of the models the app already
fit — coefficients always come from the loaded models, never from literals.
All functions are pure: callers supply the live pool data from feeds.py.
"""

from __future__ import annotations

import re
from typing import Any

from backend.inference import load_models

INNINGS_SHARE_FLOOR = 0.4
INNINGS_SHARE_CAP = 0.8
def mwaa_label(season: int) -> str:
    """Built per call — the pool's season is the backend clock, never a literal."""
    return (
        "Offense (or run prevention) only — no defense, no baserunning, no park "
        f'adjustment; "average" means the {season} qualified pool. This is not WAR.'
    )

# The auditable media-pulse lexicon: small, visible, and returned with every
# score so a reader can re-derive it in ten seconds.
PULSE_POSITIVE = [
    "walk-off", "walkoff", "streak", "sweep", "swept", "activated", "returns",
    "career-high", "career high", "clinch", "clinched", "milestone", "no-hitter",
    "shutout", "comeback", "extension", "all-star",
]
PULSE_NEGATIVE = [
    "injured", "injury", " il ", "10-day", "15-day", "60-day", "surgery",
    "skid", "eliminated", "designated for assignment", "released", "setback",
    "strained", "sprain", "fracture", "torn", "out for season", "losing streak",
]


def _coefficients() -> dict[str, float]:
    models = load_models()
    return {
        "beta_obp": float(models["rs"].coef_[0]),
        "beta_slg": float(models["rs"].coef_[1]),
        "beta_oobp": float(models["ra"].coef_[0]),
        "beta_oslg": float(models["ra"].coef_[1]),
        "wins_per_run": float(models["wins"].coef_[0]),
    }


def runs_per_win() -> float:
    """Derived from the fitted W~RD slope — never hardcoded."""
    return 1 / _coefficients()["wins_per_run"]


def runs_per_win_receipt() -> str:
    coefficients = _coefficients()
    return (
        f"The fitted W~RD slope is {coefficients['wins_per_run']:.4f} wins per run — "
        f"i.e. ≈ {runs_per_win():.1f} runs ≈ 1 win, the famous sabermetric rule, "
        "rediscovered by this app's own regression."
    )


def hitter_run_value(
    obp: float,
    slg: float,
    plate_appearances: float,
    league_obp: float,
    league_slg: float,
    league_team_pa: float,
    season: int,
) -> dict[str, Any]:
    """ΔRS and mWAA for a hitter vs the qualified-pool league mean."""
    coefficients = _coefficients()
    share = plate_appearances / league_team_pa if league_team_pa else 0.0
    obp_delta = obp - league_obp
    slg_delta = slg - league_slg
    obp_runs = share * coefficients["beta_obp"] * obp_delta
    slg_runs = share * coefficients["beta_slg"] * slg_delta
    delta_rs = obp_runs + slg_runs
    mwaa = delta_rs * coefficients["wins_per_run"]
    return {
        "kind": "hitter",
        "share": round(share, 4),
        "delta_rs": round(delta_rs, 1),
        "delta_ra": None,
        "delta_rd": round(delta_rs, 1),
        "mwaa": round(mwaa, 2),
        "receipts": [
            {
                "feature": "OBP",
                "player": round(obp, 3),
                "league": round(league_obp, 3),
                "delta": round(obp_delta, 3),
                "coefficient": round(coefficients["beta_obp"], 1),
                "share": round(share, 4),
                "runs": round(obp_runs, 1),
                "formula": "share × β_OBP × (OBP_p − OBP_lg)",
            },
            {
                "feature": "SLG",
                "player": round(slg, 3),
                "league": round(league_slg, 3),
                "delta": round(slg_delta, 3),
                "coefficient": round(coefficients["beta_slg"], 1),
                "share": round(share, 4),
                "runs": round(slg_runs, 1),
                "formula": "share × β_SLG × (SLG_p − SLG_lg)",
            },
        ],
        "wins_formula": (
            f"mWAA = ΔRD × {coefficients['wins_per_run']:.4f} wins/run "
            f"= {delta_rs:.1f} × {coefficients['wins_per_run']:.4f} = {mwaa:.2f}"
        ),
        "runs_per_win_receipt": runs_per_win_receipt(),
        "label": mwaa_label(season),
    }


def pitcher_run_value(
    obp_against: float,
    slg_against: float,
    innings_pitched: float,
    league_obp_against: float,
    league_slg_against: float,
    league_team_ip: float,
    season: int,
) -> dict[str, Any]:
    """ΔRA and mWAA for a pitcher — sign flipped so run prevention is positive."""
    coefficients = _coefficients()
    share = innings_pitched / league_team_ip if league_team_ip else 0.0
    obp_delta = obp_against - league_obp_against
    slg_delta = slg_against - league_slg_against
    obp_runs = share * coefficients["beta_oobp"] * obp_delta
    slg_runs = share * coefficients["beta_oslg"] * slg_delta
    delta_ra = obp_runs + slg_runs
    delta_rd = -delta_ra
    mwaa = delta_rd * coefficients["wins_per_run"]
    return {
        "kind": "pitcher",
        "share": round(share, 4),
        "delta_rs": None,
        "delta_ra": round(delta_ra, 1),
        "delta_rd": round(delta_rd, 1),
        "mwaa": round(mwaa, 2),
        "receipts": [
            {
                "feature": "OBP against",
                "player": round(obp_against, 3),
                "league": round(league_obp_against, 3),
                "delta": round(obp_delta, 3),
                "coefficient": round(coefficients["beta_oobp"], 1),
                "share": round(share, 4),
                "runs": round(obp_runs, 1),
                "formula": "share × β_OOBP × (OBPa_p − OBPa_lg)",
            },
            {
                "feature": "SLG against",
                "player": round(slg_against, 3),
                "league": round(league_slg_against, 3),
                "delta": round(slg_delta, 3),
                "coefficient": round(coefficients["beta_oslg"], 1),
                "share": round(share, 4),
                "runs": round(slg_runs, 1),
                "formula": "share × β_OSLG × (SLGa_p − SLGa_lg)",
            },
        ],
        "wins_formula": (
            f"mWAA = ΔRD × {coefficients['wins_per_run']:.4f} wins/run "
            f"= {delta_rd:.1f} × {coefficients['wins_per_run']:.4f} = {mwaa:.2f} "
            "(ΔRA sign flipped: run prevention is positive value)"
        ),
        "runs_per_win_receipt": runs_per_win_receipt(),
        "label": mwaa_label(season),
    }


def percentile(value: float, pool_values: list[float]) -> float:
    """Percentile of value inside the qualified pool (midpoint convention)."""
    if not pool_values:
        return 0.0
    below = sum(1 for other in pool_values if other < value)
    equal = sum(1 for other in pool_values if other == value)
    return round(100 * (below + 0.5 * equal) / len(pool_values), 1)


def beane_badge(obp_percentile: float, ba_percentile: float) -> bool:
    """WOULD-BEANE-BUY: OBP percentile beats BA percentile by 20+ points."""
    return obp_percentile - ba_percentile >= 20


def starter_innings_share(innings_pitched: float, games_started: int) -> float | None:
    """Starter innings share w = IP ÷ (GS × 9), capped to [0.4, 0.8]."""
    if games_started <= 0 or innings_pitched <= 0:
        return None
    raw = innings_pitched / (games_started * 9)
    return round(min(max(raw, INNINGS_SHARE_FLOOR), INNINGS_SHARE_CAP), 4)


def blend_defense_inputs(
    starter_obp_against: float,
    starter_slg_against: float,
    team_obp_against: float,
    team_slg_against: float,
    innings_share: float,
) -> dict[str, float]:
    """Blend starter and team rates: w·starter + (1−w)·team (bullpen proxy)."""
    return {
        "oobp": round(
            innings_share * starter_obp_against + (1 - innings_share) * team_obp_against, 4
        ),
        "oslg": round(
            innings_share * starter_slg_against + (1 - innings_share) * team_slg_against, 4
        ),
    }


def parse_innings(raw: str | float | int | None) -> float:
    """MLB reports IP as e.g. '139.2' meaning 139⅔ innings."""
    if raw is None:
        return 0.0
    text = str(raw)
    if "." in text:
        whole, outs = text.split(".", 1)
        try:
            return int(whole) + int(outs) / 3
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def score_pulse_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Lexicon tone score over wire items, normalized to −100…+100.

    Rule (auditable): count positive and negative lexicon matches across all
    item texts; pulse = 100 × (pos − neg) ÷ (pos + neg), 0 when no matches.
    Every scored item returns with its matched words.
    """
    positives = 0
    negatives = 0
    evidence: list[dict[str, Any]] = []
    for item in items:
        text = f" {item.get('text', '')} ".lower()
        matched_positive = [
            word for word in PULSE_POSITIVE if word if _matches(text, word)
        ]
        matched_negative = [
            word for word in PULSE_NEGATIVE if word if _matches(text, word)
        ]
        positives += len(matched_positive)
        negatives += len(matched_negative)
        if matched_positive or matched_negative:
            evidence.append(
                {
                    **item,
                    "matched_positive": [w.strip() for w in matched_positive],
                    "matched_negative": [w.strip() for w in matched_negative],
                }
            )
    total = positives + negatives
    score = round(100 * (positives - negatives) / total) if total else 0
    return {
        "pulse": score,
        "items_scanned": len(items),
        "items_matched": len(evidence),
        "positive_matches": positives,
        "negative_matches": negatives,
        "evidence": evidence,
        "method": (
            "pulse = 100 × (positive − negative) ÷ (positive + negative) lexicon "
            "matches over the last 7 days of wire items; 0 when nothing matches."
        ),
        "lexicon": {
            "positive": [w.strip() for w in PULSE_POSITIVE],
            "negative": [w.strip() for w in PULSE_NEGATIVE],
        },
    }


def _matches(text: str, word: str) -> bool:
    if word.startswith(" ") or word.endswith(" "):
        return word in text
    return re.search(rf"(?<![a-z]){re.escape(word)}", text) is not None
