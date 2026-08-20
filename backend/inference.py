"""The single load-once model inference module used by tests and the API."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

import model_setup
from backend.odds import probability_to_moneyline, pythagorean_strength
from backend.precompute import MODELS_PATH, STATIC_DATA, build_artifacts


@lru_cache(maxsize=1)
def load_models() -> dict[str, Any]:
    if not MODELS_PATH.exists():
        build_artifacts()
    return joblib.load(MODELS_PATH)


@lru_cache(maxsize=1)
def load_data() -> pd.DataFrame:
    return pd.read_csv(model_setup.paths["baseball.csv"])


def _number(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def predict_from_inputs(
    obp: float,
    slg: float,
    oobp: float | None = None,
    oslg: float | None = None,
) -> dict[str, Any]:
    """Run the Moneyball chain for real or user-adjusted team inputs."""
    models = load_models()
    predicted_rs = float(models["rs"].predict(pd.DataFrame([{"OBP": obp, "SLG": slg}]))[0])
    has_defense = oobp is not None and oslg is not None
    predicted_ra = (
        float(models["ra"].predict(pd.DataFrame([{"OOBP": oobp, "OSLG": oslg}]))[0])
        if has_defense
        else None
    )
    predicted_rd = predicted_rs - predicted_ra if predicted_ra is not None else None
    predicted_wins = (
        float(models["wins"].predict(pd.DataFrame([{"RD": predicted_rd}]))[0])
        if predicted_rd is not None
        else None
    )
    playoff_probability = (
        float(models["playoffs"].predict_proba(pd.DataFrame([{"W": predicted_wins}]))[0][1])
        if predicted_wins is not None
        else None
    )
    generic_strength = (
        pythagorean_strength(predicted_rs, predicted_ra) if predicted_ra is not None else None
    )

    receipt_fields = [
        ("OBP", obp, float(models["rs"].coef_[0])),
        ("SLG", slg, float(models["rs"].coef_[1])),
    ]
    if has_defense:
        receipt_fields += [
            ("OOBP", float(oobp), float(models["ra"].coef_[0])),
            ("OSLG", float(oslg), float(models["ra"].coef_[1])),
        ]
    receipts = [
        {
            "feature": feature,
            "value": _number(value, 3),
            "coefficient": _number(coefficient, 1),
            "contribution": _number(value * coefficient, 1),
        }
        for feature, value, coefficient in receipt_fields
    ]
    return {
        "inputs": {"obp": obp, "slg": slg, "oobp": oobp, "oslg": oslg},
        "predicted": {
            "rs": _number(predicted_rs),
            "ra": _number(predicted_ra) if predicted_ra is not None else None,
            "rd": _number(predicted_rd) if predicted_rd is not None else None,
            "wins": _number(predicted_wins) if predicted_wins is not None else None,
            "playoff_prob": _number(playoff_probability, 4) if playoff_probability is not None else None,
        },
        "fair_line": probability_to_moneyline(generic_strength) if generic_strength is not None else None,
        "offense_only": not has_defense,
        "receipts": receipts,
    }


def predict_team(team: str, year: int) -> dict[str, Any]:
    """Run the chain for one verified bundled team-season."""
    data = load_data()
    selection = data[(data["Team"].str.upper() == team.upper()) & (data["Year"] == year)]
    if selection.empty:
        raise LookupError(f"{team.upper()} {year} is not in the bundled dataset.")
    row = selection.iloc[0]
    oobp = None if pd.isna(row["OOBP"]) else float(row["OOBP"])
    oslg = None if pd.isna(row["OSLG"]) else float(row["OSLG"])
    result = predict_from_inputs(float(row["OBP"]), float(row["SLG"]), oobp, oslg)
    result["team"] = str(row["Team"])
    result["year"] = int(row["Year"])
    result["actual"] = {
        "rs": int(row["RS"]),
        "ra": int(row["RA"]),
        "wins": int(row["W"]),
        "playoffs": int(row["Playoffs"]),
    }
    return result


def static_json(name: str) -> dict[str, Any]:
    path = STATIC_DATA / name
    if not path.exists():
        build_artifacts()
    return json.loads(path.read_text(encoding="utf-8"))