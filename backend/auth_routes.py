"""The `/api/auth/*` surface the frontend consumes.

Response shapes, in one place so the frontend contract is readable without
reading the handlers:

  Session-establishing routes (signup, login, session) return
    {"authenticated": true,
     "user": {"id", "email", "display_name", "created_at", "has_password",
              "google_linked",
              "account": {"status",
                          "entitlement": {"tier", "source", "expires_at"}}},
     "session": {"expires_at"}}

  Every failure returns the app-wide envelope
    {"error": {"code", "message"}}
  with a stable code from `backend.auth`: auth_required, invalid_credentials,
  validation_error, email_taken, reset_invalid, reset_expired, oauth_failed,
  oauth_link_required, auth_unavailable, rate_limited.

The entitlement block is deliberately inert: a tier name and its provenance so
the frontend can branch on it later. Nothing here bills, checks out, or gates.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from backend import auth as auth_lib
from backend import auth_store, mailer, oauth
from backend.errors import MoneylineError

logger = logging.getLogger("moneyline.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_RESET_MESSAGE = (
    "If that address has a MONEYLINE account, a reset link is on its way."
)
GENERIC_CREDENTIALS_MESSAGE = "That email and password combination is not valid."


class SignupInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=4096)
    display_name: str | None = Field(default=None, max_length=120)


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=4096)


class ResetRequestInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetCompleteInput(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    password: str = Field(min_length=1, max_length=4096)


def _unavailable() -> MoneylineError:
    return MoneylineError(
        auth_lib.AUTH_UNAVAILABLE,
        "Accounts are unavailable right now. Try again shortly.",
        503,
    )


def _throttle(request: Request, bucket: str, default_limit: int, default_window: int) -> None:
    limit, window = auth_lib.rate_limit_config(bucket.upper(), default_limit, default_window)
    auth_lib.enforce_rate_limit(bucket, auth_lib.client_fingerprint(request), limit, window)


def _throttle_identity(bucket: str, email: str, default_limit: int, default_window: int) -> None:
    """Second window keyed on the account, so one address cannot be ground down
    from many IPs. The key is hashed, so the throttle state holds no addresses."""
    limit, window = auth_lib.rate_limit_config(
        f"{bucket.upper()}_IDENTITY", default_limit, default_window
    )
    key = auth_lib.token_fingerprint(auth_lib.normalize_email(email))
    auth_lib.enforce_rate_limit(f"{bucket}:identity", key, limit, window)


async def _start_session(
    request: Request, user: dict[str, Any]
) -> tuple[dict[str, Any], str, Any]:
    """Mint a brand-new opaque session; returns (body, cookie token, expiry).

    Session fixation defence: the identifier is generated here, after the
    credential check, and any session the caller arrived holding is revoked
    first. A value an attacker planted in the browser can never survive a
    successful authentication.
    """
    incoming = auth_lib.read_session_cookie(request)
    if incoming:
        try:
            await auth_store.revoke_session(incoming)
        except auth_store.AuthStoreUnavailable:
            raise _unavailable() from None
    token = auth_lib.new_opaque_token()
    try:
        session = await auth_store.create_session(
            int(user["id"]),
            token,
            auth_lib.session_ttl(),
            user_agent=request.headers.get("user-agent"),
            ip_address=auth_lib.client_fingerprint(request),
        )
        await auth_store.touch_login(int(user["id"]))
    except auth_store.AuthStoreUnavailable:
        raise _unavailable() from None
    return auth_lib.session_payload(user, session), token, session["expires_at"]


@router.get("/session")
async def read_session(request: Request) -> JSONResponse:
    """Authenticated: the account summary. Unauthenticated: a 401 auth_required.

    Reached before the gate resolves anything (this path is on the public
    allow-list, since a signed-out browser has to be able to ask), so it does
    its own resolution.
    """
    token = auth_lib.read_session_cookie(request)
    if not token:
        raise MoneylineError(auth_lib.AUTH_REQUIRED, "Sign in to use the desk.", 401)
    try:
        resolved = await auth_store.resolve_session(token)
    except auth_store.AuthStoreUnavailable:
        raise _unavailable() from None
    if resolved is None:
        raise MoneylineError(auth_lib.AUTH_REQUIRED, "Sign in to use the desk.", 401)
    return JSONResponse(auth_lib.session_payload(resolved["user"], resolved["session"]))


@router.post("/signup")
async def signup(request: Request, payload: SignupInput) -> JSONResponse:
    _throttle(request, "signup", 10, 3600)
    email = auth_lib.validate_email(payload.email)
    auth_lib.validate_password(payload.password)
    _throttle_identity("signup", email, 5, 3600)
    password_hash = auth_lib.hash_password(payload.password)
    try:
        user = await auth_store.create_user(
            email, password_hash, (payload.display_name or "").strip() or None
        )
    except auth_store.AuthStoreUnavailable:
        raise _unavailable() from None
    if user is None:
        # Signup cannot avoid revealing that an address is unusable — that is
        # inherent to unique accounts — but the wording stops short of
        # confirming an account exists.
        raise MoneylineError(
            auth_lib.EMAIL_TAKEN,
            "That email cannot be used to create a new account.",
            409,
        )
    body, token, expires_at = await _start_session(request, user)
    response = JSONResponse(status_code=201, content=body)
    auth_lib.set_session_cookie(response, token, expires_at)
    return response


@router.post("/login")
async def login(request: Request, payload: LoginInput) -> JSONResponse:
    _throttle(request, "login", 20, 900)
    _throttle_identity("login", payload.email, 10, 900)
    try:
        user = await auth_store.find_user_by_email(payload.email)
    except auth_store.AuthStoreUnavailable:
        raise _unavailable() from None
    password_ok = auth_lib.verify_password(
        payload.password, user.get("password_hash") if user else None
    )
    # One message and one status for "no such account", "wrong password", and
    # "Google-only account": an attacker learns nothing about which it was.
    if user is None or not password_ok or user.get("account_status") != "active":
        raise MoneylineError(
            auth_lib.INVALID_CREDENTIALS, GENERIC_CREDENTIALS_MESSAGE, 401
        )
    body, token, expires_at = await _start_session(request, user)
    response = JSONResponse(content=body)
    auth_lib.set_session_cookie(response, token, expires_at)
    return response


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Idempotent: signing out twice, or with no session, is a 200 either way."""
    token = auth_lib.read_session_cookie(request)
    if token:
        try:
            await auth_store.revoke_session(token)
        except auth_store.AuthStoreUnavailable:
            # The cookie still gets cleared; a revoke we could not record is
            # not a reason to leave the browser holding a session.
            logger.warning("logout_revoke_failed reason=auth_store_unavailable")
    response = JSONResponse(content={"ok": True, "authenticated": False})
    auth_lib.clear_session_cookie(response)
    return response


@router.get("/google/start")
async def google_start(request: Request, next: str | None = None) -> RedirectResponse:
    _throttle(request, "oauth_start", 30, 900)
    if not oauth.is_configured():
        raise MoneylineError(
            auth_lib.AUTH_UNAVAILABLE,
            "Google sign-in is not configured on this deployment.",
            503,
        )
    state = auth_lib.new_opaque_token()
    destination = auth_lib.safe_redirect_target(next, _post_login_path())
    try:
        await auth_store.create_oauth_state(state, oauth.STATE_TTL, destination)
    except auth_store.AuthStoreUnavailable:
        raise _unavailable() from None
    return RedirectResponse(oauth.authorization_url(state), status_code=307)


def _post_login_path() -> str:
    return os.getenv("AUTH_POST_LOGIN_PATH") or "/"


def _sign_in_redirect(error_code: str) -> str:
    """Bounce a failed callback back to the frontend's sign-in screen.

    Only the stable error code travels in the query string — never a Google
    message, a token, or an email.
    """
    path = os.getenv("AUTH_SIGN_IN_PATH") or "/sign-in"
    base = auth_lib.safe_redirect_target(path, path)
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'error': error_code})}"


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    """Validate state, exchange the code, then link or create — and only then
    establish a session. A cancelled or malformed callback redirects to the
    sign-in screen with a code; it never 500s and never sets a cookie.
    """
    if error or not code or not state:
        # `error=access_denied` is the user pressing Cancel — not a failure to
        # shout about, just a return trip to the sign-in screen.
        return RedirectResponse(_sign_in_redirect(auth_lib.OAUTH_FAILED), status_code=303)
    try:
        state_row = await auth_store.consume_oauth_state(state)
    except auth_store.AuthStoreUnavailable:
        return RedirectResponse(
            _sign_in_redirect(auth_lib.AUTH_UNAVAILABLE), status_code=303
        )
    if state_row is None:
        # Unknown, expired, or already-used state: a forged or replayed
        # callback. Stop before spending the code.
        logger.warning("google_callback_state_rejected")
        return RedirectResponse(_sign_in_redirect(auth_lib.OAUTH_FAILED), status_code=303)

    try:
        tokens = await oauth.exchange_code(code)
        access_token = tokens.get("access_token")
        if not access_token:
            raise MoneylineError(
                auth_lib.OAUTH_FAILED, "Google sign-in could not be completed.", 400
            )
        identity = await oauth.fetch_identity(access_token)
    except MoneylineError as failure:
        return RedirectResponse(_sign_in_redirect(failure.code), status_code=303)
    except Exception:
        logger.warning("google_callback_failed", exc_info=True)
        return RedirectResponse(_sign_in_redirect(auth_lib.OAUTH_FAILED), status_code=303)

    try:
        user, link_blocked = await _resolve_google_user(identity)
    except auth_store.AuthStoreUnavailable:
        return RedirectResponse(
            _sign_in_redirect(auth_lib.AUTH_UNAVAILABLE), status_code=303
        )
    if link_blocked:
        return RedirectResponse(
            _sign_in_redirect(auth_lib.OAUTH_LINK_REQUIRED), status_code=303
        )
    if user is None or user.get("account_status") != "active":
        return RedirectResponse(_sign_in_redirect(auth_lib.OAUTH_FAILED), status_code=303)

    destination = auth_lib.safe_redirect_target(
        state_row.get("redirect_to"), _post_login_path()
    )
    _, token, expires_at = await _start_session(request, user)
    response = RedirectResponse(destination, status_code=303)
    auth_lib.set_session_cookie(response, token, expires_at)
    return response


async def _resolve_google_user(
    identity: dict[str, Any]
) -> tuple[dict[str, Any] | None, bool]:
    """The account-linking rule, in one place.

    1. Known Google subject -> that account. The subject, not the email, is the
       durable identity; Google addresses can be renamed.
    2. No such subject, and no local account on the verified email -> create a
       Google-only account.
    3. No such subject, but the verified email matches an account that has NO
       password and no other Google identity -> link. That account could only
       have been created by this same flow, so linking takes nothing over.
    4. No such subject, and the email matches an account WITH a password ->
       refuse (`oauth_link_required`). Silently attaching Google to a
       password account would let anyone who can obtain that Google address
       inherit the account. The owner links it deliberately instead, from a
       signed-in session, via POST /api/auth/google/link.
    """
    existing = await auth_store.find_user_by_google_subject(identity["subject"])
    if existing is not None:
        return existing, False

    local = await auth_store.find_user_by_email(identity["email"])
    if local is None:
        created = await auth_store.create_user(
            identity["email"], None, identity.get("name")
        )
        if created is None:
            # Lost a race with a concurrent signup on the same address; re-read
            # and fall through to the linking rules.
            local = await auth_store.find_user_by_email(identity["email"])
        else:
            await auth_store.link_google_identity(
                int(created["id"]), identity["subject"], identity["email"]
            )
            return await auth_store.get_user_by_id(int(created["id"])), False

    if local is None:
        return None, False
    if local.get("password_hash") or local.get("google_linked"):
        logger.info("google_link_refused reason=existing_local_account")
        return None, True
    linked = await auth_store.link_google_identity(
        int(local["id"]), identity["subject"], identity["email"]
    )
    if not linked:
        return None, True
    return await auth_store.get_user_by_id(int(local["id"])), False


@router.post("/google/link")
async def google_link(request: Request) -> JSONResponse:
    """Start the deliberate link of a Google identity to the signed-in account.

    This is the safe path out of rule 4 above: the caller has already proved
    they hold the password account, so completing the OAuth round trip is
    enough to bind the identity. Requires an authenticated session — the gate
    enforces that, since this path is not on the public allow-list.
    """
    context = auth_lib.current_auth(request)
    if context is None:
        raise MoneylineError(auth_lib.AUTH_REQUIRED, "Sign in to use the desk.", 401)
    if not oauth.is_configured():
        raise MoneylineError(
            auth_lib.AUTH_UNAVAILABLE,
            "Google sign-in is not configured on this deployment.",
            503,
        )
    state = auth_lib.new_opaque_token()
    try:
        await auth_store.create_oauth_state(
            state, oauth.STATE_TTL, auth_lib.safe_redirect_target(None, _post_login_path())
        )
    except auth_store.AuthStoreUnavailable:
        raise _unavailable() from None
    return JSONResponse({"authorization_url": oauth.authorization_url(state)})


def _reset_ttl() -> timedelta:
    minutes = float(os.getenv("AUTH_PASSWORD_RESET_TTL_MINUTES") or "30")
    return timedelta(minutes=max(minutes, 1.0))


@router.post("/password-reset/request")
async def password_reset_request(
    request: Request, payload: ResetRequestInput
) -> JSONResponse:
    """Always the same 202 and the same message, account or not.

    A differing status, body, or obvious timing gap would turn this endpoint
    into an account-existence oracle.
    """
    _throttle(request, "reset_request", 10, 3600)
    _throttle_identity("reset_request", payload.email, 5, 3600)
    generic = JSONResponse(
        status_code=202, content={"ok": True, "message": GENERIC_RESET_MESSAGE}
    )
    try:
        email = auth_lib.validate_email(payload.email)
    except MoneylineError:
        # Even a malformed address gets the generic answer: rejecting it
        # differently is still a signal.
        return generic
    try:
        user = await auth_store.find_user_by_email(email)
    except auth_store.AuthStoreUnavailable:
        logger.warning("password_reset_lookup_failed reason=auth_store_unavailable")
        return generic
    if user is None or user.get("account_status") != "active":
        return generic

    token = auth_lib.new_opaque_token()
    try:
        await auth_store.create_reset_token(
            int(user["id"]),
            token,
            _reset_ttl(),
            requested_ip=auth_lib.client_fingerprint(request),
        )
    except auth_store.AuthStoreUnavailable:
        return generic
    reset_url = _reset_url(token)
    # The token exists only in the database (hashed) and in this email. It is
    # never returned to the caller and never logged.
    await mailer.send_password_reset(user["email"], reset_url)
    return generic


def _reset_url(token: str) -> str:
    path = os.getenv("AUTH_PASSWORD_RESET_PATH") or "/reset-password"
    base = auth_lib.safe_redirect_target(path, path)
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'token': token})}"


@router.post("/password-reset/complete")
async def password_reset_complete(
    request: Request, payload: ResetCompleteInput
) -> JSONResponse:
    _throttle(request, "reset_complete", 20, 3600)
    auth_lib.validate_password(payload.password)
    try:
        outcome = await auth_store.consume_reset_token(payload.token)
    except auth_store.AuthStoreUnavailable:
        raise _unavailable() from None
    if outcome["status"] == "expired":
        raise MoneylineError(
            auth_lib.RESET_EXPIRED,
            "That reset link has expired. Request a new one.",
            400,
        )
    if outcome["status"] != "ok":
        raise MoneylineError(
            auth_lib.RESET_INVALID,
            "That reset link is not valid. Request a new one.",
            400,
        )
    user_id = int(outcome["user_id"])
    try:
        await auth_store.set_password(user_id, auth_lib.hash_password(payload.password))
        # Whoever forced the reset does not get to keep a session that predates
        # it — every existing session for the account is revoked.
        await auth_store.revoke_user_sessions(user_id)
    except auth_store.AuthStoreUnavailable:
        raise _unavailable() from None
    response = JSONResponse(
        content={"ok": True, "message": "Password updated. Sign in with the new one."}
    )
    auth_lib.clear_session_cookie(response)
    return response
