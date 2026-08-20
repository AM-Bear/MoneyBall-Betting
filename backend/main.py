"""FastAPI application for the MONEYLINE Moneyball Trading Desk."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from backend.feeds import close_client, get_final_score, get_slate
from backend.inference import (
    load_data,
    load_models,
    predict_from_inputs,
    predict_team,
    static_json,
)
from backend.odds import (
    edge_probability,
    half_kelly_fraction,
    log5_probability,
    market_vig,
    moneyline_to_probability,
    probability_to_moneyline,
    pythagorean_strength,
)
from backend.record_store import (
    database_available,
    get_record,
    grade_pick,
    pending_picks,
    store_slate_snapshot,
)


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("moneyline")
DIST_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "moneyline" / "dist" / "public"
EQUITY_CAVEAT = (
    "Game-level lines also price pitchers, injuries, and lineups this "
    "season-aggregate model cannot see."
)


class MoneylineError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class TeamStats(BaseModel):
    team: str | None = None
    year: int | None = None
    obp: float = Field(gt=0, lt=1)
    slg: float = Field(gt=0, lt=1)
    oobp: float = Field(gt=0, lt=1)
    oslg: float = Field(gt=0, lt=1)


class PriceInput(BaseModel):
    obp: float = Field(gt=0, lt=1)
    slg: float = Field(gt=0, lt=1)
    oobp: float | None = Field(default=None, gt=0, lt=1)
    oslg: float | None = Field(default=None, gt=0, lt=1)


class MatchupInput(BaseModel):
    team_a: TeamStats
    team_b: TeamStats
    book_line_a: int | None = None
    book_line_b: int | None = None

    @model_validator(mode="after")
    def validate_lines(self) -> "MatchupInput":
        for line in (self.book_line_a, self.book_line_b):
            if line == 0 or (line is not None and abs(line) < 100):
                raise ValueError("American moneylines must be ≤ −100 or ≥ +100.")
        return self


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


async def grade_pending_records() -> dict[str, int]:
    if not await asyncio.to_thread(database_available):
        return {"checked": 0, "graded": 0}
    rows = await asyncio.to_thread(pending_picks)
    semaphore = asyncio.Semaphore(3)
    graded = 0

    async def grade_one(row: dict[str, Any]) -> bool:
        async with semaphore:
            try:
                final = await get_final_score(str(row["game_pk"]))
                if final is None:
                    return False
                return await asyncio.to_thread(
                    grade_pick,
                    str(row["game_pk"]),
                    int(final["final_away"]),
                    int(final["final_home"]),
                    str(final["away"]),
                    str(final["home"]),
                )
            except Exception:
                logger.warning("record_grade_failed game_pk=%s", row["game_pk"])
                return False

    if rows:
        graded = sum(await asyncio.gather(*(grade_one(row) for row in rows)))
    return {"checked": len(rows), "graded": graded}


GRADE_INTERVAL_SECONDS = max(int(os.getenv("GRADE_INTERVAL_SECONDS", "1800")), 60)


async def snapshot_live_slate() -> bool:
    """Persist today's live slate so the record never depends on a page visit.

    Returns True when a snapshot write ran; ON CONFLICT guards in
    store_slate_snapshot make repeated runs idempotent.
    """
    if not await asyncio.to_thread(database_available):
        return False
    data = await get_slate()
    if data.get("mode") != "live":
        return False
    return await asyncio.to_thread(store_slate_snapshot, data)


async def grade_scheduler() -> None:
    """Snapshot today's slate and grade pending picks on a fixed cadence.

    Failures in either step are logged and retried next cycle.
    """
    while True:
        try:
            persisted = await snapshot_live_slate()
            logger.info(
                "record_autosnapshot persisted=%s next_run_s=%s",
                persisted,
                GRADE_INTERVAL_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "record_autosnapshot_failed retry_in_s=%s",
                GRADE_INTERVAL_SECONDS,
                exc_info=True,
            )
        try:
            result = await grade_pending_records()
            logger.info(
                "record_autograde checked=%s graded=%s next_run_s=%s",
                result["checked"],
                result["graded"],
                GRADE_INTERVAL_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("record_autograde_failed retry_in_s=%s", GRADE_INTERVAL_SECONDS, exc_info=True)
        await asyncio.sleep(GRADE_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    started = time.perf_counter()
    load_models()
    app.state.model_loaded = True
    app.state.startup_ms = round((time.perf_counter() - started) * 1000)
    app.state.grade_task = asyncio.create_task(grade_scheduler())
    yield
    grade_task = getattr(app.state, "grade_task", None)
    if grade_task and not grade_task.done():
        grade_task.cancel()
        try:
            await grade_task
        except asyncio.CancelledError:
            pass
    await close_client()


app = FastAPI(
    title="MONEYLINE API",
    version="1.0.0",
    docs_url="/api/docs" if os.getenv("NODE_ENV") != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("DEV_ORIGIN", "http://localhost:18612"),
        "http://127.0.0.1:18612",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(MoneylineError)
async def moneyline_error_handler(_request: Request, error: MoneylineError):
    return _error_response(error.code, error.message, error.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, _error: RequestValidationError):
    return _error_response(
        "invalid_request",
        "One or more fields are outside the accepted statistical range.",
        400,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, error: Exception):
    logger.exception("unhandled_api_error", exc_info=error)
    return _error_response(
        "internal_error",
        "The desk could not complete this calculation.",
        500,
    )


@app.middleware("http")
async def request_log(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    cache_status = response.headers.get("X-Cache", "n/a")
    team = request.path_params.get("team", "-")
    logger.info(
        "path=%s team=%s ms=%.1f cache=%s status=%s",
        request.url.path,
        team,
        elapsed_ms,
        cache_status,
        response.status_code,
    )
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    return {
        "model_loaded": bool(getattr(request.app.state, "model_loaded", False)),
        "startup_ms": getattr(request.app.state, "startup_ms", None),
        "database_ready": await asyncio.to_thread(database_available),
        "model_version": "chronological-1962-2001-v1",
    }


@app.get("/api/teams")
async def teams() -> dict[str, Any]:
    data = load_data()[["Team", "Year"]].sort_values(["Year", "Team"], ascending=[False, True])
    return {
        "teams": [
            {
                "team": str(row.Team),
                "year": int(row.Year),
                "label": f"{row.Team} {int(row.Year)}",
            }
            for row in data.itertuples(index=False)
        ]
    }


@app.get("/api/team/{team}/{year}")
async def team_price(team: str, year: int) -> dict[str, Any]:
    if year < 1962 or year > 2012:
        raise MoneylineError(
            "bad_year",
            "NOT IN DATASET — 1962–2012 SEASONS ONLY",
            400,
        )
    try:
        prediction = predict_team(team.upper(), year)
        data = load_data()
        prediction["data_ranges"] = {
            field.lower(): {
                "min": round(float(data[field].min()), 3),
                "max": round(float(data[field].max()), 3),
            }
            for field in ("OBP", "SLG", "OOBP", "OSLG")
        }
        return prediction
    except LookupError:
        raise MoneylineError(
            "team_not_found",
            "NOT IN DATASET — CHECK THE TEAM CODE AND SEASON",
            404,
        ) from None


@app.post("/api/price")
async def price_inputs(payload: PriceInput) -> dict[str, Any]:
    prediction = predict_from_inputs(
        payload.obp,
        payload.slg,
        payload.oobp,
        payload.oslg,
    )
    prediction["data_ranges"] = {
        field.lower(): {
            "min": round(float(load_data()[field].min()), 3),
            "max": round(float(load_data()[field].max()), 3),
        }
        for field in ("OBP", "SLG", "OOBP", "OSLG")
    }
    return prediction


@app.post("/api/matchup")
async def matchup(payload: MatchupInput) -> dict[str, Any]:
    team_a = predict_from_inputs(
        payload.team_a.obp,
        payload.team_a.slg,
        payload.team_a.oobp,
        payload.team_a.oslg,
    )
    team_b = predict_from_inputs(
        payload.team_b.obp,
        payload.team_b.slg,
        payload.team_b.oobp,
        payload.team_b.oslg,
    )
    strength_a = pythagorean_strength(
        team_a["predicted"]["rs"], team_a["predicted"]["ra"]
    )
    strength_b = pythagorean_strength(
        team_b["predicted"]["rs"], team_b["predicted"]["ra"]
    )
    model_prob_a = log5_probability(strength_a, strength_b)
    fair_line_a = probability_to_moneyline(model_prob_a)
    fair_line_b = probability_to_moneyline(1 - model_prob_a)

    implied_a = (
        moneyline_to_probability(payload.book_line_a)
        if payload.book_line_a is not None
        else None
    )
    implied_b = (
        moneyline_to_probability(payload.book_line_b)
        if payload.book_line_b is not None
        else None
    )
    edge = (
        edge_probability(model_prob_a, payload.book_line_a)
        if payload.book_line_a is not None
        else None
    )
    vig = (
        market_vig(payload.book_line_a, payload.book_line_b)
        if payload.book_line_a is not None and payload.book_line_b is not None
        else None
    )
    vig_threshold = max((vig or 0.0476) / 2, 0)
    verdict: Literal[
        "VALUE", "INSIDE THE VIG — NO PLAYABLE EDGE", "NO VALUE", "NO LINE"
    ]
    if edge is None:
        verdict = "NO LINE"
    elif edge > vig_threshold:
        verdict = "VALUE"
    elif edge >= 0:
        verdict = "INSIDE THE VIG — NO PLAYABLE EDGE"
    else:
        verdict = "NO VALUE"

    half_kelly = (
        half_kelly_fraction(model_prob_a, payload.book_line_a)
        if payload.book_line_a is not None
        else 0
    )
    return {
        "model_prob_a": round(model_prob_a, 4),
        "model_prob_b": round(1 - model_prob_a, 4),
        "implied_prob_a": round(implied_a, 4) if implied_a is not None else None,
        "implied_prob_b": round(implied_b, 4) if implied_b is not None else None,
        "edge_pp": round(edge * 100, 1) if edge is not None else None,
        "vig_pp": round(vig * 100, 1) if vig is not None else None,
        "break_even_rate": round(implied_a, 4) if implied_a is not None else None,
        "verdict": verdict,
        "kelly_fraction": round(half_kelly, 4),
        "fair_line_a": fair_line_a,
        "fair_line_b": fair_line_b,
        "formula": {
            "pythagorean_a": round(strength_a, 4),
            "pythagorean_b": round(strength_b, 4),
            "method": "Pythagorean expectation combined with log5",
            "kelly": "½ × ((p × decimal odds − 1) / (decimal odds − 1))",
        },
        "team_a_prediction": team_a["predicted"],
        "team_b_prediction": team_b["predicted"],
        "receipts": {"team_a": team_a["receipts"], "team_b": team_b["receipts"]},
        "caveat": EQUITY_CAVEAT,
    }


@app.get("/api/slate")
async def slate(
    request: Request,
    slate_date: date | None = Query(default=None, alias="date"),
) -> dict[str, Any]:
    data = await get_slate(slate_date)
    request.state.cache_status = data.get("cache", "n/a")
    persisted = False
    if data.get("mode") == "live":
        try:
            persisted = await asyncio.to_thread(store_slate_snapshot, data)
        except Exception:
            logger.warning("record_snapshot_store_failed date=%s", data.get("date"))
        request.app.state.slate_grade_task = asyncio.create_task(grade_pending_records())
    data["record_persisted"] = persisted
    return data


def _prior_team(team: str, year: int) -> tuple[str, int]:
    return {
        ("LAA", 2005): ("ANA", 2004),
        ("MIA", 2012): ("FLA", 2011),
        ("TBR", 2008): ("TBD", 2007),
        ("WSN", 2005): ("MON", 2004),
    }.get((team, year), (team, year - 1))


@app.get("/api/screener")
async def screener(year: int = Query(2002, ge=1962, le=2012)) -> dict[str, Any]:
    data = load_data()
    season = data[data["Year"] == year].copy()
    if season.empty:
        raise MoneylineError("bad_year", "No bundled data exists for that season.", 400)
    models = load_models()
    season["predicted_rs"] = models["rs"].predict(season[["OBP", "SLG"]])
    offense_only = bool(season[["OOBP", "OSLG"]].isna().any(axis=None))
    if offense_only:
        season["predicted_ra"] = season["RA"]
    else:
        season["predicted_ra"] = models["ra"].predict(season[["OOBP", "OSLG"]])
    season["predicted_rd"] = season["predicted_rs"] - season["predicted_ra"]
    season["predicted_wins"] = models["wins"].predict(
        season[["predicted_rd"]].rename(columns={"predicted_rd": "RD"})
    )

    rows: list[dict[str, Any]] = []
    for item in season.itertuples(index=False):
        prior_team, prior_year = _prior_team(str(item.Team), int(item.Year))
        prior_row = data[(data["Team"] == prior_team) & (data["Year"] == prior_year)]
        prior_wins = float(prior_row.iloc[0]["W"]) if not prior_row.empty else None
        predicted_wins = float(item.predicted_wins)
        mispricing = predicted_wins - prior_wins if prior_wins is not None else None
        badge = None
        if mispricing is not None and abs(mispricing) >= 5:
            badge = "MISPRICED ▲" if mispricing > 0 else "MISPRICED ▼"
        rows.append(
            {
                "year": int(item.Year),
                "team": str(item.Team),
                "obp": round(float(item.OBP), 3),
                "slg": round(float(item.SLG), 3),
                "oobp": None if pd.isna(item.OOBP) else round(float(item.OOBP), 3),
                "oslg": None if pd.isna(item.OSLG) else round(float(item.OSLG), 3),
                "predicted_wins": round(predicted_wins, 1),
                "actual_wins": int(item.W),
                "prior_wins": int(prior_wins) if prior_wins is not None else None,
                "mispricing": round(mispricing, 1) if mispricing is not None else None,
                "offense_only": offense_only,
                "badge": badge,
            }
        )
    rows.sort(
        key=lambda row: row["mispricing"] if row["mispricing"] is not None else -999,
        reverse=True,
    )
    return {
        "year": year,
        "offense_only": offense_only,
        "rows": rows,
        "payroll_available": False,
        "method": (
            "Offense model with observed RA; OOBP/OSLG are unavailable before 1999."
            if offense_only
            else "Full model chain versus previous-season wins."
        ),
    }


@app.get("/api/track-record")
async def track_record() -> dict[str, Any]:
    return static_json("track_record.json")


@app.get("/api/backtest")
async def backtest() -> dict[str, Any]:
    return static_json("backtest.json")


@app.get("/api/ba-paradox")
async def ba_paradox() -> dict[str, Any]:
    return static_json("ba_paradox.json")


def _empty_record() -> dict[str, Any]:
    return {
        "picks": 0,
        "graded": 0,
        "wins": 0,
        "losses": 0,
        "hit_rate": None,
        "units_pnl": 0,
        "break_even_rate": round(110 / 210, 4),
        "tracking_since": None,
        "sample_label": "SMALL SAMPLE",
        "curve": [],
        "entries": [],
        "database_ready": False,
    }


@app.get("/api/record")
async def live_record() -> dict[str, Any]:
    try:
        record = await asyncio.to_thread(get_record)
        record["database_ready"] = True
        return record
    except Exception:
        logger.warning("record_read_failed")
        return _empty_record()


@app.post("/api/record/grade")
async def grade_record() -> dict[str, Any]:
    if not await asyncio.to_thread(database_available):
        raise MoneylineError(
            "record_unavailable",
            "The persistent record store is not available.",
            503,
        )
    result = await grade_pending_records()
    record = await asyncio.to_thread(get_record)
    record["database_ready"] = True
    result["record"] = record
    return result


if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str):
    if path.startswith("api/"):
        raise MoneylineError("not_found", "API route not found.", 404)
    index_path = DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path, headers={"Cache-Control": "no-cache"})
    raise MoneylineError(
        "frontend_not_built",
        "The frontend build is not available in this runtime.",
        503,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("NODE_ENV") != "production",
    )