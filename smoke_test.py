"""Phase 0 smoke test: validate model fits, inference, and odds mathematics."""

from __future__ import annotations

import json

import model_setup
from backend.feeds import current_season
from backend.analytics import (
    beane_badge,
    blend_defense_inputs,
    hitter_run_value,
    parse_innings,
    percentile,
    pitcher_run_value,
    runs_per_win,
    score_pulse_items,
    starter_innings_share,
)
from backend.inference import predict_team
from backend.odds import (
    decimal_odds,
    decimal_to_american,
    edge_probability,
    half_kelly_fraction,
    log5_probability,
    market_vig,
    moneyline_to_probability,
    parlay_book_decimal,
    parlay_ev,
    parlay_probability,
    parlay_vig_comparison,
    probability_to_moneyline,
    pythagorean_strength,
)
from backend.precompute import build_artifacts
from backend.verdict import evaluate as evaluate_verdict
from backend.season_sim import simulate_season


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

    v2_tests(artifacts)
    production_entrypoint_test()


def production_entrypoint_test() -> None:
    """The production start command must boot the API and bind $PORT.

    Runs the exact process the deploy scripts run — NODE_ENV=production
    python -m backend.main — on a scratch port and requires a healthy
    /api/health before the deadline.
    """
    import json
    import os
    import subprocess
    import sys
    import time
    import urllib.request

    port = "8123"
    env = {**os.environ, "NODE_ENV": "production", "PORT": port}
    process = subprocess.Popen(
        [sys.executable, "-m", "backend.main"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        health = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(
                    "production entrypoint exited immediately "
                    f"(code {process.returncode}) instead of serving"
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health", timeout=2
                ) as response:
                    health = json.load(response)
                break
            except Exception:
                time.sleep(0.5)
        assert health is not None, "production entrypoint never answered /api/health"
        assert health["model_loaded"] is True, health
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    print("Production entrypoint passed: python -m backend.main serves $PORT.")


def v2_tests(artifacts: dict) -> None:
    """v2 math, every formula against a hand-checked example."""
    models = artifacts["models"]
    beta_obp = float(models["rs"].coef_[0])
    wins_slope = float(models["wins"].coef_[0])

    # 1. Runs per win derives from the fitted W~RD slope — the ~9.5 rule.
    assert_close(runs_per_win(), 1 / wins_slope, 1e-9, "runs/win from fitted slope")
    assert_close(runs_per_win(), 9.5, 0.2, "runs/win ≈ 9.5 (rediscovered rule)")

    # 2. mWAA receipts: a +.050 OBP hitter at exactly a 10% PA share.
    league = {"obp": 0.320, "slg": 0.410, "team_pa": 6000.0}
    value = hitter_run_value(
        obp=league["obp"] + 0.050,
        slg=league["slg"],  # SLG at league mean: the OBP term is the whole story
        plate_appearances=600.0,  # 600 / 6000 = 10% share
        league_obp=league["obp"],
        league_slg=league["slg"],
        league_team_pa=league["team_pa"],
        season=current_season(),
    )
    expected_delta_rs = 0.10 * beta_obp * 0.050
    assert_close(value["delta_rs"], expected_delta_rs, 0.05, "hitter ΔRS receipts")
    assert_close(
        value["mwaa"], expected_delta_rs * wins_slope, 0.01, "hitter mWAA = ΔRD × slope"
    )
    assert value["receipts"][0]["feature"] == "OBP"
    assert_close(
        value["receipts"][0]["runs"] + value["receipts"][1]["runs"],
        value["delta_rs"],
        0.11,
        "receipts sum to ΔRS",
    )

    # Pitcher: run prevention is positive value (sign flipped).
    beta_oobp = float(models["ra"].coef_[0])
    pitcher = pitcher_run_value(
        obp_against=0.290,
        slg_against=0.390,
        innings_pitched=144.0,  # 10% of a 1440-inning league-average team season
        league_obp_against=0.320,
        league_slg_against=0.390,
        league_team_ip=1440.0,
        season=current_season(),
    )
    expected_delta_ra = 0.10 * beta_oobp * -0.030
    assert_close(pitcher["delta_ra"], expected_delta_ra, 0.05, "pitcher ΔRA receipts")
    assert pitcher["mwaa"] > 0, "run prevention must be positive mWAA"

    # 3. Parlay math, hand-checked. Two independent 55% legs:
    combined = parlay_probability([0.55, 0.55])
    assert_close(combined, 0.3025, 1e-9, "55%×55% combined probability")
    assert probability_to_moneyline(combined) == 230, "fair parlay odds ≈ +230"

    # Two −110 legs pay ≈ +264 while true-fair coin flips deserve +300.
    book = parlay_book_decimal([-110, -110])
    assert decimal_to_american(book) == 264, "standard −110 parlay pays +264"
    assert probability_to_moneyline(0.25) == 300, "fair 25% parlay is +300"
    comparison = parlay_vig_comparison([0.5, 0.5], None)
    assert comparison["standard_book_parlay_line"] == 264
    assert comparison["fair_parlay_line"] == 300
    assert (
        comparison["parlay_house_take_pct"] > comparison["singles_house_take_pct"]
    ), "vig compounds: the parlay take must exceed the singles take"

    # A 60%/60% parlay priced at +250 is positive EV.
    combined_60 = parlay_probability([0.6, 0.6])
    ev = parlay_ev(combined_60, decimal_odds(250))
    assert_close(ev, 0.26, 1e-9, "60/60 at +250 EV per unit")
    assert ev > 0
    assert_close(
        half_kelly_fraction(combined_60, 250), 0.052, 1e-6, "60/60 half-Kelly"
    )

    # Same-game legs are refused with the v1 error envelope, before any fetch.
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)  # no lifespan: the rejection needs no models/feeds
    response = client.post(
        "/api/parlay/price",
        json={"legs": [{"gamePk": "1", "side": "home"}, {"gamePk": "1", "side": "away"}]},
    )
    assert response.status_code == 400
    envelope = response.json()
    assert envelope["error"]["code"] == "correlated_legs", envelope

    # 4. Blended ADJ inputs: w·starter + (1−w)·team, share capped to [0.4, 0.8].
    assert parse_innings("139.2") == 139 + 2 / 3, "MLB .2 innings notation"
    assert_close(starter_innings_share(90.0, 15), 2 / 3, 1e-4, "innings share 90/(15×9)")
    assert starter_innings_share(200.0, 20) == 0.8, "share capped at 0.8"
    assert starter_innings_share(30.0, 15) == 0.4, "share floored at 0.4"
    assert starter_innings_share(50.0, 0) is None, "no starts → no blend"
    blend = blend_defense_inputs(0.250, 0.350, 0.330, 0.430, 0.6)
    assert_close(blend["oobp"], 0.6 * 0.250 + 0.4 * 0.330, 1e-9, "blended OOBP")
    assert_close(blend["oslg"], 0.6 * 0.350 + 0.4 * 0.430, 1e-9, "blended OSLG")

    # 5. Percentiles and the WOULD-BEANE-BUY badge rule.
    pool = [0.300, 0.310, 0.320, 0.330, 0.340, 0.350, 0.360, 0.370, 0.380, 0.390]
    assert percentile(0.395, pool) == 100.0
    assert percentile(0.345, pool) == 50.0
    assert beane_badge(80.0, 55.0) and not beane_badge(70.0, 55.0)

    # 6. Pulse lexicon: auditable arithmetic, evidence returned.
    pulse = score_pulse_items(
        [
            {"text": "Walk-off win extends the streak"},
            {"text": "Star placed on 60-day IL after surgery"},
            {"text": "Nothing notable"},
        ]
    )
    # "walk-off"+"streak" vs "il"+"60-day"+"surgery": 100×(2−3)/5 = −20.
    assert pulse["positive_matches"] == 2 and pulse["negative_matches"] == 3
    assert pulse["pulse"] == -20 and len(pulse["evidence"]) == 2

    # 7. Simulation determinism: same seed + same inputs → the same table.
    standings = [
        {
            "team_id": index,
            "wins": 60 + index,
            "losses": 60 - index,
            "games_played": 120,
            "league_id": 103 if index < 6 else 104,
            "division_id": 200 + index // 3,
        }
        for index in range(12)
    ]
    strengths = {index: 0.42 + index * 0.015 for index in range(12)}
    schedule = [
        {"game_pk": 1000 + i, "home_id": i % 12, "away_id": (i + 5) % 12}
        for i in range(240)
        if i % 12 != (i + 5) % 12
    ]
    first = simulate_season(standings, strengths, schedule, seed=7, iterations=200)
    second = simulate_season(standings, strengths, schedule, seed=7, iterations=200)
    assert first == second, "same seed + inputs must reproduce the same table"
    third = simulate_season(standings, strengths, schedule, seed=8, iterations=200)
    assert first != third, "a different seed must be allowed to differ"
    for team_result in first.values():
        assert 0 <= team_result["playoff_odds"] <= 1
    # Fixture has 2 divisions per league: 2 winners + 3 wild cards = 5 spots each.
    total_playoff = sum(r["playoff_odds"] for r in first.values())
    assert_close(total_playoff, 10.0, 0.01, "12-team fixture: 5 playoff spots per league")

    # 8. Verdict engine: the hand-checked Appendix A arithmetic.
    # Green tests prove no regression against known values; they do not prove
    # new math is right. These two cases were worked by hand first (the
    # derivation is in verified_stats.json's comment history) and only then
    # confirmed against odds.py, so they are ground truth rather than a
    # snapshot of whatever the code happens to do.
    with open(model_setup.paths["verified_stats.json"], encoding="utf-8") as file:
        checks = json.load(file)["verdict_checks"]
    for name in ("fixture_1", "fixture_6"):
        case = checks[name]
        result = evaluate_verdict(
            p_season_home=case["probability"],
            p_adj_home=case["probability"],
            price_home=case["price"],
            gp_home=126,
            gp_away=126,
            starters_confirmed=True,
        )
        side = result["sides"]["home"]
        assert_close(side["raw"]["implied"], case["implied"], 1e-6, f"{name} implied")
        assert_close(side["raw"]["edge"], case["edge"], 1e-6, f"{name} edge")
        assert_close(side["raw"]["ev"], case["ev_per_unit"], 1e-6, f"{name} EV per unit")
        assert_close(side["raw"]["gap"], case["gap"], 1e-4, f"{name} signal gap")
        assert side["verdict"] == case["verdict"], f"{name} verdict"
        assert side["signal"] == case["signal"], f"{name} signal"
    # The engine composes odds.py rather than re-deriving it: the edge it
    # reports must equal edge_probability to the last bit, not merely round
    # to the same display value.
    assert (
        evaluate_verdict(
            p_season_home=0.58, price_home=-115, gp_home=126, gp_away=126
        )["sides"]["home"]["raw"]["edge"]
        == edge_probability(0.58, -115)
    ), "verdict edge must be odds.edge_probability exactly"

    print("v2 passed: mWAA receipts, runs/win, parlay math, blends, pulse, and the seeded sim.")


if __name__ == "__main__":
    main()