"""Security contracts for private paper parlay records."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.main import ParlayInput
from backend.record_store import store_parlay_slip


def _payload(book_odds: int | None = None) -> dict:
    payload = {
        "legs": [
            {"gamePk": "990001", "side": "home"},
            {"gamePk": "990002", "side": "away"},
        ]
    }
    if book_odds is not None:
        payload["book_odds"] = book_odds
    return payload

def test_parlay_log_requires_a_configured_desk_actor(monkeypatch):
    """A paying subscriber cannot claim the application-wide slip."""
    monkeypatch.setenv("MONEYLINE_DESK_USER_IDS", "desk-user")
    main.app.dependency_overrides[main.get_current_user] = lambda: {"id": "reader"}
    try:
        with TestClient(main.app) as client:
            response = client.post("/api/parlay/log", json=_payload())
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "desk_authorization_required"


def test_parlay_log_scopes_the_slip_to_the_authenticated_user(monkeypatch):
    """Request data cannot choose which user's private record is written."""
    stored_args: list[tuple] = []

    main.app.dependency_overrides[main.get_current_user] = lambda: {"id": "reader"}
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(
        main,
        "_resolve_parlay_legs",
        AsyncMock(
            return_value=[
                {"game_pk": "990001", "game_date": "2026-08-24", "team": "NYY", "side": "home", "probability": 0.56},
                {"game_pk": "990002", "game_date": "2026-08-24", "team": "BOS", "side": "away", "probability": 0.55},
            ]
        ),
    )

    def capture_store(*args):
        stored_args.append(args)
        return {"stored": True, "already_logged": False, "slip_id": 1}

    monkeypatch.setattr(main, "store_parlay_slip", capture_store)
    try:
        with TestClient(main.app) as client:
            response = client.post("/api/parlay/log", json=_payload(book_odds=1000))
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)

    assert response.status_code == 200
    assert stored_args and stored_args[0][-1] == "reader"
    assert response.json()["priced"]["book"]["book_odds"] == 1000


@pytest.mark.parametrize("book_odds", [-10001, 10001, 2147483647])
def test_parlay_pricing_rejects_unbounded_american_odds(book_odds):
    with pytest.raises(ValueError, match="(greater|less) than or equal"):
        ParlayInput.model_validate(_payload(book_odds=book_odds))


@pytest.mark.parametrize("book_line", [-10001, 10001])
def test_store_parlay_slip_rejects_out_of_range_book_lines(record_schema, book_line):
    with pytest.raises(ValueError, match="between"):
        store_parlay_slip(
            slip_date="2026-08-24",
            legs=[{"game_pk": "990001", "team": "NYY", "side": "home"}],
            combined_probability=0.33,
            fair_line=260,
            book_line=book_line,
        )

def test_desk_actor_log_never_persists_caller_book_odds(monkeypatch):
    """A configured desk account cannot set settlement from request odds."""
    stored_args: list[tuple] = []

    monkeypatch.setenv("MONEYLINE_DESK_USER_IDS", "desk-user")
    main.app.dependency_overrides[main.get_current_user] = lambda: {"id": "desk-user"}
    monkeypatch.setattr(main, "database_available", lambda: True)
    monkeypatch.setattr(
        main,
        "_resolve_parlay_legs",
        AsyncMock(
            return_value=[
                {"game_pk": "990001", "game_date": "2026-08-24", "team": "NYY", "side": "home", "probability": 0.56},
                {"game_pk": "990002", "game_date": "2026-08-24", "team": "BOS", "side": "away", "probability": 0.55},
            ]
        ),
    )

    def capture_store(*args):
        stored_args.append(args)
        return {"stored": True, "already_logged": False, "slip_id": 1}

    monkeypatch.setattr(main, "store_parlay_slip", capture_store)
    try:
        with TestClient(main.app) as client:
            response = client.post("/api/parlay/log", json=_payload(book_odds=1000))
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)

    assert response.status_code == 200
    assert stored_args and stored_args[0][-1] is None
    assert response.json()["priced"]["book"] is None

def test_parlay_log_fails_closed_without_a_desk_allowlist(monkeypatch):
    monkeypatch.delenv("MONEYLINE_DESK_USER_IDS", raising=False)
    main.app.dependency_overrides[main.get_current_user] = lambda: {"id": "desk-user"}
    try:
        with TestClient(main.app) as client:
            response = client.post("/api/parlay/log", json=_payload())
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "desk_authorization_required"
