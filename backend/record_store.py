"""Persistent, append-only Live Record storage in Replit PostgreSQL."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row


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
                cursor.execute(
                    """
                    INSERT INTO moneyline_record_picks (
                      snapshot_id, game_pk, game_date, away_team, home_team,
                      pick_team, model_probability, fair_line
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
                SELECT pick_team, entered_line
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
            cursor.execute(
                """
                UPDATE moneyline_record_picks
                SET final_away = %s, final_home = %s, result = %s,
                    units_pnl = %s, graded_at = NOW()
                WHERE game_pk = %s AND result IS NULL
                """,
                (
                    final_away,
                    final_home,
                    "WIN" if won else "LOSS",
                    units_pnl,
                    game_pk,
                ),
            )
        connection.commit()
    return True


def get_record() -> dict[str, Any]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.game_pk, p.game_date, p.away_team, p.home_team,
                       p.pick_team, p.model_probability, p.fair_line,
                       p.entered_line, p.final_away, p.final_home, p.result,
                       p.units_pnl, s.created_at
                FROM moneyline_record_picks p
                JOIN moneyline_slate_snapshots s ON s.id = p.snapshot_id
                ORDER BY p.game_date, p.id
                """
            )
            rows = list(cursor.fetchall())

    wins = sum(row["result"] == "WIN" for row in rows)
    losses = sum(row["result"] == "LOSS" for row in rows)
    graded = wins + losses
    cumulative = 0.0
    graded_so_far = 0
    wins_so_far = 0
    curve: list[dict[str, Any]] = []
    serialized: list[dict[str, Any]] = []
    for row in rows:
        if row["units_pnl"] is not None:
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
            }
        )
    tracking_since = rows[0]["game_date"].isoformat() if rows else None
    return {
        "picks": len(rows),
        "graded": graded,
        "wins": wins,
        "losses": losses,
        "hit_rate": round(wins / graded, 4) if graded else None,
        "units_pnl": round(cumulative, 3),
        "break_even_rate": round(110 / 210, 4),
        "tracking_since": tracking_since,
        "sample_label": "SMALL SAMPLE" if graded < 100 else "ESTABLISHED SAMPLE",
        "curve": curve,
        "entries": serialized,
    }