"""Appendix A fixtures for the verdict engine.

Provenance matters here, so it is marked. Tests named `test_fixture_N_*` are
the ten fixtures the spec says must pass before the engine ships
(`attached_assets/MONEYLINE_v3_Product_Strategy_and_UX_Plan_1787528143354.md:1337-1350`).
Tests marked DESK-AUTHORED are ours: Appendix A ships three rules with no
fixture at all (`small_sample`, `prices_disagree`, the volatility bands), and
untested rules are how a rubric quietly stops matching its own description.
A later reader can tell which expectations carry spec authority and which
carry ours.

Every expected number was reproduced against `backend/odds.py` before being
written down, not copied from the spec table.

One correction to the fixture table, applied throughout: fixtures 1 and 4 both
expect a **Strong** signal, and Strong requires `agree`, which is undefined
without `p_adj`. Fixture 10 is defined as "fixture 1 with `p_adj` null" and
expects a *different* answer (capped Moderate). If fixture 1 already had
`p_adj` null, fixture 10 would be the same case and would prove nothing. So
fixture 1 carries `p_adj == p_season`, consistent with its own "starters
confirmed", and fixture 4 likewise.
"""

from __future__ import annotations

import pytest

from backend.verdict import THRESHOLDS, evaluate

FULL_SEASON = {"gp_home": 126, "gp_away": 126, "starters_confirmed": True}


def home(result):
    return result["sides"]["home"]


def away(result):
    return result["sides"]["away"]


# --------------------------------------------------------------------------
# The ten Appendix A fixtures
# --------------------------------------------------------------------------

def test_fixture_1_clear_candidate_on_a_confirmed_full_season_slate():
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115, **FULL_SEASON
    )
    side = home(result)
    assert side["edge_pts"] == 4.5
    assert side["ev_per_100"] == 8.4
    assert side["verdict"] == "BET_CANDIDATE"
    assert side["gap"] == 1.13
    assert side["signal"] == "Strong"
    assert side["flags"] == []
    # The label is not yet backed by graded outcomes and says so.
    assert side["signal_provisional"] is True
    assert result["game"]["side"] == "home"
    assert result["game"]["verdict"] == "BET_CANDIDATE"


def test_fixture_2_avoid_on_one_side_no_value_on_the_other():
    # LAD (home) 0.55 at -150; SD (away) 0.45 at +125.
    result = evaluate(
        p_season_home=0.55, price_home=-150, price_away=125,
        gp_home=126, gp_away=126,
    )
    lad, sdp = home(result), away(result)
    assert lad["edge_pts"] == -5.0
    assert lad["ev_per_100"] == -8.3
    assert lad["verdict"] == "AVOID_AT_THIS_PRICE"
    assert sdp["edge_pts"] == 0.6
    # The spec prints this one to 2 d.p.; the raw value is exactly +1.25.
    assert sdp["raw"]["ev"] * 100 == pytest.approx(1.25, abs=1e-9)
    # +0.56 pts displays as +0.6, but 0.005556 < 0.01 raw. Compared raw, so the
    # rounding cannot promote a near-miss into a pass.
    assert sdp["verdict"] == "NO_VALUE"
    assert result["game"]["verdict"] == "NO_VALUE"
    assert result["game"]["side"] is None
    assert "Home" in result["game"]["avoid_note"]


def test_fixture_3_no_price_still_publishes_the_fair_line():
    result = evaluate(p_season_home=0.53, gp_home=126, gp_away=126)
    side = home(result)
    assert side["verdict"] == "INSUFFICIENT_DATA"
    assert side["verdict_reason"] == "no_price"
    assert "no_price" in side["flags"]
    assert side["fair_line"] == -115
    # Nothing to be edgy against, so nothing is claimed.
    assert side["edge_pts"] is None
    assert side["ev_per_100"] is None
    assert side["signal"] is None


def test_fixture_4_large_underdog_edge():
    result = evaluate(
        p_season_home=0.60, p_adj_home=0.60, price_home=150, **FULL_SEASON
    )
    side = home(result)
    assert side["edge_pts"] == 20.0
    assert side["ev_per_100"] == 50.0
    assert side["verdict"] == "BET_CANDIDATE"
    assert side["signal"] == "Strong"


def test_fixture_5_slightly_negative_ev_is_no_value_not_avoid():
    # The case that proves AVOID's rule is a strict subset of NO_VALUE's and
    # the table must be read top-down.
    result = evaluate(
        p_season_home=0.52, p_adj_home=0.52, price_home=-110, **FULL_SEASON
    )
    side = home(result)
    assert side["edge_pts"] == -0.4
    assert side["ev_per_100"] == -0.7
    assert side["verdict"] == "NO_VALUE"


def test_fixture_6_marginal_value_with_a_weak_signal():
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-130, **FULL_SEASON
    )
    side = home(result)
    assert side["edge_pts"] == 1.5
    assert side["ev_per_100"] == 2.6
    assert side["verdict"] == "MARGINAL_VALUE"
    assert side["gap"] == 0.37
    assert side["signal"] == "Weak"


def test_fixture_7_evaluates_on_the_adjusted_chance_and_says_so():
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.54, price_home=-115, **FULL_SEASON
    )
    side = home(result)
    assert side["p_basis"] == "adj"
    assert side["p_eval"] == 0.54
    assert side["edge_pts"] == 0.5
    assert side["verdict"] == "NO_VALUE"
    # Both EVs are positive here, so this is agreement, not a disagreement.
    assert side["agree"] is True
    assert "prices_disagree" not in side["flags"]
    assert side["basis_note"] is not None
    assert "season-only" in side["basis_note"]


def test_fixture_8_early_season_gates_both_sides():
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115,
        gp_home=18, gp_away=20, starters_confirmed=True,
    )
    for side in (home(result), away(result)):
        assert side["verdict"] == "INSUFFICIENT_DATA"
        assert side["verdict_reason"] == "early_season"
        # The model's chance is still displayed; only the value call is refused.
        assert side["p_eval"] is not None
        assert side["fair_line"] is not None
    assert result["game"]["verdict"] == "INSUFFICIENT_DATA"
    assert result["game"]["side"] is None


def test_fixture_9_a_stale_price_flags_but_does_not_overturn():
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115,
        price_age_s=40 * 60, **FULL_SEASON
    )
    side = home(result)
    assert side["verdict"] == "BET_CANDIDATE"
    assert "stale" in side["flags"]
    # The spec does not assert the signal here; it derives it. gap 1.13 with
    # one ingredient missing is Moderate.
    assert side["signal"] == "Moderate"


def test_fixture_10_unconfirmed_starters_cap_the_signal_at_moderate():
    result = evaluate(
        p_season_home=0.58, p_adj_home=None, price_home=-115, **FULL_SEASON
    )
    side = home(result)
    assert side["verdict"] == "BET_CANDIDATE"
    assert "starters_unconfirmed" in side["flags"]
    assert side["signal"] == "Moderate"
    assert side["p_basis"] == "season"
    # `agree` is undefined, not false -- and the two behave differently.
    assert side["agree"] is None


# --------------------------------------------------------------------------
# DESK-AUTHORED. Not Appendix A: these three rules ship with no fixture.
# --------------------------------------------------------------------------

def test_desk_small_sample_flags_and_raises_uncertainty():
    # 45 GP clears the hard floor of 30 but is under the 60 small-sample mark.
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115,
        gp_home=45, gp_away=50, starters_confirmed=True,
    )
    side = home(result)
    assert side["verdict"] == "BET_CANDIDATE"
    assert "small_sample" in side["flags"]
    assert side["uncertainty"] == "High"
    # One ingredient missing caps an otherwise-Strong signal.
    assert side["signal"] == "Moderate"


def test_desk_prices_disagree_demotes_a_candidate_to_marginal():
    # Season says clear value, the starter-adjusted chance says the opposite
    # sign of EV. A side that would be a candidate becomes MARGINAL.
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.52, price_home=-115, **FULL_SEASON
    )
    side = home(result)
    assert side["agree"] is False
    assert side["verdict"] != "BET_CANDIDATE"


def test_desk_prices_disagree_flag_fires_when_the_adjusted_side_still_qualifies():
    # p_adj clears both candidate thresholds on its own, but the season EV is
    # negative, so the two bases disagree: MARGINAL plus the flag. At +140 the
    # break-even is 0.4167, so the season probability has to sit below that for
    # the signs to actually differ.
    result = evaluate(
        p_season_home=0.35, p_adj_home=0.62, price_home=140, **FULL_SEASON
    )
    side = home(result)
    assert side["raw"]["ev"] >= THRESHOLDS["candidate_ev"]
    assert side["raw"]["edge"] >= THRESHOLDS["candidate_edge"]
    assert side["agree"] is False
    assert "prices_disagree" in side["flags"]
    assert side["verdict"] == "MARGINAL_VALUE"


def test_desk_volatility_bands():
    # "shorter" is a bigger favourite, "longer" a bigger underdog.
    short = evaluate(
        p_season_home=0.90, p_adj_home=0.90, price_home=-250, **FULL_SEASON
    )
    assert home(short)["volatility"] == "Lower"
    long_dog = evaluate(
        p_season_home=0.60, p_adj_home=0.60, price_home=150, **FULL_SEASON
    )
    assert home(long_dog)["volatility"] == "Higher"
    typical = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115, **FULL_SEASON
    )
    assert home(typical)["volatility"] == "Typical"


def test_desk_the_value_side_can_differ_from_the_lean():
    """The failure this engine exists to fix, as an assertion.

    The model leans home, but the away price is the one with value. Before
    this engine the card showed a lean naming home and a verdict computed for
    away, with nothing saying they were different questions.
    """
    result = evaluate(
        p_season_home=0.55, p_adj_home=0.55,
        price_home=-200, price_away=250, **FULL_SEASON
    )
    game = result["game"]
    assert game["lean_side"] == "home"
    assert game["side"] == "away"
    assert game["lean_differs_from_value"] is True
    assert "not the lean" in game["takeaway"]


def test_desk_a_started_game_is_frozen_with_no_verdict():
    for status in ("live", "final", "postponed"):
        result = evaluate(
            p_season_home=0.58, p_adj_home=0.58, price_home=-115,
            status=status, **FULL_SEASON
        )
        assert result["game"]["frozen"] is True
        assert result["game"]["verdict"] is None
        assert home(result)["verdict"] is None
        assert home(result)["verdict_reason"] == "status_frozen"


def test_desk_a_frozen_game_carries_no_evaluation_flags():
    """Flags are outputs of an evaluation that did not happen.

    Leaving `no_price` on a frozen side made the card render a "No book price
    entered" chip beside a "Verdict frozen" pill -- pointing the reader at a
    price input the card does not show for a started game.
    """
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.58, status="final", **FULL_SEASON
    )
    assert home(result)["flags"] == []
    assert away(result)["flags"] == []
    # A scheduled game with the same inputs still reports them.
    live = evaluate(p_season_home=0.58, p_adj_home=0.58, **FULL_SEASON)
    assert "no_price" in home(live)["flags"]


def test_desk_missing_games_played_gates_rather_than_defaulting():
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115,
        gp_home=None, gp_away=None, starters_confirmed=True,
    )
    assert home(result)["verdict"] == "INSUFFICIENT_DATA"
    assert result["sample"]["label"] == "GP UNKNOWN"


def test_desk_unknown_gp_is_not_reported_as_an_early_season():
    """Two different facts, two different refusals.

    A missing count is a statement about our own data; a young season is a
    statement about the season. Collapsing them would have the desk announce
    "not enough of the season on the board" in late August because a team
    lookup missed -- a false statement dressed up as a refusal, and the same
    species of error as writing `entered_line = fair_line`.
    """
    unknown = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115,
        gp_home=None, gp_away=None, starters_confirmed=True,
    )
    young = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115,
        gp_home=18, gp_away=20, starters_confirmed=True,
    )
    assert home(unknown)["verdict_reason"] == "gp_unavailable"
    assert "gp_unavailable" in home(unknown)["flags"]
    assert home(young)["verdict_reason"] == "early_season"
    assert "early_season" in home(young)["flags"]
    # The takeaway must not claim a young season when the truth is a miss.
    assert "season on the board" not in unknown["game"]["takeaway"]
    assert "unavailable" in unknown["game"]["takeaway"]


def test_desk_both_sides_are_always_evaluated():
    """A one-price payload is the one-sidedness this replaces."""
    result = evaluate(
        p_season_home=0.55, p_adj_home=0.55,
        price_home=-120, price_away=110, **FULL_SEASON
    )
    assert home(result)["price"] == -120
    assert away(result)["price"] == 110
    assert away(result)["p_eval"] == pytest.approx(0.45)
    assert home(result)["edge_pts"] is not None
    assert away(result)["edge_pts"] is not None


def test_desk_no_price_anywhere_is_a_data_state_not_a_judgment():
    """Regression: the game must not reject a price the reader never entered.

    With both sides unpriced the engine used to fall through to the contenders
    branch and answer NO_VALUE / "no side clears the minimum edge at your
    price" -- a considered-sounding rejection of nothing, rendered over an
    empty price box. Found by the card worker against the live endpoint.
    """
    result = evaluate(p_season_home=0.58, p_adj_home=0.58, **FULL_SEASON)
    game = result["game"]
    assert game["verdict"] == "INSUFFICIENT_DATA"
    assert game["verdict_reason"] == "no_price"
    assert game["side"] is None
    assert "minimum edge" not in game["takeaway"]
    assert "your price" not in game["takeaway"]
    # The model's own answer is still published on both sides.
    assert home(result)["fair_line"] is not None
    assert away(result)["fair_line"] is not None


def test_desk_one_priced_side_still_gets_a_real_verdict():
    """The no-price short circuit must not swallow a half-priced game."""
    result = evaluate(
        p_season_home=0.58, p_adj_home=0.58, price_home=-115, **FULL_SEASON
    )
    assert result["game"]["verdict"] == "BET_CANDIDATE"
    assert result["game"]["side"] == "home"
    assert away(result)["verdict_reason"] == "no_price"


def test_desk_user_facing_copy_carries_no_double_hyphen():
    """Comments may use `--`; prose a person reads may not."""
    result = evaluate(
        p_season_home=0.55, p_adj_home=0.55,
        price_home=-200, price_away=250, **FULL_SEASON
    )
    game = result["game"]
    assert "--" not in game["takeaway"]
    avoid = evaluate(
        p_season_home=0.55, price_home=-150, price_away=125,
        gp_home=126, gp_away=126,
    )["game"]["avoid_note"]
    assert avoid is not None and "--" not in avoid
    # A single avoided side takes a singular verb.
    assert " is priced" in avoid


def test_desk_thresholds_ship_with_every_response():
    result = evaluate(p_season_home=0.58, price_home=-115, **FULL_SEASON)
    published = result["thresholds"]
    assert published["sigma"] == 0.04
    assert published["candidate_ev"] == 0.04
    assert published["candidate_edge"] == 0.03
    assert published["avoid_ev"] == -0.05
    # sigma is a placeholder and the payload says so rather than implying
    # a calibrated statistic.
    assert published["sigma_is_provisional"] is True


def test_desk_engine_touches_no_context_signals():
    """Doctrine, checked mechanically rather than by eye.

    Pulse, injury flags and the wire cannot reach a verdict because the module
    does not import anything that carries them. Asserted against the import
    graph, not the text: a prose mention of `load_models()` explaining why it
    is absent must not fail the check, and a real import must not pass it.
    """
    import ast

    import backend.verdict as module

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert {name for name in imported if name.startswith("backend")} == {
        "backend.odds"
    }


def test_desk_an_unknown_status_is_rejected_rather_than_assumed():
    with pytest.raises(ValueError):
        evaluate(p_season_home=0.58, price_home=-115, status="rain-delay", **FULL_SEASON)
