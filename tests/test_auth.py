"""End-to-end contract tests for the MONEYLINE authentication surface.

Every test here is marked `auth_gate`, which switches off the conftest bypass
so the real app-level dependency runs. That is the point: these are the tests
that must fail if the gate is ever weakened.

They also stand in as the written contract for the frontend — each assertion
below pins a status code, an error code, or a response key the sign-in screen
is going to read.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import backend.auth_store as auth_store
import backend.main as main
from backend import auth as auth_lib
from backend import auth_routes, mailer, oauth

pytestmark = pytest.mark.auth_gate

PASSWORD = "Longenough-2026!"
OTHER_PASSWORD = "Adifferentone-2026!"


@pytest.fixture()
def client(auth_schema) -> TestClient:
    """A client with the gate live and isolated account tables behind it."""
    return TestClient(main.app)


def signup(client: TestClient, email: str = "desk@example.com", password: str = PASSWORD):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


# --------------------------------------------------------------------------
# Signup
# --------------------------------------------------------------------------
def test_signup_creates_account_and_session(client: TestClient) -> None:
    response = signup(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "desk@example.com"
    assert body["user"]["has_password"] is True
    assert body["user"]["google_linked"] is False
    # The forward-compatible entitlement boundary: present, neutral, inert.
    assert body["user"]["account"]["status"] == "active"
    assert body["user"]["account"]["entitlement"]["tier"] == "free"
    assert "expires_at" in body["session"]
    assert client.cookies.get(auth_lib.session_cookie_name())


def test_signup_never_stores_the_plaintext_password(client: TestClient, auth_schema) -> None:
    signup(client)
    with auth_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT email, password_hash FROM moneyline_users")
            row = cursor.fetchone()
    assert row["password_hash"] != PASSWORD
    assert PASSWORD not in row["password_hash"]
    assert row["password_hash"].startswith("$2")  # bcrypt, not a bare digest
    assert auth_lib.verify_password(PASSWORD, row["password_hash"])
    assert not auth_lib.verify_password(OTHER_PASSWORD, row["password_hash"])


def test_duplicate_email_is_refused_case_insensitively(client: TestClient) -> None:
    assert signup(client, "Desk@Example.com").status_code == 201
    duplicate = signup(client, "desk@example.com  ")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_taken"
    # No session is handed out on the refusal.
    assert duplicate.cookies.get(auth_lib.session_cookie_name()) is None


@pytest.mark.parametrize(
    "email,password",
    [
        ("not-an-email", PASSWORD),
        ("desk@example.com", "short1!"),
        ("desk@example.com", "allletterspassword"),
    ],
)
def test_signup_validation_errors(client: TestClient, email: str, password: str) -> None:
    response = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    # The rejection describes the rule, never the value the caller sent.
    assert password not in response.text


# --------------------------------------------------------------------------
# Login / logout / session
# --------------------------------------------------------------------------
def test_login_success_returns_account_summary(client: TestClient) -> None:
    signup(client)
    client.cookies.clear()
    response = client.post(
        "/api/auth/login", json={"email": "DESK@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "desk@example.com"
    assert client.cookies.get(auth_lib.session_cookie_name())


@pytest.mark.parametrize(
    "email,password",
    [("desk@example.com", OTHER_PASSWORD), ("nobody@example.com", PASSWORD)],
)
def test_login_failures_are_indistinguishable(
    client: TestClient, email: str, password: str
) -> None:
    """Wrong password and no-such-account must be the same answer.

    Any difference here — status, code, or message — turns login into an
    account-existence oracle.
    """
    signup(client)
    client.cookies.clear()
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_credentials",
            "message": auth_routes.GENERIC_CREDENTIALS_MESSAGE,
        }
    }


def test_logout_revokes_the_session_server_side(client: TestClient) -> None:
    signup(client)
    assert client.get("/api/auth/session").status_code == 200
    token = client.cookies.get(auth_lib.session_cookie_name())

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["authenticated"] is False

    # Not merely a cleared cookie: replaying the exact token is dead too.
    client.cookies.set(auth_lib.session_cookie_name(), token)
    assert client.get("/api/auth/session").status_code == 401
    assert client.get("/api/teams").json()["error"]["code"] == "auth_required"


def test_logout_without_a_session_is_a_no_op(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 200


def test_session_endpoint_is_401_when_signed_out(client: TestClient) -> None:
    response = client.get("/api/auth/session")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_expired_session_is_rejected(client: TestClient, auth_schema) -> None:
    signup(client)
    with auth_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE moneyline_auth_sessions SET expires_at = %s",
                (datetime.now(timezone.utc) - timedelta(minutes=1),),
            )
        connection.commit()
    assert client.get("/api/teams").status_code == 401


def test_revoked_session_is_rejected(client: TestClient, auth_schema) -> None:
    signup(client)
    with auth_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE moneyline_auth_sessions SET revoked_at = now()")
        connection.commit()
    assert client.get("/api/teams").status_code == 401


def test_forged_session_token_is_rejected(client: TestClient) -> None:
    client.cookies.set(auth_lib.session_cookie_name(), auth_lib.new_opaque_token())
    assert client.get("/api/teams").status_code == 401


def test_session_identifier_is_opaque_and_hashed_at_rest(
    client: TestClient, auth_schema
) -> None:
    signup(client, "opaque@example.com")
    token = client.cookies.get(auth_lib.session_cookie_name())
    # Not user data, not a JWT, not anything decodable back to the account.
    assert "opaque@example.com" not in token
    assert "." not in token and len(token) >= 32
    with auth_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT token_hash FROM moneyline_auth_sessions")
            stored = cursor.fetchone()["token_hash"]
    assert stored != token
    assert stored == auth_lib.token_fingerprint(token)


def test_login_rotates_the_session_identifier(client: TestClient, auth_schema) -> None:
    """Session fixation: a value present before authentication cannot survive it."""
    signup(client)
    planted = client.cookies.get(auth_lib.session_cookie_name())

    login = client.post(
        "/api/auth/login", json={"email": "desk@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    rotated = client.cookies.get(auth_lib.session_cookie_name())
    assert rotated != planted

    with auth_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT revoked_at FROM moneyline_auth_sessions WHERE token_hash = %s",
                (auth_lib.token_fingerprint(planted),),
            )
            assert cursor.fetchone()["revoked_at"] is not None


# --------------------------------------------------------------------------
# Cookie attributes
# --------------------------------------------------------------------------
def _session_cookie_header(response) -> str:
    for name, value in response.headers.raw:
        if name.decode().lower() == "set-cookie" and value.decode().startswith(
            auth_lib.session_cookie_name()
        ):
            return value.decode()
    raise AssertionError("no session cookie was set")


def test_cookie_security_attributes_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
    header = _session_cookie_header(signup(client))
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header
    assert "Max-Age=" in header


def test_cookie_is_not_secure_on_plain_http_dev(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local dev runs over http; a Secure cookie there would never be sent back."""
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
    header = _session_cookie_header(signup(client, "dev@example.com"))
    assert "HttpOnly" in header
    assert "Secure" not in header


def test_logout_clears_the_cookie(client: TestClient) -> None:
    signup(client)
    header = _session_cookie_header(client.post("/api/auth/logout"))
    assert "HttpOnly" in header
    assert "Path=/" in header
    assert 'Max-Age=0' in header or '=""' in header or "expires=" in header.lower()


# --------------------------------------------------------------------------
# The gate over the rest of the desk
# --------------------------------------------------------------------------
PROTECTED_PATHS = [
    "/api/teams",
    "/api/slate",
    "/api/record",
    "/api/track-record",
    "/api/screener",
    "/api/wire",
    "/api/season-sim",
    "/api/teams-live",
    "/api/players",
]


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_application_routes_require_a_session(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 401, path
    assert response.json() == {
        "error": {"code": "auth_required", "message": "Sign in to use the desk."}
    }


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/price", {"obp": 0.35, "slg": 0.43, "oobp": 0.31, "oslg": 0.38}),
        ("/api/parlay/price", {"legs": [{"gamePk": "1", "side": "home"}]}),
        ("/api/record/grade", None),
    ],
)
def test_post_routes_require_a_session_before_body_validation(
    client: TestClient, path: str, payload
) -> None:
    """The gate runs first: an invalid body from a stranger is still a 401.

    A 400 here would confirm the route exists and hand out its validation rules
    to an unauthenticated caller.
    """
    response = client.post(path, json=payload)
    assert response.status_code == 401, path
    assert response.json()["error"]["code"] == "auth_required"


def test_health_stays_public(client: TestClient) -> None:
    """The deployment startup probe has no credentials to present."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "model_version" in response.json()


def test_unknown_api_route_is_still_gated(client: TestClient) -> None:
    """Even a 404 is application information; a stranger gets the gate instead."""
    assert client.get("/api/does-not-exist").status_code == 401


def test_public_allowlist_is_only_the_bootstrap_surface() -> None:
    assert auth_lib.PUBLIC_API_PATHS == frozenset(
        {
            "/api/health",
            "/api/auth/session",
            "/api/auth/signup",
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/google/start",
            "/api/auth/google/callback",
            "/api/auth/password-reset/request",
            "/api/auth/password-reset/complete",
        }
    )


def test_spa_shell_stays_reachable_for_signed_out_browsers() -> None:
    """The sign-in screen has to render. No application data crosses here."""
    assert auth_lib.is_public_path("/") is True
    assert auth_lib.is_public_path("/research/players") is True
    assert auth_lib.is_public_path("/assets/index-abc123.js") is True
    assert auth_lib.is_public_path("/api/slate") is False
    assert auth_lib.is_public_path("/api/auth/google/link") is False


def test_authenticated_session_reaches_a_protected_route(client: TestClient) -> None:
    signup(client)
    response = client.get("/api/teams")
    assert response.status_code == 200
    assert "teams" in response.json()


# --------------------------------------------------------------------------
# Fail-closed
# --------------------------------------------------------------------------
def test_unreachable_database_fails_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client)

    def explode(*_args, **_kwargs):
        raise auth_store.AuthStoreUnavailable("simulated outage")

    monkeypatch.setattr(auth_store, "_connection", explode)
    response = client.get("/api/teams")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_unavailable"


# --------------------------------------------------------------------------
# Password reset
# --------------------------------------------------------------------------
@pytest.fixture()
def captured_reset(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []

    async def fake_send(to_email: str, reset_url: str) -> bool:
        sent.append((to_email, reset_url))
        return True

    monkeypatch.setattr(mailer, "send_password_reset", fake_send)
    return sent


def _token_from(reset_url: str) -> str:
    from urllib.parse import parse_qs, urlsplit

    return parse_qs(urlsplit(reset_url).query)["token"][0]


def test_reset_request_answer_is_identical_for_unknown_addresses(
    client: TestClient, captured_reset
) -> None:
    signup(client)
    client.cookies.clear()

    known = client.post(
        "/api/auth/password-reset/request", json={"email": "desk@example.com"}
    )
    unknown = client.post(
        "/api/auth/password-reset/request", json={"email": "nobody@example.com"}
    )
    malformed = client.post(
        "/api/auth/password-reset/request", json={"email": "not-an-email"}
    )

    assert known.status_code == unknown.status_code == malformed.status_code == 202
    assert known.json() == unknown.json() == malformed.json()
    assert known.json()["message"] == auth_routes.GENERIC_RESET_MESSAGE
    # Only the real account actually gets mail.
    assert [address for address, _ in captured_reset] == ["desk@example.com"]


def test_reset_token_is_never_in_the_response_body(
    client: TestClient, captured_reset
) -> None:
    signup(client)
    response = client.post(
        "/api/auth/password-reset/request", json={"email": "desk@example.com"}
    )
    token = _token_from(captured_reset[0][1])
    assert token not in response.text
    assert "token" not in response.json()


def test_reset_token_is_hashed_at_rest(
    client: TestClient, captured_reset, auth_schema
) -> None:
    signup(client)
    client.post("/api/auth/password-reset/request", json={"email": "desk@example.com"})
    token = _token_from(captured_reset[0][1])
    with auth_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT token_hash FROM moneyline_password_resets")
            stored = cursor.fetchone()["token_hash"]
    assert stored != token
    assert stored == auth_lib.token_fingerprint(token)


def test_reset_completes_and_revokes_existing_sessions(
    client: TestClient, captured_reset
) -> None:
    signup(client)
    old_session = client.cookies.get(auth_lib.session_cookie_name())
    client.post("/api/auth/password-reset/request", json={"email": "desk@example.com"})
    token = _token_from(captured_reset[0][1])

    completed = client.post(
        "/api/auth/password-reset/complete",
        json={"token": token, "password": OTHER_PASSWORD},
    )
    assert completed.status_code == 200

    # The session that existed before the reset does not survive it.
    client.cookies.set(auth_lib.session_cookie_name(), old_session)
    assert client.get("/api/auth/session").status_code == 401

    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/login", json={"email": "desk@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "desk@example.com", "password": OTHER_PASSWORD},
        ).status_code
        == 200
    )


def test_reset_token_is_single_use(client: TestClient, captured_reset) -> None:
    signup(client)
    client.post("/api/auth/password-reset/request", json={"email": "desk@example.com"})
    token = _token_from(captured_reset[0][1])
    body = {"token": token, "password": OTHER_PASSWORD}

    assert client.post("/api/auth/password-reset/complete", json=body).status_code == 200
    replay = client.post("/api/auth/password-reset/complete", json=body)
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "reset_invalid"


def test_expired_reset_token_reports_reset_expired(
    client: TestClient, captured_reset, auth_schema
) -> None:
    signup(client)
    client.post("/api/auth/password-reset/request", json={"email": "desk@example.com"})
    token = _token_from(captured_reset[0][1])
    with auth_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE moneyline_password_resets SET expires_at = %s",
                (datetime.now(timezone.utc) - timedelta(minutes=1),),
            )
        connection.commit()

    response = client.post(
        "/api/auth/password-reset/complete",
        json={"token": token, "password": OTHER_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "reset_expired"


def test_unknown_reset_token_reports_reset_invalid(client: TestClient) -> None:
    response = client.post(
        "/api/auth/password-reset/complete",
        json={"token": auth_lib.new_opaque_token(), "password": OTHER_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "reset_invalid"


def test_requesting_a_second_link_burns_the_first(
    client: TestClient, captured_reset
) -> None:
    signup(client)
    client.post("/api/auth/password-reset/request", json={"email": "desk@example.com"})
    client.post("/api/auth/password-reset/request", json={"email": "desk@example.com"})
    first, second = (_token_from(url) for _, url in captured_reset)

    stale = client.post(
        "/api/auth/password-reset/complete",
        json={"token": first, "password": OTHER_PASSWORD},
    )
    assert stale.status_code == 400
    assert stale.json()["error"]["code"] == "reset_invalid"
    assert (
        client.post(
            "/api/auth/password-reset/complete",
            json={"token": second, "password": OTHER_PASSWORD},
        ).status_code
        == 200
    )


def test_reset_rejects_a_weak_new_password(client: TestClient, captured_reset) -> None:
    signup(client)
    client.post("/api/auth/password-reset/request", json={"email": "desk@example.com"})
    token = _token_from(captured_reset[0][1])
    response = client.post(
        "/api/auth/password-reset/complete", json={"token": token, "password": "short"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


# --------------------------------------------------------------------------
# Google OAuth
# --------------------------------------------------------------------------
@pytest.fixture()
def google_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI", "https://desk.example.com/api/auth/google/callback"
    )
    monkeypatch.setenv("AUTH_APP_ORIGIN", "https://desk.example.com")


def _stub_google(monkeypatch: pytest.MonkeyPatch, identity: dict) -> None:
    async def fake_exchange(_code: str) -> dict:
        return {"access_token": "stub-access-token"}

    async def fake_identity(_token: str) -> dict:
        return identity

    monkeypatch.setattr(oauth, "exchange_code", fake_exchange)
    monkeypatch.setattr(oauth, "fetch_identity", fake_identity)


def test_google_start_redirects_without_leaking_the_secret(
    client: TestClient, google_env
) -> None:
    response = client.get("/api/auth/google/start", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=test-client-id" in location
    assert "state=" in location
    # The client secret is a server-side credential and must never reach a
    # browser, including via a redirect the browser follows.
    assert "test-client-secret" not in location


def test_google_start_is_unavailable_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URI",
    ):
        monkeypatch.delenv(name, raising=False)
    response = client.get("/api/auth/google/start", follow_redirects=False)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_unavailable"


def _start_and_capture_state(client: TestClient) -> str:
    from urllib.parse import parse_qs, urlsplit

    location = client.get("/api/auth/google/start", follow_redirects=False).headers[
        "location"
    ]
    return parse_qs(urlsplit(location).query)["state"][0]


def test_google_callback_creates_an_account_and_a_session(
    client: TestClient, google_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _start_and_capture_state(client)
    _stub_google(
        monkeypatch,
        {"subject": "google-sub-1", "email": "google@example.com", "name": "Desk"},
    )
    response = client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("https://desk.example.com/")
    assert client.cookies.get(auth_lib.session_cookie_name())

    session = client.get("/api/auth/session").json()
    assert session["user"]["email"] == "google@example.com"
    assert session["user"]["google_linked"] is True
    assert session["user"]["has_password"] is False


def test_google_callback_rejects_an_unknown_state(
    client: TestClient, google_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_google(
        monkeypatch, {"subject": "google-sub-1", "email": "google@example.com", "name": None}
    )
    response = client.get(
        f"/api/auth/google/callback?code=abc&state={auth_lib.new_opaque_token()}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=oauth_failed" in response.headers["location"]
    assert client.cookies.get(auth_lib.session_cookie_name()) is None


def test_google_state_is_single_use(
    client: TestClient, google_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _start_and_capture_state(client)
    _stub_google(
        monkeypatch, {"subject": "google-sub-1", "email": "google@example.com", "name": None}
    )
    assert (
        client.get(
            f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
        ).status_code
        == 303
    )
    client.cookies.clear()
    replay = client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert "error=oauth_failed" in replay.headers["location"]
    assert client.cookies.get(auth_lib.session_cookie_name()) is None


def test_cancelled_google_callback_returns_to_sign_in(
    client: TestClient, google_env
) -> None:
    response = client.get(
        "/api/auth/google/callback?error=access_denied&state=whatever",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=oauth_failed" in response.headers["location"]
    assert client.cookies.get(auth_lib.session_cookie_name()) is None


def test_failed_token_exchange_returns_to_sign_in(
    client: TestClient, google_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _start_and_capture_state(client)

    async def failing_exchange(_code: str) -> dict:
        raise auth_routes.MoneylineError(
            auth_lib.OAUTH_FAILED, "Google sign-in could not be completed.", 400
        )

    monkeypatch.setattr(oauth, "exchange_code", failing_exchange)
    response = client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=oauth_failed" in response.headers["location"]
    assert client.cookies.get(auth_lib.session_cookie_name()) is None


def test_unverified_google_email_is_refused(
    client: TestClient, google_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _start_and_capture_state(client)

    async def fake_exchange(_code: str) -> dict:
        return {"access_token": "stub"}

    monkeypatch.setattr(oauth, "exchange_code", fake_exchange)
    # fetch_identity is the real one; it is what enforces email_verified.
    import httpx

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"sub": "s", "email": "x@example.com", "email_verified": False}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    response = client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert "error=oauth_failed" in response.headers["location"]


def test_google_will_not_take_over_a_password_account(
    client: TestClient, google_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The linking rule: a Google address matching a password account is refused.

    Auto-linking here would mean anyone able to obtain that Google address
    inherits the MONEYLINE account without ever knowing its password.
    """
    signup(client, "shared@example.com")
    client.cookies.clear()

    state = _start_and_capture_state(client)
    _stub_google(
        monkeypatch,
        {"subject": "google-sub-2", "email": "shared@example.com", "name": None},
    )
    response = client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=oauth_link_required" in response.headers["location"]
    assert client.cookies.get(auth_lib.session_cookie_name()) is None


def test_returning_google_user_reuses_the_same_account(
    client: TestClient, google_env, monkeypatch: pytest.MonkeyPatch, auth_schema
) -> None:
    identity = {"subject": "google-sub-3", "email": "repeat@example.com", "name": None}
    for _ in range(2):
        state = _start_and_capture_state(client)
        _stub_google(monkeypatch, identity)
        client.get(
            f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
        )
        client.cookies.clear()
    with auth_schema() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS n FROM moneyline_users")
            assert cursor.fetchone()["n"] == 1


def test_google_link_requires_a_session(client: TestClient, google_env) -> None:
    assert client.post("/api/auth/google/link").status_code == 401


def test_google_link_is_available_to_a_signed_in_account(
    client: TestClient, google_env
) -> None:
    signup(client, "linker@example.com")
    response = client.post("/api/auth/google/link")
    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?"
    )


# --------------------------------------------------------------------------
# Redirect and CORS safety
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "candidate",
    ["https://evil.example/steal", "//evil.example", "/\\evil.example", "javascript:alert(1)"],
)
def test_unsafe_redirect_targets_fall_back_to_the_app_origin(
    monkeypatch: pytest.MonkeyPatch, candidate: str
) -> None:
    monkeypatch.setenv("AUTH_APP_ORIGIN", "https://desk.example.com")
    monkeypatch.delenv("AUTH_ALLOWED_REDIRECT_ORIGINS", raising=False)
    assert auth_lib.safe_redirect_target(candidate) == "https://desk.example.com/"


def test_configured_redirect_origins_are_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_APP_ORIGIN", "https://desk.example.com")
    monkeypatch.setenv("AUTH_ALLOWED_REDIRECT_ORIGINS", "https://staging.example.com")
    assert (
        auth_lib.safe_redirect_target("https://staging.example.com/today")
        == "https://staging.example.com/today"
    )
    assert (
        auth_lib.safe_redirect_target("/research/players")
        == "https://desk.example.com/research/players"
    )


def test_cors_never_uses_a_wildcard_with_credentials() -> None:
    for middleware in main.app.user_middleware:
        options = getattr(middleware, "kwargs", {})
        if "allow_credentials" in options:
            assert options["allow_credentials"] is True
            assert "*" not in options["allow_origins"]
            assert options["allow_origins"], "credentialed CORS needs concrete origins"
            break
    else:  # pragma: no cover - the middleware is configured in backend.main
        pytest.fail("CORS middleware is not configured")


def test_preflight_succeeds_for_a_configured_dev_origin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = auth_lib.dev_cors_origins()[0]
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_preflight_is_refused_for_an_unlisted_origin(client: TestClient) -> None:
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------
def test_login_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("AUTH_RATE_LIMIT_LOGIN_MAX", "3")
    monkeypatch.setenv("AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    auth_lib.reset_rate_limits()
    try:
        body = {"email": "desk@example.com", "password": OTHER_PASSWORD}
        codes = [
            client.post("/api/auth/login", json=body).status_code for _ in range(5)
        ]
        assert codes[-1] == 429
        assert client.post("/api/auth/login", json=body).json()["error"][
            "code"
        ] == "rate_limited"
    finally:
        auth_lib.reset_rate_limits()


def test_password_reset_requests_are_rate_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, captured_reset
) -> None:
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("AUTH_RATE_LIMIT_RESET_REQUEST_MAX", "2")
    monkeypatch.setenv("AUTH_RATE_LIMIT_RESET_REQUEST_WINDOW_SECONDS", "60")
    auth_lib.reset_rate_limits()
    try:
        body = {"email": "desk@example.com"}
        client.post("/api/auth/password-reset/request", json=body)
        client.post("/api/auth/password-reset/request", json=body)
        throttled = client.post("/api/auth/password-reset/request", json=body)
        assert throttled.status_code == 429
    finally:
        auth_lib.reset_rate_limits()
