"""Regression tests for the public pick ledger's write and grading paths."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

import backend.main as main
import backend.record_store as record_store


TODAY = date.today()


def _slate(*games: dict[str, Any], mode: str = "live") -> dict[str, Any]:
    return {"date": TODAY.isoformat(), "mode": mode, "games": list(games)}


def _game(
    game_pk: str,
    *,
    model_prob_home: float = 0.56,
    fair_home: int = -127,
    fair_away: int = 127,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "game_pk": game_pk,
        "game_date": TODAY.isoformat(),
        "away": "BOS",
        "home": "NYY",
        "model_prob_home": model_prob_home,
        "fair_lines": {"home": fair_home, "away": fair_away},
        **extra,
    }


def _rows(record_schema, table: str) -> list[dict[str, Any]]:
    with record_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table} ORDER BY id")
            return list(cursor.fetchall())


def test_store_slate_snapshot_is_idempotent_and_selects_pick_prices(record_schema):
    slate = _slate(
        _game(
            "favorite",
            model_prob_home=0.56,
            fair_home=-127,
            fair_away=127,
            adj_prob=0.58,
            adj_fair_lines={"home": -138, "away": 138},
        ),
        _game(
            "underdog",
            model_prob_home=0.44,
            fair_home=-138,
            fair_away=127,
            adj_prob=0.42,
            adj_fair_lines={"home": -145, "away": 125},
        ),
    )

    assert record_store.store_slate_snapshot(slate) is True
    first_snapshots = _rows(record_schema, "moneyline_slate_snapshots")
    first_picks = _rows(record_schema, "moneyline_record_picks")

    # Reopening the same date must not create a second snapshot or duplicate
    # either pick, even though the feed payload is supplied again.
    assert record_store.store_slate_snapshot(slate) is True
    assert _rows(record_schema, "moneyline_slate_snapshots") == first_snapshots
    assert _rows(record_schema, "moneyline_record_picks") == first_picks

    picks = {row["game_pk"]: row for row in first_picks}
    assert picks["favorite"]["pick_team"] == "NYY"
    assert picks["favorite"]["model_probability"] == pytest.approx(0.56)
    assert picks["favorite"]["fair_line"] == -127
    assert picks["favorite"]["adj_pick_team"] == "NYY"
    assert picks["favorite"]["adj_probability"] == pytest.approx(0.58)
    assert picks["favorite"]["adj_fair_line"] == -138
    assert picks["underdog"]["pick_team"] == "BOS"
    assert picks["underdog"]["model_probability"] == pytest.approx(0.56)
    assert picks["underdog"]["fair_line"] == 127
    assert picks["underdog"]["adj_pick_team"] == "BOS"
    assert picks["underdog"]["adj_probability"] == pytest.approx(0.58)
    assert picks["underdog"]["adj_fair_line"] == 125


def test_store_slate_snapshot_skips_non_live_and_pricing_error_games(record_schema):
    assert record_store.store_slate_snapshot(
        _slate(_game("not-live"), mode="final")
    ) is False
    assert _rows(record_schema, "moneyline_slate_snapshots") == []

    assert record_store.store_slate_snapshot(
        _slate(
            _game("bad-price", pricing_error="market unavailable"),
            _game("good-price"),
        )
    ) is True

    assert [row["game_pk"] for row in _rows(record_schema, "moneyline_record_picks")] == [
        "good-price"
    ]


@pytest.mark.parametrize(
    ("entered_line", "won", "expected_units"),
    [
        (None, True, 100 / 110),
        (-135, True, 100 / 135),
        (150, True, 1.5),
        (-135, False, -1.0),
    ],
)
def test_grade_pick_records_result_and_units_math(
    seed_pick, fetch_pick, entered_line, won, expected_units
):
    seed_pick(
        "graded-game",
        TODAY,
        "NYY",
        "BOS",
        pick_team="BOS",
        entered_line=entered_line,
    )
    final_away, final_home = (3, 5) if won else (7, 2)

    assert record_store.grade_pick(
        "graded-game", final_away, final_home, "NYY", "BOS"
    ) is True

    row = fetch_pick("graded-game")
    assert row["result"] == ("WIN" if won else "LOSS")
    assert row["units_pnl"] == pytest.approx(expected_units)


async def test_snapshot_live_slate_short_circuits_without_database(monkeypatch):
    monkeypatch.setattr(main, "database_available", lambda: False)
    monkeypatch.setattr(
        main, "get_slate", lambda: pytest.fail("slate feed must not be called")
    )
    monkeypatch.setattr(
        main,
        "store_slate_snapshot",
        lambda _: pytest.fail("ledger write must not be called"),
    )

    assert await main.snapshot_live_slate() is False