"""Transparent, unit-tested odds calculations used throughout MONEYLINE."""

from __future__ import annotations

from math import isfinite


def probability_to_moneyline(probability: float) -> int:
    """Convert a probability into an American line, rounded to the nearest 5."""
    if not 0 < probability < 1:
        raise ValueError("Probability must be strictly between 0 and 1.")

    raw_line = (
        -100 * probability / (1 - probability)
        if probability >= 0.5
        else 100 * (1 - probability) / probability
    )
    return int(round(raw_line / 5.0) * 5)


def moneyline_to_probability(line: int | float) -> float:
    """Convert a non-zero American moneyline to its implied probability."""
    if not isfinite(line) or line == 0:
        raise ValueError("Moneyline must be a non-zero finite number.")
    return abs(line) / (abs(line) + 100) if line < 0 else 100 / (line + 100)


def edge_probability(model_probability: float, line: int | float) -> float:
    """Return model probability minus the market's break-even probability."""
    return model_probability - moneyline_to_probability(line)


def market_vig(line_a: int | float, line_b: int | float) -> float:
    """Return a two-sided market's overround as a probability."""
    return (
        moneyline_to_probability(line_a)
        + moneyline_to_probability(line_b)
        - 1
    )


def no_vig_probabilities(
    line_a: int | float, line_b: int | float
) -> tuple[float, float]:
    """Strip a two-sided market's overround, returning both true probabilities.

    A book's two posted prices imply probabilities that sum to more than 1; the
    excess is its margin, and `market_vig` reports it. Normalising each side by
    that sum recovers what the book actually thinks, which is the only market
    number a model edge should be measured against.

    This answers a different question than `edge_probability`, and the two are
    not interchangeable:

    - "Is this bet +EV at this price?" -> `edge_probability`, against the raw
      implied probability. Break-even is break-even; you must beat the price the
      book is actually charging, vig included, to make money.
    - "Does the model disagree with the market?" -> this function. Model quality,
      CLV, and calibration are all measured against what the book thinks, not
      against what it charges.

    Using the raw implied probability for the second question understates the
    disagreement on *both* sides, because stripping the margin lowers both
    implied probabilities. It understates it more on the favourite, which
    absorbs more of the overround in absolute terms.

    Method is proportional (multiplicative) de-vigging: the standard choice, and
    the only one derivable from the two prices alone. It distributes the margin
    in proportion to each side's implied probability, which slightly favours the
    favourite relative to Shin or power methods. Those need a parameter this
    function is not given, so the simpler method is the honest one here.

    An arbitrage — a sum below 1 — is a real market state, not an error, and
    normalises the same way.
    """
    implied_a = moneyline_to_probability(line_a)
    implied_b = moneyline_to_probability(line_b)
    total = implied_a + implied_b
    if total <= 0:
        raise ValueError("A two-sided market must imply a positive probability.")
    return implied_a / total, implied_b / total


def no_vig_edge(
    model_probability: float, line: int | float, opposite_line: int | float
) -> float:
    """Return model probability minus the de-vigged market probability.

    The two-sided analogue of `edge_probability`. `line` is the side being
    priced; `opposite_line` is the other side of the same market, needed only to
    strip the margin.
    """
    fair_probability, _ = no_vig_probabilities(line, opposite_line)
    return model_probability - fair_probability


def decimal_odds(line: int | float) -> float:
    """Return decimal odds (including stake) for an American moneyline."""
    if line == 0:
        raise ValueError("Moneyline must be non-zero.")
    return 1 + (100 / abs(line) if line < 0 else line / 100)


def half_kelly_fraction(model_probability: float, line: int | float) -> float:
    """Return a capped half-Kelly paper stake fraction for the supplied side."""
    if not 0 < model_probability < 1:
        raise ValueError("Model probability must be strictly between 0 and 1.")

    odds = decimal_odds(line) - 1
    full_kelly = (model_probability * (odds + 1) - 1) / odds
    return max(0.0, full_kelly / 2)


def decimal_to_american(decimal: float) -> int:
    """Convert decimal odds (including stake) back to an American line."""
    if decimal <= 1:
        raise ValueError("Decimal odds must exceed 1.")
    if decimal >= 2:
        return int(round((decimal - 1) * 100))
    return -int(round(100 / (decimal - 1)))


def parlay_probability(probabilities: list[float]) -> float:
    """Combined probability of independent legs — Π p_i.

    The independence assumption is stated by every caller; correlated
    (same-game) legs must be rejected before this function is reached.
    """
    if not 2 <= len(probabilities) <= 6:
        raise ValueError("Parlays are limited to 2–6 legs.")
    combined = 1.0
    for probability in probabilities:
        if not 0 < probability < 1:
            raise ValueError("Every leg probability must be strictly between 0 and 1.")
        combined *= probability
    return combined


def parlay_book_decimal(lines: list[int | float]) -> float:
    """Book parlay payout: convert each American leg to decimal and multiply."""
    payout = 1.0
    for line in lines:
        payout *= decimal_odds(line)
    return payout


def parlay_ev(probability: float, decimal_payout: float) -> float:
    """EV per 1 unit staked: P·(decimal − 1) − (1 − P)."""
    if not 0 < probability < 1:
        raise ValueError("Probability must be strictly between 0 and 1.")
    return probability * (decimal_payout - 1) - (1 - probability)


def parlay_vig_comparison(
    leg_probabilities: list[float],
    parlay_book_line: int | float | None = None,
    leg_book_line: int | float = -110,
) -> dict[str, float | int]:
    """The vig-compounding demo: house take on a parlay vs the same legs single.

    Uses standard −110 legs as the reference book price for singles (stated),
    and the actual entered parlay payout when one exists — otherwise the
    standard book parlay built by compounding −110 legs.
    """
    n = len(leg_probabilities)
    combined = parlay_probability(leg_probabilities)
    standard_decimal = parlay_book_decimal([leg_book_line] * n)
    book_decimal = (
        decimal_odds(parlay_book_line) if parlay_book_line is not None else standard_decimal
    )
    # Expected loss per unit staked at the model's probabilities.
    parlay_take = -(combined * book_decimal - 1)
    singles_take = sum(
        -(p * decimal_odds(leg_book_line) - 1) for p in leg_probabilities
    ) / n
    return {
        "legs": n,
        "leg_reference_line": int(leg_book_line),
        "standard_book_parlay_line": decimal_to_american(standard_decimal),
        "fair_parlay_line": probability_to_moneyline(combined),
        "parlay_house_take_pct": round(parlay_take * 100, 2),
        "singles_house_take_pct": round(singles_take * 100, 2),
    }


def pythagorean_strength(runs_scored: float, runs_allowed: float) -> float:
    """Estimate team strength using baseball's Pythagorean expectation."""
    rs_squared = max(runs_scored, 1) ** 2
    ra_squared = max(runs_allowed, 1) ** 2
    return rs_squared / (rs_squared + ra_squared)


def log5_probability(team_a_strength: float, team_b_strength: float) -> float:
    """Combine two Pythagorean strengths using Bill James' log5 formula."""
    denominator = (
        team_a_strength
        + team_b_strength
        - 2 * team_a_strength * team_b_strength
    )
    if denominator == 0:
        return 0.5
    return (team_a_strength - team_a_strength * team_b_strength) / denominator