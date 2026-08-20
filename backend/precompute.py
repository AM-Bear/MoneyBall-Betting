"""Fit MONEYLINE's canonical chronological models and write startup artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score

import model_setup


ROOT = Path(__file__).resolve().parent
STATIC_DATA = ROOT / "static_data"
MODELS_PATH = STATIC_DATA / "moneyline_models.joblib"
TRACK_RECORD_PATH = STATIC_DATA / "track_record.json"
BACKTEST_PATH = STATIC_DATA / "backtest.json"
BA_PARADOX_PATH = STATIC_DATA / "ba_paradox.json"


def load_bundle() -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Load every bundled input through model_setup.paths as required."""
    with open(model_setup.paths["model_config.json"], encoding="utf-8") as file:
        model_config = json.load(file)
    with open(model_setup.paths["verified_stats.json"], encoding="utf-8") as file:
        verified_stats = json.load(file)
    data = pd.read_csv(model_setup.paths["baseball.csv"])
    return data, verified_stats, model_config


def _rounded(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _calibration(predictions: pd.Series, labels: pd.Series) -> list[dict[str, Any]]:
    buckets = [(0.5, 0.6, "50-60%"), (0.6, 0.7, "60-70%"), (0.7, 1.01, "70-100%")]
    result: list[dict[str, Any]] = []
    for lower, upper, label in buckets:
        mask = (predictions >= lower) & (predictions < upper)
        if int(mask.sum()) == 0:
            continue
        result.append(
            {
                "bucket": label,
                "n": int(mask.sum()),
                "actual_rate": _rounded(labels[mask].mean(), 3),
            }
        )
    return result


def _franchise_prior(team: str, year: int) -> tuple[str, int]:
    """Bridge the only historic naming transitions called out by the spec."""
    rebrands = {
        ("LAA", 2005): ("ANA", 2004),
        ("MIA", 2012): ("FLA", 2011),
        ("TBR", 2008): ("TBD", 2007),
        ("WSN", 2005): ("MON", 2004),
    }
    return rebrands.get((team, year), (team, year - 1))


def _backtest(data: pd.DataFrame, wins_model: LinearRegression, playoff_model: LogisticRegression) -> dict[str, Any]:
    """Create a transparent paper bankroll series with no season lookahead."""
    test = data[data["Year"] >= 2002].copy()
    previous_wins: list[float | None] = []
    for row in test.itertuples(index=False):
        prior_team, prior_year = _franchise_prior(str(row.Team), int(row.Year))
        prior = data[(data["Team"] == prior_team) & (data["Year"] == prior_year)]
        previous_wins.append(float(prior.iloc[0]["W"]) if not prior.empty else None)
    test["prior_wins"] = previous_wins
    test = test.dropna(subset=["prior_wins"]).copy()
    test["RD"] = test["RS"] - test["RA"]
    test["predicted_wins"] = wins_model.predict(test[["RD"]])
    test["playoff_probability"] = playoff_model.predict_proba(test[["W"]])[:, 1]
    test["model_gap"] = test["predicted_wins"] - test["prior_wins"]

    model_bankroll = 1000.0
    baseline_bankroll = 1000.0
    model_curve = [{"year": 2002, "bankroll": model_bankroll}]
    baseline_curve = [{"year": 2002, "bankroll": baseline_bankroll}]
    model_bets = model_wins = baseline_bets = baseline_wins = 0

    for year in sorted(test["Year"].unique()):
        season = test[test["Year"] == year]
        model_selection = season[season["model_gap"] >= 5]
        baseline_selection = season[season["prior_wins"] >= 90]
        for selection, kind in ((model_selection, "model"), (baseline_selection, "baseline")):
            for item in selection.itertuples(index=False):
                won = bool(item.Playoffs)
                if kind == "model":
                    model_bets += 1
                    model_wins += int(won)
                    model_bankroll += 1 if won else -1
                else:
                    baseline_bets += 1
                    baseline_wins += int(won)
                    baseline_bankroll += 1 if won else -1
        model_curve.append({"year": int(year), "bankroll": _rounded(model_bankroll, 2)})
        baseline_curve.append({"year": int(year), "bankroll": _rounded(baseline_bankroll, 2)})

    def summary(wins: int, bets: int, bankroll: float) -> dict[str, float]:
        units = bankroll - 1000
        return {
            "bets": bets,
            "wins": wins,
            "hit_rate": _rounded(wins / bets, 3) if bets else 0.0,
            "units": _rounded(units, 2),
            "roi": _rounded(units / bets, 3) if bets else 0.0,
        }

    return {
        "assumptions": {
            "starting_bankroll": 1000,
            "unit_size": 1,
            "vig": "none — educational paper simulation",
            "market_prior": "previous season wins",
            "model_selection": "predicted wins at least 5 above prior",
            "baseline_selection": "previous-season 90+ win teams",
            "prior_join_rows": int(len(test)),
            "franchise_bridges": ["ANA→LAA", "FLA→MIA", "TBD→TBR", "MON→WSN"],
        },
        "model": {"curve": model_curve, **summary(model_wins, model_bets, model_bankroll)},
        "baseline": {
            "curve": baseline_curve,
            **summary(baseline_wins, baseline_bets, baseline_bankroll),
        },
    }


def build_artifacts() -> dict[str, Any]:
    """Fit the specified models chronologically and persist all derived data."""
    STATIC_DATA.mkdir(parents=True, exist_ok=True)
    data, verified, model_config = load_bundle()
    if model_config.get("hub_repo_id") is not None:
        raise RuntimeError("MONEYLINE only supports the supplied local data bundle.")

    required_columns = {
        "Team", "League", "Year", "RS", "RA", "W", "OBP", "SLG", "BA",
        "Playoffs", "RankSeason", "RankPlayoffs", "G", "OOBP", "OSLG",
    }
    if data.shape != (1232, 15) or set(data.columns) != required_columns:
        raise RuntimeError("Bundled baseball.csv does not match the verified schema.")

    train = data[data["Year"] <= 2001].copy()
    test = data[data["Year"] >= 2002].copy()
    if len(train) != 902 or len(test) != 330:
        raise RuntimeError("Chronological split did not reproduce the verified row counts.")

    rs_model = LinearRegression().fit(train[["OBP", "SLG"]], train["RS"])
    ba_model = LinearRegression().fit(train[["OBP", "SLG", "BA"]], train["RS"])
    ra_train = train.dropna(subset=["OOBP", "OSLG"])
    ra_test = test.dropna(subset=["OOBP", "OSLG"])
    ra_model = LinearRegression().fit(ra_train[["OOBP", "OSLG"]], ra_train["RA"])

    train["RD"] = train["RS"] - train["RA"]
    test["RD"] = test["RS"] - test["RA"]
    wins_model = LinearRegression().fit(train[["RD"]], train["W"])
    playoff_model = LogisticRegression(max_iter=1000, random_state=0).fit(
        train[["W"]], train["Playoffs"]
    )

    rs_test_prediction = rs_model.predict(test[["OBP", "SLG"]])
    ra_test_prediction = ra_model.predict(ra_test[["OOBP", "OSLG"]])
    wins_test_prediction = wins_model.predict(test[["RD"]])
    playoff_test_prediction = playoff_model.predict(test[["W"]])
    playoff_probability = pd.Series(
        playoff_model.predict_proba(test[["W"]])[:, 1], index=test.index
    )

    models = {
        "rs": rs_model,
        "ba": ba_model,
        "ra": ra_model,
        "wins": wins_model,
        "playoffs": playoff_model,
        "data_ranges": {
            column: {"min": _rounded(data[column].min(), 3), "max": _rounded(data[column].max(), 3)}
            for column in ["OBP", "SLG", "OOBP", "OSLG"]
        },
    }
    joblib.dump(models, MODELS_PATH)

    track_record = {
        "dataset": {
            "rows": len(data),
            "train_rows": len(train),
            "test_rows": len(test),
            "split": "train ≤ 2001 · test ≥ 2002",
            "years": [int(data["Year"].min()), int(data["Year"].max())],
        },
        "runs": {
            "r2_train": _rounded(rs_model.score(train[["OBP", "SLG"]], train["RS"]), 3),
            "r2_test": _rounded(r2_score(test["RS"], rs_test_prediction), 3),
            "ra_r2_test": _rounded(r2_score(ra_test["RA"], ra_test_prediction), 3),
            "ra_training_rows": int(len(ra_train)),
            "ra_training_period": "1999–2001",
        },
        "wins": {
            "r2_test": _rounded(r2_score(test["W"], wins_test_prediction), 3),
            "mae_test_wins": _rounded(mean_absolute_error(test["W"], wins_test_prediction), 2),
        },
        "playoffs": {
            "accuracy_test": _rounded(accuracy_score(test["Playoffs"], playoff_test_prediction), 3),
            "majority_baseline": _rounded(1 - test["Playoffs"].mean(), 3),
            "test_base_rate": _rounded(test["Playoffs"].mean(), 3),
            "calibration": _calibration(playoff_probability, test["Playoffs"]),
            "note": "Top-end probabilities are under-confident in this historical test.",
        },
        "models": {
            "rs": {
                "intercept": _rounded(rs_model.intercept_, 1),
                "coefficients": {"OBP": _rounded(rs_model.coef_[0], 1), "SLG": _rounded(rs_model.coef_[1], 1)},
            },
            "ra": {
                "intercept": _rounded(ra_model.intercept_, 1),
                "coefficients": {"OOBP": _rounded(ra_model.coef_[0], 1), "OSLG": _rounded(ra_model.coef_[1], 1)},
            },
            "wins": {
                "intercept": _rounded(wins_model.intercept_, 2),
                "coefficients": {"RD": _rounded(wins_model.coef_[0], 4)},
            },
        },
        "verified_reference": verified,
    }
    ba_paradox = {
        "base": {
            "features": ["OBP", "SLG"],
            "coefficients": {
                "OBP": _rounded(rs_model.coef_[0], 1),
                "SLG": _rounded(rs_model.coef_[1], 1),
            },
            "r2_train": _rounded(rs_model.score(train[["OBP", "SLG"]], train["RS"]), 3),
        },
        "with_ba": {
            "features": ["OBP", "SLG", "BA"],
            "coefficients": {
                "OBP": _rounded(ba_model.coef_[0], 1),
                "SLG": _rounded(ba_model.coef_[1], 1),
                "BA": _rounded(ba_model.coef_[2], 1),
            },
            "r2_train": _rounded(ba_model.score(train[["OBP", "SLG", "BA"]], train["RS"]), 3),
        },
        "caption": "Once OBP and SLG are known, BA adds no positive predictive signal in this fit.",
    }

    TRACK_RECORD_PATH.write_text(json.dumps(track_record, indent=2), encoding="utf-8")
    BA_PARADOX_PATH.write_text(json.dumps(ba_paradox, indent=2), encoding="utf-8")
    BACKTEST_PATH.write_text(json.dumps(_backtest(data, wins_model, playoff_model), indent=2), encoding="utf-8")
    return {"models": models, "track_record": track_record, "verified": verified}


if __name__ == "__main__":
    build_artifacts()
    print("MONEYLINE artifacts built.")