# MONEYLINE

A Moneyball-doctrine baseball trading desk: it refits the classic OBP/SLG run regressions on 1962–2001 data, prices live 2026 MLB games as fair moneylines, and tracks its own record honestly — receipts for every number, refusals instead of fake precision.

## Run & Operate

- Workflow `artifacts/api-server: API Server` runs `python -m uvicorn backend.main:app` on `$PORT` (FastAPI, python 3.12 in `.pythonlibs`)
- Workflow `artifacts/moneyline: web` runs the Vite frontend
- `python smoke_test.py` — full regression suite (v1 model chain + v2 math); must pass before and after any backend change
- `pnpm --filter @workspace/moneyline run smoke` — builds the production frontend, boots `NODE_ENV=production python -m backend.main`, and checks all six public tab routes for panel text and browser errors
- The `test` validation workflow runs both `python -m pytest -q` and the frontend smoke gate
- Required env: `DATABASE_URL` — Postgres for the pick/parlay record store
- Debug via `curl http://localhost:80/api/...` (path-routed preview proxy)

## Stack

- Backend: FastAPI + httpx + scikit-learn/pandas (`backend/`, `requirements.txt`) — NOT the Express/Drizzle template stack
- Frontend: React + Vite (`artifacts/moneyline`)
- DB: Postgres via psycopg (`backend/record_store.py`); schema created by `ensure_schema()` idempotent boot migration

## Where things live

- `backend/main.py` — all API routes, `{"error":{"code","message"}}` envelope, lifespan (model load, schema migration, grading task)
- `backend/feeds.py` — MLB Stats API fetchers + TTL caches (slate/standings ~10m, pools/rosters ~6h, transactions/news ~30m), slate enrichment (probables, ADJ price, flags)
- `backend/analytics.py` — pure v2 math: mWAA run values, runs/win from fitted slope, percentiles, Beane badge, starter innings-share blend, pulse lexicon
- `backend/odds.py` — pythag/log5/moneyline + parlay math (combined prob, EV, ½-Kelly, vig comparison)
- `backend/season_sim.py` — seeded Monte Carlo (N=2000) rest-of-season sim, 2026 playoff format (top 6/league)
- `backend/wire.py` — merged wire (transactions/RSS/desk notes) + team media pulse
- `backend/players.py` — player card / comparison assembly
- `backend/record_store.py` — Postgres pick + parlay-slip persistence, dual SEASON/ADJ grading
- `notes/mlb_api_transcripts.md` — dated curl transcripts for every MLB endpoint used
- `verified_stats.json` + `smoke_test.py` — hand-checked ground truth (2002 A's chain, parlay examples)

## Architecture decisions

- All model coefficients come from `load_models()` — never hardcoded literals; every derived number ships a receipt
- Media pulse and injury flags are disclosed context only; they NEVER move a price (doctrine)
- ADJ (starter-blended) price is an experiment graded alongside SEASON in the record — the app never claims it's better
- Playoff odds for 2026 come from simulated standings (top 6/league), not the historical 1962–2012 logistic
- Keyless data only: MLB Stats API + MLB RSS; ESPN is optional (silent skip on failure); no salary data served
- Honest refusals: hitter-vs-pitcher comparisons, 2027 projections, and injury-adjusted prices return boundary payloads, not fake numbers

## Gotchas

- Team codes are B-Ref style from `TEAM_CODES` in feeds.py (TBR, SDP, KCR…) — standings/teams endpoints must map through it, not MLB's official abbreviations (TB, SD), or record grading breaks
- MLB standings API returns short names ("Mets"); always resolve full names via `/api/v1/teams`
- Innings use MLB ".2 = two-thirds" notation — parse with `analytics.parse_innings`
- DB tables predate the repo (created externally): migrations must be `IF NOT EXISTS` style and never rewrite existing rows

## Pointers

- v2 spec (source of truth for formulas/doctrine): `attached_assets/moneyline_v2_expansion_replit_prompt_1787245184521.md`
- See the `pnpm-workspace` skill for workspace structure
