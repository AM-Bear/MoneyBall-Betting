"""Manual moneylines must be evaluated for the side the user entered."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.odds import moneyline_to_probability


TEAM_A = {"obp": 0.336, "slg": 0.432, "oobp": 0.312, "oslg": 0.398}
TEAM_B = {"obp": 0.308, "slg": 0.382, "oobp": 0.329, "oslg": 0.421}


@pytest.mark.parametrize(
    ("side", "lines", "probability_key"),
    [
        ("a", {"book_line_a": 120, "book_line_b": None}, "model_prob_a"),
        ("b", {"book_line_a": None, "book_line_b": 120}, "model_prob_b"),
    ],
)
def test_matchup_evaluates_the_requested_manual_price_side(
    side: str, lines: dict[str, int | None], probability_key: str
) -> None:
    response = TestClient(main.app).post(
        "/api/matchup",
        json={"team_a": TEAM_A, "team_b": TEAM_B, "evaluation_side": side, **lines},
    )

    assert response.status_code == 200
    body = response.json()
    implied = moneyline_to_probability(120)
    assert body["evaluation_side"] == side
    assert body["verdict"] != "NO LINE"
    assert body["break_even_rate"] == round(implied, 4)
    assert body["edge_pp"] == round((body[probability_key] - implied) * 100, 1)
    assert body["kelly_fraction"] >= 0