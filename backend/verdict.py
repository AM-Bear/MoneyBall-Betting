"""Appendix A verdict engine: is there value at this price, and on which side?

Pure over probabilities and prices. This module does not load models, does not
fetch, and does not re-run the price chain -- `p_season` and `p_adj` arrive
already computed by `feeds._chain_probability`. It imports `backend.odds` and
the stdlib and nothing else, which is what makes the doctrine check mechanical:
no pulse, no injury flags, no wire can reach a verdict from here.

`backend.odds` is composed, never re-derived. Every quantity below is an
existing odds.py function call; writing the arithmetic inline would create a
second, silently divergent copy of the price math.

The rules are Appendix A of the v3 strategy doc
(`attached_assets/MONEYLINE_v3_Product_Strategy_and_UX_Plan_1787528143354.md:1304-1350`).
They are declared policy, not fitted coefficients: they do NOT come from
`load_models()`, and they ship in every response so a reader can audit the
rubric instead of taking the label on trust.

This engine is deliberately NOT the one behind `/api/matchup`. That endpoint
keeps its own vig-relative threshold and its one-sided `evaluation_side`
contract for the historical Matchups tool. Two rulesets coexist on purpose;
mixing them is the most likely way this ships wrong.
"""

from __future__ import annotations

from typing import Any

from backend.odds import (
    decimal_odds,
    edge_probability,
    market_vig,
    moneyline_to_probability,
    no_vig_edge,
    no_vig_probabilities,
    parlay_ev,
    probability_to_moneyline,
)

# Published rubric. Changeable only with a changelog entry [S:1322], and
# returned in full on every response so the thresholds a verdict was produced
# under travel with it.
THRESHOLDS: dict[str, Any] = {
    "avoid_ev": -0.05,
    "no_value_edge": 0.01,
    "candidate_ev": 0.04,
    "candidate_edge": 0.03,
    "sigma": 0.04,
    "stale_seconds": 900,
    "gp_hard_floor": 30,
    "gp_small_sample": 60,
    "gp_moderate": 100,
    "signal_provisional_n": 200,
    "signal_strong_gap": 1.0,
    "signal_moderate_gap": 0.5,
    "volatility_lower_price": -200,
    "volatility_higher_price": 150,
    "uncertainty_high_basis_spread": 0.05,
    "uncertainty_moderate_basis_spread": 0.03,
    # Said plainly rather than implied: sigma is a placeholder to be "revised
    # from live calibration" [S:1333]. `gap` is therefore a rule-of-thumb
    # scaling, not a measured statistic, and the signal labels stay
    # provisional until a bucket has 200 graded candidates.
    "sigma_is_provisional": True,
    "notes": {
        "sigma": "Placeholder pending live calibration; gap = edge / sigma is not a calibrated statistic.",
        "signal": "Signal labels are provisional until the bucket holds 200 graded candidates.",
        "thresholds": "Declared policy, not fitted coefficients. Not sourced from load_models().",
        "edge": (
            "With both prices entered, edge is measured against the no-vig market "
            "probability (what the book thinks); with one price, against the posted "
            "implied probability (break-even). EV is always at the posted price."
        ),
        "hold": (
            "Hold is the overround of the two entered prices: implied home plus "
            "implied away, minus 1. It is the book's margin on this market, not a "
            "model number. Below zero means the two prices sum under 100%: an "
            "arbitrage, or a typo."
        ),
    },
}

FROZEN_STATUSES = frozenset({"live", "final", "postponed"})
VALID_STATUSES = frozenset({"scheduled"}) | FROZEN_STATUSES

BET_CANDIDATE = "BET_CANDIDATE"
MARGINAL_VALUE = "MARGINAL_VALUE"
NO_VALUE = "NO_VALUE"
AVOID_AT_THIS_PRICE = "AVOID_AT_THIS_PRICE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def _sign(value: float) -> int:
    """Literal sign, so `agree` matches the spec's `sign(a) == sign(b)`.

    Not `(a > 0) == (b > 0)`: that folds an exactly-zero EV in with the
    negatives. An EV of zero is its own case and should not silently count as
    agreement with a loss.
    """
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _ev_at(probability: float, price: int) -> float:
    """Per-unit EV of a single bet.

    `parlay_ev` is named for the parlay path, but its body is
    `p * (decimal - 1) - (1 - p)` -- generic per-unit EV, and Appendix A's EV
    formula character for character. Reused rather than re-typed here so there
    is exactly one definition of EV in the codebase; a local copy would drift
    the first time either was touched.
    """
    return parlay_ev(probability, decimal_odds(price))


def _volatility(price: int) -> str:
    """Betting idiom, pinned in code because it reads ambiguously in review:
    "shorter" means a bigger favourite (more negative), "longer" a bigger
    underdog (more positive) [S:1335].
    """
    if price <= THRESHOLDS["volatility_lower_price"]:
        return "Lower"
    if price >= THRESHOLDS["volatility_higher_price"]:
        return "Higher"
    return "Typical"


def _uncertainty(min_gp: int | None, basis_spread: float | None) -> str:
    """`uncertainty` per [S:1335].

    The spec's Moderate arm reads "or the gap is at least 0.03". Read as the
    season-vs-adjusted spread, matching the High arm directly above it which
    uses the same quantity at 0.05. The alternative reading -- the signal
    `gap` (edge/sigma) -- would fire at an edge of 0.0012 and make almost
    every game Moderate, which cannot be the intent.
    """
    spread = abs(basis_spread) if basis_spread is not None else None
    if min_gp is None:
        # Not "Low". Low is a claim, and with no games-played count there is
        # nothing to base it on. Appendix A's vocabulary is Low/Moderate/High
        # because it assumed gp always exists; it does not.
        return "Unknown"
    if min_gp < THRESHOLDS["gp_small_sample"]:
        return "High"
    if spread is not None and spread >= THRESHOLDS["uncertainty_high_basis_spread"]:
        return "High"
    if min_gp < THRESHOLDS["gp_moderate"]:
        return "Moderate"
    if spread is not None and spread >= THRESHOLDS["uncertainty_moderate_basis_spread"]:
        return "Moderate"
    return "Low"


def _signal(gap: float, agree: bool | None, missing_ingredients: int) -> str:
    """Strong / Moderate / Weak per [S:1333].

    Strong needs `gap >= 1.0`, agreement, and complete data. `agree` is
    undefined when there is no `p_adj`, and the spec never says in prose what
    that does -- fixture 10 settles it: undefined caps at Moderate, exactly as
    a missing ingredient does. So undefined and False behave differently from
    each other and both differ from True; hence the explicit three-way branch.
    """
    strong_gap = gap >= THRESHOLDS["signal_strong_gap"]
    if strong_gap and agree is True and missing_ingredients == 0:
        return "Strong"
    # Everything at gap >= 0.5 is Moderate, which subsumes the spec's separate
    # "gap >= 1.0 with one ingredient missing" arm -- that is fixture 10's
    # case, and it lands here rather than in a branch of its own.
    if gap >= THRESHOLDS["signal_moderate_gap"]:
        return "Moderate"
    return "Weak"


def _edge(probability: float, price: int, opposite_price: int | None) -> float:
    """Model probability minus the market, on whichever basis the market allows.

    Two prices: the no-vig probability, what the book actually thinks
    (`no_vig_edge`). One price: the posted implied probability, break-even
    (`edge_probability`). Both compose odds.py; neither re-derives it. The
    verdict and the season-only basis note both call this, so they cannot
    disagree about which market they were judged against.
    """
    if opposite_price is not None:
        return no_vig_edge(probability, price, opposite_price)
    return edge_probability(probability, price)


def _evaluate_side(
    *,
    p_season: float,
    p_adj: float | None,
    price: int | None,
    opposite_price: int | None,
    min_gp: int | None,
    starters_confirmed: bool,
    price_age_s: float | None,
    sample_gate: str | None,
) -> dict[str, Any]:
    """One side, gates first, then the verdict table."""
    p_eval = p_adj if p_adj is not None else p_season
    p_basis = "adj" if p_adj is not None else "season"

    # `p_adj` null IS the starters-unconfirmed condition per the gate table; a
    # caller claiming confirmation without supplying an adjusted probability
    # does not get the benefit of the doubt.
    starters_unconfirmed = p_adj is None or not starters_confirmed
    stale = (
        price_age_s is not None
        and price_age_s > THRESHOLDS["stale_seconds"]
    )
    small_sample = (
        min_gp is not None and min_gp < THRESHOLDS["gp_small_sample"]
    )

    side: dict[str, Any] = {
        "p_eval": round(p_eval, 4),
        "p_basis": p_basis,
        "p_season": round(p_season, 4),
        "p_adj": round(p_adj, 4) if p_adj is not None else None,
        "price": price,
        "chance_lose": round(1 - p_eval, 4),
        # The fair line is published even when nothing else can be: it is the
        # model's own answer and does not depend on a price existing.
        "fair_line": probability_to_moneyline(p_eval),
        "implied": None,
        "breakeven": None,
        "market_prob": None,
        "edge_basis": None,
        "edge_pts": None,
        "edge_vs_implied_pts": None,
        "ev_per_100": None,
        "verdict": None,
        "verdict_reason": None,
        "signal": None,
        "signal_provisional": None,
        "gap": None,
        "volatility": None,
        "uncertainty": _uncertainty(
            min_gp,
            (p_adj - p_season) if p_adj is not None else None,
        ),
        "agree": None,
        "flags": [],
        "basis_note": None,
    }

    flags: list[str] = []
    if starters_unconfirmed:
        flags.append("starters_unconfirmed")
    if small_sample:
        flags.append("small_sample")

    # Gate: not enough season to mean anything -- or no way to tell. Both
    # refuse, but they refuse for different reasons and say so separately.
    # "early_season" is a claim about the season; "gp_unavailable" is a claim
    # about our own data. Collapsing them would have the desk announce "not
    # enough of the season on the board" in late August because a team lookup
    # missed, which is a false statement dressed as a refusal.
    if sample_gate is not None:
        flags.append(sample_gate)
        side["verdict"] = INSUFFICIENT_DATA
        side["verdict_reason"] = sample_gate
        side["flags"] = flags
        return side

    # Gate: no price. The model chance and the fair line still publish; edge,
    # EV and signal do not, because there is nothing to be edgy against.
    if price is None:
        flags.append("no_price")
        side["verdict"] = INSUFFICIENT_DATA
        side["verdict_reason"] = "no_price"
        side["flags"] = flags
        return side

    if stale:
        flags.append("stale")

    # Break-even and the posted implied probability are the same number, so
    # the two provably agree rather than agreeing by coincidence. The
    # thresholded edge is measured against the market on whichever basis the
    # entered prices allow (v4 1.3): with the opposite price known, the no-vig
    # probability -- the posted price understates every edge by the vig
    # share, more so on the favourite; with one price, break-even. EV is
    # always at the posted price: that is the number the bet is paid at.
    implied = moneyline_to_probability(price)
    edge_implied = edge_probability(p_eval, price)
    if opposite_price is not None:
        market_prob: float | None = no_vig_probabilities(price, opposite_price)[0]
        edge_basis = "no_vig"
    else:
        market_prob = None
        edge_basis = "implied"
    edge = _edge(p_eval, price, opposite_price)
    ev = _ev_at(p_eval, price)
    gap = edge / THRESHOLDS["sigma"]

    agree: bool | None = None
    ev_season = None
    if p_adj is not None:
        ev_season = _ev_at(p_season, price)
        agree = _sign(ev_season) == _sign(ev)

    would_be_candidate = (
        ev >= THRESHOLDS["candidate_ev"] and edge >= THRESHOLDS["candidate_edge"]
    )
    is_candidate = would_be_candidate and (p_adj is None or agree is True)
    if would_be_candidate and agree is False:
        flags.append("prices_disagree")

    # Verdict table, evaluated top-down. AVOID's rule is a strict subset of
    # NO_VALUE's, so order is load-bearing: fixture 5 (ev -0.007) is the case
    # that separates them and it is NO_VALUE.
    if ev <= THRESHOLDS["avoid_ev"]:
        verdict, reason = AVOID_AT_THIS_PRICE, "ev_at_or_below_avoid_threshold"
    elif ev <= 0 or edge < THRESHOLDS["no_value_edge"]:
        verdict, reason = NO_VALUE, "ev_not_positive" if ev <= 0 else "edge_below_minimum"
    elif is_candidate:
        verdict, reason = BET_CANDIDATE, "ev_and_edge_clear_candidate_thresholds"
    else:
        verdict = MARGINAL_VALUE
        reason = (
            "candidate_thresholds_met_but_prices_disagree"
            if would_be_candidate
            else "positive_edge_below_candidate_thresholds"
        )

    if verdict in (BET_CANDIDATE, MARGINAL_VALUE):
        missing = sum((starters_unconfirmed, small_sample, stale))
        side["signal"] = _signal(gap, agree, missing)
        # Hardcoded true, and the reason travels with it: the record cannot
        # yet count graded candidates per bucket, so no signal label has been
        # checked against an outcome.
        side["signal_provisional"] = True
        side["gap"] = round(gap, 2)

    # Fixture 7: evaluated on the adjusted price the side is NO_VALUE, but the
    # season price alone would have shown value. Saying so is the difference
    # between a refusal a reader can audit and one that looks arbitrary.
    if (
        p_adj is not None
        and ev_season is not None
        and verdict in (NO_VALUE, AVOID_AT_THIS_PRICE)
    ):
        season_edge = _edge(p_season, price, opposite_price)
        if ev_season > 0 and season_edge >= THRESHOLDS["no_value_edge"]:
            side["basis_note"] = (
                "Evaluated on the starter-adjusted chance. The season-only "
                "price would have shown value here."
            )

    side.update(
        {
            "implied": round(implied, 4),
            "breakeven": round(implied, 4),
            "market_prob": round(market_prob, 4) if market_prob is not None else None,
            "edge_basis": edge_basis,
            "edge_pts": round(edge * 100, 1),
            "edge_vs_implied_pts": round(edge_implied * 100, 1),
            "ev_per_100": round(ev * 100, 1),
            "verdict": verdict,
            "verdict_reason": reason,
            "volatility": _volatility(price),
            "agree": agree,
            "flags": flags,
        }
    )
    # Raw, unrounded values for callers that must compare against thresholds
    # rather than display. Rounding first creates a boundary lie: a raw edge of
    # 0.0096 displays as +1.0 points, which reads as clearing `edge >= 0.01`
    # while the raw comparison correctly fails it.
    side["raw"] = {
        "edge": edge,
        "edge_implied": edge_implied,
        "market_prob": market_prob,
        "ev": ev,
        "implied": implied,
        "gap": gap,
    }
    return side


def evaluate(
    *,
    p_season_home: float,
    p_adj_home: float | None = None,
    price_home: int | None = None,
    price_away: int | None = None,
    gp_home: int | None = None,
    gp_away: int | None = None,
    starters_confirmed: bool = False,
    price_age_s: float | None = None,
    status: str = "scheduled",
    book: str | None = None,
) -> dict[str, Any]:
    """Evaluate both sides of one game and name the value side, if any.

    Both sides, always. A one-price endpoint would reproduce the exact
    one-sidedness this engine exists to fix: today the card evaluates the away
    team only, so a favourable price on the home side is never surfaced.

    Only home probabilities are supplied; away is `1 - p_home`, matching
    `_price_game` and `matchup`. Accepting both would let a caller submit an
    incoherent pair.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown game status: {status!r}")

    p_season_away = 1 - p_season_home
    p_adj_away = (1 - p_adj_home) if p_adj_home is not None else None

    # A missing games-played count still gates -- it must never default to a
    # comfortable number -- but it gates under its own name.
    known_gp = [gp for gp in (gp_home, gp_away) if gp is not None]
    min_gp = min(known_gp) if len(known_gp) == 2 else None
    if min_gp is None:
        sample_gate = "gp_unavailable"
    elif min_gp < THRESHOLDS["gp_hard_floor"]:
        sample_gate = "early_season"
    else:
        sample_gate = None

    common = {
        "min_gp": min_gp,
        "starters_confirmed": starters_confirmed,
        "price_age_s": price_age_s,
        "sample_gate": sample_gate,
    }
    home = _evaluate_side(
        p_season=p_season_home, p_adj=p_adj_home,
        price=price_home, opposite_price=price_away, **common
    )
    away = _evaluate_side(
        p_season=p_season_away, p_adj=p_adj_away,
        price=price_away, opposite_price=price_home, **common
    )

    # v4 1.4: what the book charges on this market. A fact about the two
    # entered prices, like `price` itself, not an artifact of the evaluation,
    # so it is set before any gate and survives a frozen game. Negative is a
    # real state (the prices sum under 1), not an error -- odds.py agrees.
    hold: float | None = None
    if price_home is not None and price_away is not None:
        try:
            hold = market_vig(price_home, price_away)
        except ValueError:
            # A price odds.py cannot read (zero, non-finite). On the ungated path the
            # side evaluation above has already raised for it; on a gated path the
            # sides returned before touching the price, and hold must not turn that
            # refusal into an exception. No number is the honest answer here.
            hold = None

    # The lean is price-independent -- it is what the model thinks, full stop.
    # Keeping it separate from the value side is the entire point of this
    # payload: conflating the two is the failure being fixed.
    # Raw, not the rounded display value: p_eval 0.50004 rounds to 0.5 and
    # would suppress the lean entirely, taking the divergence banner with it.
    p_home_eval = p_adj_home if p_adj_home is not None else p_season_home
    if p_home_eval > 0.5:
        lean_side = "home"
    elif p_home_eval < 0.5:
        lean_side = "away"
    else:
        lean_side = None

    frozen = status in FROZEN_STATUSES
    game: dict[str, Any] = {
        "side": None,
        "verdict": None,
        "verdict_reason": None,
        "lean_side": lean_side,
        "lean_differs_from_value": False,
        "avoid_note": None,
        "frozen": frozen,
        "status": status,
        "book": book,
        "hold_pct": round(hold * 100, 1) if hold is not None else None,
        "takeaway": None,
    }

    if frozen:
        # Not a refusal of the user: pre-game evaluation is frozen once a game
        # starts so the graded record cannot be rewritten after the fact.
        game["verdict_reason"] = "status_frozen"
        game["takeaway"] = (
            f"No pre-game verdict: this game is {status}. "
            "Evaluation is frozen once a game starts so the record stays honest."
        )
        for side in (home, away):
            side["verdict"] = None
            side["verdict_reason"] = "status_frozen"
            side["signal"] = None
            side["signal_provisional"] = None
            # Flags go too. They are artifacts of an evaluation that did not
            # happen, not facts about the game: leaving `no_price` on a frozen
            # card renders a chip telling the reader to enter a price, next to
            # a price input the card does not show for a started game.
            side["flags"] = []
        return _envelope(home, away, game, gp_home, gp_away, min_gp)

    if sample_gate is not None:
        game["verdict"] = INSUFFICIENT_DATA
        game["verdict_reason"] = sample_gate
        game["takeaway"] = (
            "Not enough of the season on the board to price this honestly. "
            "The model's chance is shown; no value call is made."
            if sample_gate == "early_season"
            else "Games played is unavailable for one of these teams, so the "
            "sample behind this price cannot be stated. No value call is made."
        )
        return _envelope(home, away, game, gp_home, gp_away, min_gp)

    # No price anywhere is a data state, not a judgment. If both sides are
    # gated there is nothing to have an opinion about, and the game must say
    # so rather than inheriting "no side clears the minimum edge" -- which
    # reads as a considered rejection of prices the reader never entered.
    if home["verdict"] == INSUFFICIENT_DATA and away["verdict"] == INSUFFICIENT_DATA:
        game["verdict"] = INSUFFICIENT_DATA
        game["verdict_reason"] = home["verdict_reason"]
        game["takeaway"] = (
            "No book price is entered, so there is no value call to make. "
            "The model's chance and fair price are shown; the desk quotes no "
            "edge against a price it does not have."
        )
        return _envelope(home, away, game, gp_home, gp_away, min_gp)

    # Game verdict: the best side by EV among candidates and marginals.
    contenders = [
        (name, side)
        for name, side in (("home", home), ("away", away))
        if side["verdict"] in (BET_CANDIDATE, MARGINAL_VALUE)
    ]
    if contenders:
        # Tie-break: EV, then edge, then home. A real book's vig forbids two
        # positive-EV sides; a typo in a manually entered price does not, so
        # the order is pinned rather than left to dict iteration.
        name, side = max(
            contenders,
            key=lambda item: (
                item[1]["raw"]["ev"],
                item[1]["raw"]["edge"],
                item[0] == "home",
            ),
        )
        game["side"] = name
        game["verdict"] = side["verdict"]
        game["verdict_reason"] = side["verdict_reason"]
    else:
        game["verdict"] = NO_VALUE
        game["verdict_reason"] = "no_side_clears_the_minimum_edge"

    avoided = [
        name
        for name, side in (("home", home), ("away", away))
        if side["verdict"] == AVOID_AT_THIS_PRICE
    ]
    if avoided:
        verb = "are" if len(avoided) == 2 else "is"
        game["avoid_note"] = (
            f"{' and '.join(name.title() for name in avoided)} {verb} priced "
            "clearly against you at this number."
        )

    game["lean_differs_from_value"] = (
        game["side"] is not None
        and lean_side is not None
        and game["side"] != lean_side
    )
    game["takeaway"] = _takeaway(game, home, away, book)
    return _envelope(home, away, game, gp_home, gp_away, min_gp)


def _takeaway(
    game: dict[str, Any],
    home: dict[str, Any],
    away: dict[str, Any],
    book: str | None,
) -> str:
    """One sentence naming the value side, and saying when it is not the lean.

    Deliberately minimal. The full copy generator is Appendix B / Tier 3
    item 4; what Appendix A requires here is only that the takeaway name the
    value side and state when it differs from the lean.
    """
    where = book or "your price"
    if game["side"] is None:
        unpriced = [
            name
            for name, side in (("home", home), ("away", away))
            if side["verdict_reason"] == "no_price"
        ]
        if unpriced:
            # Name what was actually judged. Saying "no side" when only one
            # side was ever scored claims a rejection that never happened.
            scored = "away" if unpriced == ["home"] else "home"
            base = (
                f"The {scored} price does not clear the minimum edge. "
                f"No price is entered for the {unpriced[0]} side, so it was "
                "not judged."
            )
        else:
            base = f"Neither price clears the minimum edge at {where}."
        return f"{base} {game['avoid_note']}" if game["avoid_note"] else base

    side = home if game["side"] == "home" else away
    label = "BET CANDIDATE" if side["verdict"] == BET_CANDIDATE else "MARGINAL"
    base = (
        f"{game['side'].title()} is the value side at {where}: "
        f"{label}, edge {side['edge_pts']:+.1f} pts, "
        f"EV {side['ev_per_100']:+.1f} per 100."
    )
    if game["lean_differs_from_value"]:
        base += (
            f" Note this is not the lean \u2014 the model leans "
            f"{game['lean_side']}, but the price makes the other side the "
            "better bet."
        )
    return base


def _envelope(
    home: dict[str, Any],
    away: dict[str, Any],
    game: dict[str, Any],
    gp_home: int | None,
    gp_away: int | None,
    min_gp: int | None,
) -> dict[str, Any]:
    return {
        "sides": {"home": home, "away": away},
        "game": game,
        "sample": {
            "gp_home": gp_home,
            "gp_away": gp_away,
            "label": f"THRU {min_gp} GP" if min_gp is not None else "GP UNKNOWN",
        },
        "thresholds": THRESHOLDS,
    }
