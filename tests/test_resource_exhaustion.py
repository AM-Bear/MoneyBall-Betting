"""Regression coverage for bounded slate and settlement work."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import backend.main as main
from backend import auth as auth_lib
from backend.errors import MoneylineError
from backend.feeds import AsyncTTLCache
from backend.record_store import MAX_PENDING_GRADE_ROWS, pending_picks


def test_cache_evicts_oldest_entry_at_its_hard_cap() -> None:
    cache = AsyncTTLCache(ttl_seconds=600, max_entries=2)

    async def load(value: str) -> str:
        return value

    async def scenario() -> None:
        await cache.get_or_set("first", lambda: load("first"))
        await cache.get_or_set("second", lambda: load("second"))
        await cache.get_or_set("third", lambda: load("third"))

    asyncio.run(scenario())
    assert len(cache._items) == 2
    assert "first" not in cache._items


def test_cache_reclaims_other_expired_entries() -> None:
    cache = AsyncTTLCache(ttl_seconds=0, max_entries=4)

    async def load(value: str) -> str:
        return value

    async def scenario() -> None:
        await cache.get_or_set("expired", lambda: load("expired"))
        await cache.get_or_set("current", lambda: load("current"))

    asyncio.run(scenario())
    assert set(cache._items) == {"current"}


def test_slate_rejects_dates_outside_the_current_window() -> None:
    today = date.today()
    assert main._validate_slate_date(today) == today

    with pytest.raises(MoneylineError) as old:
        main._validate_slate_date(today - timedelta(days=main.SLATE_DATE_WINDOW_DAYS + 1))
    assert old.value.code == "unsupported_slate_date"

    with pytest.raises(MoneylineError) as future:
        main._validate_slate_date(today + timedelta(days=main.SLATE_DATE_WINDOW_DAYS + 1))
    assert future.value.code == "unsupported_slate_date"


def test_slate_date_rejection_happens_before_the_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_feed(*_args: Any) -> dict[str, Any]:
        pytest.fail("unsupported date must not reach the MLB feed")

    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setattr(main, "get_slate", fail_feed)
    client = TestClient(main.app)
    too_old = date.today() - timedelta(days=main.SLATE_DATE_WINDOW_DAYS + 1)

    response = client.get(f"/api/slate?date={too_old.isoformat()}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_slate_date"


def test_slate_requests_are_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    async def historical(*_args: Any) -> dict[str, Any]:
        return {"mode": "historical", "cache": "miss", "games": []}

    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SLATE_MAX", "1")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SLATE_WINDOW_SECONDS", "60")
    monkeypatch.setattr(main, "get_slate", historical)
    auth_lib.reset_rate_limits()
    try:
        client = TestClient(main.app)
        assert client.get("/api/slate").status_code == 200
        throttled = client.get("/api/slate")
        assert throttled.status_code == 429
        assert throttled.json()["error"]["code"] == auth_lib.RATE_LIMITED
    finally:
        auth_lib.reset_rate_limits()


async def test_concurrent_settlement_callers_share_one_full_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def one_pass() -> dict[str, int]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return {
            "checked": 0,
            "graded": 0,
            "voided": 0,
            "parlays_graded": 0,
            "parlays_voided": 0,
        }

    monkeypatch.setattr(main, "_grade_task", None)
    monkeypatch.setattr(main, "_grade_pending_records_once", one_pass)

    results = await asyncio.gather(*(main.grade_pending_records() for _ in range(8)))

    assert calls == 1
    assert all(result["checked"] == 0 for result in results)


def test_manual_grade_requires_an_explicit_operator_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
    request.state.auth = auth_lib.AuthContext({"id": 42}, {})
    monkeypatch.delenv("MONEYLINE_RECORD_OPERATOR_IDS", raising=False)

    with pytest.raises(MoneylineError) as denied:
        main._require_record_operator(request)
    assert denied.value.code == "operator_required"

    monkeypatch.setenv("MONEYLINE_RECORD_OPERATOR_IDS", "42, 99")
    assert main._require_record_operator(request).user_id == 42


def test_pending_pick_read_is_capped_to_one_settlement_batch(seed_pick) -> None:
    for number in range(MAX_PENDING_GRADE_ROWS + 5):
        seed_pick(
            f"batch-{number}",
            date.today() - timedelta(days=1),
            "NYY",
            "BOS",
            "BOS",
        )

    rows = pending_picks()

    assert len(rows) == MAX_PENDING_GRADE_ROWS