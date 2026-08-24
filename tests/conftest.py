"""Shared fixtures: run grading tests against an isolated Postgres schema.

The real ledger lives in the ``public`` schema. These fixtures create a
throwaway, per-process schema with identical DDL and point
``backend.record_store`` at it via ``search_path``, so tests exercise the real
SQL paths (locking, conflict handling, grading updates) without ever touching
production rows -- and without colliding with a concurrent run of the same
suite.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Callable

import psycopg
import pytest
from psycopg.rows import dict_row

import backend.record_store as record_store

# Per-process, not a fixed name. The fixture below DROPs this schema CASCADE
# at both setup and teardown, so two pytest runs sharing one DATABASE_URL used
# to demolish each other's tables mid-test: ~22 failures per run, and clean on
# the very next sequential run. That reads as flaky application code and sent
# one investigation down the wrong path already. It matters here because this
# project routinely runs several Claude sessions and subagents at once, each
# running the suite.
#
# The pid suffix makes concurrent runs independent. The DROP-on-setup is kept
# so a process that died without teardown still starts clean, and pid reuse
# cannot collide with a live run.
TEST_SCHEMA = f"moneyline_grading_tests_{os.getpid()}"

DDL = """
CREATE TABLE moneyline_slate_snapshots (
  id SERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL,
  mode TEXT NOT NULL,
  model_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX moneyline_snapshot_date_idx
  ON moneyline_slate_snapshots (snapshot_date);

CREATE TABLE moneyline_record_picks (
  id SERIAL PRIMARY KEY,
  snapshot_id INTEGER NOT NULL
    REFERENCES moneyline_slate_snapshots(id) ON DELETE RESTRICT,
  game_pk TEXT NOT NULL,
  game_date DATE NOT NULL,
  away_team TEXT NOT NULL,
  home_team TEXT NOT NULL,
  pick_team TEXT NOT NULL,
  model_probability DOUBLE PRECISION NOT NULL,
  fair_line INTEGER NOT NULL,
  entered_line INTEGER,
  final_away INTEGER,
  final_home INTEGER,
  result TEXT,
  units_pnl DOUBLE PRECISION,
  graded_at TIMESTAMPTZ,
  -- v2 dual-price (ADJ) columns, matching ensure_schema()
  probables JSONB,
  adj_probability DOUBLE PRECISION,
  adj_pick_team TEXT,
  adj_fair_line INTEGER,
  adj_result TEXT,
  adj_units_pnl DOUBLE PRECISION,
  model_version TEXT
);
CREATE UNIQUE INDEX moneyline_record_game_idx
  ON moneyline_record_picks (game_pk);
CREATE INDEX moneyline_record_grade_idx
  ON moneyline_record_picks (game_date, result);

CREATE TABLE moneyline_parlay_slips (
  id SERIAL PRIMARY KEY,
  slip_date DATE NOT NULL UNIQUE,
  legs JSONB NOT NULL,
  combined_probability DOUBLE PRECISION NOT NULL,
  fair_line INTEGER NOT NULL,
  book_line INTEGER,
  result TEXT,
  units_pnl DOUBLE PRECISION,
  graded_at TIMESTAMPTZ,
  model_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL is not configured; schema-backed tests need Postgres.")
    return dsn


@pytest.fixture()
def record_schema(monkeypatch: pytest.MonkeyPatch):
    """Create the isolated schema and redirect record_store connections at it."""
    dsn = _dsn()

    def test_connection() -> psycopg.Connection[Any]:
        return psycopg.connect(
            dsn,
            row_factory=dict_row,
            options=f"-c search_path={TEST_SCHEMA}",
        )

    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
        admin.execute(f"CREATE SCHEMA {TEST_SCHEMA}")
        admin.execute(f"SET search_path TO {TEST_SCHEMA}")
        admin.execute(DDL)

    monkeypatch.setattr(record_store, "_connection", test_connection)
    try:
        yield test_connection
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")


@pytest.fixture()
def seed_pick(record_schema) -> Callable[..., None]:
    """Insert a snapshot (idempotently) and one pending pick into the test schema."""

    def _seed(
        game_pk: str,
        game_date: date,
        away_team: str,
        home_team: str,
        pick_team: str,
        entered_line: int | None = None,
    ) -> None:
        with record_schema() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO moneyline_slate_snapshots (snapshot_date, mode)
                    VALUES (%s, 'live')
                    ON CONFLICT (snapshot_date) DO NOTHING
                    """,
                    (game_date,),
                )
                cursor.execute(
                    "SELECT id FROM moneyline_slate_snapshots WHERE snapshot_date = %s",
                    (game_date,),
                )
                snapshot_id = cursor.fetchone()["id"]
                cursor.execute(
                    """
                    INSERT INTO moneyline_record_picks (
                      snapshot_id, game_pk, game_date, away_team, home_team,
                      pick_team, model_probability, fair_line, entered_line
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 0.55, -122, %s)
                    """,
                    (snapshot_id, game_pk, game_date, away_team, home_team, pick_team, entered_line),
                )
            connection.commit()

    return _seed


@pytest.fixture()
def fetch_pick(record_schema) -> Callable[[str], dict[str, Any] | None]:
    """Read one pick row back from the test schema by game_pk."""

    def _fetch(game_pk: str) -> dict[str, Any] | None:
        with record_schema() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM moneyline_record_picks WHERE game_pk = %s",
                    (game_pk,),
                )
                return cursor.fetchone()

    return _fetch
