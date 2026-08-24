"""FastAPI application for the MONEYLINE Moneyball Trading Desk."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from backend.feeds import (
    EASTERN,
    FeedUnavailable,
    GameNotFound,
    _team_inputs,
    close_client,
    current_season,
    get_final_score,
    get_injury_flags,
    get_prior_season_wins,
    get_slate,
    get_team_directory,
    get_team_live,
)
from backend.inference import (
    load_data,
    load_models,
    predict_from_inputs,
    predict_team,
    static_json,
)
from backend.odds import (
    decimal_odds,
    edge_probability,
    half_kelly_fraction,
    log5_probability,
    market_vig,
    moneyline_to_probability,
    parlay_ev,
    parlay_probability,
    parlay_vig_comparison,
    probability_to_moneyline,
    pythagorean_strength,
)
from backend.players import build_player_card, compare_players, search_players
from backend.record_store import (
    database_available,
    ensure_schema,
    get_record,
    grade_parlay,
    grade_pick,
    pending_parlays,
    pending_picks,
    store_parlay_slip,
    store_slate_snapshot,
    void_parlay,
    void_pick,
)
from backend.season_sim import get_season_sim, get_team_outlook
from backend.seo import (
    SITEMAP_PATH,
    is_public_client_route,
    not_found_html,
    render_index,
    sitemap_xml,
)
from backend.wire import get_team_pulse, get_wire


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("moneyline")
DIST_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "moneyline" / "dist" / "public"
IMMUTABLE_PREFIX = "assets/"
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

class ParlayLeg(BaseModel):
    gamePk: str
    side: Literal["home", "away"]


class ParlayInput(BaseModel):
    legs: list[ParlayLeg] = Field(min_length=2, max_length=6)
    book_odds: int | None = None

    @model_validator(mode="after")
    def validate_book_odds(self) -> "ParlayInput":
        if self.book_odds is not None and abs(self.book_odds) < 100:
            raise ValueError("American moneylines must be ≤ −100 or ≥ +100.")
        return self


INDEPENDENCE_NOTE = (
    "Combined probability multiplies the legs under an independence "
    "assumption. Legs from the same game are refused: they are correlated "
    "and the math would be dishonest."
)


class MatchupInput(BaseModel):
    team_a: TeamStats
    team_b: TeamStats
    book_line_a: int | None = None
    book_line_b: int | None = None
    evaluation_side: Literal["a", "b"] = "a"

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


VOID_AFTER_DAYS = max(int(os.getenv("VOID_AFTER_DAYS", "3")), 1)


async def grade_pending_records() -> dict[str, int]:
    if not await asyncio.to_thread(database_available):
        return {
            "checked": 0,
            "graded": 0,
            "voided": 0,
            "parlays_graded": 0,
            "parlays_voided": 0,
        }
    rows = await asyncio.to_thread(pending_picks)
    semaphore = asyncio.Semaphore(3)

    async def grade_one(row: dict[str, Any]) -> str:
        """Resolve one pending pick; returns 'graded', 'voided', or 'pending'."""
        game_pk = str(row["game_pk"])
        async with semaphore:
            try:
                final = await get_final_score(game_pk)
            except GameNotFound:
                # A vanished game_pk usually means the game was rescheduled
                # under a new pk. Give the feed a few days before voiding, in
                # case the pk reappears.
                cutoff = date.today() - timedelta(days=VOID_AFTER_DAYS)
                if row["game_date"] <= cutoff and await asyncio.to_thread(
                    void_pick, game_pk
                ):
                    logger.info(
                        "record_pick_voided game_pk=%s reason=vanished", game_pk
                    )
                    return "voided"
                return "pending"
            except Exception:
                logger.warning("record_grade_failed game_pk=%s", game_pk)
                return "pending"
            try:
                if final is None:
                    return "pending"
                if final.get("status") == "cancelled":
                    if await asyncio.to_thread(void_pick, game_pk):
                        logger.info(
                            "record_pick_voided game_pk=%s reason=cancelled", game_pk
                        )
                        return "voided"
                    return "pending"
                graded = await asyncio.to_thread(
                    grade_pick,
                    game_pk,
                    int(final["final_away"]),
                    int(final["final_home"]),
                    str(final["away"]),
                    str(final["home"]),
                )
                return "graded" if graded else "pending"
            except Exception:
                logger.warning("record_grade_failed game_pk=%s", game_pk)
                return "pending"

    outcomes: list[str] = []
    if rows:
        outcomes = list(await asyncio.gather(*(grade_one(row) for row in rows)))

    parlay_result = await _grade_pending_parlays()

    return {
        "checked": len(rows),
        "graded": outcomes.count("graded"),
        "voided": outcomes.count("voided"),
        "parlays_graded": parlay_result["graded"],
        "parlays_voided": parlay_result["voided"],
    }


async def _grade_pending_parlays() -> dict[str, int]:
    """Settle pending parlay slips against finals.

    All-or-nothing grading once every leg has a final. A slip is voided —
    terminally, at 0 units — when any leg's game is cancelled or its game_pk
    has vanished from the feed past the same grace period picks get: an
    all-or-nothing slip can never settle honestly once a leg can never
    produce a final. One malformed or unresolvable slip never blocks the
    others.
    """
    graded = 0
    voided = 0
    try:
        slips = await asyncio.to_thread(pending_parlays)
    except Exception:
        logger.warning("parlay_pending_fetch_failed", exc_info=True)
        return {"graded": 0, "voided": 0}
    for slip in slips:
        try:
            leg_winners: dict[str, str] = {}
            void_slip = False
            for leg in slip["legs"]:
                game_pk = str(leg["game_pk"])
                try:
                    final = await get_final_score(game_pk)
                except GameNotFound:
                    cutoff = date.today() - timedelta(days=VOID_AFTER_DAYS)
                    if slip["slip_date"] <= cutoff:
                        void_slip = True
                    continue
                except Exception:
                    logger.warning("parlay_leg_feed_failed game_pk=%s", game_pk)
                    continue
                if final is None:
                    continue
                if final.get("status") == "cancelled":
                    void_slip = True
                    continue
                away_score = final.get("final_away")
                home_score = final.get("final_home")
                if away_score is None or home_score is None:
                    continue
                if int(away_score) == int(home_score):
                    continue  # tie — leg unresolved, slip stays pending
                leg_winners[game_pk] = (
                    str(final["away"])
                    if int(away_score) > int(home_score)
                    else str(final["home"])
                )
            if void_slip:
                if await asyncio.to_thread(void_parlay, int(slip["id"])):
                    logger.info("parlay_voided slip_id=%s", slip["id"])
                    voided += 1
            elif len(leg_winners) == len(slip["legs"]):
                graded += int(
                    await asyncio.to_thread(grade_parlay, int(slip["id"]), leg_winners)
                )
        except Exception:
            logger.warning("parlay_grade_failed slip_id=%s", slip.get("id"))
    return {"graded": graded, "voided": voided}


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
                "record_autograde checked=%s graded=%s voided=%s next_run_s=%s",
                result["checked"],
                result["graded"],
                result["voided"],
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
    try:
        app.state.schema_ready = await asyncio.to_thread(ensure_schema)
    except Exception:
        logger.warning("schema_migration_skipped — database unavailable at boot")
        app.state.schema_ready = False
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
    model_prob_b = 1 - model_prob_a
    evaluates_b = payload.evaluation_side == "b"
    evaluated_probability = model_prob_b if evaluates_b else model_prob_a
    evaluated_line = payload.book_line_b if evaluates_b else payload.book_line_a

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
        edge_probability(evaluated_probability, evaluated_line)
        if evaluated_line is not None
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
        half_kelly_fraction(evaluated_probability, evaluated_line)
        if evaluated_line is not None
        else 0
    )
    return {
        "model_prob_a": round(model_prob_a, 4),
        "model_prob_b": round(model_prob_b, 4),
        "implied_prob_a": round(implied_a, 4) if implied_a is not None else None,
        "implied_prob_b": round(implied_b, 4) if implied_b is not None else None,
        "edge_pp": round(edge * 100, 1) if edge is not None else None,
        "vig_pp": round(vig * 100, 1) if vig is not None else None,
        "break_even_rate": round(
            implied_b if evaluates_b else implied_a, 4
        ) if evaluated_line is not None else None,
        "verdict": verdict,
        "kelly_fraction": round(half_kelly, 4),
        "evaluation_side": payload.evaluation_side,
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
        # The ledger is append-only and one row per date, so only *today's* live slate
        # may enter it. Without this guard, ?date= lets any backfilled slate seed the
        # graded record. Grading is deliberately NOT gated on the date: it only settles
        # already-pending picks that have a final score.
        today_et = datetime.now(EASTERN).date().isoformat()
        if data.get("date") == today_et:
            try:
                persisted = await asyncio.to_thread(store_slate_snapshot, data)
            except Exception:
                logger.warning("record_snapshot_store_failed date=%s", data.get("date"))
        else:
            logger.info(
                "record_snapshot_skipped_not_today date=%s today=%s",
                data.get("date"),
                today_et,
            )
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


async def _screener_live(season: int) -> dict[str, Any]:
    """Live season (SO FAR): live inputs through the full chain, priced
    against last season's final wins as the naive preseason prior."""
    directory = await get_team_directory()
    prior = await get_prior_season_wins()
    semaphore = asyncio.Semaphore(5)
    inputs_by_team: dict[int, dict[str, float]] = {}

    async def one(team_id: int) -> None:
        async with semaphore:
            inputs, _cached = await _team_inputs(team_id, season)
            inputs_by_team[team_id] = inputs

    await asyncio.gather(*(one(team_id) for team_id in directory))

    rows: list[dict[str, Any]] = []
    for team_id, team in directory.items():
        inputs = inputs_by_team[team_id]
        predicted = predict_from_inputs(**inputs)["predicted"]
        prior_wins = prior["wins"].get(team_id)
        predicted_wins = float(predicted["wins"])
        mispricing = (
            predicted_wins - prior_wins if prior_wins is not None else None
        )
        badge = None
        if mispricing is not None and abs(mispricing) >= 5:
            badge = "MISPRICED ▲" if mispricing > 0 else "MISPRICED ▼"
        rows.append(
            {
                "year": season,
                "team": team["code"],
                "obp": round(inputs["obp"], 3),
                "slg": round(inputs["slg"], 3),
                "oobp": round(inputs["oobp"], 3),
                "oslg": round(inputs["oslg"], 3),
                "predicted_wins": round(predicted_wins, 1),
                "actual_wins": team["wins"],
                "prior_wins": prior_wins,
                "mispricing": round(mispricing, 1) if mispricing is not None else None,
                "offense_only": False,
                "badge": badge,
                "games_played": team["games_played"],
            }
        )
    rows.sort(
        key=lambda row: row["mispricing"] if row["mispricing"] is not None else -999,
        reverse=True,
    )
    max_gp = max(team["games_played"] for team in directory.values())
    return {
        "year": season,
        "offense_only": False,
        "rows": rows,
        "payroll_available": False,
        "season_so_far": True,
        "sample_label": f"THRU {max_gp} GP",
        "method": (
            f"SEASON SO FAR — live {season} rates through the full chain "
            f"(a 162-game projection), priced against {prior['season']} final "
            "wins as the naive preseason prior. Partial season; actual wins "
            "are season-to-date."
        ),
    }


@app.get("/api/screener")
async def screener(year: int = Query(2002, ge=1962)) -> dict[str, Any]:
    if year == current_season():
        try:
            return await _screener_live(year)
        except Exception:
            logger.exception("screener_live_failed")
            raise MoneylineError(
                "pool_unavailable",
                f"Live {year} team inputs are temporarily unavailable.",
                503,
            ) from None
    if year > 2012:
        raise MoneylineError(
            "bad_year",
            f"NOT IN DATASET — 1962–2012 SEASONS, OR {current_season()} (SEASON SO FAR)",
            400,
        )
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
        "voided": 0,
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

@app.get("/api/players")
async def players(
    group: Literal["hitting", "pitching"] = Query("hitting"),
    pool: Literal["qualified", "all"] = Query("qualified"),
    q: str | None = Query(default=None, max_length=60),
) -> dict[str, Any]:
    try:
        results = await search_players(group, pool, q)
    except Exception:
        raise MoneylineError(
            "pool_unavailable",
            f"The {current_season()} player pool is temporarily unavailable.",
            503,
        ) from None
    return {
        "group": group,
        "pool": pool,
        "query": q,
        "players": results,
        "floor_note": "The all pool is floored at ≥100 PA or ≥30 IP.",
    }
def _price_parlay_payload(
    legs: list[dict[str, Any]], book_odds: int | None
) -> dict[str, Any]:
    probabilities = [leg["probability"] for leg in legs]
    combined = parlay_probability(probabilities)
    fair_line = probability_to_moneyline(combined)
    result: dict[str, Any] = {
        "legs": legs,
        "combined_prob": round(combined, 4),
        "fair_odds": fair_line,
        "independence_note": INDEPENDENCE_NOTE,
        "price_basis": "SEASON model probabilities (not ADJ).",
        "vig_comparison": parlay_vig_comparison(probabilities, book_odds),
    }
    if book_odds is not None:
        implied = moneyline_to_probability(book_odds)
        payout = decimal_odds(book_odds)
        ev = parlay_ev(combined, payout)
        kelly = half_kelly_fraction(combined, book_odds) if ev > 0 else 0.0
        result["book"] = {
            "book_odds": book_odds,
            "implied_prob": round(implied, 4),
            "edge_pp": round((combined - implied) * 100, 1),
            "ev_per_unit": round(ev, 4),
            "half_kelly": round(kelly, 4),
            "stake_label": f"{kelly:.4f}" if ev > 0 else "0.00 — NO EDGE",
        }
    else:
        result["book"] = None
    return result

@app.get("/api/compare/players")
async def compare_players_route(
    a: int = Query(...), b: int = Query(...)
) -> dict[str, Any]:
    if a == b:
        raise MoneylineError(
            "invalid_comparison", "Pick two different players to compare.", 400
        )
    try:
        comparison = await compare_players(a, b)
    except Exception:
        raise MoneylineError(
            "pool_unavailable",
            f"The {current_season()} player pool is temporarily unavailable.",
            503,
        ) from None
    if comparison is None:
        raise MoneylineError(
            "player_not_found",
            f"NOT IN THE {current_season()} POOL — the desk assesses players with ≥100 PA or ≥30 IP.",
            404,
        )
    return comparison

@app.get("/api/wire")
async def wire(
    team: str | None = Query(default=None, max_length=3),
    types: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=100, ge=1, le=250),
) -> dict[str, Any]:
    try:
        record = await asyncio.to_thread(get_record)
    except Exception:
        record = None
    type_list = [t.strip() for t in types.split(",")] if types else None
    return await get_wire(record, team=team, types=type_list, limit=limit)

@app.post("/api/parlay/log")
async def parlay_log(payload: ParlayInput) -> dict[str, Any]:
    if not await asyncio.to_thread(database_available):
        raise MoneylineError(
            "record_unavailable",
            "The persistent record store is not available.",
            503,
        )
    legs = await _resolve_parlay_legs(payload)
    priced = _price_parlay_payload(legs, payload.book_odds)
    slip_date = legs[0]["game_date"]
    stored = await asyncio.to_thread(
        store_parlay_slip,
        slip_date,
        legs,
        priced["combined_prob"],
        priced["fair_odds"],
        payload.book_odds,
    )
    return {
        **stored,
        "slip_date": slip_date,
        "priced": priced,
        "note": (
            "Paper slip only — graded all-or-nothing when finals arrive. "
            "One slip per day; reopening never duplicates it."
        ),
    }

@app.get("/api/team-live/{team_id}")
async def team_live(team_id: int) -> dict[str, Any]:
    try:
        team = await get_team_live(team_id)
    except FeedUnavailable as error:
        raise MoneylineError("team_not_found", str(error), 404) from None
    try:
        record = await asyncio.to_thread(get_record)
    except Exception:
        record = None
    flags: list[dict[str, Any]] = []
    pulse: dict[str, Any] | None = None
    try:
        flags = (await get_injury_flags()).get(team_id, [])
    except Exception:
        logger.warning("injury_flags_unavailable team_id=%s", team_id)
    try:
        pulse = await get_team_pulse(team_id, record)
    except Exception:
        logger.warning("pulse_unavailable team_id=%s", team_id)
    return {
        **team,
        "flags": flags,
        "pulse": pulse,
        "hard_rule": "Flags and pulse are disclosed context; they never move a price.",
    }

@app.post("/api/parlay/price")
async def parlay_price(payload: ParlayInput) -> dict[str, Any]:
    legs = await _resolve_parlay_legs(payload)
    return _price_parlay_payload(legs, payload.book_odds)

@app.get("/api/player/{player_id}")
async def player_card(player_id: int) -> dict[str, Any]:
    try:
        card = await build_player_card(player_id)
    except MoneylineError:
        raise
    except Exception:
        raise MoneylineError(
            "pool_unavailable",
            f"The {current_season()} player pool is temporarily unavailable.",
            503,
        ) from None
    if card is None:
        raise MoneylineError(
            "player_not_found",
            f"NOT IN THE {current_season()} POOL — the desk assesses players with ≥100 PA or ≥30 IP.",
            404,
        )
    return card

async def _resolve_parlay_legs(payload: ParlayInput) -> list[dict[str, Any]]:
    game_pks = [leg.gamePk for leg in payload.legs]
    if len(set(game_pks)) != len(game_pks):
        raise MoneylineError(
            "correlated_legs",
            "SAME-GAME LEGS REFUSED — correlated outcomes; the independence "
            "math would be dishonest.",
            400,
        )
    slate = await get_slate()
    if slate.get("mode") != "live":
        raise MoneylineError(
            "slate_unavailable",
            "Parlays price only against today's live slate.",
            503,
        )
    rows = {game["game_pk"]: game for game in slate.get("games", [])}
    legs: list[dict[str, Any]] = []
    for leg in payload.legs:
        row = rows.get(leg.gamePk)
        if row is None or row.get("pricing_error"):
            raise MoneylineError(
                "leg_not_found",
                f"Game {leg.gamePk} is not on today's priced slate.",
                404,
            )
        probability = (
            float(row["model_prob_home"])
            if leg.side == "home"
            else 1 - float(row["model_prob_home"])
        )
        legs.append(
            {
                "game_pk": leg.gamePk,
                "side": leg.side,
                "team": row["home"] if leg.side == "home" else row["away"],
                "opponent": row["away"] if leg.side == "home" else row["home"],
                "probability": round(probability, 4),
                "fair_line": probability_to_moneyline(probability),
                "game_date": row["game_date"],
            }
        )
    return legs

@app.get("/api/season-sim")
async def season_sim() -> dict[str, Any]:
    try:
        return await get_season_sim()
    except Exception:
        logger.exception("season_sim_failed")
        raise MoneylineError(
            "sim_unavailable",
            "Season simulation inputs are temporarily unavailable.",
            503,
        ) from None


@app.get("/api/season-sim/team/{team_id}")
async def season_sim_team(team_id: int) -> dict[str, Any]:
    try:
        return await get_team_outlook(team_id)
    except LookupError:
        raise MoneylineError(
            "team_not_found", "Unknown MLB team id.", 404
        ) from None
    except Exception:
        logger.exception("team_outlook_failed team_id=%s", team_id)
        raise MoneylineError(
            "sim_unavailable",
            "Remaining-schedule inputs are temporarily unavailable.",
            503,
        ) from None


@app.get("/api/teams-live")
async def teams_live() -> dict[str, Any]:
    """Directory of all 30 current-season teams for omnisearch and the
    live Team Pricer — codes map through TEAM_CODES, ids are MLB ids."""
    try:
        directory = await get_team_directory()
    except Exception:
        raise MoneylineError(
            "feed_unavailable",
            f"The {current_season()} team directory is temporarily unavailable.",
            503,
        ) from None
    season = current_season()
    return {
        "season": season,
        "teams": [
            {
                "team_id": team["team_id"],
                "team": team["code"],
                "name": team["name"],
                "label": f"{team['code']} {season}",
                "wins": team["wins"],
                "losses": team["losses"],
                "games_played": team["games_played"],
            }
            for team in sorted(directory.values(), key=lambda t: t["code"])
        ],
    }


if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


@app.get(SITEMAP_PATH, include_in_schema=False)
async def sitemap():
    return Response(
        sitemap_xml(),
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str):
    if path == "api" or path.startswith("api/"):
        raise MoneylineError("not_found", "API route not found.", 404)
    normalized_path = path.lstrip("/")
    candidate = (DIST_DIR / normalized_path).resolve()
    try:
        inside = candidate.is_relative_to(DIST_DIR)
    except ValueError:
        inside = False
    if inside and candidate.is_file():
        headers = (
            {"Cache-Control": "public, max-age=31536000, immutable"}
            if normalized_path.startswith(IMMUTABLE_PREFIX)
            else {"Cache-Control": "no-cache"}
        )
        return FileResponse(candidate, headers=headers)
    last_segment = normalized_path.rsplit("/", 1)[-1]
    if normalized_path.startswith(IMMUTABLE_PREFIX) or "." in last_segment:
        return HTMLResponse(not_found_html(), status_code=404)
    if not is_public_client_route(normalized_path):
        return HTMLResponse(not_found_html(), status_code=404)
    index_path = DIST_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(
            render_index(index_path.read_text(encoding="utf-8"), normalized_path),
            headers={"Cache-Control": "no-cache"},
        )
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
