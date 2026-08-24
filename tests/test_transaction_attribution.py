"""A transaction belongs to its major-league club, not its affiliate.

`get_transactions` sent no `sportId`, so the feed returned every affiliated
league — Mexican League, Arizona Complex League — roughly 4x the rows, none of
them majors-relevant. And the team was resolved as `toTeam or fromTeam`, so an
option-down ("to Buffalo Bisons, from Toronto Blue Jays") was attributed to the
affiliate; `_team_code` then coined a phantom code from its initials.

Scoping to sportId=1 fixes the first. It cannot fix the second — "optioned to
Buffalo Bisons" is a legitimate MLB transaction with an affiliate on one end —
so the side that is a real MLB club is the one the wire means.
"""

from __future__ import annotations

from backend.feeds import TEAM_CODES, _majors_side, _team_code


def _move(to: str | None, frm: str | None) -> dict:
    return {
        "toTeam": {"name": to} if to else None,
        "fromTeam": {"name": frm} if frm else None,
    }


def test_an_option_down_is_attributed_to_the_parent_club() -> None:
    """The bug: toTeam is the affiliate, so the move looked like the Bisons'."""
    assert _majors_side(_move("Buffalo Bisons", "Toronto Blue Jays")) == "Toronto Blue Jays"


def test_a_call_up_is_attributed_to_the_parent_club() -> None:
    assert _majors_side(_move("Toronto Blue Jays", "Buffalo Bisons")) == "Toronto Blue Jays"


def test_a_trade_between_two_clubs_keeps_the_receiving_side() -> None:
    """Both sides are MLB, so the existing toTeam preference still holds."""
    assert _majors_side(_move("Boston Red Sox", "New York Yankees")) == "Boston Red Sox"


def test_a_signing_with_only_one_side_still_resolves() -> None:
    assert _majors_side(_move("Seattle Mariners", None)) == "Seattle Mariners"
    assert _majors_side(_move(None, "Seattle Mariners")) == "Seattle Mariners"


def test_a_purely_minor_league_move_falls_back_rather_than_vanishing() -> None:
    """No MLB side: keep something rather than dropping the row silently."""
    assert _majors_side(_move("Buffalo Bisons", "Durham Bulls")) == "Buffalo Bisons"


def test_no_teams_at_all_resolves_to_none() -> None:
    assert _majors_side({}) is None
    assert _majors_side(_move(None, None)) is None


def test_the_resolved_side_produces_a_real_code_not_initials() -> None:
    """End to end: the attribution is what keeps _team_code off the fallback."""
    parent = _majors_side(_move("Buffalo Bisons", "Toronto Blue Jays"))
    assert parent is not None
    assert _team_code(parent) == "TOR"
    assert _team_code(parent) in set(TEAM_CODES.values())
