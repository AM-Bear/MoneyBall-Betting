"""Every ledger row records which model priced it — and the write path exists.

`entered_line` is the cautionary tale: a column that was read in three places,
covered by tests, and written by nothing but a test fixture. Every pick has
graded at the −110 default ever since. So these tests do not assert that the
column exists or that the constant is importable; they store through the real
`store_*` functions and read the row back out of Postgres, because the only
question worth asking of a stamp is whether anything actually applies it.

The second claim under test is the bootstrap. `scripts/post-merge.sh` used to
run `drizzle-kit push`, which was the only thing in the repo capable of
creating these tables on an empty database. Removing it (so a stale mirror
could never propose dropping the `adj_*` columns) makes `ensure_schema` the
sole authority, and an authority that cannot stand a schema up is not one.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

import backend.record_store as record_store
from backend.precompute import MODEL_VERSION
from tests.conftest import TEST_SCHEMA

TODAY = date.today()

# Per-process, for the same reason as conftest.TEST_SCHEMA: this test DROPs
# the schema CASCADE, and a concurrent run of the suite against the same
# DATABASE_URL would pull it out from under this one. That failure is
# especially nasty here -- ensure_schema is all IF NOT EXISTS, so a lost
# search_path can silently no-op instead of raising, and the test would then
# pass while proving nothing.
BOOTSTRAP_SCHEMA = f"moneyline_bootstrap_test_{os.getpid()}"


def _live_slate(day: date) -> dict[str, Any]:
    """A minimal live slate in the shape `store_slate_snapshot` consumes."""
    return {
        "date": day.isoformat(),
        "mode": "live",
        "games": [
            {
                "game_pk": "990001",
                "game_date": day.isoformat(),
                "away": "BOS",
                "home": "NYY",
                "model_prob_home": 0.56,
                "fair_lines": {"home": -127, "away": 127},
                "adj_prob": 0.58,
                "adj_fair_lines": {"home": -138, "away": 138},
            }
        ],
    }


def _rows(table: str) -> list[dict[str, Any]]:
    with record_store._connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table} ORDER BY id")
            return list(cursor.fetchall())


def test_slate_snapshot_stamps_the_version_on_snapshot_and_picks(record_schema):
    assert record_store.store_slate_snapshot(_live_slate(TODAY)) is True

    snapshots = _rows("moneyline_slate_snapshots")
    picks = _rows("moneyline_record_picks")
    assert len(snapshots) == 1 and len(picks) == 1
    # Read back from Postgres, not from the payload we passed in.
    assert snapshots[0]["model_version"] == MODEL_VERSION
    assert picks[0]["model_version"] == MODEL_VERSION


def test_parlay_slip_stamps_the_version(record_schema):
    stored = record_store.store_parlay_slip(
        slip_date=TODAY.isoformat(),
        legs=[{"game_pk": "990001", "team": "NYY", "side": "home"}],
        combined_probability=0.33,
        fair_line=260,
        book_line=None,
    )
    assert stored["stored"] is True

    slips = _rows("moneyline_parlay_slips")
    assert len(slips) == 1
    assert slips[0]["model_version"] == MODEL_VERSION


def test_record_reports_versions_present_and_counts_the_unversioned(
    record_schema, seed_pick
):
    """A record spanning a version bump must say so, not average across it.

    `seed_pick` inserts without a version, which is exactly what the rows
    already in production look like. They are counted, never relabelled:
    stamping them "v1" would assert a provenance nobody ever checked.
    """
    seed_pick("880001", TODAY - timedelta(days=1), "BOS", "NYY", "NYY")
    assert record_store.store_slate_snapshot(_live_slate(TODAY)) is True

    record = record_store.get_record()
    assert record["picks"] == 2
    assert record["model_versions_present"] == [MODEL_VERSION]
    assert record["unversioned_picks"] == 1

    entries = {entry["game_pk"]: entry for entry in record["entries"]}
    assert entries["880001"]["model_version"] is None
    assert entries["990001"]["model_version"] == MODEL_VERSION


def test_ensure_schema_is_idempotent_over_an_existing_ledger(record_schema, seed_pick):
    """Booting twice must add nothing and must not touch a row that exists."""
    seed_pick("880001", TODAY, "BOS", "NYY", "NYY")
    before = _rows("moneyline_record_picks")

    assert record_store.ensure_schema() is True
    assert record_store.ensure_schema() is True

    assert _rows("moneyline_record_picks") == before

    with record_store._connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) AS n FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = 'moneyline_record_picks'
                  AND column_name = 'model_version'
                """,
                (TEST_SCHEMA,),
            )
            assert cursor.fetchone()["n"] == 1


def test_ensure_schema_can_stand_up_an_empty_database(monkeypatch):
    """The migration is the sole schema authority, so it must bootstrap.

    Before this, statement one was an ALTER and `moneyline_slate_snapshots`
    was created by no Python at all — the tables only existed because they
    predated the repo and because `drizzle-kit push` happened to run. With the
    push gone, a fresh database has nothing else to fall back on.
    """
    dsn = record_store.os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL is not configured; schema-backed tests need Postgres.")

    def bootstrap_connection() -> psycopg.Connection[Any]:
        return psycopg.connect(
            dsn, row_factory=dict_row, options=f"-c search_path={BOOTSTRAP_SCHEMA}"
        )

    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f"DROP SCHEMA IF EXISTS {BOOTSTRAP_SCHEMA} CASCADE")
        admin.execute(f"CREATE SCHEMA {BOOTSTRAP_SCHEMA}")

    monkeypatch.setattr(record_store, "_connection", bootstrap_connection)
    try:
        assert record_store.ensure_schema() is True

        # Not just "the tables exist" — the ledger has to accept a real write
        # and grade it, on nothing but what the migration built.
        assert record_store.store_slate_snapshot(_live_slate(TODAY)) is True
        assert record_store.grade_pick("990001", 2, 7, "BOS", "NYY") is True

        record = record_store.get_record()
        assert record["picks"] == 1
        assert record["wins"] == 1
        assert record["model_versions_present"] == [MODEL_VERSION]
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f"DROP SCHEMA IF EXISTS {BOOTSTRAP_SCHEMA} CASCADE")
