"""De-vigging a two-sided market.

`entered_line` is the cautionary tale this module is trying not to repeat: a
number the product collects, reads in three places, and never writes. These
functions exist so the verdict engine can measure an edge against what the book
actually thinks rather than against its vig-inflated posted price.
"""
from __future__ import annotations

import pytest

from backend.odds import (
    market_vig,
    moneyline_to_probability,
    no_vig_edge,
    no_vig_probabilities,
)


def test_probabilities_sum_to_one():
    home, away = no_vig_probabilities(-110, -110)
    assert home + away == pytest.approx(1.0)


def test_symmetric_market_is_a_coin_flip():
    home, away = no_vig_probabilities(-110, -110)
    assert home == pytest.approx(0.5)
    assert away == pytest.approx(0.5)


def test_hand_checked_case():
    # -150 / +130.  implied: 150/250 = 0.6, 100/230 = 0.434782...
    # total 1.034782..., so fair home = 0.6 / 1.034782... = 0.579831...
    home, away = no_vig_probabilities(-150, 130)
    assert home == pytest.approx(0.5798319327731093)
    assert away == pytest.approx(0.4201680672268907)
    assert home + away == pytest.approx(1.0)


def test_removes_exactly_the_overround_market_vig_reports():
    line_a, line_b = -150, 130
    hold = market_vig(line_a, line_b)
    total = moneyline_to_probability(line_a) + moneyline_to_probability(line_b)
    assert total == pytest.approx(1 + hold)
    home, away = no_vig_probabilities(line_a, line_b)
    assert home == pytest.approx(moneyline_to_probability(line_a) / (1 + hold))
    assert away == pytest.approx(moneyline_to_probability(line_b) / (1 + hold))


def test_arbitrage_is_a_market_state_not_an_error():
    # Both sides plus money: the implied total is below 1.  Normalising is still
    # the right operation, and it must not raise.
    home, away = no_vig_probabilities(105, 110)
    assert home + away == pytest.approx(1.0)
    assert moneyline_to_probability(105) + moneyline_to_probability(110) < 1


def test_stripping_the_margin_raises_the_disagreement_on_both_sides():
    """De-vigging lowers both implied probabilities, so both edges rise.

    The measure this replaces is not wrong, it answers a different question:
    `edge_probability` against the raw price is the +EV test, and you must beat
    the vig to profit.  `no_vig_edge` is the model-disagreement test.
    """
    fav_one_sided = 0.62 - moneyline_to_probability(-150)
    fav_two_sided = no_vig_edge(0.62, -150, 130)
    dog_one_sided = 0.46 - moneyline_to_probability(130)
    dog_two_sided = no_vig_edge(0.46, 130, -150)

    assert fav_two_sided > fav_one_sided
    assert dog_two_sided > dog_one_sided


def test_the_favourite_absorbs_more_of_the_overround():
    """The asymmetry proportional de-vigging actually produces."""
    fav_shift = moneyline_to_probability(-150) - no_vig_probabilities(-150, 130)[0]
    dog_shift = moneyline_to_probability(130) - no_vig_probabilities(130, -150)[0]

    assert fav_shift > dog_shift
    assert fav_shift + dog_shift == pytest.approx(market_vig(-150, 130))


def test_edge_is_zero_when_the_model_agrees_with_the_stripped_market():
    home, _ = no_vig_probabilities(-150, 130)
    assert no_vig_edge(home, -150, 130) == pytest.approx(0.0)


def test_a_zero_line_is_still_rejected():
    with pytest.raises(ValueError):
        no_vig_probabilities(0, -110)
