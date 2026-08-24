"""The parlay independence gate must key on the matchup, not the game instance.

`parlay_probability` multiplies the legs, which is only honest if the legs are
independent. The original gate compared `gamePk`s, and a doubleheader is two
distinct `gamePk`s between the same two clubs on the same day — so both legs
sailed through and were multiplied as independent. They are not: the same two
rosters and bullpens decide both games. The combined probability came out
overstated, and the EV and half-Kelly stake derived from it were both wrong.

These tests pin all three behaviours the gate owes: the doubleheader is
refused, the literal same-game parlay is still refused, and two genuinely
different matchups on the same date are still allowed. The last one matters as
much as the first — a gate that refuses everything is not a fix.

Nothing here touches `backend/odds.py`; the parlay math was never the bug.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend.main as main

SLATE_DATE = "2026-08-24"


def _game(game_pk: str, away: str, home: str, prob_home: float) -> dict[str, Any]:
    """One priced slate row, shaped like `feeds._price_game` returns."""
    return {
        "game_pk": game_pk,
        "game_date": SLATE_DATE,
        "away": away,
        "home": home,
        "model_prob_home": prob_home,
        "fair_lines": {"home": -120, "away": 100},
    }


# NYY @ BOS twice on one day is a doubleheader: two gamePks, one matchup.
# TBR @ TOR is a genuinely independent third game on the same date.
SLATE_GAMES = [
    _game("790001", "NYY", "BOS", 0.55),
    _game("790002", "NYY", "BOS", 0.55),
    _game("790003", "TBR", "TOR", 0.60),
    # Same two clubs, home and away reversed — a split doubleheader still
    # collides, because the pair in the key is unordered.
    _game("790004", "BOS", "NYY", 0.52),
]


@pytest.fixture()
def live_slate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the parlay path at a deterministic live slate."""

    async def fake_slate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"mode": "live", "date": SLATE_DATE, "games": SLATE_GAMES}

    monkeypatch.setattr(main, "get_slate", fake_slate)


def _price(legs: list[dict[str, str]]) -> Any:
    return TestClient(main.app).post("/api/parlay/price", json={"legs": legs})


def test_doubleheader_legs_are_refused(live_slate: None) -> None:
    """The bug this file exists for: two gamePks, same clubs, same day."""
    response = _price(
        [
            {"gamePk": "790001", "side": "home"},
            {"gamePk": "790002", "side": "home"},
        ]
    )
    assert response.status_code == 400
    envelope = response.json()
    assert envelope["error"]["code"] == "correlated_legs", envelope
    assert "SAME-MATCHUP LEGS REFUSED" in envelope["error"]["message"]


def test_doubleheader_refused_when_home_and_away_are_reversed(
    live_slate: None,
) -> None:
    """The team pair is unordered, so a flipped host still collides."""
    response = _price(
        [
            {"gamePk": "790001", "side": "home"},
            {"gamePk": "790004", "side": "away"},
        ]
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "correlated_legs"


def test_same_game_pk_is_still_refused(live_slate: None) -> None:
    """The original gate must survive the widening — `smoke_test` asserts it."""
    response = _price(
        [
            {"gamePk": "790001", "side": "home"},
            {"gamePk": "790001", "side": "away"},
        ]
    )
    assert response.status_code == 400
    envelope = response.json()
    assert envelope["error"]["code"] == "correlated_legs", envelope
    assert "SAME-GAME LEGS REFUSED" in envelope["error"]["message"]


def test_distinct_matchups_on_the_same_date_are_still_priced(
    live_slate: None,
) -> None:
    """A gate that refuses everything is not a fix."""
    response = _price(
        [
            {"gamePk": "790001", "side": "home"},
            {"gamePk": "790003", "side": "home"},
        ]
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert len(body["legs"]) == 2
    # 0.55 * 0.60 — the legs really are multiplied when they are independent.
    assert body["combined_prob"] == pytest.approx(0.33, abs=5e-5)


def test_three_legs_refuse_on_the_correlated_pair(live_slate: None) -> None:
    """One doubleheader leg poisons an otherwise-independent slip."""
    response = _price(
        [
            {"gamePk": "790003", "side": "home"},
            {"gamePk": "790001", "side": "home"},
            {"gamePk": "790002", "side": "away"},
        ]
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "correlated_legs"


def test_matchup_key_is_order_independent_and_date_scoped() -> None:
    """The key itself, in isolation."""
    game_one = _game("790001", "NYY", "BOS", 0.55)
    game_two = _game("790002", "NYY", "BOS", 0.55)
    reversed_hosts = _game("790004", "BOS", "NYY", 0.52)
    other_matchup = _game("790003", "TBR", "TOR", 0.60)
    next_day = {**game_one, "game_pk": "790005", "game_date": "2026-08-25"}

    assert main._matchup_key(game_one) == main._matchup_key(game_two)
    assert main._matchup_key(game_one) == main._matchup_key(reversed_hosts)
    assert main._matchup_key(game_one) != main._matchup_key(other_matchup)
    assert main._matchup_key(game_one) != main._matchup_key(next_day)
