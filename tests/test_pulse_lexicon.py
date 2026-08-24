"""The media-pulse lexicon must score the event that happened, once.

Pulse is disclosed context and never moves a price, so these are not pricing
bugs — but the score is published with its own evidence list so a reader can
re-derive it in ten seconds, and it was not re-derivable. Three defects:

* `_matches` had a leading word boundary and no trailing one, so "torn"
  matched "tornado" and a weather note scored as an injury.
* "losing streak" is negative and contains "streak", which is positive. One
  phrase scored +1 and −1: no net move, but it inflated the denominator and
  diluted every other item in the window.
* "clinched" contains "clinch" and both are positive, so a clinch counted
  twice — the same defect, unreported, in the other direction.
"""

from __future__ import annotations

from backend.analytics import score_pulse_items


def _score(*texts: str) -> dict:
    return score_pulse_items([{"text": t} for t in texts])


# --------------------------------------------------------------------------
# Word boundaries
# --------------------------------------------------------------------------


def test_torn_does_not_match_tornado() -> None:
    result = _score("Game postponed after a tornado warning in the area")
    assert result["negative_matches"] == 0
    assert result["pulse"] == 0


def test_torn_still_matches_a_real_injury() -> None:
    result = _score("Outfielder has a torn labrum and will miss the season")
    assert "torn" in result["evidence"][0]["matched_negative"]


def test_a_short_inflection_still_matches() -> None:
    """The lexicon lists most variants but relies on stems for a few."""
    assert _score("Shortstop sprained his ankle")["negative_matches"] >= 1
    assert _score("The winning streaks continued")["positive_matches"] >= 1


def test_a_longer_word_does_not_match_the_stem() -> None:
    """"streak" must not fire on an unrelated longer word."""
    result = _score("The pitcher was streaklessly consistent")
    assert result["positive_matches"] == 0


# --------------------------------------------------------------------------
# Overlapping lexicon entries
# --------------------------------------------------------------------------


def test_losing_streak_scores_negative_only() -> None:
    """The reported bug: one phrase counted in both directions."""
    result = _score("Club drops another one, now on a six-game losing streak")
    assert result["negative_matches"] == 1
    assert result["positive_matches"] == 0
    assert result["pulse"] == -100
    evidence = result["evidence"][0]
    assert evidence["matched_negative"] == ["losing streak"]
    assert evidence["matched_positive"] == []


def test_a_winning_streak_is_still_positive() -> None:
    """The dedup must not swallow the plain positive case."""
    result = _score("Club rides a seven-game streak into the weekend")
    assert result["positive_matches"] == 1
    assert result["negative_matches"] == 0
    assert result["pulse"] == 100


def test_clinched_counts_once_not_twice() -> None:
    """Unreported instance of the same defect: "clinched" contains "clinch"."""
    result = _score("Club clinched the division last night")
    assert result["positive_matches"] == 1
    assert result["evidence"][0]["matched_positive"] == ["clinched"]


def test_a_diluted_window_now_scores_correctly() -> None:
    """Why the double-count mattered: it moved the score, not just the counts.

    One losing streak plus one genuine positive used to read 2 positive /
    1 negative -> +33, calling a mixed week net-good. It is 1-1 -> 0.
    """
    result = _score(
        "Club drops another one, now on a six-game losing streak",
        "Ace returns from the injured list to a walk-off win",
    )
    assert result["pulse"] == 0


# --------------------------------------------------------------------------
# The published evidence must stay re-derivable.
# --------------------------------------------------------------------------


def test_counts_agree_with_the_published_evidence() -> None:
    """The score's own receipts must add up to the score."""
    result = _score(
        "Club clinched the division after a walk-off",
        "Reliever placed on the 15-day IL with a strained oblique",
        "Nothing newsworthy happened today",
    )
    positives = sum(len(e["matched_positive"]) for e in result["evidence"])
    negatives = sum(len(e["matched_negative"]) for e in result["evidence"])
    assert positives == result["positive_matches"]
    assert negatives == result["negative_matches"]
    assert result["items_scanned"] == 3
    assert result["items_matched"] == len(result["evidence"])
    total = positives + negatives
    assert result["pulse"] == round(100 * (positives - negatives) / total)


def test_no_matches_scores_zero_not_a_division_error() -> None:
    result = _score("A routine day at the ballpark")
    assert result["pulse"] == 0
    assert result["items_matched"] == 0
