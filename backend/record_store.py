"""Persistent, append-only Live Record storage in Replit PostgreSQL."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def _connection() -> psycopg.Connection[Any]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return psycopg.connect(database_url, row_factory=dict_row)


def database_available() -> bool:
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() is not None
    except Exception:
        return False

def ensure_schema() -> bool:
    """Idempotent v2 boot migration: existing record rows are untouched.

    Adds dual-price (ADJ) grading columns + probables to the picks table and
    creates the parlay-slips table. Safe to run on every boot.
    """
    statements = [
        """
        ALTER TABLE moneyline_record_picks
          ADD COLUMN IF NOT EXISTS probables jsonb,
          ADD COLUMN IF NOT EXISTS adj_probability double precision,
          ADD COLUMN IF NOT EXISTS adj_pick_team text,
          ADD COLUMN IF NOT EXISTS adj_fair_line integer,
          ADD COLUMN IF NOT EXISTS adj_result text,
          ADD COLUMN IF NOT EXISTS adj_units_pnl double precision
        """,
        """
        CREATE TABLE IF NOT EXISTS moneyline_parlay_slips (
          id serial PRIMARY KEY,
          slip_date date NOT NULL UNIQUE,
          legs jsonb NOT NULL,
          combined_probability double precision NOT NULL,
          fair_line integer NOT NULL,
          book_line integer,
          result text,
          units_pnl double precision,
          graded_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ]
    with _connection() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
    return True
def store_slate_snapshot(slate: dict[str, Any]) -> bool:
    """Store one immutable snapshot per live date; reopening never duplicates it."""
    if slate.get("mode") != "live":
        return False
    games = [game for game in slate.get("games", []) if not game.get("pricing_error")]
    if not games:
        return False

    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO moneyline_slate_snapshots (snapshot_date, mode)
                VALUES (%s, %s)
                ON CONFLICT (snapshot_date) DO NOTHING
                RETURNING id
                """,
                (slate["date"], slate["mode"]),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                cursor.execute(
                    "SELECT id FROM moneyline_slate_snapshots WHERE snapshot_date = %s",
                    (slate["date"],),
                )
                existing = cursor.fetchone()
                if existing is None:
                    return False
                snapshot_id = int(existing["id"])
            else:
                snapshot_id = int(inserted["id"])

            for game in games:
                pick_home = float(game["model_prob_home"]) >= 0.5
                pick_team = game["home"] if pick_home else game["away"]
                probability = (
                    float(game["model_prob_home"])
                    if pick_home
                    else 1 - float(game["model_prob_home"])
                )
                fair_line = (
                    int(game["fair_lines"]["home"])
                    if pick_home
                    else int(game["fair_lines"]["away"])
                )
                adj_prob_home = game.get("adj_prob")
                adj_pick_team = None
                adj_probability = None
                adj_fair_line = None
                if adj_prob_home is not None:
                    adj_pick_home = float(adj_prob_home) >= 0.5
                    adj_pick_team = game["home"] if adj_pick_home else game["away"]
                    adj_probability = (
                        float(adj_prob_home)
                        if adj_pick_home
                        else 1 - float(adj_prob_home)
                    )
                    adj_lines = game.get("adj_fair_lines") or {}
                    adj_fair_line = adj_lines.get("home" if adj_pick_home else "away")
                cursor.execute(
                    """
                    INSERT INTO moneyline_record_picks (
                      snapshot_id, game_pk, game_date, away_team, home_team,
                      pick_team, model_probability, fair_line,
                      probables, adj_probability, adj_pick_team, adj_fair_line
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (game_pk) DO NOTHING
                    """,
                    (
                        snapshot_id,
                        game["game_pk"],
                        game["game_date"],
                        game["away"],
                        game["home"],
                        pick_team,
                        probability,
                        fair_line,
                        Jsonb(game.get("probables"))
                        if game.get("probables") is not None
                        else None,
                        adj_probability,
                        adj_pick_team,
                        adj_fair_line,
                    ),
                )
        connection.commit()
    return True


def pending_picks() -> list[dict[str, Any]]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT game_pk, game_date, away_team, home_team, pick_team
                FROM moneyline_record_picks
                WHERE result IS NULL AND game_date <= CURRENT_DATE
                ORDER BY game_date, id
                """
            )
            return list(cursor.fetchall())


def grade_pick(
    game_pk: str,
    final_away: int,
    final_home: int,
    final_away_team: str,
    final_home_team: str,
) -> bool:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pick_team, entered_line, adj_pick_team
                FROM moneyline_record_picks
                WHERE game_pk = %s AND result IS NULL
                FOR UPDATE
                """,
                (game_pk,),
            )
            row = cursor.fetchone()
            if row is None or final_away == final_home:
                return False
            winner = final_away_team if final_away > final_home else final_home_team
            won = row["pick_team"] == winner
            line = int(row["entered_line"]) if row["entered_line"] is not None else -110
            payout = 100 / abs(line) if line < 0 else line / 100
            units_pnl = payout if won else -1.0
            adj_result = None
            adj_units_pnl = None
            if row["adj_pick_team"] is not None:
                adj_won = row["adj_pick_team"] == winner
                adj_result = "WIN" if adj_won else "LOSS"
                adj_units_pnl = payout if adj_won else -1.0
            cursor.execute(
                """
                UPDATE moneyline_record_picks
                SET final_away = %s, final_home = %s, result = %s,
                    units_pnl = %s, adj_result = %s, adj_units_pnl = %s,
                    graded_at = NOW()
                WHERE game_pk = %s AND result IS NULL
                """,
                (
                    final_away,
                    final_home,
                    "WIN" if won else "LOSS",
                    units_pnl,
                    adj_result,
                    adj_units_pnl,
                    game_pk,
                ),
            )
        connection.commit()
    return True


def void_pick(game_pk: str) -> bool:
    """Terminally resolve a pick whose game will never produce a final score.

    Sets a VOID result at 0 units so the pick leaves the pending queue but is
    never counted as a win or a loss. Already-graded picks are left untouched.
    """
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE moneyline_record_picks
                SET result = 'VOID', units_pnl = 0, graded_at = NOW()
                WHERE game_pk = %s AND result IS NULL
                """,
                (game_pk,),
            )
            voided = cursor.rowcount > 0
        connection.commit()
    return voided


def get_record() -> dict[str, Any]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.game_pk, p.game_date, p.away_team, p.home_team,
                       p.pick_team, p.model_probability, p.fair_line,
                       p.entered_line, p.final_away, p.final_home, p.result,
                       p.units_pnl, p.probables, p.adj_probability,
                       p.adj_pick_team, p.adj_fair_line, p.adj_result,
                       p.adj_units_pnl, s.created_at
                FROM moneyline_record_picks p
                JOIN moneyline_slate_snapshots s ON s.id = p.snapshot_id
                ORDER BY p.game_date, p.id
                """
            )
            rows = list(cursor.fetchall())

    wins = sum(row["result"] == "WIN" for row in rows)
    losses = sum(row["result"] == "LOSS" for row in rows)
    voided = sum(row["result"] == "VOID" for row in rows)
    graded = wins + losses
    cumulative = 0.0
    graded_so_far = 0
    wins_so_far = 0
    curve: list[dict[str, Any]] = []
    serialized: list[dict[str, Any]] = []
    for row in rows:
        # Voided picks are terminal but carry 0 units and must never dilute
        # the hit rate, so the curve only advances on decided picks.
        if row["result"] in ("WIN", "LOSS"):
            graded_so_far += 1
            wins_so_far += row["result"] == "WIN"
            cumulative += float(row["units_pnl"])
            curve.append(
                {
                    "date": row["game_date"].isoformat(),
                    "units": round(cumulative, 3),
                    "hit_rate": round(wins_so_far / graded_so_far, 4),
                }
            )
        serialized.append(
            {
                **row,
                "game_date": row["game_date"].isoformat(),
                "created_at": row["created_at"].isoformat(),
                "model_probability": round(float(row["model_probability"]), 4),
                "units_pnl": (
                    round(float(row["units_pnl"]), 3)
                    if row["units_pnl"] is not None
                    else None
                ),
                "adj_probability": (
                    round(float(row["adj_probability"]), 4)
                    if row["adj_probability"] is not None
                    else None
                ),
                "adj_units_pnl": (
                    round(float(row["adj_units_pnl"]), 3)
                    if row["adj_units_pnl"] is not None
                    else None
                ),
            }
        )
    tracking_since = rows[0]["game_date"].isoformat() if rows else None

    adj_rows = [row for row in rows if row["adj_result"] in ("WIN", "LOSS")]
    adj_wins = sum(row["adj_result"] == "WIN" for row in adj_rows)
    adj_units = sum(float(row["adj_units_pnl"] or 0.0) for row in adj_rows)
    adj_record = {
        "picks": sum(row["adj_pick_team"] is not None for row in rows),
        "graded": len(adj_rows),
        "wins": adj_wins,
        "losses": len(adj_rows) - adj_wins,
        "hit_rate": round(adj_wins / len(adj_rows), 4) if adj_rows else None,
        "units_pnl": round(adj_units, 3),
        "note": (
            "The ADJ starter-blended price is an experiment the record grades; "
            "the desk never claims it is better — only this scoreboard can."
        ),
    }

    return {
        "picks": len(rows),
        "graded": graded,
        "wins": wins,
        "losses": losses,
        "voided": voided,
        "hit_rate": round(wins / graded, 4) if graded else None,
        "units_pnl": round(cumulative, 3),
        "break_even_rate": round(110 / 210, 4),
        "tracking_since": tracking_since,
        "sample_label": "SMALL SAMPLE" if graded < 100 else "ESTABLISHED SAMPLE",
        "curve": curve,
        "entries": serialized,
        "adj_record": adj_record,
        "parlay_record": parlay_record(),
    }

def store_parlay_slip(
    slip_date: str,
    legs: list[dict[str, Any]],
    combined_probability: float,
    fair_line: int,
    book_line: int | None,
) -> dict[str, Any]:
    """Store today's slip; one paper slip per day, reopening never duplicates."""
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO moneyline_parlay_slips (
                  slip_date, legs, combined_probability, fair_line, book_line
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (slip_date) DO NOTHING
                RETURNING id
                """,
                (slip_date, Jsonb(legs), combined_probability, fair_line, book_line),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                cursor.execute(
                    "SELECT id, legs, created_at FROM moneyline_parlay_slips WHERE slip_date = %s",
                    (slip_date,),
                )
                existing = cursor.fetchone()
                connection.commit()
                return {
                    "stored": False,
                    "already_logged": True,
                    "slip_id": int(existing["id"]) if existing else None,
                }
        connection.commit()
    return {"stored": True, "already_logged": False, "slip_id": int(inserted["id"])}

def grade_parlay(slip_id: int, leg_outcomes: dict[str, str]) -> bool:
    """Grade all-or-nothing: every leg must have a final; one loss sinks it.

    leg_outcomes maps game_pk → winning team code (finals only).
    """
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT legs, book_line, fair_line
                FROM moneyline_parlay_slips
                WHERE id = %s AND result IS NULL
                FOR UPDATE
                """,
                (slip_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return False
            legs = row["legs"]
            outcomes = []
            for leg in legs:
                winner = leg_outcomes.get(str(leg["game_pk"]))
                if winner is None:
                    return False  # a leg is not final yet — stay pending
                outcomes.append(leg["team"] == winner)
            won = all(outcomes)
            line = row["book_line"] if row["book_line"] is not None else row["fair_line"]
            line = int(line)
            payout = 100 / abs(line) if line < 0 else line / 100
            units_pnl = payout if won else -1.0
            cursor.execute(
                """
                UPDATE moneyline_parlay_slips
                SET result = %s, units_pnl = %s, graded_at = NOW()
                WHERE id = %s AND result IS NULL
                """,
                ("WIN" if won else "LOSS", units_pnl, slip_id),
            )
        connection.commit()
    return True

def parlay_record() -> dict[str, Any]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, slip_date, legs, combined_probability, fair_line,
                       book_line, result, units_pnl, created_at
                FROM moneyline_parlay_slips
                ORDER BY slip_date, id
                """
            )
            rows = list(cursor.fetchall())
    wins = sum(row["result"] == "WIN" for row in rows)
    losses = sum(row["result"] == "LOSS" for row in rows)
    units = sum(float(row["units_pnl"] or 0.0) for row in rows)
    return {
        "slips": len(rows),
        "graded": wins + losses,
        "wins": wins,
        "losses": losses,
        "voided": sum(row["result"] == "VOID" for row in rows),
        "units_pnl": round(units, 3),
        "line": f"PARLAYS {wins}–{losses}, {'+' if units >= 0 else ''}{units:.1f}u",
        "entries": [
            {
                **row,
                "slip_date": row["slip_date"].isoformat(),
                "created_at": row["created_at"].isoformat(),
                "combined_probability": round(float(row["combined_probability"]), 4),
                "units_pnl": (
                    round(float(row["units_pnl"]), 3)
                    if row["units_pnl"] is not None
                    else None
                ),
            }
            for row in rows
        ],
    }

def pending_parlays() -> list[dict[str, Any]]:
    """Ungraded slips up to and including today.

    Same-day slips are included so a completed parlay grades as soon as all
    of its finals arrive, not on the following day.
    """
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, slip_date, legs, book_line, fair_line
                FROM moneyline_parlay_slips
                WHERE result IS NULL AND slip_date <= CURRENT_DATE
                ORDER BY slip_date, id
                """
            )
            return list(cursor.fetchall())


def void_parlay(slip_id: int) -> bool:
    """Terminally void a slip whose legs can never all produce finals.

    Mirrors void_pick: a VOID result at 0 units leaves the pending queue but
    never counts as a win or a loss. Already-graded slips are left untouched.
    """
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE moneyline_parlay_slips
                SET result = 'VOID', units_pnl = 0, graded_at = NOW()
                WHERE id = %s AND result IS NULL
                """,
                (slip_id,),
            )
            voided = cursor.rowcount > 0
        connection.commit()
    return voided
