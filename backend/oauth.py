"""Google OAuth 2.0 (OpenID Connect) authorization-code flow.

Configuration comes entirely from the environment. The client secret is used
only in the server-to-server token exchange and is never placed in a redirect,
a response body, or a log line.

State is minted here but persisted by `backend.auth_store`, which makes it
single-use and expiring; this module only formats and parses.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from backend import auth as auth_lib
from backend.errors import MoneylineError

logger = logging.getLogger("moneyline.auth")

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPES = "openid email profile"
STATE_TTL = timedelta(minutes=10)


def client_id() -> str | None:
    return os.getenv("GOOGLE_OAUTH_CLIENT_ID") or None


def client_secret() -> str | None:
    return os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or None


def redirect_uri() -> str | None:
    return os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or None


def is_configured() -> bool:
    return bool(client_id() and client_secret() and redirect_uri())


def validated_redirect_uri() -> str:
    """The one redirect URI we will ever hand Google, checked before use.

    Google matches this against its own registered list too, but validating
    here means a typo'd or downgraded (http, off-origin) value fails at our
    boundary with a clear code rather than as an opaque Google error page.
    """
    configured = redirect_uri()
    if not configured:
        raise MoneylineError(
            auth_lib.AUTH_UNAVAILABLE,
            "Google sign-in is not configured on this deployment.",
            503,
        )
    parts = urlsplit(configured)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise MoneylineError(
            auth_lib.AUTH_UNAVAILABLE,
            "Google sign-in is not configured on this deployment.",
            503,
        )
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1"}:
        # Plain HTTP off localhost would put the authorization code on the wire.
        raise MoneylineError(
            auth_lib.AUTH_UNAVAILABLE,
            "Google sign-in is not configured on this deployment.",
            503,
        )
    return configured


def authorization_url(state: str) -> str:
    if not is_configured():
        raise MoneylineError(
            auth_lib.AUTH_UNAVAILABLE,
            "Google sign-in is not configured on this deployment.",
            503,
        )
    query = urlencode(
        {
            "client_id": client_id(),
            "redirect_uri": validated_redirect_uri(),
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "access_type": "online",
            "include_granted_scopes": "true",
            "prompt": "select_account",
        }
    )
    return f"{AUTHORIZATION_ENDPOINT}?{query}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Trade the authorization code for tokens. Server-to-server, secret never leaves."""
    timeout = float(os.getenv("GOOGLE_OAUTH_TIMEOUT_SECONDS", "10"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client_id(),
                "client_secret": client_secret(),
                "redirect_uri": validated_redirect_uri(),
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code != 200:
        # Google's body can echo request parameters; log the status only.
        logger.warning("google_token_exchange_failed status=%s", response.status_code)
        raise MoneylineError(
            auth_lib.OAUTH_FAILED, "Google sign-in could not be completed.", 400
        )
    return response.json()


async def fetch_identity(access_token: str) -> dict[str, Any]:
    """Read the verified profile from Google's OIDC userinfo endpoint.

    Reading userinfo over TLS rather than parsing the id_token locally means
    there is no JWT signature verification to get subtly wrong; Google itself
    is the one asserting the claims on this connection.
    """
    timeout = float(os.getenv("GOOGLE_OAUTH_TIMEOUT_SECONDS", "10"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code != 200:
        logger.warning("google_userinfo_failed status=%s", response.status_code)
        raise MoneylineError(
            auth_lib.OAUTH_FAILED, "Google sign-in could not be completed.", 400
        )
    profile = response.json()
    subject = str(profile.get("sub") or "").strip()
    email = str(profile.get("email") or "").strip()
    email_verified = bool(profile.get("email_verified"))
    if not subject or not email:
        raise MoneylineError(
            auth_lib.OAUTH_FAILED, "Google sign-in could not be completed.", 400
        )
    if not email_verified:
        # An unverified Google address must never be allowed to reach an
        # account keyed on that address.
        raise MoneylineError(
            auth_lib.OAUTH_FAILED,
            "Google has not verified that email address.",
            400,
        )
    return {
        "subject": subject,
        "email": email,
        "name": (profile.get("name") or "").strip() or None,
    }
