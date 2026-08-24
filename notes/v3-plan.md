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

~~Known non-blocking caveat: `ensure_schema` cannot bootstrap a fresh DB — statement 1 is
ALTER not CREATE, and `moneyline_slate_snapshots` is never created by any code.~~
**Closed (uncommitted, Tier 3 item 2.)** `ensure_schema` now CREATEs both v1 tables and
their indexes ahead of the ALTERs, so it can stand up a fresh database. That became
necessary rather than merely nice when `drizzle-kit push` was removed from
`scripts/post-merge.sh`: the push was the only other thing that could bootstrap a schema,
and it read a stale mirror that did not know about the `probables`, `adj_*` or
`model_version` columns. The migration is now the schema's sole authority.

## TIER 1 — Record integrity (do first, no price math)

The graded record is the product's honesty claim. It has three defects.

1. **`entered_line` — NOT A BUG. Reframed 2026-08-24, do not "fix" it.** The column is
   read at `record_store.py:182,194,253` and written nowhere, so picks grade at the −110
   default. That is **correct**: MONEYLINE ingests no odds provider (verified — zero
   sportsbook references in `backend/`), and the UI states it outright
   (`presentation-preferences.tsx:64`, "Book price = your manual input"). There is no market
   line to record. Writing `entered_line = fair_line` would grade every pick as if you got
   the model's own price — systematically optimistic, and exactly the fake precision the
   doctrine forbids. `entered_line` is an unimplemented *manual-entry* feature.
   Rows already graded at −110 are internally consistent. No era marking, no regrade.
   ~~**The real defect is the asymmetry:** parlays fall back to `fair_line`
   (`record_store.py:409`) while picks fall back to −110.~~
   ✅ **RESOLVED (0ea4cc0), and this entry was stale.** `record_store.py:20` now defines
   `STANDARD_LEG_LINE = -110` — "the parlay analogue" of the pick fallback — and
   `record_store.py:508-518` grades a slip with a NULL `book_line` at
   `parlay_book_decimal([STANDARD_LEG_LINE] * len(legs))`, i.e. the same −110 legs
   compounded. Symmetric with picks; one honesty standard. Covered by
   `tests/test_parlay_grading_basis.py`.
   Note the trap that produced the stale entry: commit `bb4d90f` is titled "Fix the pulse
   lexicon, **the parlay grading basis**, and wire attribution" but touches only
   `feeds.py` and `tests/test_transaction_attribution.py`. The parlay fix is in `0ea4cc0`.
   **Verify against code before trusting a status line in this file.**
2. ✅ **FIXED (7137c05). Any date can enter the ledger.** `/api/slate?date=` flows to persistence at
   `main.py:601-618`; the only guard is `mode == "live"` (also re-checked
   `record_store.py:70`). No date or status check. `ON CONFLICT (snapshot_date) DO NOTHING`
   caps it at one row per date. Urgent because a Today date bar makes this user-reachable.
3. ✅ **FIXED (7137c05). Silent initials fallback** at `feeds.py:208`. An MLB team rename would diverge stored
   vs. derived codes and grade every affected pick LOSS, with no signal. One
   `logger.warning` closes it.

✅ **DONE (c681238). Also in Tier 1 — the prerequisite for Tier 3.** No test computes an actual game price:
`_chain_probability`, `_blended_side`, `_price_game`, the SEASON→ADJ path, and the
hitter-vs-pitcher boundary payload all have zero coverage. Build an end-to-end price
integration test here. Tier 3's risky items cannot be verified without it.

Related test gap: `smoke_test` asserts only the RS intercept and coefficients. The RA
coefficients and the W~RD slope pinned in `verified_stats.json` are unchecked; the slope
drives every mWAA number and is covered only by a loose 9.5 ± 0.2 band that a 5% drift
would pass.

## TIER 2 — Dead and broken

- ✅ **FIXED (a62416b). `get_news()` raised `NameError` on every call.** `RSS_URL`, `ESPN_NEWS_URL`, `_espn_dead`
  are referenced at `feeds.py:488,506-509,530` and defined nowhere (verified by import).
  MLB RSS headlines have never worked in v2; undefined since a2780cd, not a regression.
  `wire.py:102-109` swallows it, so it surfaces only as `sources_up.news = false`. The
  intended URL is in `notes/mlb_api_transcripts.md:127` and re-verified live 2026-08-24.
  ~~**ESPN discovery:** ESPN is not down — *we* are blocked. It returns 403 to
  `USER_AGENT` and 200 to httpx's default (recorded §9b). Unblocking it would move every
  team's media-pulse score — a visible product change.~~
  ⚠️ **THAT PREMISE HAS EXPIRED. Re-measured 2026-08-24; see
  `notes/decision-espn-user-agent.md`.**
  - `site.api.espn.com` now 403s **every** User-Agent from our egress — our UA, httpx's
    default, bare curl, full Chrome, Chrome+Referer. 5/5 repeats, Akamai edge denial
    (`server: AkamaiGHost`). **The User-Agent options are dead no-ops.** Do not spend
    another session on the UA.
  - **A fourth option exists:** `site.web.api.espn.com` (AWS origins, off the Akamai edge)
    returns 200 to the honest MONEYLINE UA, identical 34207-byte payload — the exact size
    §9b recorded for its 200. Verified genuine ESPN by TLS cert (`O=The Walt Disney
    Company`). **No UA lie is involved**, which removes the honesty objection entirely.
    It is a one-line host change at `feeds.py:38`.
  - **The blast radius is measurably zero, not merely display-only.** All 30 teams, pulse
    unchanged with ESPN's 6 live articles merged through the unmodified production path.
    Wire goes 175 → 181 items; four teams gain one scanned item each and none matches the
    lexicon. Worst case (forced `?limit=50`): 2 of 30 teams move, both from IL news already
    present in the transactions feed. Structural reason: ESPN items carry `team: null` and
    reach a pulse only via full-club-name matching in `wire._item_mentions`, while ESPN
    headlines use nicknames.
  OPEN DECISION (Asher), but now a small one: take the host swap, or leave ESPN off on
  principle. Either way the note above was stale and is corrected.
- ✅ **FIXED (c565770). Slow API had no ceiling.** A *dead* MLB API degrades gracefully (historical_slate
  fallback); a *slow* one does not. No request deadline anywhere; ~20.25s per logical fetch;
  `get_rosters` fans 30 calls at concurrency 5 (~120s); `AsyncTTLCache` held its per-key
  lock for the whole loader, so concurrent `/api/slate` requests queued behind the first.
  Fixed by bounding the wait, **not** by dropping single-flight — dropping the lock would
  let each concurrent request fan out its own roster sweep. The loader is now a shielded
  shared task with a `FEED_DEADLINE_SECONDS` (25s) deadline; stale is served on timeout,
  and only with nothing cached does `FeedUnavailable` reach `historical_slate`.
- ✅ **FIXED (bf1e7ab + f0ef5b2). Doubleheader parlay mispricing.** Same-game refusal keys on `gamePk` only
  (`main.py:1001-1007`). A doubleheader is two gamePks with the same two teams, so
  correlated legs pass the independence check and get multiplied as independent.
- **Playoff logistic leaks unflagged.** ✅ FIXED on `tier2-logistic-flag`. Every
  `predicted` block now carries `playoff_prob_basis` beside `playoff_prob`
  (`panel`, `season`, `in_panel`, `status`, `note`), built from the bundle's own year
  bounds. Undeclared season stays flagged — the desk does not vouch for calibration it
  cannot check. `/api/price` takes an optional `season`; `/api/matchup` passes each
  side's `year`; `predict_team` declares its own row year. Math verified identical.
  **Follow-up (not done, deliberately):** `pricer-panel.tsx:188-205` still gates on the
  client-side `liveContext`, not on the flag. It is *not* redundant — it substitutes the
  Season Desk simulation, which the flag does not do — but the gate should be re-pointed
  at `predicted.playoff_prob_basis.in_panel` so the refusal is payload-driven and there is
  one source of truth. `pricer-panel.tsx` is the only display consumer of `playoff_prob`.
- Minor: pulse lexicon double-counts ("streak" and "losing streak" both match,
  `analytics.py:26-35`); `_matches` (`:282-285`) has a leading word boundary but no trailing
  one, so "torn" matches "tornado"; `get_transactions` sends no `sportId`
  (`feeds.py:679-698`) so MiLB affiliates get phantom codes (wire display only).
- Non-coefficient literals: `main.py:557` `vig_threshold = max((vig or 0.0476)/2, 0)`
  hardcodes the −110 overround that `market_vig(-110,-110)` already derives; the
  Pythagorean exponent 2 is duplicated at `odds.py:133-134`, `players.py:119-121`,
  `players.py:187-189`.

## STATUS — 2026-08-24

Tier 1 and Tier 2 are complete on branch `tier2-integration` (off `main`, unmerged).

Verified against the running Replit api-server after every merge: health OK,
`sources_up.news` now `true` for the first time, and slate prices byte-identical
(`TBR @ DET` 110/−110, `BOS @ MIA` 105/−105, `COL @ WSN` −150/150). Four changes to the
live pricing path, zero movement in any price.

One decision parked for Asher: the ESPN User-Agent. (The parlay/pick grading fallback
asymmetry was the second, and it is **already resolved in `0ea4cc0`** — see Tier 1 item 1.
This file said "OPEN DECISION" for it long after the code was fixed.)

**Doc discipline, learned the hard way 2026-08-24:** a status line in this file is a claim,
not evidence. Sessions lose context and commit messages misattribute work. Before acting on
any ✅/OPEN marker here, verify it against the code.

### Tier 3 progress — everything below is UNCOMMITTED in the working tree

pytest **154 passed / 2 failed**, up from 92. The two failures are the same pre-existing
`tests/test_serve_spa.py` pair (stale committed frontend `dist/`) that have been failing
throughout. `smoke_test.py` green. `pnpm typecheck` green.

- **Item 1** (`?date=` ledger guard) — done in Tier 1 (7137c05).
- **Item 2** (`MODEL_VERSION`) — **done.** One constant in `backend/precompute.py`;
  `model_version` column on all three ledger tables; stamped on every insert; `get_record`
  reports `model_versions_present` and `unversioned_picks` (rows predating versioning stay
  NULL rather than being relabelled); `pnpm --filter db push` removed from
  `scripts/post-merge.sh`; `lib/db/src/schema/moneyline.ts` demoted to documentation-only;
  the footer reads the version from `/api/health` instead of restating a literal.
  `tests/test_model_version_stamping.py` added.
- **Item 3** (verdict engine) — **backend done, frontend slot in progress.**
  `backend/verdict.py` + `POST /api/evaluate` (`main.py:609`, spliced between
  `/api/matchup` and `/api/slate`). `main.py` gained 72 lines and deleted zero, so the
  change is provably additive; `/api/price` still returns the 2002 A's chain unchanged.
  `/api/matchup` untouched and keeps its own vig-relative ruleset — a test asserts the two
  engines share no verdict vocabulary. 33 new tests: 10 Appendix A fixtures, 11
  desk-authored (for the three rules Appendix A ships with no fixture at all), 12 route
  contract tests. Hand-checked cases added to `verified_stats.json` (`verdict_checks`) and
  asserted in `smoke_test.py`.
- **Item 4** (`model_detail` + `backend/explain.py`) — not started. Design groundwork was
  dispatched to a peer session and lost when that session was terminated; redo it.
- **Item 5** (Track Record completion) — **done.** Historical banner, Wilson score
  interval, calibration buckets, proof statement, CSV export, all as client arithmetic over
  `/api/record`. New components under `artifacts/moneyline/src/components/record/`.

### Corrections found while building item 3

1. **The Appendix A fixture table contradicts itself, and `notes/verdict-design.md` §2.1
   copied the error.** The doc says fixture 1 defaults to `p_adj` absent. It cannot:
   fixture 10 is defined as "fixture 1 with `p_adj` null" and expects a *different* result
   (signal capped Moderate). If F1 already had `p_adj` null, F10 would be the same case and
   prove nothing. F1 states "starters confirmed", and the gate table makes `p_adj` null ⟺
   starters unconfirmed, so F1 carries `p_adj = p_season`. Same correction for F4.
2. **`uncertainty`'s Moderate arm is ambiguous in the spec.** `[S:1335]` reads "Moderate if
   `min(gp) < 100` or the gap is at least 0.03". Implemented as the season-vs-adjusted
   spread, matching the High arm above it which uses that same quantity at 0.05. The other
   reading — the signal `gap` (edge/σ) — would fire at an edge of 0.0012 and make nearly
   every game Moderate.
3. **Slate rows carry no games-played, and `min(gp)` gates the whole verdict.** Passing
   null returns `INSUFFICIENT_DATA (early_season)` for every game. The card sources gp from
   the existing `/api/teams-live` rather than touching the price path; the real plumbing is
   a separate change (see `notes/verdict-design.md` §3.6).

### Multi-session caveat

Only 1–2 Claude sessions run at a time (server-side issue). `SendMessage` returns
`success: true` for sessions that never start, so work handed to a third peer can silently
go nowhere — two lanes were lost that way on 2026-08-24. Prefer in-process subagents for
parallelism that has to be reliable.

## TIER 3 — v3 build, in dependency order

1. `?date=` ledger guard *(same as Tier 1 item 2 — do it there)*. No price math.
2. ✅ **DONE (uncommitted). `MODEL_VERSION` constant + `model_version` column.** Two literals today:
   `main.py:443`, `status-strip.tsx:18`. Hard-blocks home-field.
   **Remove the Drizzle/post-merge `db push` first** so a push cannot drop `adj_*` columns.
   No price math.
3. 🔄 **Backend DONE (uncommitted), frontend slot in progress. GameCard verdict slot.** Everything else in the card matches spec; the one structural
   element the design is built on is absent, and EdgeFinder's one-sided `/api/matchup`
   verdict fills the space — that is the "lean is not the value side" failure, live.
   Needs `backend/verdict.py` + `POST /api/evaluate`. **PRICE MATH** (composes `odds.py`,
   additive only, `odds.py` unchanged, 10 Appendix A fixtures).
4. **`model_detail` on slate rows + `backend/explain.py`.** `feeds._chain_probability`
   discards `predict_from_inputs` results; no reason bullets anywhere.
   **PRICE MATH** — requires a byte-identical `/api/slate` diff.
5. ✅ **DONE (uncommitted). Track Record completion** — persistent historical banner, 95% interval, calibration
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
