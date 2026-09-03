"""v4-plan 4.1: the half-Kelly paper stake is capped in the display layer.

`odds.half_kelly_fraction` says "capped" and is not: 0.99 at +1000 returns 0.4945, half the
bankroll. The plan keeps odds.py as it is (smoke_test pins its raw values) and caps the number
where it is shown -- the API responses -- visibly (the raw value, the cap and whether it bound
ship as receipts) and adjustably (`stake_cap` on the request, bounded by policy).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.odds import half_kelly_fraction
from backend.stakes import STAKE_CAP_DEFAULT, STAKE_CAP_MAX, capped_stake
from tests.test_parlay_correlation import SLATE_DATE, SLATE_GAMES

client = TestClient(main.app)

TEAM_A = {"obp": 0.336, "slg": 0.432, "oobp": 0.312, "oslg": 0.398}
TEAM_B = {"obp": 0.308, "slg": 0.382, "oobp": 0.329, "oslg": 0.421}


# --- the policy, pure ---------------------------------------------------------------------


def test_default_cap_is_two_percent_of_bankroll():
    """The plan names 1-2%; the default is the top of that range."""
    assert STAKE_CAP_DEFAULT == 0.02
    assert capped_stake(0.5)["cap"] == 0.02


def test_a_stake_below_the_cap_passes_through_unchanged():
    stake = capped_stake(0.0123)
    assert stake["fraction"] == 0.0123
    assert stake["raw_fraction"] == 0.0123
    assert stake["capped"] is False


def test_a_stake_exactly_at_the_cap_is_not_reported_as_capped():
    stake = capped_stake(0.02)
    assert stake["fraction"] == 0.02
    assert stake["capped"] is False


def test_a_wildly_positive_ev_stake_is_held_at_the_cap():
    """The docstring's promise, kept here: 0.99 at +1000 is 49% of bankroll raw."""
    raw = half_kelly_fraction(0.99, 1000)
    assert raw == pytest.approx(0.4945)
    stake = capped_stake(raw)
    assert stake["fraction"] == 0.02
    assert stake["raw_fraction"] == pytest.approx(0.4945)
    assert stake["capped"] is True


def test_zero_and_negative_edge_stay_zero():
    assert capped_stake(0.0)["fraction"] == 0.0
    assert capped_stake(half_kelly_fraction(0.6, -150))["fraction"] == 0.0
    assert capped_stake(0.0)["capped"] is False


def test_the_cap_is_adjustable_within_policy():
    assert capped_stake(0.5, cap=0.01)["fraction"] == 0.01
    assert capped_stake(0.5, cap=STAKE_CAP_MAX)["fraction"] == STAKE_CAP_MAX
    with pytest.raises(ValueError):
        capped_stake(0.5, cap=0.0)
    with pytest.raises(ValueError):
        capped_stake(0.5, cap=STAKE_CAP_MAX + 0.001)


def test_odds_py_is_untouched():
    """The plan says do not mutate odds.py; smoke_test asserts its raw values."""
    assert half_kelly_fraction(0.99, 1000) == pytest.approx(0.4945)
    assert half_kelly_fraction(0.6, -150) == 0


# --- /api/matchup -------------------------------------------------------------------------


def _matchup(**extra: Any) -> dict[str, Any]:
    response = client.post(
        "/api/matchup", json={"team_a": TEAM_A, "team_b": TEAM_B, "evaluation_side": "a", **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_matchup_caps_a_runaway_stake_and_says_so():
    body = _matchup(book_line_a=1000)
    raw = half_kelly_fraction(body["model_prob_a"], 1000)
    assert raw > STAKE_CAP_DEFAULT  # the cap must actually bind in this case
    assert body["kelly_fraction"] == STAKE_CAP_DEFAULT
    assert body["kelly_fraction_raw"] == pytest.approx(raw, abs=2e-4)
    assert body["kelly_cap"] == STAKE_CAP_DEFAULT
    assert body["kelly_capped"] is True


def test_matchup_output_is_unchanged_where_the_cap_does_not_bind():
    # -190 sits just under this pair's fair line, so the edge is small and the cap idle.
    body = _matchup(book_line_a=-190)
    raw = half_kelly_fraction(body["model_prob_a"], -190)
    assert raw < STAKE_CAP_DEFAULT
    assert body["kelly_fraction"] == pytest.approx(raw, abs=2e-4)
    assert body["kelly_fraction_raw"] == body["kelly_fraction"]
    assert body["kelly_capped"] is False


def test_matchup_accepts_a_tighter_cap_and_refuses_one_above_policy():
    body = _matchup(book_line_a=1000, stake_cap=0.01)
    assert body["kelly_fraction"] == 0.01
    assert body["kelly_cap"] == 0.01
    response = client.post(
        "/api/matchup",
        json={"team_a": TEAM_A, "team_b": TEAM_B, "book_line_a": 1000, "stake_cap": 0.5},
    )
    # The app renders validation failures as 400 with its error envelope, not FastAPI's 422.
    assert response.status_code == 400
    assert "error" in response.json()


def test_matchup_with_no_line_reports_a_zero_stake_uncapped():
    body = _matchup()
    assert body["kelly_fraction"] == 0
    assert body["kelly_capped"] is False


# --- /api/parlay/price --------------------------------------------------------------------


@pytest.fixture()
def live_slate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_slate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"mode": "live", "date": SLATE_DATE, "games": SLATE_GAMES}

    monkeypatch.setattr(main, "get_slate", fake_slate)


LEGS = [{"gamePk": "790001", "side": "home"}, {"gamePk": "790003", "side": "home"}]


def test_parlay_caps_a_runaway_stake_and_says_so(live_slate: None):
    body = client.post("/api/parlay/price", json={"legs": LEGS, "book_odds": 2000}).json()
    book = body["book"]
    raw = half_kelly_fraction(body["combined_prob"], 2000)
    assert raw > STAKE_CAP_DEFAULT
    assert book["half_kelly"] == STAKE_CAP_DEFAULT
    assert book["half_kelly_raw"] == pytest.approx(round(raw, 4), abs=1e-4)
    assert book["kelly_cap"] == STAKE_CAP_DEFAULT
    assert book["kelly_capped"] is True
    assert book["stake_label"] == f"{STAKE_CAP_DEFAULT:.4f}"


def test_parlay_output_is_unchanged_where_the_cap_does_not_bind(live_slate: None):
    body = client.post("/api/parlay/price", json={"legs": LEGS, "book_odds": 220}).json()
    book = body["book"]
    raw = half_kelly_fraction(body["combined_prob"], 220) if book["ev_per_unit"] > 0 else 0.0
    assert raw < STAKE_CAP_DEFAULT
    assert book["half_kelly"] == pytest.approx(round(raw, 4), abs=1e-4)
    assert book["kelly_capped"] is False
