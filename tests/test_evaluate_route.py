"""Contract tests for POST /api/evaluate.

The engine's arithmetic is pinned in tests/test_verdict_engine.py. These
cover only what the route adds: request validation, the error envelope, the
fields main.py attaches, and the guarantee that adding this endpoint left
/api/matchup alone.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import backend.main as main
from backend.precompute import MODEL_VERSION

client = TestClient(main.app)

FULL = {
    "p_season_home": 0.58,
    "p_adj_home": 0.58,
    "price_home": -115,
    "gp_home": 126,
    "gp_away": 126,
    "starters_confirmed": True,
}


def test_route_returns_the_appendix_a_verdict():
    response = client.post("/api/evaluate", json=FULL)
    assert response.status_code == 200
    body = response.json()
    home = body["sides"]["home"]
    assert home["verdict"] == "BET_CANDIDATE"
    assert home["edge_pts"] == 4.5
    assert home["ev_per_100"] == 8.4
    assert body["game"]["side"] == "home"


def test_route_stamps_the_model_version_and_the_equity_caveat():
    body = client.post("/api/evaluate", json=FULL).json()
    assert body["model_version"] == MODEL_VERSION
    # EQUITY_CAVEAT is the exact text the "not priced" chips need and had no
    # home before this endpoint.
    assert body["caveat"] == main.EQUITY_CAVEAT


def test_route_publishes_the_rubric_it_judged_by():
    body = client.post("/api/evaluate", json=FULL).json()
    published = body["thresholds"]
    assert published["candidate_ev"] == 0.04
    assert published["candidate_edge"] == 0.03
    assert published["avoid_ev"] == -0.05
    assert published["sigma"] == 0.04


def test_both_sides_are_scored_when_both_prices_are_supplied():
    body = client.post(
        "/api/evaluate",
        json={**FULL, "p_season_home": 0.55, "p_adj_home": 0.55,
              "price_home": -200, "price_away": 250},
    ).json()
    assert body["sides"]["home"]["edge_pts"] is not None
    assert body["sides"]["away"]["edge_pts"] is not None
    # The model leans home; the price makes away the value side. The payload
    # says so rather than leaving the reader to fuse the two.
    assert body["game"]["lean_side"] == "home"
    assert body["game"]["side"] == "away"
    assert body["game"]["lean_differs_from_value"] is True


def test_an_impossible_moneyline_is_a_400_in_the_standard_envelope():
    response = client.post("/api/evaluate", json={**FULL, "price_home": -50})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_zero_moneyline_is_rejected():
    response = client.post("/api/evaluate", json={**FULL, "price_away": 0})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_probability_outside_the_unit_interval_is_rejected():
    response = client.post("/api/evaluate", json={**FULL, "p_season_home": 1.4})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_an_unknown_status_is_rejected_by_validation_not_by_a_500():
    response = client.post("/api/evaluate", json={**FULL, "status": "rain-delay"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_refusal_is_a_200_result_not_an_error():
    """Honest refusals are payloads. An early-season game is not a failure."""
    response = client.post(
        "/api/evaluate",
        json={**FULL, "gp_home": 18, "gp_away": 20},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sides"]["home"]["verdict"] == "INSUFFICIENT_DATA"
    assert body["sides"]["home"]["verdict_reason"] == "early_season"
    # The model's chance is still published; only the value call is withheld.
    assert body["sides"]["home"]["p_eval"] == 0.58
    assert body["sides"]["home"]["fair_line"] is not None


def test_no_price_still_publishes_a_fair_line_and_no_edge():
    body = client.post(
        "/api/evaluate",
        json={"p_season_home": 0.53, "gp_home": 126, "gp_away": 126},
    ).json()
    home = body["sides"]["home"]
    assert home["verdict_reason"] == "no_price"
    assert home["fair_line"] == -115
    assert home["edge_pts"] is None
    assert home["ev_per_100"] is None


def test_the_endpoint_returns_no_stake_and_no_kelly():
    """Scope boundary, asserted so it cannot drift in.

    Staking is Appendix C and a different endpoint. It matters here because
    odds.half_kelly_fraction is uncapped despite its docstring -- 0.99 at
    +1000 returns 0.4945, i.e. 49% of bankroll -- so the safest respect for
    that is to expose no stake from this route at all.
    """
    body = client.post("/api/evaluate", json=FULL).json()
    flat = repr(body)
    assert "kelly" not in flat.lower()
    assert "stake" not in flat.lower()


def test_matchup_is_untouched_by_the_new_endpoint():
    """/api/matchup keeps its own ruleset, one-sided contract included."""
    inputs = {"obp": 0.339, "slg": 0.432, "oobp": 0.315, "oslg": 0.384}
    response = client.post(
        "/api/matchup",
        json={
            "team_a": inputs,
            "team_b": {"obp": 0.330, "slg": 0.420, "oobp": 0.320, "oslg": 0.395},
            "book_line_a": -115,
            "evaluation_side": "a",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_side"] == "a"
    assert body["verdict"] in {
        "VALUE",
        "INSIDE THE VIG — NO PLAYABLE EDGE",
        "NO VALUE",
        "NO LINE",
    }
    # The two engines share no vocabulary, which is how they stay separable.
    assert body["verdict"] not in {
        "BET_CANDIDATE", "MARGINAL_VALUE", "AVOID_AT_THIS_PRICE",
        "INSUFFICIENT_DATA",
    }
