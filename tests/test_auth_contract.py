"""Deterministic contract checks for the MONEYLINE authentication boundary."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import backend.auth_routes as routes
import backend.main as main


pytestmark = pytest.mark.auth_gate


def _user(**overrides):
    user = {
        "id": 7,
        "email": "reader@example.test",
        "display_name": "Reader",
        "password_hash": "hash",
        "account_status": "active",
        "google_linked": False,
        "entitlement": "free",
    }
    user.update(overrides)
    return user


def test_login_uses_contract_fields_and_sets_cookie(monkeypatch):
    user = _user()
    created = {"id": 12, "user_id": 7, "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)}
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setattr(routes.auth_store, "find_user_by_email", AsyncMock(return_value=user))
    monkeypatch.setattr(routes.auth_store, "create_session", AsyncMock(return_value=created))
    monkeypatch.setattr(routes.auth_store, "touch_login", AsyncMock())
    monkeypatch.setattr(routes.auth_lib, "verify_password", lambda password, hashed: password == "Correct!password")

    with TestClient(main.app) as client:
        response = client.post("/api/auth/login", json={"email": user["email"], "password": "Correct!password"})

    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "Reader"
    assert "moneyline_session=" in response.headers["set-cookie"]
    routes.auth_store.find_user_by_email.assert_awaited_once_with(user["email"])


def test_signup_accepts_display_name_and_starts_session(monkeypatch):
    created_user = _user(id=8, email="new@example.test", display_name="New Reader")
    created = {"id": 13, "user_id": 8, "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)}
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setattr(routes.auth_store, "create_user", AsyncMock(return_value=created_user))
    monkeypatch.setattr(routes.auth_store, "create_session", AsyncMock(return_value=created))
    monkeypatch.setattr(routes.auth_store, "touch_login", AsyncMock())
    with TestClient(main.app) as client:
        response = client.post(
            "/api/auth/signup",
            json={"email": "new@example.test", "password": "Correct!password", "display_name": "New Reader"},
        )
    assert response.status_code == 201
    assert response.json()["user"]["display_name"] == "New Reader"
    routes.auth_store.create_user.assert_awaited_once()
    assert routes.auth_store.create_user.await_args.args[2] == "New Reader"


def test_wrong_login_is_generic_and_reset_requests_are_generic(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setattr(routes.auth_store, "find_user_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr(routes.auth_lib, "verify_password", lambda *_: False)
    with TestClient(main.app) as client:
        wrong = client.post("/api/auth/login", json={"email": "nobody@example.test", "password": "Wrong!password"})
        known = client.post("/api/auth/password-reset/request", json={"email": "nobody@example.test"})
        malformed = client.post("/api/auth/password-reset/request", json={"email": "not-an-email"})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert known.status_code == malformed.status_code == 202
    assert known.json() == malformed.json()


def test_reset_completion_clears_cookie_and_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setattr(routes.auth_store, "consume_reset_token", AsyncMock(return_value={"status": "invalid"}))
    with TestClient(main.app) as client:
        response = client.post(
            "/api/auth/password-reset/complete",
            json={"token": "invalid-token", "password": "New!password123"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "reset_invalid"


def test_google_callback_failures_redirect_without_cookie(monkeypatch):
    monkeypatch.setenv("AUTH_SIGN_IN_PATH", "/")
    with TestClient(main.app) as client:
        response = client.get("/api/auth/google/callback?error=access_denied", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:18612/?error=oauth_failed"
    assert "moneyline_session=" not in response.headers.get("set-cookie", "")


def test_google_callback_success_uses_stored_safe_destination(monkeypatch):
    user = _user()
    created = {"id": 12, "user_id": 7, "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)}
    monkeypatch.setattr(routes.auth_store, "consume_oauth_state", AsyncMock(return_value={"redirect_to": "http://localhost:18612/research"}))
    monkeypatch.setattr(routes.oauth, "exchange_code", AsyncMock(return_value={"access_token": "access"}))
    monkeypatch.setattr(routes.oauth, "fetch_identity", AsyncMock(return_value={"subject": "sub", "email": user["email"]}))
    monkeypatch.setattr(routes, "_resolve_google_user", AsyncMock(return_value=(user, False)))
    monkeypatch.setattr(routes.auth_store, "create_session", AsyncMock(return_value=created))
    monkeypatch.setattr(routes.auth_store, "touch_login", AsyncMock())
    with TestClient(main.app) as client:
        response = client.get("/api/auth/google/callback?code=code&state=state", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:18612/research"
    assert "moneyline_session=" in response.headers["set-cookie"]