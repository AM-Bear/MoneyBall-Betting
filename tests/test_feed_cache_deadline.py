"""AsyncTTLCache: single-flight, bounded wait, graceful degradation.

A dead MLB API was always handled well — `get_slate` catches `FeedUnavailable`
and falls back to `historical_slate`. A *slow* one was not. `FEED_TIMEOUT_SECONDS`
is per HTTP request (10s) and a logical fetch retries once, so `get_rosters`
fanning 30 calls at concurrency 5 could stack past two minutes; because the
loader ran under a per-key lock, every concurrent `/api/slate` queued behind it.
The result was a multi-minute app-wide hang rather than a clean degrade.

The fix keeps single-flight — dropping it would let each concurrent request fan
out its own roster sweep — but bounds how long a caller waits, and shields the
in-flight loader so a caller giving up does not throw away work the next caller
needs.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.feeds import AsyncTTLCache, FeedUnavailable


def test_a_fresh_entry_is_served_from_cache_without_calling_the_loader() -> None:
    calls = 0

    async def loader() -> str:
        nonlocal calls
        calls += 1
        return "value"

    cache = AsyncTTLCache(ttl_seconds=600)

    async def scenario() -> None:
        first, cached = await cache.get_or_set("k", loader)
        assert (first, cached) == ("value", False)
        second, cached = await cache.get_or_set("k", loader)
        assert (second, cached) == ("value", True)

    asyncio.run(scenario())
    assert calls == 1


def test_concurrent_callers_share_one_loader() -> None:
    """Single-flight. Without it a cold slate fans out N roster sweeps."""
    calls = 0

    async def slow_loader() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return "value"

    cache = AsyncTTLCache(ttl_seconds=600)

    async def scenario() -> list[tuple[str, bool]]:
        return await asyncio.gather(*(cache.get_or_set("k", slow_loader) for _ in range(8)))

    results = asyncio.run(scenario())
    assert calls == 1, "eight concurrent callers must trigger exactly one load"
    assert all(value == "value" for value, _ in results)


def test_a_slow_loader_does_not_pin_the_caller_past_the_deadline() -> None:
    """The actual bug: an upstream slower than the deadline used to hang the app."""

    async def very_slow_loader() -> str:
        await asyncio.sleep(30)
        return "never arrives"

    cache = AsyncTTLCache(ttl_seconds=600, deadline_seconds=0.05)

    async def scenario() -> float:
        started = asyncio.get_running_loop().time()
        with pytest.raises(FeedUnavailable):
            await cache.get_or_set("k", very_slow_loader)
        return asyncio.get_running_loop().time() - started

    elapsed = asyncio.run(scenario())
    assert elapsed < 1.0, f"caller waited {elapsed:.2f}s; the deadline was 0.05s"


def test_stale_data_is_served_when_a_refresh_blows_the_deadline() -> None:
    """Better a slightly old slate than none. Only degrade when there is nothing."""
    state = {"slow": False}

    async def loader() -> str:
        if state["slow"]:
            await asyncio.sleep(30)
            return "fresh"
        return "original"

    cache = AsyncTTLCache(ttl_seconds=0, deadline_seconds=0.05)

    async def scenario() -> tuple[str, bool]:
        first, _ = await cache.get_or_set("k", loader)
        assert first == "original"
        state["slow"] = True
        # TTL is 0, so this is a forced refresh that will blow the deadline.
        return await cache.get_or_set("k", loader)

    value, cached = asyncio.run(scenario())
    assert value == "original", "stale value should be served rather than hanging"
    assert cached is True


def test_work_survives_a_caller_giving_up() -> None:
    """The loader is shielded: a timed-out caller must not cancel it.

    Otherwise a slow upstream means every caller cancels, the cache never fills,
    and the app is permanently degraded until upstream recovers.
    """
    completed = False

    async def loader() -> str:
        nonlocal completed
        await asyncio.sleep(0.2)
        completed = True
        return "value"

    cache = AsyncTTLCache(ttl_seconds=600, deadline_seconds=0.05)

    async def scenario() -> tuple[str, bool]:
        with pytest.raises(FeedUnavailable):
            await cache.get_or_set("k", loader)  # gives up at 0.05s
        await asyncio.sleep(0.3)  # the shielded loader keeps running
        assert completed, "the abandoned loader should have finished on its own"
        return await cache.get_or_set("k", loader)  # now a cache hit

    value, cached = asyncio.run(scenario())
    assert (value, cached) == ("value", True)


def test_a_failing_loader_propagates_and_does_not_poison_the_key() -> None:
    """A dead upstream must still raise so historical_slate can take over."""
    attempts = 0

    async def flaky_loader() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FeedUnavailable("upstream down")
        return "recovered"

    cache = AsyncTTLCache(ttl_seconds=600)

    async def scenario() -> tuple[str, bool]:
        with pytest.raises(FeedUnavailable):
            await cache.get_or_set("k", flaky_loader)
        return await cache.get_or_set("k", flaky_loader)

    value, cached = asyncio.run(scenario())
    assert (value, cached) == ("recovered", False)
    assert attempts == 2, "a failed load must not leave a wedged in-flight entry"


def test_distinct_keys_do_not_block_each_other() -> None:
    """A slow rosters sweep must not stall an unrelated standings fetch."""

    async def slow() -> str:
        await asyncio.sleep(30)
        return "slow"

    async def fast() -> str:
        return "fast"

    cache = AsyncTTLCache(ttl_seconds=600, deadline_seconds=0.05)

    async def scenario() -> tuple[str, bool]:
        slow_call = asyncio.ensure_future(cache.get_or_set("slow-key", slow))
        result = await cache.get_or_set("fast-key", fast)
        slow_call.cancel()
        return result

    assert asyncio.run(scenario()) == ("fast", False)
