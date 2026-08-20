"""grade_pending_records tests: stuck, tied, or vanished games never block or corrupt grading."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

import backend.main as main
from backend.feeds import FeedUnavailable, GameNotFound
from backend.record_store import get_record, pending_picks

YESTERDAY = date.today() - timedelta(days=1)
STALE = date.today() - timedelta(days=main.VOID_AFTER_DAYS + 2)


def _rows(*game_pks: str, game_date: date = YESTERDAY) -> list[dict[str, Any]]:
    return [
        {
            "game_pk": pk,
            "game_date": game_date,
            "away_team": "NYY",
            "home_team": "BOS",
            "pick_team": "BOS",
        }
        for pk in game_pks
    ]


async def test_database_unavailable_short_circuits(monkeypatch):
    monkeypatch.setattr(main, "database_available", lambda: False)
    monkeypatch.setattr(
        main, "pending_picks", lambda: pytest.fail("pending_picks must not be called")
    )

    assert await main.grade_pending_records() == {
        "checked": 0,
        "graded": 0,
        "voided": 0,
    }


async def test_no_pending_picks_checks_nothing(monkeypatch):
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(main, "pending_picks", lambda: [])

    async def fail_feed(game_pk: str):
        pytest.fail("feed must not be called with no pending picks")

    monkeypatch.setattr(main, "get_final_score", fail_feed)

    assert await main.grade_pending_records() == {
        "checked": 0,
        "graded": 0,
        "voided": 0,
    }


async def test_not_final_games_are_checked_but_not_graded(monkeypatch):
    """Postponed/suspended games return None from the feed and stay pending."""
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(main, "pending_picks", lambda: _rows("gm-1", "gm-2"))

    async def never_final(game_pk: str):
        return None

    graded_calls: list[str] = []
    monkeypatch.setattr(main, "get_final_score", never_final)
    monkeypatch.setattr(
        main, "grade_pick", lambda pk, *args: graded_calls.append(pk) or True
    )

    assert await main.grade_pending_records() == {
        "checked": 2,
        "graded": 0,
        "voided": 0,
    }
    assert graded_calls == []


async def test_stuck_pick_never_blocks_other_picks(monkeypatch):
    """One postponed game and one vanished game_pk must not stop a final from grading."""
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(
        main, "pending_picks", lambda: _rows("gm-postponed", "gm-vanished", "gm-final")
    )

    async def feed(game_pk: str):
        if game_pk == "gm-postponed":
            return None  # never went Final
        if game_pk == "gm-vanished":
            raise FeedUnavailable("game_pk no longer exists in the MLB feed")
        return {
            "game_pk": game_pk,
            "away": "NYY",
            "home": "BOS",
            "final_away": 2,
            "final_home": 5,
        }

    graded_calls: list[str] = []

    def fake_grade(game_pk: str, *args: Any) -> bool:
        graded_calls.append(game_pk)
        return True

    monkeypatch.setattr(main, "get_final_score", feed)
    monkeypatch.setattr(main, "grade_pick", fake_grade)

    assert await main.grade_pending_records() == {
        "checked": 3,
        "graded": 1,
        "voided": 0,
    }
    assert graded_calls == ["gm-final"]


async def test_unexpected_feed_crash_is_contained(monkeypatch):
    """Even a non-feed exception in one pick must not propagate or block others."""
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(main, "pending_picks", lambda: _rows("gm-crash", "gm-final"))

    async def feed(game_pk: str):
        if game_pk == "gm-crash":
            raise KeyError("malformed feed payload")
        return {
            "game_pk": game_pk,
            "away": "NYY",
            "home": "BOS",
            "final_away": 1,
            "final_home": 4,
        }

    monkeypatch.setattr(main, "get_final_score", feed)
    monkeypatch.setattr(main, "grade_pick", lambda *args: True)

    assert await main.grade_pending_records() == {
        "checked": 2,
        "graded": 1,
        "voided": 0,
    }


async def test_cancelled_game_is_voided(monkeypatch):
    """A Cancelled game gets a terminal void instead of staying pending forever."""
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(main, "pending_picks", lambda: _rows("gm-cancelled", "gm-live"))

    async def feed(game_pk: str):
        if game_pk == "gm-cancelled":
            return {"game_pk": game_pk, "status": "cancelled"}
        return None

    void_calls: list[str] = []
    monkeypatch.setattr(main, "get_final_score", feed)
    monkeypatch.setattr(main, "void_pick", lambda pk: void_calls.append(pk) or True)
    monkeypatch.setattr(
        main, "grade_pick", lambda *args: pytest.fail("cancelled games must not grade")
    )

    assert await main.grade_pending_records() == {
        "checked": 2,
        "graded": 0,
        "voided": 1,
    }
    assert void_calls == ["gm-cancelled"]


async def test_vanished_game_pk_voids_only_after_grace_period(monkeypatch):
    """A 404'd game_pk voids once stale, but a fresh one gets time to reappear."""
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(
        main,
        "pending_picks",
        lambda: _rows("gm-stale", game_date=STALE) + _rows("gm-fresh"),
    )

    async def feed(game_pk: str):
        raise GameNotFound("game_pk no longer exists in the MLB feed")

    void_calls: list[str] = []
    monkeypatch.setattr(main, "get_final_score", feed)
    monkeypatch.setattr(main, "void_pick", lambda pk: void_calls.append(pk) or True)

    assert await main.grade_pending_records() == {
        "checked": 2,
        "graded": 0,
        "voided": 1,
    }
    assert void_calls == ["gm-stale"]


async def test_generic_feed_outage_never_voids_stale_picks(monkeypatch):
    """A plain outage (not a 404) must never void, no matter how old the pick."""
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(main, "pending_picks", lambda: _rows("gm-stale", game_date=STALE))

    async def feed(game_pk: str):
        raise FeedUnavailable("MLB Stats API is down")

    monkeypatch.setattr(main, "get_final_score", feed)
    monkeypatch.setattr(
        main, "void_pick", lambda pk: pytest.fail("outages must not void picks")
    )

    assert await main.grade_pending_records() == {
        "checked": 1,
        "graded": 0,
        "voided": 0,
    }


async def test_end_to_end_tie_postponed_and_final_against_real_store(
    monkeypatch, seed_pick
):
    """Full path through the real store: only the true final grades; the ledger stays clean."""
    seed_pick("gm-postponed", YESTERDAY, "NYY", "BOS", pick_team="BOS")
    seed_pick("gm-tie", YESTERDAY, "CHC", "STL", pick_team="STL")
    seed_pick("gm-final", YESTERDAY, "LAD", "SFG", pick_team="LAD")

    async def feed(game_pk: str):
        if game_pk == "gm-postponed":
            return None
        if game_pk == "gm-tie":
            return {
                "game_pk": game_pk,
                "away": "CHC",
                "home": "STL",
                "final_away": 3,
                "final_home": 3,
            }
        return {
            "game_pk": game_pk,
            "away": "LAD",
            "home": "SFG",
            "final_away": 7,
            "final_home": 2,
        }

    monkeypatch.setattr(main, "get_final_score", feed)

    assert await main.grade_pending_records() == {
        "checked": 3,
        "graded": 1,
        "voided": 0,
    }

    record = get_record()
    assert record["picks"] == 3
    assert record["graded"] == 1
    assert record["wins"] == 1
    assert record["losses"] == 0
    # The postponed and tied games are still pending — never lost, never mis-scored.
    still_pending = sorted(pick["game_pk"] for pick in pending_picks())
    assert still_pending == ["gm-postponed", "gm-tie"]

    # A second unattended cycle with the same feed state changes nothing.
    assert await main.grade_pending_records() == {
        "checked": 2,
        "graded": 0,
        "voided": 0,
    }
    record = get_record()
    assert record["graded"] == 1
    assert record["units_pnl"] == pytest.approx(100 / 110, abs=1e-3)


async def test_end_to_end_void_path_against_real_store(monkeypatch, seed_pick):
    """Cancelled and long-vanished games resolve terminally; the record stays honest."""
    seed_pick("gm-cancelled", YESTERDAY, "NYY", "BOS", pick_team="BOS")
    seed_pick("gm-vanished", STALE, "CHC", "STL", pick_team="STL")
    seed_pick("gm-final", YESTERDAY, "LAD", "SFG", pick_team="LAD")

    async def feed(game_pk: str):
        if game_pk == "gm-cancelled":
            return {"game_pk": game_pk, "status": "cancelled"}
        if game_pk == "gm-vanished":
            raise GameNotFound("game_pk no longer exists in the MLB feed")
        return {
            "game_pk": game_pk,
            "status": "final",
            "away": "LAD",
            "home": "SFG",
            "final_away": 7,
            "final_home": 2,
        }

    monkeypatch.setattr(main, "get_final_score", feed)

    assert await main.grade_pending_records() == {
        "checked": 3,
        "graded": 1,
        "voided": 2,
    }

    record = get_record()
    assert record["picks"] == 3
    assert record["graded"] == 1
    assert record["wins"] == 1
    assert record["losses"] == 0
    assert record["voided"] == 2
    # Voided picks carry 0 units and never touch the hit rate or the curve.
    assert record["hit_rate"] == pytest.approx(1.0)
    assert record["units_pnl"] == pytest.approx(100 / 110, abs=1e-3)
    assert len(record["curve"]) == 1
    voided_entries = {
        entry["game_pk"]: entry for entry in record["entries"] if entry["result"] == "VOID"
    }
    assert sorted(voided_entries) == ["gm-cancelled", "gm-vanished"]
    assert all(entry["units_pnl"] == 0 for entry in voided_entries.values())

    # Nothing is left pending, so the auto-grader stops polling entirely.
    assert pending_picks() == []
    assert await main.grade_pending_records() == {
        "checked": 0,
        "graded": 0,
        "voided": 0,
    }
