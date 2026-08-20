"""grade_pick / pending_picks tests against the isolated Postgres schema."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.record_store import get_record, grade_pick, pending_picks, void_pick

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def test_win_grades_pick_with_default_line(seed_pick, fetch_pick):
    seed_pick("gm-win", YESTERDAY, "NYY", "BOS", pick_team="BOS")

    assert grade_pick("gm-win", 3, 5, "NYY", "BOS") is True

    row = fetch_pick("gm-win")
    assert row["result"] == "WIN"
    assert row["final_away"] == 3
    assert row["final_home"] == 5
    # No entered_line stored: payout defaults to -110 pricing.
    assert row["units_pnl"] == pytest.approx(100 / 110)
    assert row["graded_at"] is not None


def test_loss_costs_exactly_one_unit(seed_pick, fetch_pick):
    seed_pick("gm-loss", YESTERDAY, "NYY", "BOS", pick_team="BOS", entered_line=-135)

    assert grade_pick("gm-loss", 7, 2, "NYY", "BOS") is True

    row = fetch_pick("gm-loss")
    assert row["result"] == "LOSS"
    assert row["units_pnl"] == pytest.approx(-1.0)


def test_win_on_positive_line_pays_line_over_100(seed_pick, fetch_pick):
    seed_pick("gm-dog", YESTERDAY, "NYY", "BOS", pick_team="NYY", entered_line=150)

    assert grade_pick("gm-dog", 6, 4, "NYY", "BOS") is True

    row = fetch_pick("gm-dog")
    assert row["result"] == "WIN"
    assert row["units_pnl"] == pytest.approx(1.5)


def test_tie_never_grades_and_never_writes_scores(seed_pick, fetch_pick):
    seed_pick("gm-tie", YESTERDAY, "NYY", "BOS", pick_team="BOS")

    assert grade_pick("gm-tie", 4, 4, "NYY", "BOS") is False

    row = fetch_pick("gm-tie")
    assert row["result"] is None
    assert row["final_away"] is None
    assert row["final_home"] is None
    assert row["units_pnl"] is None
    # The tie stays pending so a completed suspended game can grade later.
    assert [pick["game_pk"] for pick in pending_picks()] == ["gm-tie"]
    # And the public ledger is untouched.
    record = get_record()
    assert record["graded"] == 0
    assert record["wins"] == 0
    assert record["losses"] == 0
    assert record["units_pnl"] == 0


def test_already_graded_pick_cannot_be_regraded(seed_pick, fetch_pick):
    seed_pick("gm-final", YESTERDAY, "NYY", "BOS", pick_team="BOS")
    assert grade_pick("gm-final", 3, 5, "NYY", "BOS") is True

    # A second (contradictory) result must be ignored entirely.
    assert grade_pick("gm-final", 9, 0, "NYY", "BOS") is False

    row = fetch_pick("gm-final")
    assert row["result"] == "WIN"
    assert row["final_away"] == 3
    assert row["final_home"] == 5
    record = get_record()
    assert record["graded"] == 1
    assert record["wins"] == 1


def test_missing_pick_returns_false(record_schema):
    assert grade_pick("gm-unknown", 3, 5, "NYY", "BOS") is False


def test_void_pick_is_terminal_at_zero_units(seed_pick, fetch_pick):
    seed_pick("gm-cancelled", YESTERDAY, "NYY", "BOS", pick_team="BOS")

    assert void_pick("gm-cancelled") is True

    row = fetch_pick("gm-cancelled")
    assert row["result"] == "VOID"
    assert row["units_pnl"] == 0
    assert row["graded_at"] is not None
    assert row["final_away"] is None
    assert row["final_home"] is None
    # Voided picks leave the pending queue, so the auto-grader stops polling.
    assert pending_picks() == []
    # And they never count as wins or losses.
    record = get_record()
    assert record["picks"] == 1
    assert record["graded"] == 0
    assert record["wins"] == 0
    assert record["losses"] == 0
    assert record["voided"] == 1
    assert record["hit_rate"] is None
    assert record["units_pnl"] == 0
    assert record["curve"] == []


def test_void_pick_never_overwrites_a_graded_result(seed_pick, fetch_pick):
    seed_pick("gm-final", YESTERDAY, "NYY", "BOS", pick_team="BOS")
    assert grade_pick("gm-final", 3, 5, "NYY", "BOS") is True

    assert void_pick("gm-final") is False

    row = fetch_pick("gm-final")
    assert row["result"] == "WIN"
    assert row["units_pnl"] == pytest.approx(100 / 110)


def test_void_pick_missing_game_returns_false(record_schema):
    assert void_pick("gm-unknown") is False


def test_voided_pick_never_dilutes_hit_rate_or_curve(seed_pick):
    seed_pick("gm-win", YESTERDAY, "NYY", "BOS", pick_team="BOS")
    seed_pick("gm-void", YESTERDAY, "CHC", "STL", pick_team="STL")

    assert grade_pick("gm-win", 3, 5, "NYY", "BOS") is True
    assert void_pick("gm-void") is True

    record = get_record()
    assert record["graded"] == 1
    assert record["voided"] == 1
    assert record["hit_rate"] == pytest.approx(1.0)
    assert len(record["curve"]) == 1
    assert record["curve"][0]["hit_rate"] == pytest.approx(1.0)


def test_pending_picks_excludes_graded_and_future_games(seed_pick):
    seed_pick("gm-old", YESTERDAY, "NYY", "BOS", pick_team="BOS")
    seed_pick("gm-today", TODAY, "CHC", "STL", pick_team="STL")
    seed_pick("gm-future", TODAY + timedelta(days=30), "LAD", "SFG", pick_team="LAD")
    assert grade_pick("gm-old", 1, 2, "NYY", "BOS") is True

    pending = [pick["game_pk"] for pick in pending_picks()]
    assert pending == ["gm-today"]


def test_doubleheader_games_share_a_date_but_grade_independently(seed_pick, fetch_pick):
    seed_pick("gm-dh-1", YESTERDAY, "NYY", "BOS", pick_team="BOS")
    seed_pick("gm-dh-2", YESTERDAY, "NYY", "BOS", pick_team="NYY")

    assert grade_pick("gm-dh-1", 2, 6, "NYY", "BOS") is True

    assert fetch_pick("gm-dh-1")["result"] == "WIN"
    assert fetch_pick("gm-dh-2")["result"] is None
    assert [pick["game_pk"] for pick in pending_picks()] == ["gm-dh-2"]

    assert grade_pick("gm-dh-2", 8, 3, "NYY", "BOS") is True
    assert fetch_pick("gm-dh-2")["result"] == "WIN"
    record = get_record()
    assert record["graded"] == 2
    assert record["wins"] == 2
