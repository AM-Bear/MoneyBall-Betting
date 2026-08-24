"""The single API error type behind the `{"error": {"code", "message"}}` envelope.

Lifted out of `backend.main` so `backend.auth` (which `main` imports) can raise
the same error without a circular import. `main` re-exports it, so
`main.MoneylineError` still resolves exactly as it did before.
"""

from __future__ import annotations


class MoneylineError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
