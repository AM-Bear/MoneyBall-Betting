"""Outbound transactional email for password resets, over configured SMTP.

Credentials come from the environment. Nothing here logs a token, a reset URL,
or a password; a failure logs the exception class and the SMTP host only.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("moneyline.auth")

_TRUE = {"1", "true", "yes", "on"}


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def is_configured() -> bool:
    return bool(_env("SMTP_HOST") and _env("SMTP_FROM_EMAIL"))


def _send_sync(to_email: str, subject: str, text_body: str, html_body: str) -> None:
    host = _env("SMTP_HOST")
    port = int(_env("SMTP_PORT", "587"))
    username = _env("SMTP_USERNAME")
    password = _env("SMTP_PASSWORD")
    sender = _env("SMTP_FROM_EMAIL")
    sender_name = _env("SMTP_FROM_NAME", "MONEYLINE")
    use_ssl = _env("SMTP_USE_SSL", "false").lower() in _TRUE
    use_starttls = _env("SMTP_STARTTLS", "true").lower() in _TRUE
    timeout = float(_env("SMTP_TIMEOUT_SECONDS", "15"))

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{sender}>"
    message["To"] = to_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    if use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    try:
        if not use_ssl and use_starttls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:  # pragma: no cover - best-effort socket teardown
            pass


async def send_password_reset(to_email: str, reset_url: str) -> bool:
    """Fire the reset email. Returns False when SMTP is unconfigured or fails.

    The caller must respond identically either way — whether the mail went out
    is not something an unauthenticated requester gets to learn.
    """
    if not is_configured():
        logger.warning("password_reset_email_skipped reason=smtp_unconfigured")
        return False
    subject = "Reset your MONEYLINE password"
    text_body = (
        "Someone asked to reset the MONEYLINE password for this address.\n\n"
        f"{reset_url}\n\n"
        "The link is single-use and expires shortly. If this was not you, no "
        "action is needed — the password is unchanged.\n"
    )
    html_body = (
        "<p>Someone asked to reset the MONEYLINE password for this address.</p>"
        f'<p><a href="{reset_url}">Set a new password</a></p>'
        "<p>The link is single-use and expires shortly. If this was not you, "
        "no action is needed — the password is unchanged.</p>"
    )
    try:
        await asyncio.to_thread(_send_sync, to_email, subject, text_body, html_body)
        return True
    except Exception as error:
        # No address, no URL, no token — just the failure class and host.
        logger.warning(
            "password_reset_email_failed host=%s error=%s",
            _env("SMTP_HOST"),
            type(error).__name__,
        )
        return False
