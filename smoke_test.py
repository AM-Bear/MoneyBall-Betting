"""Phase 0 smoke test: validate model fits, inference, and odds mathematics."""

from __future__ import annotations

import json

import model_setup
from backend.inference import predict_team
from backend.odds import (
    edge_probability,
    half_kelly_fraction,
    log5_probability,
    market_vig,
    moneyline_to_probability,
    probability_to_moneyline,
    pythagorean_strength,
)
from backend.precompute import build_artifacts


def assert_close(actual: float, expected: float, tolerance: float, label: str) -> None:
    if abs(actual - expected) > tolerance:
        raise AssertionError(
            f"{label}: expected {expected} ± {tolerance}, received {actual}"
        )


def main() -> None:
    artifacts = build_artifacts()
    with open(model_setup.paths["verified_stats.json"], encoding="utf-8") as file:
        verified = json.load(file)

    data, _reference, _config = __import__("backend.precompute", fromlist=["load_bundle"]).load_bundle()
    assert data.shape == (1232, 15)
    assert int(data["Year"].min()) == 1962 and int(data["Year"].max()) == 2012

    chain = predict_team("OAK", 2002)
    expected = verified["oak_2002_chain"]["predicted"]
    assert_close(chain["predicted"]["rs"], expected["RS"], 2, "2002 OAK predicted RS")
    assert_close(chain["predicted"]["ra"], expected["RA"], 2, "2002 OAK predicted RA")
    assert_close(chain["predicted"]["wins"], expected["W"], 1, "2002 OAK predicted wins")
    assert_close(
        chain["predicted"]["playoff_prob"],
        expected["playoff_prob"],
        0.02,
        "2002 OAK playoff probability",
    )

    rs_model = artifacts["models"]["rs"]
    assert_close(rs_model.intercept_, verified["rs_model"]["intercept"], 1, "RS intercept")
    assert_close(rs_model.coef_[0], verified["rs_model"]["coef_OBP"], 2, "RS OBP coefficient")
    assert_close(rs_model.coef_[1], verified["rs_model"]["coef_SLG"], 2, "RS SLG coefficient")

    assert probability_to_moneyline(0.6) == verified["odds_checks"]["p60_to_ml"]
    assert_close(
        moneyline_to_probability(-150),
        verified["odds_checks"]["ml_minus150_to_p"],
        0.001,
        "-150 implied probability",
    )
    assert_close(
        moneyline_to_probability(130),
        verified["odds_checks"]["ml_plus130_to_p"],
        0.001,
        "+130 implied probability",
    )
    assert_close(
        half_kelly_fraction(0.6, 150),
        1 / 6,
        0.0001,
        "half-Kelly for 60% at +150",
    )
    assert_close(
        edge_probability(0.6, 150),
        0.2,
        0.0001,
        "edge versus a +150 break-even rate",
    )
    assert_close(
        market_vig(-110, -110),
        0.047619,
        0.0001,
        "two-sided -110 market vig",
    )
    assert half_kelly_fraction(0.6, -150) == 0
    strength = pythagorean_strength(800, 650)
    assert_close(
        log5_probability(strength, 0.5),
        strength,
        0.0001,
        "log5 versus a league-average opponent",
    )
    print("Phase 0 passed: models, 2002 OAK chain, and odds math reproduce the bundle.")


if __name__ == "__main__":
    main()