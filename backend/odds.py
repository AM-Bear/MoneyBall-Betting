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