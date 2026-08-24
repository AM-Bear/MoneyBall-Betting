"""End-to-end coverage of the SEASON price chain.

Before this file nothing computed an actual game price in a test: `smoke_test.py`
asserts the RS intercept and coefficients, and the grading tests seed rows
directly, but `_chain_probability` -> `_price_game` -> a fair moneyline was
entirely uncovered. Tier 3 (`notes/v3-plan.md`) adds a verdict engine and
`model_detail`, both of which refactor this path, so it needs a net first.

Two deliberate choices:

1. The expected values are re-derived **longhand in the test** from coefficients
   read off `load_models()`, not by calling the production helpers. A test that
   asserts `_chain_probability(...) == log5_probability(pythagorean_strength(...))`
   only proves the code equals itself; it would happily bless swapped OBP/SLG
   arguments or an inverted home/away. Writing the arithmetic out independently
   catches wiring bugs.

2. The anchor is the hand-checked 2002 OAK row in `verified_stats.json` — the
   same oracle `smoke_test.py` uses — so the inputs are known-good rather than
   invented.

These are correctness tests, not characterisation tests: they must keep passing
because the math is right, not because the output has not changed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.feeds import _chain_probability, _price_game
from backend.inference import load_models
from backend.odds import probability_to_moneyline

VERIFIED = json.loads((Path(__file__).resolve().parents[1] / "verified_stats.json").read_text())
OAK_2002 = VERIFIED["oak_2002_chain"]

# A weaker synthetic opponent. Not a real club — the point is a decisive
# favourite/underdog split so an inverted home/away would change the sign.
WEAK_TEAM = {"obp": 0.300, "slg": 0.380, "oobp": 0.345, "oslg": 0.440}

OAK_INPUTS = {
    "obp": OAK_2002["inputs"]["OBP"],
    "slg": OAK_2002["inputs"]["SLG"],
    "oobp": OAK_2002["inputs"]["OOBP"],
    "oslg": OAK_2002["inputs"]["OSLG"],
}


def _longhand_rs_ra(inputs: dict[str, float]) -> tuple[float, float]:
    """RS/RA from first principles: intercept + sum(coefficient * feature).

    Rounded to one decimal on purpose. `_chain_probability` prices off
    `predict_from_inputs(...)["predicted"]`, whose values are already rounded,
    so the live chain feeds rounded RS/RA into the Pythagorean step. The effect
    is ~4e-6 on the probability — far too small to move a nearest-5 moneyline —
    but replicating it keeps this test exact, and a Tier 3 refactor that starts
    pricing off unrounded values will fail here rather than drift silently.
    """
    models = load_models()
    rs_model, ra_model = models["rs"], models["ra"]
    rs = (
        float(rs_model.intercept_)
        + float(rs_model.coef_[0]) * inputs["obp"]
        + float(rs_model.coef_[1]) * inputs["slg"]
    )
    ra = (
        float(ra_model.intercept_)
        + float(ra_model.coef_[0]) * inputs["oobp"]
        + float(ra_model.coef_[1]) * inputs["oslg"]
    )
    return round(rs, 1), round(ra, 1)


def _longhand_strength(rs: float, ra: float) -> float:
    """Pythagorean expectation, exponent 2, with the production floor at 1."""
    rs2 = max(rs, 1) ** 2
    ra2 = max(ra, 1) ** 2
    return rs2 / (rs2 + ra2)


def _longhand_log5(home_strength: float, away_strength: float) -> float:
    """Bill James log5. Production calls log5_probability(home, away)."""
    denominator = home_strength + away_strength - 2 * home_strength * away_strength
    if denominator == 0:
        return 0.5
    return (home_strength - home_strength * away_strength) / denominator


def _longhand_home_probability(
    away_inputs: dict[str, float], home_inputs: dict[str, float]
) -> float:
    away_rs, away_ra = _longhand_rs_ra(away_inputs)
    home_rs, home_ra = _longhand_rs_ra(home_inputs)
    return _longhand_log5(
        _longhand_strength(home_rs, home_ra),
        _longhand_strength(away_rs, away_ra),
    )


# --------------------------------------------------------------------------
# Coefficient assertions smoke_test.py does not make.
# Lane 1 found that only the RS intercept and coefficients are pinned; the RA
# coefficients and the wins slope are not, and the slope drives every mWAA
# number through a band loose enough for a 5% drift to pass.
# --------------------------------------------------------------------------


def test_ra_coefficients_match_the_verified_bundle() -> None:
    ra = load_models()["ra"]
    assert float(ra.intercept_) == pytest.approx(VERIFIED["ra_model"]["intercept"], abs=0.05)
    assert float(ra.coef_[0]) == pytest.approx(VERIFIED["ra_model"]["coef_OOBP"], abs=0.05)
    assert float(ra.coef_[1]) == pytest.approx(VERIFIED["ra_model"]["coef_OSLG"], abs=0.05)


def test_wins_slope_matches_the_verified_bundle_tightly() -> None:
    """The runs-per-win divisor. A 5% drift here moves every mWAA number."""
    wins = load_models()["wins"]
    assert float(wins.intercept_) == pytest.approx(VERIFIED["wins_model"]["intercept"], abs=0.01)
    assert float(wins.coef_[0]) == pytest.approx(VERIFIED["wins_model"]["coef_RD"], abs=0.0001)


# --------------------------------------------------------------------------
# The chain itself.
# --------------------------------------------------------------------------


def test_oak_2002_inputs_reproduce_the_verified_rs_and_ra() -> None:
    """Anchor the longhand derivation to the hand-checked oracle row."""
    rs, ra = _longhand_rs_ra(OAK_INPUTS)
    assert round(rs) == OAK_2002["predicted"]["RS"]
    assert round(ra) == OAK_2002["predicted"]["RA"]


def test_chain_probability_matches_an_independent_derivation() -> None:
    """_chain_probability(away, home) must equal longhand RS/RA -> pythag -> log5."""
    produced = _chain_probability(WEAK_TEAM, OAK_INPUTS)
    expected = _longhand_home_probability(WEAK_TEAM, OAK_INPUTS)
    assert produced == pytest.approx(expected, abs=1e-12)


def test_strong_home_team_is_favoured() -> None:
    """Sanity on orientation: 2002 OAK at home over a weak club is a favourite."""
    probability = _chain_probability(WEAK_TEAM, OAK_INPUTS)
    assert 0.5 < probability < 1.0
    assert probability_to_moneyline(probability) < 0


def test_swapping_home_and_away_complements_the_probability() -> None:
    """Catches an inverted home/away wiring, which no single-sided test can."""
    home_side = _chain_probability(WEAK_TEAM, OAK_INPUTS)
    away_side = _chain_probability(OAK_INPUTS, WEAK_TEAM)
    assert home_side + away_side == pytest.approx(1.0, abs=1e-12)


def test_identical_teams_price_as_a_coin_flip() -> None:
    assert _chain_probability(OAK_INPUTS, OAK_INPUTS) == pytest.approx(0.5, abs=1e-12)
    assert _chain_probability(WEAK_TEAM, WEAK_TEAM) == pytest.approx(0.5, abs=1e-12)


def test_fair_lines_are_two_sided_and_consistent_with_the_probability() -> None:
    """The two posted sides must reflect the same probability, opposite signs."""
    probability = _chain_probability(WEAK_TEAM, OAK_INPUTS)
    home_line = probability_to_moneyline(probability)
    away_line = probability_to_moneyline(1 - probability)
    assert home_line < 0 < away_line
    # Fair (vig-free) lines: the two implied probabilities sum to ~1, allowing
    # for the nearest-5 rounding in probability_to_moneyline.
    implied_home = abs(home_line) / (abs(home_line) + 100)
    implied_away = 100 / (away_line + 100)
    assert implied_home + implied_away == pytest.approx(1.0, abs=0.01)


# --------------------------------------------------------------------------
# _price_game end to end, with the only network call stubbed.
# --------------------------------------------------------------------------


def _game(status: str = "Scheduled") -> dict:
    return {
        "gamePk": 776001,
        "gameDate": "2026-08-24T23:05:00Z",
        "status": {"detailedState": status},
        "teams": {
            "away": {"team": {"id": 111, "name": "Boston Red Sox"}},
            "home": {"team": {"id": 133, "name": "Athletics"}},
        },
    }


@pytest.fixture()
def stub_team_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the only networked dependency of _price_game."""
    by_id = {111: WEAK_TEAM, 133: OAK_INPUTS}

    async def fake_team_inputs(team_id: int, season: int) -> tuple[dict[str, float], bool]:
        return by_id[team_id], True

    monkeypatch.setattr("backend.feeds._team_inputs", fake_team_inputs)


def test_price_game_produces_the_expected_fair_lines(stub_team_inputs: None) -> None:
    priced = asyncio.run(_price_game(_game(), 2026))

    expected_home_probability = _longhand_home_probability(WEAK_TEAM, OAK_INPUTS)
    assert priced["model_prob_home"] == pytest.approx(round(expected_home_probability, 4))
    assert priced["fair_lines"]["home"] == probability_to_moneyline(expected_home_probability)
    assert priced["fair_lines"]["away"] == probability_to_moneyline(1 - expected_home_probability)


def test_price_game_maps_team_codes_through_team_codes(stub_team_inputs: None) -> None:
    """Guards the B-Ref/MLB code boundary the graded record depends on.

    "Athletics" (not "Oakland Athletics") is the current TEAM_CODES key --
    the bundle already tracks the relocation. A stale name here would fall
    through to the initials fallback and produce "OA".
    """
    priced = asyncio.run(_price_game(_game(), 2026))
    assert priced["away"] == "BOS"
    assert priced["home"] == "ATH"
    assert priced["away_name"] == "Boston Red Sox"
    assert priced["home_name"] == "Athletics"


def test_price_game_without_context_emits_no_adj_price(stub_team_inputs: None) -> None:
    """SEASON only when no starter context is supplied; ADJ must stay absent."""
    priced = asyncio.run(_price_game(_game(), 2026))
    assert priced["adj_prob"] is None
    assert priced["adj_fair_lines"] is None
    assert priced["adj_detail"] is None
    assert priced["flags"] == []


def test_price_game_marks_a_started_game_live(stub_team_inputs: None) -> None:
    assert asyncio.run(_price_game(_game("In Progress"), 2026))["badges"] == ["LIVE"]
    assert asyncio.run(_price_game(_game("Scheduled"), 2026))["badges"] == []
