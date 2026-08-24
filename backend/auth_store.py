"""Postgres persistence for accounts, sessions, resets, and Google identities.

Separate from `backend.record_store` on purpose: the pick/parlay ledger is
append-only production history and this file must never be in a position to
touch it. The two share the same database and the same idempotent-boot-migration
discipline — every statement here is `CREATE ... IF NOT EXISTS` or
`ADD COLUMN IF NOT EXISTS`, so a boot can stand up a fresh database and can
never rewrite an existing row.

Public functions are async wrappers over synchronous psycopg calls run on a
worker thread, matching how `backend.main` already treats the record store.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend import auth as auth_lib

logger = logging.getLogger("moneyline.auth")


class AuthStoreUnavailable(RuntimeError):
    """The database is not configured or not reachable. Callers must fail closed."""


def _connection() -> psycopg.Connection[Any]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise AuthStoreUnavailable("DATABASE_URL is not configured.")
    try:
        return psycopg.connect(database_url, row_factory=dict_row)
    except psycopg.Error as error:  # pragma: no cover - depends on live database
        raise AuthStoreUnavailable(str(error)) from error


def _connect() -> psycopg.Connection[Any]:
    """Every query goes through here so a driver error becomes AuthStoreUnavailable."""
    try:
        return _connection()
    except AuthStoreUnavailable:
        raise
    except Exception as error:
        raise AuthStoreUnavailable(str(error)) from error


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run(func, *args):
    """Run a synchronous store call, turning any driver error into unavailable.

    Callers fail closed on `AuthStoreUnavailable`, so a missing table, a dropped
    connection, or a timeout all land as a 503 rather than an unhandled 500 that
    would leak SQL detail through the error envelope.
    """
    try:
        return func(*args)
    except AuthStoreUnavailable:
        raise
    except psycopg.Error as error:
        logger.warning("auth_store_query_failed error=%s", type(error).__name__)
        raise AuthStoreUnavailable(str(error)) from error


AUTH_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS moneyline_users (
      id bigserial PRIMARY KEY,
      email text NOT NULL,
      email_normalized text NOT NULL,
      password_hash text,
      display_name text,
      account_status text NOT NULL DEFAULT 'active',
      entitlement text NOT NULL DEFAULT 'free',
      entitlement_source text,
      entitlement_expires_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      last_login_at timestamptz
    )
    """,
    # Uniqueness is on the normalized form, so Asher@X.com and asher@x.com
    # cannot become two accounts.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS moneyline_users_email_idx
      ON moneyline_users (email_normalized)
    """,
    """
    CREATE TABLE IF NOT EXISTS moneyline_google_identities (
      id bigserial PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES moneyline_users(id) ON DELETE CASCADE,
      google_subject text NOT NULL,
      email text,
      linked_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS moneyline_google_subject_idx
      ON moneyline_google_identities (google_subject)
    """,
    """
    CREATE INDEX IF NOT EXISTS moneyline_google_user_idx
      ON moneyline_google_identities (user_id)
    """,
    # Sessions store only a SHA-256 of the opaque cookie value: a dump of this
    # table hands an attacker nothing they can present as a session.
    """
    CREATE TABLE IF NOT EXISTS moneyline_auth_sessions (
      id bigserial PRIMARY KEY,
      token_hash text NOT NULL,
      user_id bigint NOT NULL REFERENCES moneyline_users(id) ON DELETE CASCADE,
      created_at timestamptz NOT NULL DEFAULT now(),
      last_seen_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      revoked_at timestamptz,
      user_agent text,
      ip_address text
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS moneyline_auth_session_token_idx
      ON moneyline_auth_sessions (token_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS moneyline_auth_session_user_idx
      ON moneyline_auth_sessions (user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS moneyline_auth_session_expiry_idx
      ON moneyline_auth_sessions (expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS moneyline_password_resets (
      id bigserial PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES moneyline_users(id) ON DELETE CASCADE,
      token_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      consumed_at timestamptz,
      requested_ip text
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS moneyline_password_reset_token_idx
      ON moneyline_password_resets (token_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS moneyline_password_reset_user_idx
      ON moneyline_password_resets (user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS moneyline_password_reset_expiry_idx
      ON moneyline_password_resets (expires_at)
    """,
    # OAuth state lives server-side rather than in a signed cookie so it can be
    # single-use: a replayed callback finds the row already consumed.
    """
    CREATE TABLE IF NOT EXISTS moneyline_oauth_states (
      id bigserial PRIMARY KEY,
      state_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      consumed_at timestamptz,
      redirect_to text
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS moneyline_oauth_state_idx
      ON moneyline_oauth_states (state_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS moneyline_oauth_state_expiry_idx
      ON moneyline_oauth_states (expires_at)
    """,
]


def ensure_auth_schema_sync() -> bool:
    with _connect() as connection:
        with connection.cursor() as cursor:
            for statement in AUTH_SCHEMA_STATEMENTS:
                cursor.execute(statement)
        connection.commit()
    return True


async def ensure_auth_schema() -> bool:
    return await asyncio.to_thread(_run, ensure_auth_schema_sync)


def auth_database_available() -> bool:
    try:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() is not None
    except Exception:
        return False


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
_USER_COLUMNS = """
  u.id, u.email, u.email_normalized, u.password_hash, u.display_name,
  u.account_status, u.entitlement, u.entitlement_source,
  u.entitlement_expires_at, u.created_at, u.last_login_at,
  EXISTS (
    SELECT 1 FROM moneyline_google_identities g WHERE g.user_id = u.id
  ) AS google_linked
"""


def _find_user_by_email_sync(email: str) -> dict[str, Any] | None:
    normalized = auth_lib.normalize_email(email)
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_USER_COLUMNS} FROM moneyline_users u "
                "WHERE u.email_normalized = %s",
                (normalized,),
            )
            return cursor.fetchone()


def _create_user_sync(
    email: str, password_hash: str | None, display_name: str | None
) -> dict[str, Any] | None:
    """Returns None when the normalized email is already taken.

    The uniqueness index is the authority, not a prior SELECT: two concurrent
    signups race, and only the index settles it.
    """
    normalized = auth_lib.normalize_email(email)
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO moneyline_users
                  (email, email_normalized, password_hash, display_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (email_normalized) DO NOTHING
                RETURNING id
                """,
                (email.strip(), normalized, password_hash, display_name),
            )
            created = cursor.fetchone()
            if created is None:
                return None
            connection.commit()
            cursor.execute(
                f"SELECT {_USER_COLUMNS} FROM moneyline_users u WHERE u.id = %s",
                (created["id"],),
            )
            return cursor.fetchone()


def _set_password_sync(user_id: int, password_hash: str) -> None:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE moneyline_users
                   SET password_hash = %s, updated_at = now()
                 WHERE id = %s
                """,
                (password_hash, user_id),
            )
        connection.commit()


def _touch_login_sync(user_id: int) -> None:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE moneyline_users SET last_login_at = now() WHERE id = %s",
                (user_id,),
            )
        connection.commit()


async def find_user_by_email(email: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_run, _find_user_by_email_sync, email)


async def create_user(
    email: str, password_hash: str | None, display_name: str | None = None
) -> dict[str, Any] | None:
    return await asyncio.to_thread(_run, _create_user_sync, email, password_hash, display_name)


async def set_password(user_id: int, password_hash: str) -> None:
    await asyncio.to_thread(_run, _set_password_sync, user_id, password_hash)


async def touch_login(user_id: int) -> None:
    await asyncio.to_thread(_run, _touch_login_sync, user_id)


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------
def _create_session_sync(
    user_id: int, token: str, ttl: timedelta, user_agent: str | None, ip_address: str | None
) -> dict[str, Any]:
    expires_at = _now() + ttl
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO moneyline_auth_sessions
                  (token_hash, user_id, expires_at, user_agent, ip_address)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, user_id, created_at, expires_at
                """,
                (
                    auth_lib.token_fingerprint(token),
                    user_id,
                    expires_at,
                    (user_agent or "")[:400] or None,
                    (ip_address or "")[:100] or None,
                ),
            )
            row = cursor.fetchone()
        connection.commit()
    return row


def _resolve_session_sync(token: str) -> dict[str, Any] | None:
    """Expired and revoked sessions resolve to None — the SQL, not the caller, decides."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT s.id AS session_id, s.expires_at, s.created_at AS session_created_at,
                       {_USER_COLUMNS}
                  FROM moneyline_auth_sessions s
                  JOIN moneyline_users u ON u.id = s.user_id
                 WHERE s.token_hash = %s
                   AND s.revoked_at IS NULL
                   AND s.expires_at > now()
                """,
                (auth_lib.token_fingerprint(token),),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            if row.get("account_status") != "active":
                return None
            cursor.execute(
                "UPDATE moneyline_auth_sessions SET last_seen_at = now() WHERE id = %s",
                (row["session_id"],),
            )
        connection.commit()
    session = {
        "id": row["session_id"],
        "expires_at": row["expires_at"],
        "created_at": row["session_created_at"],
    }
    user = {
        key: value
        for key, value in row.items()
        if key not in {"session_id", "expires_at", "session_created_at"}
    }
    return {"user": user, "session": session}


def _revoke_session_sync(token: str) -> bool:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE moneyline_auth_sessions
                   SET revoked_at = now()
                 WHERE token_hash = %s AND revoked_at IS NULL
                """,
                (auth_lib.token_fingerprint(token),),
            )
            revoked = cursor.rowcount > 0
        connection.commit()
    return revoked


def _revoke_user_sessions_sync(user_id: int) -> int:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE moneyline_auth_sessions
                   SET revoked_at = now()
                 WHERE user_id = %s AND revoked_at IS NULL
                """,
                (user_id,),
            )
            revoked = cursor.rowcount
        connection.commit()
    return revoked


async def create_session(
    user_id: int,
    token: str,
    ttl: timedelta,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _create_session_sync, user_id, token, ttl, user_agent, ip_address
    )


async def resolve_session(token: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_run, _resolve_session_sync, token)


async def revoke_session(token: str) -> bool:
    return await asyncio.to_thread(_run, _revoke_session_sync, token)


async def revoke_user_sessions(user_id: int) -> int:
    return await asyncio.to_thread(_run, _revoke_user_sessions_sync, user_id)


# --------------------------------------------------------------------------
# Password resets
# --------------------------------------------------------------------------
def _create_reset_token_sync(
    user_id: int, token: str, ttl: timedelta, requested_ip: str | None
) -> datetime:
    expires_at = _now() + ttl
    with _connect() as connection:
        with connection.cursor() as cursor:
            # Outstanding tokens are burned first: requesting a new link must
            # invalidate the old one, or a leaked older email stays live.
            cursor.execute(
                """
                UPDATE moneyline_password_resets
                   SET consumed_at = now()
                 WHERE user_id = %s AND consumed_at IS NULL
                """,
                (user_id,),
            )
            cursor.execute(
                """
                INSERT INTO moneyline_password_resets
                  (user_id, token_hash, expires_at, requested_ip)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user_id,
                    auth_lib.token_fingerprint(token),
                    expires_at,
                    (requested_ip or "")[:100] or None,
                ),
            )
        connection.commit()
    return expires_at


def _consume_reset_token_sync(token: str) -> dict[str, Any]:
    """Single-use and time-limited, decided in one atomic UPDATE.

    Returns a status string rather than a bool so the route can distinguish
    `reset_expired` from `reset_invalid` without a second, racy lookup.
    """
    token_hash = auth_lib.token_fingerprint(token)
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE moneyline_password_resets
                   SET consumed_at = now()
                 WHERE token_hash = %s
                   AND consumed_at IS NULL
                   AND expires_at > now()
                RETURNING user_id
                """,
                (token_hash,),
            )
            claimed = cursor.fetchone()
            if claimed is not None:
                connection.commit()
                return {"status": "ok", "user_id": claimed["user_id"]}
            cursor.execute(
                """
                SELECT consumed_at, expires_at
                  FROM moneyline_password_resets
                 WHERE token_hash = %s
                """,
                (token_hash,),
            )
            existing = cursor.fetchone()
        connection.rollback()
    if existing is None:
        return {"status": "invalid"}
    if existing["consumed_at"] is not None:
        # A reused token is reported as invalid, not "already used": telling a
        # holder which of the two it is tells them the token was real.
        return {"status": "invalid"}
    return {"status": "expired"}


async def create_reset_token(
    user_id: int, token: str, ttl: timedelta, requested_ip: str | None = None
) -> datetime:
    return await asyncio.to_thread(
        _create_reset_token_sync, user_id, token, ttl, requested_ip
    )


async def consume_reset_token(token: str) -> dict[str, Any]:
    return await asyncio.to_thread(_run, _consume_reset_token_sync, token)


# --------------------------------------------------------------------------
# OAuth state
# --------------------------------------------------------------------------
def _create_oauth_state_sync(state: str, ttl: timedelta, redirect_to: str | None) -> None:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO moneyline_oauth_states (state_hash, expires_at, redirect_to)
                VALUES (%s, %s, %s)
                """,
                (auth_lib.token_fingerprint(state), _now() + ttl, redirect_to),
            )
            # Opportunistic cleanup so the table cannot grow without bound.
            cursor.execute(
                "DELETE FROM moneyline_oauth_states WHERE expires_at < now() - interval '1 day'"
            )
        connection.commit()


def _consume_oauth_state_sync(state: str) -> dict[str, Any] | None:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE moneyline_oauth_states
                   SET consumed_at = now()
                 WHERE state_hash = %s
                   AND consumed_at IS NULL
                   AND expires_at > now()
                RETURNING redirect_to
                """,
                (auth_lib.token_fingerprint(state),),
            )
            row = cursor.fetchone()
        connection.commit()
    return row


async def create_oauth_state(
    state: str, ttl: timedelta, redirect_to: str | None = None
) -> None:
    await asyncio.to_thread(_run, _create_oauth_state_sync, state, ttl, redirect_to)


async def consume_oauth_state(state: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_run, _consume_oauth_state_sync, state)


# --------------------------------------------------------------------------
# Google identities
# --------------------------------------------------------------------------
def _find_user_by_google_subject_sync(subject: str) -> dict[str, Any] | None:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_USER_COLUMNS}
                  FROM moneyline_google_identities g
                  JOIN moneyline_users u ON u.id = g.user_id
                 WHERE g.google_subject = %s
                """,
                (subject,),
            )
            return cursor.fetchone()


def _link_google_identity_sync(user_id: int, subject: str, email: str | None) -> bool:
    """Idempotent, and never steals a subject already bound to another account."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO moneyline_google_identities (user_id, google_subject, email)
                VALUES (%s, %s, %s)
                ON CONFLICT (google_subject) DO NOTHING
                RETURNING id
                """,
                (user_id, subject, email),
            )
            inserted = cursor.fetchone() is not None
        connection.commit()
    return inserted


async def find_user_by_google_subject(subject: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_run, _find_user_by_google_subject_sync, subject)


async def link_google_identity(user_id: int, subject: str, email: str | None) -> bool:
    return await asyncio.to_thread(_run, _link_google_identity_sync, user_id, subject, email)


async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    def _fetch() -> dict[str, Any] | None:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_USER_COLUMNS} FROM moneyline_users u WHERE u.id = %s",
                    (user_id,),
                )
                return cursor.fetchone()

    return await asyncio.to_thread(_run, _fetch)
