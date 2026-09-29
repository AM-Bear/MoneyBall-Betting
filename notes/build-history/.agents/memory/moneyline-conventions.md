---
name: MONEYLINE backend conventions
description: Non-obvious rules for the MONEYLINE FastAPI backend — team codes, doctrine, data quirks.
---

# MONEYLINE backend conventions

**Rule:** Team codes everywhere in the app are the B-Ref-style codes (TBR, SDP, KCR, SFG, WSN), resolved from FULL team names.
**Why:** Grading compares codes across slate rows, finals, and standings; MLB's official abbreviations (TB, SD, KC) differ and silently break the ledger if mixed in.
**How to apply:** Any new fetcher that surfaces a team must resolve the full name first (MLB standings return short names like "Mets"; the teams endpoint owns full names) before mapping to a code.

**Rule:** Prices come only from the fitted regression chain; media pulse, injury flags, and wire items are disclosed context and must never feed a price. Model coefficients are always read from the fitted bundle, never hardcoded.
**Why:** Core product doctrine from the v2 spec; the smoke tests assert receipts arithmetic against the live coefficients.

**Data quirks (checked 2026-08-20):**
- MLB innings notation ".2" means two-thirds of an inning, not a decimal.
- ESPN news is optional — skip silently on failure, never a dependency.
- DB tables were created outside the repo; all migrations must be idempotent and leave existing rows untouched.
- Ledger honesty: ties and postponed games stay pending; cancelled or long-vanished games void terminally at 0 units (picks and parlay slips alike) so nothing clogs the pending queue or dilutes the hit rate.

**Testing:** `python smoke_test.py` is the gate — v1 chain (2002 A's) plus v2 hand-checked math — and `pytest` covers the grading ledger against an isolated Postgres schema, so its DDL must be kept in lockstep with the boot migration. FastAPI `TestClient(app)` without a context manager skips lifespan (no model load/network) — useful for pure-validation error paths.
