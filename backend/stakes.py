"""Stake policy: the cap on the half-Kelly paper stake (v4-plan 4.1).

`odds.half_kelly_fraction` says "capped" and is not: 0.99 at +1000 returns 0.4945, half the
bankroll. The plan keeps odds.py exactly as it is -- smoke_test pins its raw values -- and
caps the number in the display layer instead: every API response that shows a stake shows
it capped, with the raw value, the cap and whether it bound shipped as receipts, and the
cap adjustable per request within a policy ceiling.

Declared policy, not a fitted coefficient: it does not come from load_models(), and it
travels with every stake so the number a reader sees carries the rule that produced it.
"""

STAKE_CAP_DEFAULT = 0.02  # 2% of bankroll: the top of the plan's 1-2%.
STAKE_CAP_MAX = 0.05  # A caller may loosen the cap, never past this.

STAKE_POLICY = {
    "default_cap": STAKE_CAP_DEFAULT,
    "max_cap": STAKE_CAP_MAX,
    "basis": "half_kelly",
    "note": (
        "min(half-Kelly, cap). Declared policy, not a fitted coefficient; odds.py is "
        "unchanged and its raw value ships alongside."
    ),
}


def capped_stake(raw_fraction: float, cap: float | None = None) -> dict[str, float | bool]:
    """Cap a raw stake fraction and return the receipt with it.

    `raw_fraction` is what odds.py computed (already 0 for a non-positive edge). `cap` is
    the per-request override; None means the default. Returns `fraction` (what to show),
    `raw_fraction`, `cap`, and `capped` -- True only when the cap actually bound.
    """
    if cap is None:
        cap = STAKE_CAP_DEFAULT
    if not 0 < cap <= STAKE_CAP_MAX:
        raise ValueError(f"stake cap must be in (0, {STAKE_CAP_MAX}], got {cap}")
    raw = max(0.0, float(raw_fraction))
    return {"fraction": min(raw, cap), "raw_fraction": raw, "cap": cap, "capped": raw > cap}
