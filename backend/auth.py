"""Password, session-cookie, rate-limit, and request-gating primitives.

This module holds the pure-ish auth machinery: everything that does not need a
database connection (that is `backend.auth_store`) and does not talk to Google
(that is `backend.oauth`).

Configuration is read from the environment on every call rather than at import
time, so a deployment can change a TTL or a cookie flag without a code change
and so tests can drive the behaviour with `monkeypatch.setenv`. No secret,
token, or password is ever written to a log line from here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit

import bcrypt
from fastapi import Request, Response

from backend.errors import MoneylineError

logger = logging.getLogger("moneyline.auth")


# --------------------------------------------------------------------------
# Stable error codes. The frontend switches on these strings, so they are part
# of the API contract and must not be renamed casually.
# --------------------------------------------------------------------------
AUTH_REQUIRED = "auth_required"
INVALID_CREDENTIALS = "invalid_credentials"
VALIDATION_ERROR = "validation_error"
EMAIL_TAKEN = "email_taken"
RESET_INVALID = "reset_invalid"
RESET_EXPIRED = "reset_expired"
OAUTH_FAILED = "oauth_failed"
OAUTH_LINK_REQUIRED = "oauth_link_required"
AUTH_UNAVAILABLE = "auth_unavailable"
RATE_LIMITED = "rate_limited"

# Everything under /api requires a session except these. They are the auth
# bootstrap (a signed-out browser must be able to reach them), the OAuth
# callback (Google calls it with no cookie of ours), the password-reset pair (a
# locked-out user has no session by definition), and health (the deployment
# probe has no credentials).
PUBLIC_API_PATHS = frozenset(
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

_TRUE = {"1", "true", "yes", "on"}
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

# A fixed, throwaway hash used to burn the same CPU on a miss as on a hit, so
# "no such user" and "wrong password" take comparable time. Computed lazily.
_DUMMY_HASH: str | None = None


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in _TRUE


def is_production() -> bool:
    return os.getenv("NODE_ENV") == "production"


# --------------------------------------------------------------------------
# Cookie policy
# --------------------------------------------------------------------------
def session_cookie_name() -> str:
    return _env("AUTH_SESSION_COOKIE_NAME", "moneyline_session")


def session_ttl() -> timedelta:
    return timedelta(hours=float(_env("AUTH_SESSION_TTL_HOURS", "336")))


def cookie_secure() -> bool:
    """Secure defaults on in production; overridable for plain-HTTP local dev."""
    return _flag("AUTH_COOKIE_SECURE", is_production())


def cookie_samesite() -> str:
    value = _env("AUTH_COOKIE_SAMESITE", "lax").lower()
    return value if value in {"lax", "strict", "none"} else "lax"


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = max(int((expires_at - _now()).total_seconds()), 0)
    response.set_cookie(
        key=session_cookie_name(),
        value=token,
        max_age=max_age,
        expires=max_age,
        path="/",
        httponly=True,
        secure=cookie_secure(),
        samesite=cookie_samesite(),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=session_cookie_name(),
        path="/",
        httponly=True,
        secure=cookie_secure(),
        samesite=cookie_samesite(),
    )


def read_session_cookie(request: Request) -> str | None:
    return request.cookies.get(session_cookie_name()) or None


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
def new_opaque_token() -> str:
    """An opaque, unguessable session/reset identifier — never user data."""
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    """What gets stored. A database leak yields hashes, not usable tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Email + password rules
# --------------------------------------------------------------------------
def normalize_email(email: str) -> str:
    """Case-folded, NFKC-normalised, trimmed. This is the uniqueness key.

    Deliberately does NOT strip dots or `+tags`: those are provider-specific
    conventions, and collapsing them would merge addresses their owners treat
    as distinct.
    """
    return unicodedata.normalize("NFKC", (email or "").strip()).casefold()


def validate_email(email: str) -> str:
    candidate = (email or "").strip()
    if not candidate or len(candidate) > 254 or not _EMAIL_PATTERN.match(candidate):
        raise MoneylineError(
            VALIDATION_ERROR, "Enter a valid email address.", 400
        )
    return candidate


def password_min_length() -> int:
    return max(int(_env("AUTH_PASSWORD_MIN_LENGTH", "12")), 8)


def validate_password(password: str) -> str:
    """Length and variety only, and never echoes the value into the message."""
    if not isinstance(password, str) or not password:
        raise MoneylineError(VALIDATION_ERROR, "A password is required.", 400)
    minimum = password_min_length()
    if len(password) < minimum:
        raise MoneylineError(
            VALIDATION_ERROR,
            f"Passwords must be at least {minimum} characters.",
            400,
        )
    if len(password.encode("utf-8")) > 4096:
        raise MoneylineError(VALIDATION_ERROR, "That password is too long.", 400)
    has_letter = any(character.isalpha() for character in password)
    has_other = any(not character.isalpha() for character in password)
    if not (has_letter and has_other):
        raise MoneylineError(
            VALIDATION_ERROR,
            "Passwords must mix letters with at least one number or symbol.",
            400,
        )
    return password


def bcrypt_rounds() -> int:
    # 12 is the common 2020s default: ~250ms on this class of hardware.
    return min(max(int(_env("AUTH_BCRYPT_ROUNDS", "12")), 4), 16)


def _password_bytes(password: str) -> bytes:
    """bcrypt silently truncates past 72 bytes; SHA-256 first so it cannot.

    base64 of the digest keeps the input NUL-free, which bcrypt also truncates
    on.
    """
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        _password_bytes(password), bcrypt.gensalt(rounds=bcrypt_rounds())
    ).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time: a missing hash still pays for one bcrypt round."""
    global _DUMMY_HASH
    if not password_hash:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password("moneyline-timing-equaliser")
        password_hash = _DUMMY_HASH
        bcrypt.checkpw(_password_bytes(password or ""), password_hash.encode("utf-8"))
        return False
    try:
        return bcrypt.checkpw(
            _password_bytes(password or ""), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


# --------------------------------------------------------------------------
# Rate limiting
#
# In-process sliding window. This runs as a single deployment process, so a
# shared store would be ceremony without benefit; if MONEYLINE ever scales to
# several API processes this becomes a per-process limit, which is a weaker
# guarantee but never a wrong one.
# --------------------------------------------------------------------------
_BUCKETS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    _BUCKETS.clear()


def rate_limits_enabled() -> bool:
    return _flag("AUTH_RATE_LIMIT_ENABLED", True)


def client_fingerprint(request: Request) -> str:
    """Best-effort caller identity for throttling only — never for authorization."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def enforce_rate_limit(bucket: str, key: str, limit: int, window_seconds: int) -> None:
    if not rate_limits_enabled():
        return
    now = time.monotonic()
    hits = _BUCKETS[(bucket, key)]
    cutoff = now - window_seconds
    while hits and hits[0] < cutoff:
        hits.popleft()
    if len(hits) >= limit:
        # The key is a hashed fingerprint at the call site for email buckets,
        # so this line never carries an address or a credential.
        logger.warning("auth_rate_limited bucket=%s", bucket)
        raise MoneylineError(
            RATE_LIMITED,
            "Too many attempts. Wait a minute and try again.",
            429,
        )
    hits.append(now)


def rate_limit_config(name: str, default_limit: int, default_window: int) -> tuple[int, int]:
    limit = int(_env(f"AUTH_RATE_LIMIT_{name}_MAX", str(default_limit)))
    window = int(_env(f"AUTH_RATE_LIMIT_{name}_WINDOW_SECONDS", str(default_window)))
    return max(limit, 1), max(window, 1)


# --------------------------------------------------------------------------
# Redirect safety
# --------------------------------------------------------------------------
def app_origin() -> str:
    return _env("AUTH_APP_ORIGIN", "http://localhost:18612").rstrip("/")


def allowed_redirect_origins() -> tuple[str, ...]:
    configured = _env("AUTH_ALLOWED_REDIRECT_ORIGINS", "")
    origins = [origin.strip().rstrip("/") for origin in configured.split(",")]
    origins.append(app_origin())
    return tuple(dict.fromkeys(origin for origin in origins if origin))


def safe_redirect_target(candidate: str | None, default_path: str = "/") -> str:
    """Resolve an untrusted `next` into an absolute URL we are willing to send to.

    Accepts a site-relative path, or an absolute URL whose scheme+host is on
    the configured allow-list. Anything else silently falls back to the default
    — an open redirect off the back of the OAuth callback would be a phishing
    primitive.
    """
    origin = app_origin()
    fallback = f"{origin}{_normalized_path(default_path)}"
    if not candidate:
        return fallback
    candidate = candidate.strip()
    if not candidate:
        return fallback
    # Protocol-relative ("//evil.example") and backslash tricks are rejected
    # before urlsplit, which is more permissive than a browser.
    if candidate.startswith("//") or "\\" in candidate:
        return fallback
    if candidate.startswith("/"):
        return f"{origin}{candidate}"
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return fallback
    candidate_origin = f"{parts.scheme}://{parts.netloc}".rstrip("/")
    if candidate_origin in allowed_redirect_origins():
        return candidate
    return fallback


def _normalized_path(path: str) -> str:
    if not path.startswith("/"):
        return f"/{path}"
    return path


def dev_cors_origins() -> list[str]:
    """Explicitly configured development origins. Never a wildcard.

    Credentialed CORS with `*` is rejected by browsers and would be unsafe
    anyway, so the list is always concrete.
    """
    configured = _env(
        "AUTH_DEV_ORIGINS",
        f"{_env('DEV_ORIGIN', 'http://localhost:18612')},http://127.0.0.1:18612",
    )
    origins = [origin.strip().rstrip("/") for origin in configured.split(",")]
    return [origin for origin in dict.fromkeys(origins) if origin and origin != "*"]


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------
class AuthContext:
    """What a resolved session hands to a route handler."""

    def __init__(self, user: dict[str, Any], session: dict[str, Any]) -> None:
        self.user = user
        self.session = session

    @property
    def user_id(self) -> int:
        return int(self.user["id"])


def is_public_path(path: str) -> bool:
    """True for anything the gate must let through unauthenticated.

    Non-`/api` paths are the SPA shell and its static assets: serving the HTML
    to a signed-out browser is what lets the frontend render its own sign-in
    screen. No application data crosses that boundary — every data route lives
    under /api and is gated.
    """
    normalized = path.rstrip("/") or "/"
    if not (normalized == "/api" or normalized.startswith("/api/")):
        return True
    return normalized in PUBLIC_API_PATHS


async def enforce_session(request: Request) -> None:
    """App-level dependency: the single gate in front of every route.

    Attached once to the FastAPI app so a new `/api` route is protected the
    moment it is written — there is no per-route decorator to forget. Resolves
    the session onto `request.state.auth` for handlers that want the user.
    """
    from backend import auth_store  # imported here to keep this module import-light

    request.state.auth = None
    if is_public_path(request.url.path):
        return
    token = read_session_cookie(request)
    if not token:
        raise MoneylineError(AUTH_REQUIRED, "Sign in to use the desk.", 401)
    try:
        resolved = await auth_store.resolve_session(token)
    except auth_store.AuthStoreUnavailable:
        # Fail closed. An unreachable database must never mean "let them in".
        raise MoneylineError(
            AUTH_UNAVAILABLE,
            "The desk cannot verify your session right now.",
            503,
        ) from None
    if resolved is None:
        raise MoneylineError(AUTH_REQUIRED, "Sign in to use the desk.", 401)
    request.state.auth = AuthContext(resolved["user"], resolved["session"])


def current_auth(request: Request) -> AuthContext | None:
    return getattr(request.state, "auth", None)


def public_user_payload(user: dict[str, Any]) -> dict[str, Any]:
    """The user/account summary returned by every session-establishing route.

    `entitlement` is the neutral forward-compatible field: a tier name and its
    provenance, nothing that implies billing exists. Nothing in this codebase
    charges for or gates on it today.
    """
    created_at = user.get("created_at")
    return {
        "id": int(user["id"]),
        "email": user["email"],
        "display_name": user.get("display_name"),
        "created_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
        "has_password": bool(user.get("password_hash")),
        "google_linked": bool(user.get("google_linked")),
        "account": {
            "status": user.get("account_status", "active"),
            "entitlement": {
                "tier": user.get("entitlement", "free"),
                "source": user.get("entitlement_source"),
                "expires_at": (
                    user["entitlement_expires_at"].isoformat()
                    if isinstance(user.get("entitlement_expires_at"), datetime)
                    else None
                ),
            },
        },
    }


def session_payload(user: dict[str, Any], session: dict[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "authenticated": True,
        "user": public_user_payload(user),
    }
    if session and isinstance(session.get("expires_at"), datetime):
        payload["session"] = {"expires_at": session["expires_at"].isoformat()}
    return payload
