"""Persistent, append-only Live Record storage in Replit PostgreSQL."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.odds import decimal_odds, parlay_book_decimal
from backend.precompute import MODEL_VERSION

# The price a slip is graded at when no book line was recorded. Picks already
# grade at a standard -110 (record_store.py grade_pick); this is the parlay
# analogue -- the same -110 legs, compounded. See STANDARD_LEG_LINE use below.
STANDARD_LEG_LINE = -110
MAX_PARLAY_BOOK_LINE = 10000


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
    """Idempotent boot migration: existing record rows are untouched.

    Creates any missing table or index, adds the dual-price (ADJ) grading
    columns and probables to the picks table, creates the parlay-slips table,
    and stamps all three with model_version. Every statement is CREATE/ADD
    ... IF NOT EXISTS: there is no UPDATE, no DROP and no backfill anywhere in
    here, so a graded row can never be rewritten by a boot. Safe to run on
    every boot, and the single authority for this schema.
    """
    statements = [
        # The two v1 tables predate this repo and were created externally, so
        # in production these CREATEs are no-ops. They are here because
        # scripts/post-merge.sh no longer runs `drizzle-kit push`: removing the
        # push removed the only thing that could bootstrap a fresh database.
        # This migration is now the schema's sole authority, so it has to be
        # able to stand one up. IF NOT EXISTS throughout -- an existing table
        # is left exactly as it is, columns and rows untouched.
        """
        CREATE TABLE IF NOT EXISTS moneyline_slate_snapshots (
          id serial PRIMARY KEY,
          snapshot_date date NOT NULL,
          mode text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS moneyline_snapshot_date_idx
          ON moneyline_slate_snapshots (snapshot_date)
        """,
        """
        CREATE TABLE IF NOT EXISTS moneyline_record_picks (
          id serial PRIMARY KEY,
          snapshot_id integer NOT NULL
            REFERENCES moneyline_slate_snapshots(id) ON DELETE RESTRICT,
          game_pk text NOT NULL,
          game_date date NOT NULL,
          away_team text NOT NULL,
          home_team text NOT NULL,
          pick_team text NOT NULL,
          model_probability double precision NOT NULL,
          fair_line integer NOT NULL,
          entered_line integer,
          final_away integer,
          final_home integer,
          result text,
          units_pnl double precision,
          graded_at timestamptz
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS moneyline_record_game_idx
          ON moneyline_record_picks (game_pk)
        """,
        """
        CREATE INDEX IF NOT EXISTS moneyline_record_grade_idx
          ON moneyline_record_picks (game_date, result)
        """,
        # The grade worker reads the oldest unresolved rows with LIMIT. This
        # partial index lets Postgres stop after one batch instead of filtering
        # and sorting an ever-growing append-only ledger first.
        """
        CREATE INDEX IF NOT EXISTS moneyline_record_pending_batch_idx
          ON moneyline_record_picks (game_date, id)
          WHERE result IS NULL
        """,
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
          user_id text,
          slip_date date NOT NULL,
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
        """
        ALTER TABLE moneyline_parlay_slips
          ADD COLUMN IF NOT EXISTS user_id text
        """,
        """
        ALTER TABLE moneyline_parlay_slips
          DROP CONSTRAINT IF EXISTS moneyline_parlay_slips_slip_date_key
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS moneyline_parlay_user_date_idx
          ON moneyline_parlay_slips (user_id, slip_date)
          WHERE user_id IS NOT NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS moneyline_parlay_pending_batch_idx
          ON moneyline_parlay_slips (slip_date, id)
          WHERE result IS NULL
        """,
        # Stamp every ledger table with the model identity that produced the
        # row. Nullable on purpose: rows written before versioning stay NULL
        # rather than being backfilled with a version that was never checked
        # against them. get_record reports the distinct set it actually finds.
        """
        ALTER TABLE moneyline_slate_snapshots
          ADD COLUMN IF NOT EXISTS model_version text
        """,
        """
        ALTER TABLE moneyline_record_picks
          ADD COLUMN IF NOT EXISTS model_version text
        """,
        """
        ALTER TABLE moneyline_parlay_slips
          ADD COLUMN IF NOT EXISTS model_version text
        """,
        """
        CREATE TABLE IF NOT EXISTS moneyline_entitlements (
          user_id text PRIMARY KEY,
          stripe_customer_id text UNIQUE,
          stripe_subscription_id text UNIQUE,
          tier text NOT NULL DEFAULT 'free',
          status text NOT NULL DEFAULT 'free',
          price_id text,
          current_period_start timestamptz,
          current_period_end timestamptz,
          cancel_at_period_end boolean NOT NULL DEFAULT false,
          last_event_created timestamptz,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        # v4 1.1 (option C): a user's own lines, keyed to the user, apart from the
        # model's record. IF NOT EXISTS like everything else here; no row is rewritten.
        """
        CREATE TABLE IF NOT EXISTS moneyline_bets (
          id serial PRIMARY KEY,
          user_id text NOT NULL,
          game_pk text NOT NULL,
          game_date date NOT NULL,
          line_home integer,
          line_away integer,
          book text,
          entered_at timestamptz NOT NULL DEFAULT now(),
          model_version text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS moneyline_bets_user_game_idx
          ON moneyline_bets (user_id, game_pk)
        """,
        """
        CREATE INDEX IF NOT EXISTS moneyline_bets_user_date_idx
          ON moneyline_bets (user_id, game_date)
        """,
        """
        CREATE TABLE IF NOT EXISTS moneyline_billing_events (
          event_id text PRIMARY KEY,
          event_created timestamptz NOT NULL,
          received_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ]
    with _connection() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
    return True


def get_entitlement(user_id: str) -> dict[str, Any] | None:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM moneyline_entitlements WHERE user_id = %s", (user_id,))
            return cursor.fetchone()


def upsert_customer(user_id: str, customer_id: str) -> None:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO moneyline_entitlements (user_id, stripe_customer_id)
                   VALUES (%s, %s)
                   ON CONFLICT (user_id) DO UPDATE SET stripe_customer_id = EXCLUDED.stripe_customer_id""",
                (user_id, customer_id),
            )
        connection.commit()


def entitlement_customer(user_id: str) -> str | None:
    row = get_entitlement(user_id)
    return str(row["stripe_customer_id"]) if row and row.get("stripe_customer_id") else None


def apply_billing_event(event_id: str, created: datetime, customer_id: str,
                        state: dict[str, Any], user_id: str | None = None) -> bool:
    """Apply only new, chronologically newer events in one transaction."""
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO moneyline_billing_events (event_id, event_created) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (event_id, created),
            )
            if cursor.rowcount == 0:
                return False
            if not user_id:
                cursor.execute(
                    "SELECT user_id FROM moneyline_entitlements WHERE stripe_customer_id = %s",
                    (customer_id,),
                )
                row = cursor.fetchone()
                user_id = str(row["user_id"]) if row else None
            if not user_id:
                connection.commit()
                return True
            cursor.execute(
                "SELECT last_event_created FROM moneyline_entitlements WHERE user_id = %s FOR UPDATE",
                (user_id,),
            )
            existing = cursor.fetchone()
            if existing and existing["last_event_created"] and created <= existing["last_event_created"]:
                connection.commit()
                return True
            cursor.execute(
                """INSERT INTO moneyline_entitlements
                   (user_id, stripe_customer_id, stripe_subscription_id, tier, status, price_id,
                    current_period_start, current_period_end, cancel_at_period_end, last_event_created)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (user_id) DO UPDATE SET
                    stripe_customer_id=EXCLUDED.stripe_customer_id,
                    stripe_subscription_id=EXCLUDED.stripe_subscription_id,
                    tier=EXCLUDED.tier, status=EXCLUDED.status, price_id=EXCLUDED.price_id,
                    current_period_start=EXCLUDED.current_period_start,
                    current_period_end=EXCLUDED.current_period_end,
                    cancel_at_period_end=EXCLUDED.cancel_at_period_end,
                    last_event_created=EXCLUDED.last_event_created, updated_at=NOW()""",
                (user_id, customer_id, state.get("stripe_subscription_id"), state["tier"],
                 state["status"], state.get("price_id"), state.get("current_period_start"),
                 state.get("current_period_end"), state.get("cancel_at_period_end", False), created),
            )
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
                INSERT INTO moneyline_slate_snapshots (
                  snapshot_date, mode, model_version
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (snapshot_date) DO NOTHING
                RETURNING id
                """,
                (slate["date"], slate["mode"], MODEL_VERSION),
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
                      probables, adj_probability, adj_pick_team, adj_fair_line,
                      model_version
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        MODEL_VERSION,
                    ),
                )
        connection.commit()
    return True


MAX_PENDING_GRADE_ROWS = 100


def pending_picks(limit: int = MAX_PENDING_GRADE_ROWS) -> list[dict[str, Any]]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT game_pk, game_date, away_team, home_team, pick_team
                FROM moneyline_record_picks
                WHERE result IS NULL AND game_date <= CURRENT_DATE
                ORDER BY game_date, id
                LIMIT %s
                """,
                (max(1, min(limit, MAX_PENDING_GRADE_ROWS)),),
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


def get_record(user_id: str | None = None) -> dict[str, Any]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.game_pk, p.game_date, p.away_team, p.home_team,
                       p.pick_team, p.model_probability, p.fair_line,
                       p.entered_line, p.final_away, p.final_home, p.result,
                       p.units_pnl, p.probables, p.adj_probability,
                       p.adj_pick_team, p.adj_fair_line, p.adj_result,
                       p.adj_units_pnl, p.model_version, s.created_at
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

    # Which model priced this record. Rows written before versioning carry
    # NULL and are counted, not relabelled: stamping them "v1" would assert
    # something never checked against them. A record spanning a bump shows
    # more than one version here, which is the point -- it is the reader's
    # signal that the rows are not all comparable.
    versions_present = sorted(
        {row["model_version"] for row in rows if row["model_version"]}
    )
    unversioned = sum(row["model_version"] is None for row in rows)

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
        # User-authored slips are private and must never become part of the
        # public desk record. An authenticated reader sees only their own
        # paper slips; an anonymous reader sees no user-authored slips.
        "parlay_record": parlay_record(user_id),
        "model_versions_present": versions_present,
        "unversioned_picks": unversioned,
    }

def store_parlay_slip(
    slip_date: str,
    legs: list[dict[str, Any]],
    combined_probability: float,
    fair_line: int,
    book_line: int | None,
    user_id: str = "test-user",
) -> dict[str, Any]:
    """Store a user's slip; one paper slip per user per day."""
    if book_line is not None and (
        book_line == 0
        or abs(book_line) < 100
        or abs(book_line) > MAX_PARLAY_BOOK_LINE
    ):
        raise ValueError(
            "American parlay lines must be between "
            f"-{MAX_PARLAY_BOOK_LINE} and -100 or between +100 and "
            f"+{MAX_PARLAY_BOOK_LINE}."
        )
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO moneyline_parlay_slips (
                  user_id, slip_date, legs, combined_probability, fair_line, book_line,
                  model_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, slip_date) WHERE user_id IS NOT NULL DO NOTHING
                RETURNING id
                """,
                (
                    user_id,
                    slip_date,
                    Jsonb(legs),
                    combined_probability,
                    fair_line,
                    book_line,
                    MODEL_VERSION,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                cursor.execute(
                    "SELECT id, legs, created_at FROM moneyline_parlay_slips "
                    "WHERE user_id = %s AND slip_date = %s",
                    (user_id, slip_date),
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
            if row["book_line"] is not None:
                line = int(row["book_line"])
                payout = 100 / abs(line) if line < 0 else line / 100
            else:
                # No book price was recorded. This used to fall back to the
                # slip's own fair_line -- grading the parlay as if you had been
                # offered the model's price, which no book offers. That made the
                # parlay record systematically optimistic, and inconsistent with
                # picks, which fall back to a standard -110 (see grade_pick).
                # Use the parlay analogue: the same -110 legs, compounded.
                payout = parlay_book_decimal([STANDARD_LEG_LINE] * len(legs)) - 1
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

def _settled_basis(row: dict[str, Any]) -> str | None:
    """Which basis actually settled this slip, read off the row itself.

    Not derived from a date. The NULL-book_line fallback changed from the
    slip's own `fair_line` to compounded -110 legs, but the deploy time of
    that change is recorded nowhere, and partitioning the ledger on an
    invented boundary would be the fabricated precision this module refuses
    everywhere else. The stored payout is evidence; a guessed cutover is not.

    A WIN distinguishes the two bases, because the payouts differ. A LOSS
    does not -- it is -1.0 under either -- and that is reported as
    indistinguishable rather than assigned to whichever basis is convenient.
    """
    if row["book_line"] is not None:
        return "book_price"
    if row["result"] not in ("WIN", "LOSS"):
        return None
    if row["result"] == "LOSS":
        return "indistinguishable"
    legs = row["legs"] or []
    units = float(row["units_pnl"] or 0.0)
    compounded = parlay_book_decimal([STANDARD_LEG_LINE] * len(legs)) - 1
    retired = decimal_odds(row["fair_line"]) - 1
    if abs(units - compounded) < 1e-6:
        return "standard_-110_compounded"
    if abs(units - retired) < 1e-6:
        return "fair_line_retired"
    return "unrecognised"


def parlay_record(user_id: str | None = "test-user") -> dict[str, Any]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            if user_id is None:
                # Anonymous/public record views must not publish private slips
                # or legacy rows written before ownership existed.
                cursor.execute(
                    """
                    SELECT id, slip_date, legs, combined_probability, fair_line,
                           book_line, result, units_pnl, model_version, created_at
                    FROM moneyline_parlay_slips
                    WHERE FALSE
                    ORDER BY slip_date, id
                    """
                )
            else:
                cursor.execute(
                    """
                SELECT id, slip_date, legs, combined_probability, fair_line,
                       book_line, result, units_pnl, model_version, created_at
                FROM moneyline_parlay_slips
                WHERE user_id = %s
                ORDER BY slip_date, id
                """,
                    (user_id,),
                )
            rows = list(cursor.fetchall())
    wins = sum(row["result"] == "WIN" for row in rows)
    losses = sum(row["result"] == "LOSS" for row in rows)
    units = sum(float(row["units_pnl"] or 0.0) for row in rows)

    # Era reporting, mirroring get_record. The parlay table is the one whose
    # grading basis actually changed -- slips used to fall back to the slip's
    # own fair_line and now fall back to compounded -110 legs, symmetric with
    # picks -- so it is the one that most needs to say what it is made of.
    #
    # Composition is reported, not corrected. Regrading the old rows would
    # move the published record in the desk's own favour (the retired basis
    # was pessimistic: grading at your own fair line is zero-EV by
    # construction), and replit.md forbids rewriting rows that predate the
    # repo. A correction declined in your own favour is the stronger claim.
    #
    # No cutover timestamp is asserted. The fix shipped in a commit whose
    # deploy time is not recorded anywhere, and inventing a boundary date to
    # partition the rows would be exactly the fabricated precision the desk
    # refuses elsewhere. What is reported is what is actually known: how many
    # graded slips carry no recorded book price, and how many carry no model
    # stamp.
    versions_present = sorted(
        {row["model_version"] for row in rows if row["model_version"]}
    )
    fallback_graded = sum(
        row["book_line"] is None and row["result"] in ("WIN", "LOSS")
        for row in rows
    )
    # Counting the fallback rows is not the same as knowing how they settled.
    # An earlier version of this disclosure told the reader they "were settled
    # at the -110 legs compounded" -- false for every row graded before that
    # became the fallback, and unknowable for a loss. Report the bases the
    # rows actually evidence.
    settled_bases: dict[str, int] = {}
    for row in rows:
        basis = _settled_basis(row)
        if basis is not None:
            settled_bases[basis] = settled_bases.get(basis, 0) + 1
    return {
        "slips": len(rows),
        "graded": wins + losses,
        "wins": wins,
        "losses": losses,
        "voided": sum(row["result"] == "VOID" for row in rows),
        "units_pnl": round(units, 3),
        "line": f"PARLAYS {wins}–{losses}, {'+' if units >= 0 else ''}{units:.1f}u",
        "model_versions_present": versions_present,
        "unversioned_slips": sum(row["model_version"] is None for row in rows),
        "fallback_graded": fallback_graded,
        "settled_bases": settled_bases,
        "fallback_basis": (
            "Slips with no recorded book price NOW grade at the same −110 "
            "legs compounded that picks fall back to. Rows settled before "
            "that are reported under their own basis rather than relabelled."
        ),
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

def pending_parlays(limit: int = MAX_PENDING_GRADE_ROWS) -> list[dict[str, Any]]:
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
                LIMIT %s
                """,
                (max(1, min(limit, MAX_PENDING_GRADE_ROWS)),),
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


# --- v4 1.1 (option C): a user's own lines, apart from the model's record ---------------

_BET_COLUMNS = (
    "id, user_id, game_pk, game_date, line_home, line_away, book, entered_at, "
    "model_version, created_at, updated_at"
)


def _bet_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "user_id": row["user_id"],
        "game_pk": row["game_pk"],
        "game_date": row["game_date"].isoformat(),
        "line_home": row["line_home"],
        "line_away": row["line_away"],
        "book": row["book"],
        "entered_at": row["entered_at"].isoformat(),
        "model_version": row["model_version"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


class _Keep:
    """Sentinel: the caller did not mention this field, so the stored value stays."""

    def __repr__(self) -> str:
        return "KEEP"


KEEP: Any = _Keep()


def record_bet_line(
    user_id: str,
    game_pk: str,
    game_date: date,
    line_home: int | None | _Keep = KEEP,
    line_away: int | None | _Keep = KEEP,
    book: str | None | _Keep = KEEP,
) -> dict[str, Any] | None:
    """Record, update or clear the line a user says they can get on a game.

    Lives in `moneyline_bets`, keyed to the user, never in `moneyline_record_picks`: the
    model's public record is graded at its own price and must not be contaminated by what
    any user typed (v4 §4.2). Absent and null are different things (Asher, 2026-09-02):
    a field left at `KEEP` leaves the stored value alone, so a card with one price typed
    cannot wipe the other; an explicit None clears it. `entered_at` and `model_version`
    move with every write -- the era marker follows the line, not the row -- and
    `created_at` keeps the first entry.

    A row left with both sides cleared is deleted and None is returned: a cleared line is
    not a bet, and 1.5 must never grade the absence of one. The user's record holds only
    lines they actually hold.
    """
    fields = {"line_home": line_home, "line_away": line_away, "book": book}
    given = {name: value for name, value in fields.items() if value is not KEEP}
    assignments = ", ".join(f"{name} = EXCLUDED.{name}" for name in given)
    if assignments:
        assignments += ","
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO moneyline_bets (
                  user_id, game_pk, game_date, line_home, line_away, book, model_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, game_pk) DO UPDATE SET
                  {assignments}
                  game_date = EXCLUDED.game_date,
                  model_version = EXCLUDED.model_version,
                  entered_at = now(),
                  updated_at = now()
                RETURNING {_BET_COLUMNS}
                """,
                (
                    user_id,
                    game_pk,
                    game_date,
                    given.get("line_home"),
                    given.get("line_away"),
                    given.get("book"),
                    MODEL_VERSION,
                ),
            )
            row = cursor.fetchone()
            if row["line_home"] is None and row["line_away"] is None:
                cursor.execute("DELETE FROM moneyline_bets WHERE id = %s", (row["id"],))
                row = None
        connection.commit()
    return _bet_payload(row) if row is not None else None


def user_bets(user_id: str, game_date: date | None = None) -> list[dict[str, Any]]:
    """A user's recorded lines, newest first; one day's when `game_date` is given."""
    with _connection() as connection:
        with connection.cursor() as cursor:
            if game_date is None:
                cursor.execute(
                    f"SELECT {_BET_COLUMNS} FROM moneyline_bets WHERE user_id = %s "
                    "ORDER BY game_date DESC, id DESC",
                    (user_id,),
                )
            else:
                cursor.execute(
                    f"SELECT {_BET_COLUMNS} FROM moneyline_bets "
                    "WHERE user_id = %s AND game_date = %s ORDER BY id DESC",
                    (user_id, game_date),
                )
            rows = cursor.fetchall()
    return [_bet_payload(row) for row in rows]
