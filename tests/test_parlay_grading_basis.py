"""A parlay with no book line must grade at a standard price, not its own.

The fallback used to be the slip's own `fair_line` — the zero-vig price implied
by the model's combined probability. Grading at your own fair price is exactly
zero-EV by construction:

    EV = P·(1/P − 1) − (1 − P) = (1 − P) − (1 − P) = 0

So the parlay record could only ever wander around break-even, whatever the
model did. It was not merely generous; it could not measure anything. Picks
already fall back to a standard −110 (see `grade_pick`), which asks the
question that matters — does the model beat a real book price? — and the
parlay fallback now asks the same one, with the same −110 legs compounded.

Slips already graded are untouched: the UPDATE carries `AND result IS NULL`,
so settlement is terminal and this change is forward-only by construction.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

import backend.record_store as record_store
from backend.odds import parlay_book_decimal

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)

LEGS = [
    {"game_pk": "880001", "team": "BOS", "side": "home"},
    {"game_pk": "880002", "team": "NYY", "side": "away"},
]


@pytest.fixture()
def slip(record_schema) -> Any:
    """Store one ungraded two-leg slip and hand back its id.

    `slip_date` is UNIQUE — one paper slip per day — so each call takes its own
    day, otherwise the second store would silently return the first slip.
    """
    day = {"offset": 1}

    def _store(book_line: int | None, fair_line: int = 260) -> int:
        slip_date = TODAY - timedelta(days=day["offset"])
        day["offset"] += 1
        stored = record_store.store_parlay_slip(
            slip_date=slip_date.isoformat(),
            legs=LEGS,
            combined_probability=0.33,
            fair_line=fair_line,
            book_line=book_line,
        )
        assert stored["stored"] is True, "fixture expected a fresh slip per day"
        return int(stored["slip_id"])

    return _store


def _fetch(slip_id: int) -> dict[str, Any]:
    with record_store._connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT result, units_pnl FROM moneyline_parlay_slips WHERE id = %s",
                (slip_id,),
            )
            return cursor.fetchone()


WINNING_OUTCOMES = {"880001": "BOS", "880002": "NYY"}
LOSING_OUTCOMES = {"880001": "NYY", "880002": "NYY"}


def test_a_won_slip_without_a_book_line_pays_the_standard_compounded_price(
    slip,
) -> None:
    slip_id = slip(book_line=None, fair_line=260)
    assert record_store.grade_parlay(slip_id, WINNING_OUTCOMES) is True

    row = _fetch(slip_id)
    expected = parlay_book_decimal([-110, -110]) - 1
    assert row["result"] == "WIN"
    assert row["units_pnl"] == pytest.approx(expected, abs=1e-9)
    assert row["units_pnl"] == pytest.approx(2.6446, abs=1e-3)


def test_the_fallback_is_no_longer_the_slips_own_fair_line(slip) -> None:
    """The regression guard. fair_line grading is self-referential."""
    slip_id = slip(book_line=None, fair_line=260)
    record_store.grade_parlay(slip_id, WINNING_OUTCOMES)

    fair_line_payout = 260 / 100  # what the old fallback would have paid
    assert _fetch(slip_id)["units_pnl"] != pytest.approx(fair_line_payout, abs=1e-6)


def test_a_recorded_book_line_still_wins_over_the_fallback(slip) -> None:
    """A real book price is always preferred; only its absence triggers -110."""
    slip_id = slip(book_line=550, fair_line=260)
    record_store.grade_parlay(slip_id, WINNING_OUTCOMES)

    assert _fetch(slip_id)["units_pnl"] == pytest.approx(5.5, abs=1e-9)


def test_a_negative_book_line_still_grades_as_before(slip) -> None:
    slip_id = slip(book_line=-150, fair_line=260)
    record_store.grade_parlay(slip_id, WINNING_OUTCOMES)

    assert _fetch(slip_id)["units_pnl"] == pytest.approx(100 / 150, abs=1e-9)


def test_a_lost_slip_is_minus_one_unit_regardless_of_basis(slip) -> None:
    """All-or-nothing: the price only matters on a win."""
    for slip_id in (slip(book_line=None), slip(book_line=550)):
        record_store.grade_parlay(slip_id, LOSING_OUTCOMES)
        row = _fetch(slip_id)
        assert row["result"] == "LOSS"
        assert row["units_pnl"] == pytest.approx(-1.0)


def test_an_already_graded_slip_is_never_regraded(slip) -> None:
    """Settlement is terminal — which is what makes this change forward-only."""
    slip_id = slip(book_line=None)
    record_store.grade_parlay(slip_id, WINNING_OUTCOMES)
    first = _fetch(slip_id)

    record_store.grade_parlay(slip_id, LOSING_OUTCOMES)
    assert _fetch(slip_id) == first


def test_an_unfinished_leg_leaves_the_slip_pending(slip) -> None:
    slip_id = slip(book_line=None)
    assert record_store.grade_parlay(slip_id, {"880001": "BOS"}) is False

    row = _fetch(slip_id)
    assert row["result"] is None
    assert row["units_pnl"] is None
