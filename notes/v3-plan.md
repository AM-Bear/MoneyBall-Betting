# MONEYLINE — recon synthesis and ranked plan

Written 2026-08-24 from three parallel read-only recon lanes.
Source maps: `notes/map-model.md`, `notes/map-data.md`, `notes/map-surface.md`.

This file is the handoff. A new session should read `CLAUDE.md`, then this, then the map
for whichever area it is touching.

## Status of the strategy docs

`attached_assets/MONEYLINE_Repository_Audit_and_v3_Strategy_*.md` was written against
`cef8cab`; `main` is ~9 commits ahead. Much of "Phase 1 frontend" already shipped — Today
page (`tabs/today.tsx`), three-layer GameCard (`components/game-card.tsx`), Research hub,
`/track-record`, `/settings`, localStorage prefs, param-preserving redirects.
**Treat the audit's "not implemented" claims as stale.** The three Phase 0 defects are open.

MODEL SLIP OF THE DAY was **deliberately deleted** during Phase 1. It is not a missing
feature. Do not rebuild it. (The v2 spec that requires it is superseded.)

## What is healthy — do not re-audit

- **TEAM_CODES: clean.** All 17 boundaries pass through `_team_code()`. Store→grade is
  symmetric (`feeds.py:284,286` → `record_store.py:140-141`; grading `feeds.py:427-428`
  compared at `record_store.py:193/200`). Short-name landmine defused at `feeds.py:611-614`.
- **Migrations: safe.** `ensure_schema` is ADD COLUMN IF NOT EXISTS ×6 + CREATE TABLE IF NOT
  EXISTS. No UPDATE/DROP/backfill. All 7 write paths guarded. Graded picks terminal.
- **Doctrine: holds.** Zero hardcoded coefficients — everything via `load_models()`
  (`analytics.py:38-46`, `inference.py:42-71`). Zero paths where pulse or injury flags reach
  a price (traced `feeds.py:228-302`, `main.py:947-972`, `wire.py:165-183`,
  `season_sim.py:239-256`, frontend).

Known non-blocking caveat: `ensure_schema` cannot bootstrap a fresh DB — statement 1 is
ALTER not CREATE, and `moneyline_slate_snapshots` is never created by any code.

## TIER 1 — Record integrity (do first, no price math)

The graded record is the product's honesty claim. It has three defects.

1. **`entered_line` is never written.** Read at `record_store.py:182,194,253`; no writer
   exists in `backend/`. `line = ... else -110` always takes the default, so every pick is
   graded at a flat −110 instead of the model's own fair line. Tests seed the column
   directly (`conftest.py:146`), which is why the suite is green.
   **OPEN DECISION (Asher):** what to do with rows already graded at −110. Options: leave
   them; regrade (violates append-only + terminal grades); or mark them as a distinct era.
   Recommendation: mark the era, never rewrite a row. *Not yet decided — do not touch
   existing rows without an explicit answer.*
2. **Any date can enter the ledger.** `/api/slate?date=` flows to persistence at
   `main.py:601-618`; the only guard is `mode == "live"` (also re-checked
   `record_store.py:70`). No date or status check. `ON CONFLICT (snapshot_date) DO NOTHING`
   caps it at one row per date. Urgent because a Today date bar makes this user-reachable.
3. **Silent initials fallback** at `feeds.py:208`. An MLB team rename would diverge stored
   vs. derived codes and grade every affected pick LOSS, with no signal. One
   `logger.warning` closes it.

**Also in Tier 1 — the prerequisite for Tier 3.** No test computes an actual game price:
`_chain_probability`, `_blended_side`, `_price_game`, the SEASON→ADJ path, and the
hitter-vs-pitcher boundary payload all have zero coverage. Build an end-to-end price
integration test here. Tier 3's risky items cannot be verified without it.

Related test gap: `smoke_test` asserts only the RS intercept and coefficients. The RA
coefficients and the W~RD slope pinned in `verified_stats.json` are unchecked; the slope
drives every mWAA number and is covered only by a loose 9.5 ± 0.2 band that a 5% drift
would pass.

## TIER 2 — Dead and broken

- **`get_news()` raises `NameError` on every call.** `RSS_URL`, `ESPN_NEWS_URL`, `_espn_dead`
  are referenced at `feeds.py:488,506-509,530` and defined nowhere (verified by import).
  MLB RSS headlines have never worked in v2; undefined since a2780cd, not a regression.
  `wire.py:102-109` swallows it, so it surfaces only as `sources_up.news = false`. The
  intended URL is in `notes/mlb_api_transcripts.md:127`.
- **Slow API has no ceiling.** A *dead* MLB API degrades gracefully (historical_slate
  fallback); a *slow* one does not. No request deadline anywhere; ~20.25s per logical fetch;
  `get_rosters` fans 30 calls at concurrency 5 (~120s); `AsyncTTLCache` holds its per-key
  lock for the whole loader (`feeds.py:98-105`), so concurrent `/api/slate` requests queue
  behind the first. Multi-minute app-wide hang.
- **Doubleheader parlay mispricing.** Same-game refusal keys on `gamePk` only
  (`main.py:1001-1007`). A doubleheader is two gamePks with the same two teams, so
  correlated legs pass the independence check and get multiplied as independent.
- **Playoff logistic leaks unflagged.** `inference.py:55-59` always computes the 1962–2012
  logistic; `main.py:490-504` returns it for live 2026 inputs. The UI refuses it
  (`pricer-panel.tsx:188-205`) but the API ships the miscalibrated number with no flag.
- Minor: pulse lexicon double-counts ("streak" and "losing streak" both match,
  `analytics.py:26-35`); `_matches` (`:282-285`) has a leading word boundary but no trailing
  one, so "torn" matches "tornado"; `get_transactions` sends no `sportId`
  (`feeds.py:679-698`) so MiLB affiliates get phantom codes (wire display only).
- Non-coefficient literals: `main.py:557` `vig_threshold = max((vig or 0.0476)/2, 0)`
  hardcodes the −110 overround that `market_vig(-110,-110)` already derives; the
  Pythagorean exponent 2 is duplicated at `odds.py:133-134`, `players.py:119-121`,
  `players.py:187-189`.

## TIER 3 — v3 build, in dependency order

1. `?date=` ledger guard *(same as Tier 1 item 2 — do it there)*. No price math.
2. **`MODEL_VERSION` constant + `model_version` column.** Two literals today:
   `main.py:443`, `status-strip.tsx:18`. Hard-blocks home-field.
   **Remove the Drizzle/post-merge `db push` first** so a push cannot drop `adj_*` columns.
   No price math.
3. **GameCard verdict slot.** Everything else in the card matches spec; the one structural
   element the design is built on is absent, and EdgeFinder's one-sided `/api/matchup`
   verdict fills the space — that is the "lean is not the value side" failure, live.
   Needs `backend/verdict.py` + `POST /api/evaluate`. **PRICE MATH** (composes `odds.py`,
   additive only, `odds.py` unchanged, 10 Appendix A fixtures).
4. **`model_detail` on slate rows + `backend/explain.py`.** `feeds._chain_probability`
   discards `predict_from_inputs` results; no reason bullets anywhere.
   **PRICE MATH** — requires a byte-identical `/api/slate` diff.
5. **Track Record completion** — persistent historical banner, 95% interval, calibration
   buckets, "what this proves", CSV. Pure client arithmetic over `/api/record`. No price
   math. Cheapest high-trust win available.

### Price-math danger list (verify hard)

- `half_kelly_fraction` (`odds.py:49-56`) is **UNCAPPED** despite its docstring. Cap in the
  display layer; do NOT mutate — `smoke_test` asserts current behavior.
- **Home-field** mutates `odds.py:138` `log5_probability` and rewrites every price ever
  quoted. Version registry must land first; run it as a third graded price experiment;
  must precede any candidates record.
- Leave `probability_to_moneyline`'s nearest-5 rounding alone.
- `explain` ranking via `analytics.runs_per_win` is read-only.

## Dead ends and UI debt

No orphan routes — all 22 `/api` routes have a consumer, and no frontend call hits a missing
endpoint. But:

- `ScreenerPanel`, `BaParadoxPanel`, `PricerPanel`, `SlateRail` are mounted **only** in
  `tabs/desk.tsx`. Retire `/desk` on schedule and three endpoints lose their only home.
  The Research hub has no "Teams & Season" or "Learn" tile.
- `/` is dual-purpose and undocumented: `App.tsx:165` renders Desk if `?team`/`?year`,
  else Today.
- Keyboard `1`–`6` still binds the OLD six tabs. `1` does not go to Today; nothing reaches
  `/track-record` or `/settings`.
- Shipped routes `/track-record` and `/research/parlay` diverge from both docs
  (`/record`, `/parlay`). Settle before Track Record becomes the marketing entry.
- `useIsMobile` is used only by the unused `ui/sidebar.tsx`.
- `EQUITY_CAVEAT` (`main.py:87`) is the exact text the "not priced" chips need and renders
  nowhere.
