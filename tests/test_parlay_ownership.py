"""Paper parlay slips are isolated by authenticated user."""

from __future__ import annotations

from datetime import date

import backend.record_store as record_store


LEGS = [
    {"game_pk": "880101", "team": "BOS", "side": "home"},
    {"game_pk": "880102", "team": "NYY", "side": "away"},
]


def _store(user_id: str, day: str) -> dict:
    return record_store.store_parlay_slip(
        slip_date=day,
        legs=LEGS,
        combined_probability=0.33,
        fair_line=203,
        book_line=None,
        user_id=user_id,
    )


def test_users_can_each_log_the_same_day(record_schema):
    day = date.today().isoformat()

    first = _store("user-a", day)
    second = _store("user-b", day)

    assert first["stored"] is True
    assert second["stored"] is True
    assert first["slip_id"] != second["slip_id"]
    assert [entry["id"] for entry in record_store.parlay_record("user-a")["entries"]] == [
        first["slip_id"]
    ]
    assert [entry["id"] for entry in record_store.parlay_record("user-b")["entries"]] == [
        second["slip_id"]
    ]


def test_same_user_reopening_does_not_disclose_or_replace_other_users_slip(
    record_schema,
):
    day = date.today().isoformat()

    first = _store("user-a", day)
    reopened = _store("user-a", day)

    assert reopened == {
        "stored": False,
        "already_logged": True,
        "slip_id": first["slip_id"],
    }
    assert record_store.parlay_record("user-b")["entries"] == []
    assert record_store.parlay_record(None)["entries"] == []
