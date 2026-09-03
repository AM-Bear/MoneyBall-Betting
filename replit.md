# MONEYLINE

A Moneyball-descended baseball trading desk, repositioning (ruled 2026-08-24, plan in `notes/v4-plan.md`) from a sports-research product into a **gambler's product**: it refits the classic OBP/SLG run regressions on 1962–2001 data, prices live 2026 MLB games as fair moneylines, measures them against the price a bettor can actually get, and tracks its own record honestly — receipts for every number, refusals instead of fake precision.

## Run & Operate

- Workflow `artifacts/api-server: API Server` runs `python -m uvicorn backend.main:app` on `$PORT` (FastAPI, python 3.12 in `.pythonlibs`)
- Workflow `artifacts/moneyline: web` runs the Vite frontend
- `python smoke_test.py` — full regression suite (v1 model chain + v2 math); must pass before and after any backend change
- `pnpm --filter @workspace/moneyline run smoke` — builds the production frontend, boots `NODE_ENV=production python -m backend.main`, and checks all six public tab routes for panel text and browser errors
- The `test` validation workflow runs both `python -m pytest -q` and the frontend smoke gate
- Required env: `DATABASE_URL` — Postgres for the pick/parlay record store
- Paper parlay slips are private to their authenticated owner; each user can log one slip per day
- Debug via `curl http://localhost:80/api/...` (path-routed preview proxy)

## Stack

- Backend: FastAPI + httpx + scikit-learn/pandas (`backend/`, `requirements.txt`) — NOT the Express/Drizzle template stack
- Frontend: React + Vite (`artifacts/moneyline`)
- DB: Postgres via psycopg (`backend/record_store.py`); schema created by `ensure_schema()` idempotent boot migration

## Where things live

- `backend/main.py` — all API routes, `{"error":{"code","message"}}` envelope, lifespan (model load, schema migration, grading task)
- `backend/feeds.py` — MLB Stats API fetchers + TTL caches (slate/standings ~10m, pools/rosters ~6h, transactions/news ~30m), slate enrichment (probables, ADJ price, flags)
- `backend/analytics.py` — pure v2 math: mWAA run values, runs/win from fitted slope, percentiles, Beane badge, starter innings-share blend, pulse lexicon
- `backend/odds.py` — pythag/log5/moneyline + parlay math (combined prob, EV, ½-Kelly, vig comparison) + no-vig (de-vig + edge vs the book's true probability)
- `backend/season_sim.py` — seeded Monte Carlo (N=2000) rest-of-season sim, 2026 playoff format (top 6/league)
- `backend/wire.py` — merged wire (transactions/RSS/desk notes) + team media pulse
- `backend/players.py` — player card / comparison assembly
- `backend/record_store.py` — Postgres pick + parlay-slip persistence, dual SEASON/ADJ grading
- `backend/verdict.py` — value-side verdict engine behind `POST /api/evaluate`
- `notes/mlb_api_transcripts.md` — dated curl transcripts for every MLB endpoint used
- `verified_stats.json` + `smoke_test.py` — hand-checked ground truth (2002 A's chain, parlay examples, verdict checks)

## Doctrine — revised 2026-08-24

The original doctrine — *keyless-only data, no market prices, context never moving a price* — is **scratched**. The ruling is recorded in `notes/v4-improvement-catalog.md` (Part 0) and sequenced in `notes/v4-plan.md`. MONEYLINE's job is now edge against the price a bettor can actually get. Most of the old doctrine survives, **as competitive assets rather than principles**: keep each of these because it wins, not because it is pure.

**What survives:**

- **Calibration, the graded record, and refusals.** Every competitor claims an edge; this product publishes a verifiable one. Keep the ledger, the calibration buckets, the Wilson intervals, and the "I don't know" states — and make them *harder* to fake, not softer.
- **Receipts on every derived number.** All model coefficients come from `load_models()` — never hardcoded literals. A number without a receipt does not ship. Hardcoded constants are how models silently rot.
- **Honest refusals:** hitter-vs-pitcher comparisons, 2027 projections, and thin-sample verdicts return boundary payloads, not fake numbers.
- **Graded experiments, never claimed better.** ADJ (starter-blended) is graded alongside SEASON in the record and the app does not claim it wins. This generalizes into the champion–challenger registry (v4 Phase 2.4): every price change lands as a graded challenger and is promoted to the headline price only on evidence.
- Playoff odds for 2026 come from simulated standings (top 6/league), not the historical 1962–2012 logistic. (A modelling decision, unrelated to the doctrine change; kept.)

**What is scratched — data purity. All of the following are now in scope:**

- **Odds feeds and sportsbook prices.** Manual entry first (v4 Phase 1: persist `entered_line`, de-vig, hold %, closing line + CLV), a vendor later (Phase 5). The market is the benchmark, not a contaminant.
- **Third-party sources:** ESPN, Statcast, Retrosheet/Lahman, salary data. "Keyless only" is gone. The rule that replaces it is **no secrets in the repository** — provider keys via environment variables only. This repo is public.
- **Context signals moving prices.** Injuries, scratches, lineups, and news may move a price (v4 Phase 3.2), but only through the graded-challenger path above, and every move ships a receipt line ("−1.8 pts: Cole scratched"). The old disclosure survives as the receipt, not as a wall.

**Current code state, so nobody enforces it as policy:** no path lets pulse or injury flags reach a price (the `hard_rule` payload string still says so); `entered_line` is read on grade and never written; no odds provider exists; no salary is served; ESPN is optional and silently skipped on failure, and the host swap in `notes/decision-espn-user-agent.md` is now unblocked pending Asher's call. These are the starting conditions the v4 plan changes deliberately. Verify against code before acting on any status claim, in this file or any note.

**The one gate that outlives the doctrine:** nothing that recommends a bet ships before something can measure whether the recommendation was any good. The +EV screener (v4 5.5) is gated on the Phase 2 backtest harness. Scratching the data doctrine does not scratch that.

## Gotchas

- Team codes are B-Ref style from `TEAM_CODES` in feeds.py (TBR, SDP, KCR…) — standings/teams endpoints must map through it, not MLB's official abbreviations (TB, SD), or record grading breaks
- MLB standings API returns short names ("Mets"); always resolve full names via `/api/v1/teams`
- Innings use MLB ".2 = two-thirds" notation — parse with `analytics.parse_innings`
- DB tables predate the repo (created externally): migrations must be `IF NOT EXISTS` style and never rewrite existing rows. This holds for v4 too: picks already graded at −110 stay at −110 and are marked as a distinct era via `model_version`, never regraded

## Pointers

- Current doctrine and build order: `notes/v4-plan.md` (Task 0, six phases, standing rules); the ruling and the full option catalog: `notes/v4-improvement-catalog.md`
- What is broken and what is verified healthy in the tree: `notes/v3-plan.md` (superseded for sequencing, still authoritative for status — verify every ✅ against code)
- v2 spec (source of truth for the *formulas*; its data doctrine is superseded): `attached_assets/moneyline_v2_expansion_replit_prompt_1787245184521.md`
- See the `pnpm-workspace` skill for workspace structure
