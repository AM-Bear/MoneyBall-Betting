"""v4-plan 1.1 as option C: the line a user says they can get lives in `moneyline_bets`,
keyed to the user, and never touches `moneyline_record_picks`.

The model's record is graded at its own price (−110 by default) and is the product's
honesty claim; §4.2 of the plan says it must not be contaminated by user behaviour. So the
user's line gets its own table, its own route, and a test that the model's rows are
byte-identical before and after a user records one.
"""

from datetime import date

from fastapi.testclient import TestClient

import backend.main as main
import backend.record_store as record_store
from backend.precompute import MODEL_VERSION

DAY = date(2026, 9, 2)


def _rows(connection_factory, table: str) -> list[dict]:
    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table} ORDER BY id")
            return [dict(row) for row in cursor.fetchall()]


# --- the store -------------------------------------------------------------------------


def test_record_bet_line_inserts_the_users_line_stamped_with_the_era(record_schema):
    bet = record_store.record_bet_line("user-a", "790001", DAY, line_home=-135, line_away=120)

    assert bet["user_id"] == "user-a"
    assert bet["game_pk"] == "790001"
    assert bet["game_date"] == "2026-09-02"
    assert bet["line_home"] == -135
    assert bet["line_away"] == 120
    assert bet["book"] is None
    assert bet["model_version"] == MODEL_VERSION
    assert bet["entered_at"]


def test_recording_again_updates_the_line_and_keeps_the_first_entry_time(record_schema):
    first = record_store.record_bet_line("user-a", "790001", DAY, line_home=-135, line_away=120)

    second = record_store.record_bet_line("user-a", "790001", DAY, line_home=-140)

    assert second["id"] == first["id"]
    assert second["line_home"] == -140
    # A side that was not sent is left alone: a card with one price typed cannot wipe the other.
    assert second["line_away"] == 120
    assert second["created_at"] == first["created_at"]
    assert second["entered_at"] >= first["entered_at"]
    assert len(record_store.user_bets("user-a")) == 1


def test_lines_are_isolated_per_user(record_schema):
    record_store.record_bet_line("user-a", "790001", DAY, line_home=-135)
    record_store.record_bet_line("user-b", "790001", DAY, line_home=-150)

    assert [bet["line_home"] for bet in record_store.user_bets("user-a")] == [-135]
    assert [bet["line_home"] for bet in record_store.user_bets("user-b")] == [-150]
    assert record_store.user_bets("user-a", DAY)[0]["game_pk"] == "790001"
    assert record_store.user_bets("user-a", date(2026, 9, 3)) == []


def test_ensure_schema_creates_the_bets_table_idempotently(record_schema):
    """The fixture pre-creates the table; the boot migration must be able to as well, and
    running it twice must be a no-op (IF NOT EXISTS throughout, per the ledger rule)."""
    with record_schema() as connection:
        connection.execute("DROP TABLE moneyline_bets")
        connection.commit()

    assert record_store.ensure_schema() is True
    assert record_store.ensure_schema() is True
    assert record_store.user_bets("nobody") == []


# --- the route -------------------------------------------------------------------------


def _put(client: TestClient, game_pk: str, **body):
    return client.put(f"/api/bets/{game_pk}", json={"game_date": "2026-09-02", **body})


def test_route_records_the_line_for_the_signed_in_user(record_schema):
    with TestClient(main.app) as client:
        response = _put(client, "790001", line_home=-135, line_away=120)

    assert response.status_code == 200, response.text
    bet = response.json()["bet"]
    assert bet["user_id"] == "test-user"  # get_current_user's identity under pytest
    assert bet["line_home"] == -135
    assert bet["line_away"] == 120
    assert record_store.user_bets("test-user")[0]["game_pk"] == "790001"


def test_route_requires_a_signed_in_user(record_schema):
    async def nobody():
        raise main.MoneylineError("authentication_required", "Sign in to use this feature.", 401)

    main.app.dependency_overrides[main.get_current_user] = nobody
    try:
        with TestClient(main.app) as client:
            response = _put(client, "790001", line_home=-135)
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)

    assert response.status_code == 401
    assert record_store.user_bets("test-user") == []


def test_route_refuses_bad_lines_empty_payloads_and_bad_game_ids(record_schema):
    with TestClient(main.app) as client:
        assert _put(client, "790001", line_home=-50).status_code == 400
        assert _put(client, "790001", line_home=0).status_code == 400
        assert _put(client, "790001").status_code == 400
        assert _put(client, "not-a-game", line_home=-135).status_code == 400
    assert record_store.user_bets("test-user") == []


def test_route_says_so_when_the_record_store_is_down(monkeypatch):
    monkeypatch.setattr(main, "database_available", lambda: False)
    with TestClient(main.app) as client:
        response = _put(client, "790001", line_home=-135)
    assert response.status_code == 503


def test_the_models_record_is_byte_identical_after_a_user_records_a_line(record_schema, seed_pick):
    """The proof §4.2 asks for: the model's rows before and after are the same bytes, and the
    pick still grades at the −110 default rather than at anything a user typed."""
    seed_pick("790001", DAY, "NYY", "BOS", "BOS")
    before = (
        _rows(record_schema, "moneyline_slate_snapshots"),
        _rows(record_schema, "moneyline_record_picks"),
        record_store.pending_picks(),
    )

    with TestClient(main.app) as client:
        assert _put(client, "790001", line_home=-135, line_away=120).status_code == 200

    after = (
        _rows(record_schema, "moneyline_slate_snapshots"),
        _rows(record_schema, "moneyline_record_picks"),
        record_store.pending_picks(),
    )
    assert after == before
    assert after[1][0]["entered_line"] is None
    assert len(record_store.user_bets("test-user")) == 1


# --- clearing a line (Asher, 2026-09-02: an emptied input clears that side) --------------
#
# The store distinguishes absent from null: absent keeps the stored side (a card with one
# price typed cannot wipe the other), an explicit None clears it. A row whose sides are both
# cleared is deleted -- a cleared line is not a bet, and 1.5 must not grade the absence of one.


def test_clearing_one_side_keeps_the_other(record_schema):
    record_store.record_bet_line("user-a", "790001", DAY, line_home=-135, line_away=120)

    bet = record_store.record_bet_line("user-a", "790001", DAY, line_home=None)

    assert bet is not None
    assert bet["line_home"] is None
    assert bet["line_away"] == 120


def test_absent_sides_are_kept(record_schema):
    record_store.record_bet_line("user-a", "790001", DAY, line_home=-135, line_away=120)

    bet = record_store.record_bet_line("user-a", "790001", DAY, book="DK")

    assert bet["line_home"] == -135
    assert bet["line_away"] == 120
    assert bet["book"] == "DK"


def test_clearing_both_sides_deletes_the_row(record_schema):
    record_store.record_bet_line("user-a", "790001", DAY, line_home=-135, line_away=120, book="DK")

    bet = record_store.record_bet_line("user-a", "790001", DAY, line_home=None, line_away=None)

    assert bet is None
    assert record_store.user_bets("user-a") == []


def test_clearing_the_last_remaining_side_deletes_the_row(record_schema):
    record_store.record_bet_line("user-a", "790001", DAY, line_home=-135)

    assert record_store.record_bet_line("user-a", "790001", DAY, line_home=None) is None
    assert record_store.user_bets("user-a") == []


def test_route_null_clears_a_side_and_absent_keeps_it(record_schema):
    with TestClient(main.app) as client:
        assert _put(client, "790001", line_home=-135, line_away=120).status_code == 200

        cleared = _put(client, "790001", line_home=None)
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["bet"]["line_home"] is None
        assert cleared.json()["bet"]["line_away"] == 120

        kept = _put(client, "790001", line_home=-140)
        assert kept.json()["bet"]["line_home"] == -140
        assert kept.json()["bet"]["line_away"] == 120


def test_route_clearing_both_sides_reports_the_row_gone(record_schema):
    with TestClient(main.app) as client:
        _put(client, "790001", line_home=-135, line_away=120)
        response = _put(client, "790001", line_home=None, line_away=None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bet"] is None
    assert body["cleared"] is True
    assert record_store.user_bets("test-user") == []


def test_route_with_no_side_at_all_is_a_400(record_schema):
    with TestClient(main.app) as client:
        response = client.put("/api/bets/790001", json={"game_date": "2026-09-02"})
    assert response.status_code == 400
