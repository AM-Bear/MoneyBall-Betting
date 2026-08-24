"""The playoff logistic is a 1962–2012 panel number and must say so.

`models["playoffs"]` was fit on train ≤ 2001 and tested on ≥ 2002, against a
bundle whose last season is 2012.  Run on live-season inputs it still returns a
probability, and that probability is miscalibrated.  The desk refuses to price
what it never fit, so the payload has to carry the panel it came from — the
number is never suppressed and never silently recalibrated.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main
from backend.inference import load_data


LIVE_SEASON = 2026
PANEL_SEASON = 2002

# 2002 OAK, the hand-checked chain in verified_stats.json.
OAK_2002 = {"obp": 0.339, "slg": 0.432, "oobp": 0.315, "oslg": 0.384}

VERIFIED = json.loads(
    (Path(__file__).resolve().parents[1] / "verified_stats.json").read_text(
        encoding="utf-8"
    )
)


def _price(payload: dict[str, object]) -> dict:
    response = TestClient(main.app).post("/api/price", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_panel_bounds_come_from_the_bundle_not_a_literal() -> None:
    data = load_data()
    assert int(data["Year"].min()) == VERIFIED["dataset"]["years"][0]
    assert int(data["Year"].max()) == VERIFIED["dataset"]["years"][1]


def test_live_season_inputs_are_flagged_as_historical_panel_only() -> None:
    basis = _price({**OAK_2002, "season": LIVE_SEASON})["predicted"][
        "playoff_prob_basis"
    ]

    assert basis["in_panel"] is False
    assert basis["status"] == "HISTORICAL PANEL ONLY"
    assert basis["season"] == LIVE_SEASON
    assert basis["panel"] == "1962–2012"
    assert basis["note"]


def test_undeclared_season_is_flagged_because_the_panel_cannot_be_vouched_for() -> None:
    basis = _price(OAK_2002)["predicted"]["playoff_prob_basis"]

    assert basis["in_panel"] is False
    assert basis["status"] == "HISTORICAL PANEL ONLY"
    assert basis["season"] is None


def test_panel_season_inputs_are_not_flagged() -> None:
    basis = _price({**OAK_2002, "season": PANEL_SEASON})["predicted"][
        "playoff_prob_basis"
    ]

    assert basis["in_panel"] is True
    assert basis["status"] == "IN PANEL"
    assert basis["season"] == PANEL_SEASON


def test_the_disclosure_does_not_change_the_playoff_probability() -> None:
    flagged = _price({**OAK_2002, "season": LIVE_SEASON})["predicted"]
    in_panel = _price({**OAK_2002, "season": PANEL_SEASON})["predicted"]
    undeclared = _price(OAK_2002)["predicted"]

    # verified_stats.json pins the hand-checked chain to three decimals; the
    # payload carries four.  Both must still describe the same number.
    expected = VERIFIED["oak_2002_chain"]["predicted"]["playoff_prob"]
    assert round(flagged["playoff_prob"], 3) == expected
    assert flagged["playoff_prob"] == in_panel["playoff_prob"]
    assert flagged["playoff_prob"] == undeclared["playoff_prob"]


def test_the_disclosure_does_not_change_the_rest_of_the_chain() -> None:
    flagged = _price({**OAK_2002, "season": LIVE_SEASON})["predicted"]
    in_panel = _price({**OAK_2002, "season": PANEL_SEASON})["predicted"]

    numbers = ("rs", "ra", "rd", "wins")
    assert [flagged[key] for key in numbers] == [in_panel[key] for key in numbers]


def test_offense_only_inputs_carry_no_playoff_basis() -> None:
    predicted = _price({"obp": OAK_2002["obp"], "slg": OAK_2002["slg"]})["predicted"]

    assert predicted["playoff_prob"] is None
    assert predicted["playoff_prob_basis"] is None


def test_a_bundled_team_season_declares_its_own_year_and_stays_in_panel() -> None:
    response = TestClient(main.app).get(f"/api/team/OAK/{PANEL_SEASON}")

    assert response.status_code == 200, response.text
    predicted = response.json()["predicted"]
    assert round(predicted["playoff_prob"], 3) == (
        VERIFIED["oak_2002_chain"]["predicted"]["playoff_prob"]
    )
    assert predicted["playoff_prob_basis"]["in_panel"] is True
    assert predicted["playoff_prob_basis"]["season"] == PANEL_SEASON


def test_matchup_predictions_carry_the_basis_beside_the_probability() -> None:
    response = TestClient(main.app).post(
        "/api/matchup",
        json={
            "team_a": {**OAK_2002, "year": LIVE_SEASON},
            "team_b": {**OAK_2002, "year": PANEL_SEASON},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["team_a_prediction"]["playoff_prob_basis"]["in_panel"] is False
    assert body["team_b_prediction"]["playoff_prob_basis"]["in_panel"] is True
