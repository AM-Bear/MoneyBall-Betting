# MONEYLINE — Repository Audit, Discrepancy Report, and Repository-Aware v3 Strategy

**Source of truth for what exists:** `github.com/AM-Bear/MoneyBall-Betting`, branch `main`, commit `cef8cab` ("Published your App", 2026-08-20 20:02 UTC), 252 tracked files, cloned and read in full for this audit.
**Source of truth for direction:** `MONEYLINE_v3_Product_Strategy_and_UX_Plan.md` (the earlier strategy document).
**Prepared for:** Asher (MONEYLINE) · **Date:** August 24, 2026

Evidence discipline: every claim about the current build cites a file path, function, route, or test, and the three checks that could be executed in this sandbox were executed (`python smoke_test.py` → pass; `python -m pytest -q` → 27 passed, 16 skipped for lack of `DATABASE_URL`, 3 failed only because `artifacts/moneyline/dist` is not built here; `backend.feeds.get_news()` → `NameError: name 'RSS_URL' is not defined`). No `.env`, credential, token, or key was read or is reproduced; the repository contains none in tracked files.

---

## 1. Executive summary

The repository is further along than the v3 strategy assumed in some places and exactly as constrained as it assumed in the ones that matter most.

What exists and works: a FastAPI backend (`backend/main.py`, 22 routes plus an SPA fallback) that fits the Moneyball regression stack at build time (`backend/precompute.py`), prices today's MLB slate from live MLB Stats API inputs with both a season price and a starter-blended "ADJ" price (`backend/feeds.py::_price_game`), computes receipts for every prediction (`backend/inference.py::predict_from_inputs`), stores an append-only daily pick snapshot in Postgres and grades it against real finals on a 30-minute in-process scheduler (`backend/main.py::grade_scheduler`, `backend/record_store.py`), prices parlays with a vig-compounding comparison (`backend/odds.py::parlay_vig_comparison`), runs a seeded rest-of-season simulation (`backend/season_sim.py`), builds player cards with percentiles and mWAA (`backend/players.py`, `backend/analytics.py`), and exposes injury flags and a lexicon media pulse as context that never touches a price. A React 19 + Vite 7 + Tailwind 4 frontend (`artifacts/moneyline`) renders this as six terminal-styled tabs (`DESK`, `PLAYERS`, `H2H`, `PARLAY`, `SEASON`, `WIRE`) over hand-written TanStack Query hooks (`artifacts/moneyline/src/api.ts`).

What does not exist, confirmed by absence in code: any sportsbook odds feed or stored book price (the only book lines are typed by hand into `EdgeFinder` and `ParlayLab` and are never persisted — `moneyline_record_picks.entered_line` is never written outside test fixtures), any closing-line or opening-line data, any user accounts, preferences, bankrolls, user bets, billing, or per-user state (no auth code, no user tables, no `localStorage` use in app code), any per-game verdict beyond the one-sided manual `VALUE / INSIDE THE VIG / NO VALUE / NO LINE` in `POST /api/matchup`, any "signal strength," any generated explanations, any home-field adjustment (`log5_probability` is symmetric), any model version registry (the version string is hard-coded in `/api/health` and in `StatusStrip`), and any light theme (`:root, .dark` share one palette in `index.css`).

Three defects surfaced during the audit that the roadmap should fix before any redesign work: the MLB.com headline feed is dead in production because `RSS_URL` and `ESPN_NEWS_URL` are referenced but never defined in `backend/feeds.py` (the wire's `safe()` wrapper hides it as "news feed down"); `GET /api/slate?date=` for a past date prices already-final games with today's season inputs and, because the payload reports `mode: "live"`, would persist backdated picks into the public ledger (the UI never passes a date, so the hole is API-only, but the ledger's immutability currently depends on nobody calling it); and the deployment is `autoscale` while the pick snapshot and grading loop is in-process, which the project's own memory note (`.agents/memory/background-scheduler-constraints.md`) says will silently miss ledger days if the instance scales to zero.

The strategic conclusion is unchanged from v3 but sharper. The doctrine and the mathematics are sound and should be preserved untouched. The v3 Today dashboard, verdict engine, bankroll experience, and closing-line-value record cannot be built truthfully without a licensed odds feed, which is the single largest external dependency. Meanwhile a large share of the v3 experience — the three-layer card, the terminology dictionary, plain-English explanations generated from the receipts and `adj_detail` that already exist, a public Track Record page with live calibration computed from `/api/record` entries, the Parlay Check reframe, sentence-case restyling, the navigation and route migration, mobile layout, and onboarding — can be built on the current API with modest or no backend change. The roadmap below therefore starts with fixes and honest-with-current-data UI work, puts the odds feed and its ledger changes on a parallel track, and gates every price-dependent verdict, stake, and record behind that feed's arrival.

---

## 2. Current GitHub repository audit

### 2.1 Repository and directory structure

```
/
├── .replit                       modules nodejs-24 / python-3.12 / postgresql-16; deploymentTarget = "autoscale";
│                                 workflow "test" = python -m pytest -q; postMerge → scripts/post-merge.sh
├── replit.md                     operator notes (run/operate, stack, where things live, doctrine, gotchas)
├── .agents/memory/*.md           six engineering memory notes (scheduler, deployment probe, live-season contract, …)
├── backend/                      Python FastAPI service (the real API)
│   ├── main.py                   all routes, error envelope, lifespan (model load, schema migration, scheduler), SPA fallback
│   ├── feeds.py                  MLB Stats API client, TTL caches, slate pricing (SEASON + ADJ), flags, pools, standings
│   ├── inference.py              load-once models; predict_from_inputs / predict_team; receipts
│   ├── odds.py                   moneyline ↔ probability, edge, vig, Kelly, parlay math, Pythagorean, log5
│   ├── analytics.py              mWAA run values, percentiles, Beane badge, starter blend, innings parsing, pulse lexicon
│   ├── players.py                player cards, comparisons, boundary payloads
│   ├── season_sim.py             seeded Monte Carlo (N=2000), team outlook
│   ├── wire.py                   merged wire (transactions + news + desk notes), team pulse
│   ├── record_store.py           Postgres persistence: snapshots, picks, grading, voiding, parlay slips
│   ├── precompute.py             chronological fits, track_record.json, backtest.json, ba_paradox.json
│   ├── serve_spa.py              lightweight Starlette static server for production web service
│   └── static_data/              moneyline_models.joblib, track_record.json, backtest.json, ba_paradox.json
├── artifacts/moneyline/          React 19 + Vite 7 + Tailwind 4 SPA (the real frontend)
│   ├── src/App.tsx               router (wouter), shell, keyboard 1–6, lazy tabs
│   ├── src/api.ts                hand-written fetch + TanStack Query hooks (23 hooks)
│   ├── src/tabs/                 desk, player-desk, h2h, parlay-lab, season-desk, wire
│   ├── src/components/           20 app components + components/ui/ (55 shadcn primitives)
│   ├── src/index.css             Tailwind 4 tokens (dark-only palette), utilities
│   └── index.html                Google Fonts (Inter, JetBrains Mono), dark pre-paint styles
├── artifacts/api-server/         Express + pino SCAFFOLD (src/app.ts, routes/health.ts). NOT the API: its
│                                 package.json `start` runs `python -m backend.main`
├── artifacts/mockup-sandbox/     Replit design-canvas scaffold (dev-only preview at /__mockup)
├── lib/db/                       Drizzle schema for TWO tables (stale vs Python migration; see 2.10)
├── lib/api-spec, lib/api-zod, lib/api-client-react   generated OpenAPI scaffolding for a /healthz route; unused by the app
├── tests/                        pytest: conftest (isolated schema), grading, pending-record, live-season, serve_spa
├── smoke_test.py                 model-chain + odds + v2 math + production-entrypoint gate
├── baseball.csv, verified_stats.json, model_config.json, model_setup.py    bundled data and ground truth
├── notes/mlb_api_transcripts.md  dated curl transcripts for every MLB endpoint used
├── attached_assets/              the v1 and v2 build specs, upload pack, a screenshot
└── screenshots/moneyline-final.jpg
```

Two workspace facts drive everything else. The API is Python, not the TypeScript template: `artifacts/api-server/package.json` scripts are `dev: python -m uvicorn backend.main:app …` and `start: NODE_ENV=production python -m backend.main`, and `replit.md` says so explicitly ("NOT the Express/Drizzle template stack"). The generated TypeScript client (`lib/api-client-react`) is a workspace dependency of the frontend but is imported nowhere in `artifacts/moneyline/src`; the app talks to the API through `src/api.ts`.

### 2.2 Frontend framework and entry points

React 19.1 with Vite 7.3, Tailwind CSS 4.1 (`@tailwindcss/vite`), wouter 3 for routing, TanStack Query for data, Recharts for charts, Radix/shadcn primitives, `lucide-react` icons, `framer-motion` and `next-themes` present as dependencies (the latter used only by the `sonner` toaster). Entry: `artifacts/moneyline/index.html` → `src/main.tsx` → `src/App.tsx`. The Vite config aliases `@` to `src` and `@assets` to `attached_assets`, builds to `dist/public`, and serves on `PORT` only for dev/preview (a memory note explains why the build must not require it).

### 2.3 Existing pages, tabs, routes, and navigation

`src/components/command-bar.tsx` exports `TABS`: `DESK /`, `PLAYERS /players`, `H2H /h2h`, `PARLAY /parlay`, `SEASON /season`, `WIRE /wire`. `App.tsx` mounts `DeskTab` eagerly and lazy-loads the five v2 tabs; unknown paths render a monospace "404 NOT FOUND". Keyboard `1`–`6` switch tabs outside inputs; `/` focuses the omnisearch (`OmniSearch` in `command-bar.tsx`), which ranks live teams (from `/api/teams-live`), historical team-seasons (`/api/teams`), and players (via `usePlayerHits` in `player-search.tsx`).

State lives in query strings and is therefore shareable: `/?team=OAK&year=2002` (pricer target; `tabs/desk.tsx` treats `year > 2012 && year === liveSeason` as live), `/players?id=`, `/h2h?mode=players|teams&a=&b=` (H2H has a "SHARE VIEW" clipboard button), `/parlay?legs=pk:side,…&book=`, `/wire?team=&types=`.

The Desk (`tabs/desk.tsx`) composes, top to bottom: `SlateRail` (left rail), `PricerPanel` + `EdgeFinder` (hero row), `BaParadoxPanel`, `TrackRecordPanel` + `BankrollPanel` (side by side), `LiveRecordPanel`, `ScreenerPanel`.

### 2.4 Existing reusable components

App components (`src/components/`): `slate-rail.tsx` (exports `formatOdds`, `formatProb`, `SlateGame` type; rows show fair lines, probables as buttons, ADJ line, IL flag chips with tooltips, `LIVE`/`HISTORICAL`/`FEED PARTIAL` badges), `pricer-panel.tsx` (pipeline, gauge, Front Office sliders via Radix `Slider`, live context with `PulseMeter`), `edge-finder.tsx` (two manual line inputs, verdict `Badge`, edge/break-even/½-Kelly grid, receipts, caveat; accepts `activeSlateGame` or `overrideB`), `live-record.tsx` (SEASON and ADJ records, parlay line, Recharts hit-rate curve with break-even reference line, ledger list with W/L/VOID/PENDING badges, "GRADE PENDING" button), `track-record.tsx`, `bankroll-backtest.tsx`, `ba-paradox.tsx`, `screener.tsx` (year `Select`, CSV export), `player-card.tsx`, `player-search.tsx`, `player-identity.tsx`, `percentile-bars.tsx` (`PercentileBarPair`), `pulse-meter.tsx`, `sparkline.tsx` (`DistributionSparkline`), `command-bar.tsx`, `status-strip.tsx`, `research-tag.tsx` (the "STATISTICAL RESEARCH · NOT WAGERING ADVICE" chip), `layout.tsx` (`TerminalBoot`, `PanelSkeleton`, `PanelError`), `error-boundary.tsx`.

UI primitives: 55 shadcn components under `src/components/ui/`; `badge.tsx` adds app variants `value`, `novalue`, `insidevig`, `success`. `hooks/use-mobile.tsx` (`useIsMobile`, 768 px) exists but is used only by the unused `ui/sidebar.tsx`.

### 2.5 Existing design system and styling approach

`src/index.css` defines HSL CSS variables consumed by Tailwind 4 `@theme inline`: background `#0b0e14`, card `#11151d`, popover `#161b26`, border `#1f2530`, foreground `#e6e9f0`, muted-foreground `#8b95a7`, destructive `#ea3943`, success `#16c784`, warning `#f5a623`, ring = success, `--radius: 0`. Fonts: Inter (sans) and JetBrains Mono (mono), loaded from Google Fonts in `index.html`. Utilities: `.moneyline-panel` (card with 1 px border, 12 px padding), `.moneyline-section-header` (11 px, uppercase, `tracking-widest`, rule after), `.moneyline-percentile-track`, `.tabular-nums`. A `@custom-variant dark` exists but `:root` and `.dark` are the same palette, so there is one theme. `prefers-reduced-motion` is honored globally. The visual language in code matches the screenshot: monospace almost everywhere (`font-mono` on nav, inputs, tables, verdicts), uppercase labels at 8–11 px (`text-[8px]`, `text-[9px]`, `text-[10px]` appear throughout), saturated green/red/amber semantics, zero border radius, a blinking `animate-pulse` LIVE dot, and a full-screen `TerminalBoot` overlay ("LOADING MODELS… OK / FITTING 1962–2001… OK / SYNCING 2026 FEEDS… OK / PRICING SLATE…") until `/api/health` reports `model_loaded`.

### 2.6 Existing API hooks and endpoint calls

`src/api.ts` wraps `fetch` with the error envelope (`ApiError{code,status}`) and exposes: `useHealth` (polls each second until `model_loaded`), `useTeams`, `useTeamPrice`, `useMatchup` (mutation), `usePrice` (mutation), `useSlate(date?)` (5-minute refetch; the app never passes `date`), `useScreener`, `useTrackRecord`, `useBacktest`, `useBaParadox`, `useLiveRecord` (60-minute refetch), `useTeamsLive`/`useLiveSeason`, `usePlayers`, `usePlayerCard`, `useComparePlayers`, `useTeamLive`, `usePriceInputs`, `useParlayPrice`, `useParlayLog` (invalidates `record`), `useSeasonSim`, `useTeamOutlook`, `useWire`, `useGradeRecord`.

### 2.7 Backend routes and response shapes

All routes are in `backend/main.py`. Errors use `{"error":{"code","message"}}` via `MoneylineError`, a `RequestValidationError` handler (400 `invalid_request`), and a catch-all 500 `internal_error`. A middleware logs `path team ms cache status` and sets `X-Response-Time-Ms`. CORS allows only the dev origins. `/api/docs` is disabled in production.

| Route | Purpose | Key response fields (as coded) |
|---|---|---|
| `GET /api/health` | boot probe | `model_loaded`, `startup_ms`, `database_ready`, `model_version` (hard-coded `"chronological-1962-2001-v1"`) |
| `GET /api/teams` | historical team-seasons | `teams[{team, year, label}]` |
| `GET /api/team/{team}/{year}` | historical chain (1962–2012 only; 400/404 otherwise) | `inputs`, `predicted{rs,ra,rd,wins,playoff_prob}`, `fair_line`, `offense_only`, `receipts[{feature,value,coefficient,contribution}]`, `actual`, `data_ranges` |
| `POST /api/price` | chain for arbitrary inputs (`obp,slg,oobp?,oslg?`) | same shape as above without `actual` |
| `POST /api/matchup` | two input sets + optional manual `book_line_a/b` | `model_prob_a/b`, `implied_prob_a/b`, `edge_pp`, `vig_pp`, `break_even_rate`, `verdict` ∈ {`VALUE`, `INSIDE THE VIG — NO PLAYABLE EDGE`, `NO VALUE`, `NO LINE`}, `kelly_fraction` (½-Kelly for side A only), `fair_line_a/b`, `formula`, `team_a/b_prediction`, `receipts`, `caveat` |
| `GET /api/slate?date=` | today's priced games (or historical fallback) | `mode` ∈ {`live`,`historical`}, `feed_up`, `date`, `updated_at`, `cache`, `record_persisted`, `games[]` with `game_pk`, `game_date`, `time_et`, `status`, `away/home` (B-Ref codes), `away_name/home_name`, `model_prob_home`, `fair_lines{home,away}`, `probables{away,home}`, `adj_prob`, `adj_fair_lines`, `adj_detail{away,home,method}`, `flags[]`, `away_inputs`, `home_inputs`, `badges`, `cache_hit`; failed rows carry `pricing_error: true` and `FEED PARTIAL` |
| `GET /api/screener?year=` | mispricing table (historical, or live "SEASON SO FAR") | `year`, `rows[]`, `offense_only`, `payroll_available: false`, `season_so_far`, `sample_label`, `method` |
| `GET /api/track-record` `GET /api/backtest` `GET /api/ba-paradox` | precomputed artifacts | see `precompute.py`; backtest is a paper $1,000 series |
| `GET /api/record` | live paper record | `picks`, `graded`, `wins`, `losses`, `voided`, `hit_rate`, `units_pnl`, `break_even_rate` (110/210), `tracking_since`, `sample_label` (`SMALL SAMPLE` under 100 graded), `curve[]`, `entries[]` (per pick incl. `adj_*`, `probables`), `adj_record{…}`, `parlay_record{…, line}`, `database_ready` |
| `POST /api/record/grade` | manual grading trigger | grading counts + full `record` |
| `GET /api/players?group&pool&q` | pool search | `players[]`, `floor_note` |
| `GET /api/player/{id}` | player card | stat line, percentiles, `model{delta_rs/ra, mwaa, receipts, wins_formula}`, `fair_odds_framing`, `would_beane_buy`, `salary{available:false}` |
| `GET /api/compare/players?a&b` | comparison or boundary payload | `mode` ∈ {`hitting`,`pitching`,`boundary`}, `deltas`, `percentile_pairs`, `verdict{leader, margin_mwaa, line}` |
| `GET /api/wire?team&types&limit` | merged feed | `items[]` (`type` ∈ TRADE/SIGNING/IL/ACTIVATED/RESULT/NEWS, `source` ∈ TRANSACTION/MLB.COM/ESPN/DESK), `sources_up{transactions,news,desk}`, `updated_at` |
| `POST /api/parlay/price` | price 2–6 legs from today's live slate | `legs[]`, `combined_prob`, `fair_odds`, `independence_note`, `price_basis: "SEASON model probabilities (not ADJ)."`, `vig_comparison{…}`, `book{book_odds, implied_prob, edge_pp, ev_per_unit, half_kelly, stake_label}` or `null`; 400 `correlated_legs`, 404 `leg_not_found`, 503 `slate_unavailable` |
| `POST /api/parlay/log` | store one paper slip per day | `stored`, `already_logged`, `slip_id`, `priced`, `note` |
| `GET /api/team-live/{team_id}` | live inputs + record + flags + pulse | `inputs`, `sample_label` (`THRU N GP`), `flags[]`, `pulse{…evidence…}`, `hard_rule` |
| `GET /api/season-sim` `GET /api/season-sim/team/{id}` | simulation table; team outlook | `rows[]`, `assumptions[]`, `seed`, `iterations`, `input_signature`, `next_season{status: "NOT PRICED"}`; outlook `next_10[]`, `mean_opponent_rating` |
| `GET /api/teams-live` | live team directory | `season` (the live-season contract), `teams[]` |
| `GET /{path}` | SPA fallback (dev/single-process) | serves `dist/public/index.html`, 404 for unknown `api/` |

### 2.8 Model and pricing calculations

`backend/precompute.py::build_artifacts` fits, chronologically (train ≤ 2001, 902 rows; test ≥ 2002, 330 rows), `RS ~ OBP + SLG`, `RS ~ OBP + SLG + BA` (paradox demo), `RA ~ OOBP + OSLG` (1999–2001, 90 rows), `W ~ RD`, and `Playoffs ~ W` (logistic), asserting the bundled CSV shape, and writes the joblib bundle plus three JSON artifacts. `backend/inference.py::predict_from_inputs` runs the chain for any inputs and returns receipts (`value × coefficient = contribution`) and a generic fair line from Pythagorean strength; `predict_team` adds actuals for a bundled team-season. Game pricing (`feeds.py::_chain_probability`) is `predict_from_inputs` for each team → `pythagorean_strength(rs, ra)` (exponent 2) → `log5_probability(home, away)`. **There is no home-field term, no recent-form input, and no lineup or bullpen model.** The ADJ price (`feeds.py::_blended_side`) replaces a team's OBP/SLG-against with `w·starter + (1−w)·team`, `w = IP/(GS×9)` capped to [0.4, 0.8] (`analytics.starter_innings_share`, `blend_defense_inputs`), when the probable starter is in the "all" pitching pool.

The smoke test reproduces the verified ground truth in this sandbox: 2002 OAK → RS 808, RA 662, 96.4 W, 76.4% playoff odds; RS coefficients −804.6 / 2737.8 / 1584.9; runs per win ≈ 9.5 from the fitted slope.

### 2.9 Probability, edge, EV, vig, and bankroll calculations

`backend/odds.py`: `probability_to_moneyline` (rounded to the nearest 5), `moneyline_to_probability`, `edge_probability` (model − implied, a probability difference), `market_vig` (overround), `decimal_odds`, `half_kelly_fraction` (full Kelly `(p·decimal − 1)/(decimal − 1)`, halved, floored at 0 — **no cap**), `decimal_to_american`, `parlay_probability` (2–6 legs, product), `parlay_book_decimal`, `parlay_ev`, `parlay_vig_comparison` (house take on the parlay vs the same legs single at a −110 reference), `pythagorean_strength`, `log5_probability`.

The only verdict logic in the codebase is in `POST /api/matchup`: `vig_threshold = max((vig or 0.0476)/2, 0)`; `edge > threshold → VALUE`; `0 ≤ edge ≤ threshold → INSIDE THE VIG — NO PLAYABLE EDGE`; `edge < 0 → NO VALUE`; no line → `NO LINE`. It evaluates **side A only** (away when a slate game is selected) and the frontend renders `edge_pp` with a `%` suffix although it is a probability-point gap. Parlay EV and ½-Kelly (`_price_parlay_payload`) use SEASON probabilities only.

Bankroll: the only bankroll in the product is the historical paper backtest (`precompute._backtest`: $1,000, flat 1 unit, no vig, "buy" teams whose predicted wins exceed the prior by ≥ 5, paid at even money on a playoff appearance). Its committed result (`backend/static_data/backtest.json`) is **model −22.0 units on 96 bets (38.5%), baseline −9.0 on 87** — the product already publishes a losing backtest. There is no user bankroll, unit, profile, cap, or stake persistence anywhere.

### 2.10 Existing database schema and persistence

`backend/record_store.py` connects with psycopg using `DATABASE_URL` (`_connection`), and `ensure_schema()` runs idempotent DDL at boot. Effective tables (the base two were created outside the repo, per `replit.md`; the DDL in `tests/conftest.py` mirrors them):

- `moneyline_slate_snapshots(id, snapshot_date UNIQUE, mode, created_at)`
- `moneyline_record_picks(id, snapshot_id → snapshots, game_pk UNIQUE, game_date, away_team, home_team, pick_team, model_probability, fair_line, entered_line, final_away, final_home, result, units_pnl, graded_at, probables jsonb, adj_probability, adj_pick_team, adj_fair_line, adj_result, adj_units_pnl)`
- `moneyline_parlay_slips(id, slip_date UNIQUE, legs jsonb, combined_probability, fair_line, book_line, result, units_pnl, graded_at, created_at)`

`lib/db/src/schema/moneyline.ts` (Drizzle) declares only the first two tables without the v2 columns, and `scripts/post-merge.sh` runs `pnpm --filter db push` (`drizzle-kit push`, un-forced) after merges. Two schema authorities exist and the TypeScript one is stale; a push could propose dropping the `adj_*`/`probables` columns of a table it manages. No user, preferences, bankroll, bet, odds, or model-version tables exist. `entered_line` is never written by application code (only by `tests/conftest.py::seed_pick`), so every graded pick pays at −110.

### 2.11 Pick logging and grading behavior

`store_slate_snapshot` (called from `GET /api/slate` when `mode == "live"` and from the scheduler) inserts one snapshot per `snapshot_date` and one pick per `game_pk` (`ON CONFLICT DO NOTHING`), choosing `pick_team` as the side with `model_prob_home ≥ 0.5` (the lean) and `adj_pick_team` likewise from `adj_prob`. It does not check game status, so a first load after games have started still records picks for them. `grade_pending_records` (`main.py`) resolves each pending pick via `feeds.get_final_score` (`/api/v1.1/game/{pk}/feed/live`): cancelled → `void_pick` (VOID, 0 units); vanished `game_pk` after `VOID_AFTER_DAYS` (default 3) → VOID; final → `grade_pick` (WIN/LOSS, `units_pnl = payout or −1`, ADJ graded on the same payout); ties and non-final games stay pending. Parlays grade all-or-nothing (`_grade_pending_parlays`, `grade_parlay`) at `book_line` or, absent one, `fair_line`. `get_record` computes totals, a cumulative curve over decided picks only, `adj_record`, and `parlay_record`. The ledger is global — there is one record, one parlay slip per day, no user dimension.

### 2.12 Background jobs and scheduled processes

`lifespan` in `main.py` loads models, runs `ensure_schema` (skipped with a warning if the database is unreachable), and starts `grade_scheduler` — an `asyncio` loop that snapshots the live slate and grades pending picks every `GRADE_INTERVAL_SECONDS` (default 1800). Every `GET /api/slate` also spawns a `grade_pending_records` task. There is no cron, no external scheduler, and no queue. `.agents/memory/background-scheduler-constraints.md` records that the loop only runs while a server process is alive and that a scale-to-zero deployment "silently misses ledger days"; `.replit` sets `deploymentTarget = "autoscale"`.

### 2.13 Existing tests and validation commands

`python smoke_test.py` (executed here, passes): bundle shape, 2002 OAK chain, coefficients, odds conversions, half-Kelly, edge, vig, log5, v2 math (runs/win, mWAA receipts, parlay math including the same-game rejection through `TestClient`, blends, percentiles, Beane badge, pulse arithmetic, simulation determinism), and a production-entrypoint boot test that spawns `python -m backend.main` and polls `/api/health`. `python -m pytest -q` (executed: 27 passed, 16 skipped, 3 failed): `tests/test_grade_pick.py` and `tests/test_grade_pending_records.py` cover grading, voiding, ties, postponements, feed crashes, parlay settlement against an isolated Postgres schema (skipped without `DATABASE_URL`); `tests/test_live_season_contract.py` pins the live-year contract including clock advance; `tests/test_serve_spa.py` requires a built frontend. `pnpm run typecheck` / `pnpm run build` exist at the workspace root. No frontend unit or end-to-end tests exist.

### 2.14 Build, deployment, and startup configuration

Two Replit artifacts deploy as two services behind a path router. **API** (`artifacts/api-server/.replit-artifact/artifact.toml`): paths `/api`, production build `pnpm --filter @workspace/moneyline run precompute` (→ `python -m backend.precompute`), production run `pnpm --filter @workspace/api-server run start` (→ `NODE_ENV=production python -m backend.main`), `PORT=8080`, startup health `/api/health`. **Web** (`artifacts/moneyline/.replit-artifact/artifact.toml`): paths `/`, build `precompute && vite build`, run `python -m backend.serve_spa` (Starlette static server with immutable caching for `/assets/`, 404 for missing file-like paths, index fallback otherwise), `PORT=18612`. `.agents/memory/deployment-startup-probe.md` explains why the web service must not run a second `backend.main`. Development: `python -m uvicorn backend.main:app --reload` on 8080 and `vite --host` on 18612. Required env: `DATABASE_URL`; optional `PORT`, `CACHE_TTL_SECONDS`, `POOL_CACHE_TTL_SECONDS`, `WIRE_CACHE_TTL_SECONDS`, `FEED_TIMEOUT_SECONDS`, `GRADE_INTERVAL_SECONDS`, `VOID_AFTER_DAYS`, `DEV_ORIGIN`, `LOG_LEVEL`.

### 2.15 Live-season and historical-season behavior

`feeds.current_season()` is the Eastern-time calendar year and is the single live-season authority (`/api/teams-live.season`; `tests/test_live_season_contract.py`). Historical routes accept 1962–2012 only (`/api/team/{team}/{year}` rejects others; `/api/screener` accepts 1962–2012 or the live year). `get_slate` returns `mode: "historical"` with five famous seasons priced against a league-average baseline whenever the schedule has no games, team statistics fail, or the feed is unavailable (`historical_slate`). The frontend switches copy on `mode` (`HISTORICAL MODE` banner, `NO LIVE SLATE` in Parlay Lab). Caches are season-scoped (`pool:{season}:…`, `standings:{season}`, `remaining_schedule:{season}`); the simulation cache key is prefixed with the season.

### 2.16 Existing loading, error, empty, stale-data, and unavailable-data states

Loading: `TerminalBoot` full-screen overlay until health reports `model_loaded`; `PanelSkeleton` per panel; `LOADING POOL…`, `PRICING…`, `SEARCHING…`. Errors: `PanelError` with red badge (pricer, backtest, live record, simulation, wire); inline `role="alert"` for malformed lines (`AMERICAN LINE MUST BE ≤ −100 OR ≥ +100`), correlated legs, `SIX LEGS MAX`; `ErrorBoundary` at root (dev-only detail). Empty: `NO GAMES`, `Enter a book line to calculate edge.`, `PICK A PLAYER`, `PICK 2–6 SIDES FROM TODAY'S SLATE`, `NO GRADED PICKS YET`. Unavailable/refusal: `HISTORICAL MODE`, `NO LIVE SLATE`, `FEED PARTIAL` row badge, `NOT IN THE {season} POOL`, `HITTER VS PITCHER: NOT PRICED`, `{season+1}: NOT PRICED`, `NO ADJ — STARTER DATA MISSING`, `NOT ON TODAY'S SLATE`, `PERSISTENT STORE UNAVAILABLE — CANNOT VERIFY RECORD`, wire `FEED(S) DOWN — SHOWING CACHED / REMAINING SOURCES ONLY` with an `AS OF` stamp, `THE WIRE IS DOWN`. Sample-size honesty: `THRU N GP` on live inputs, `SMALL SAMPLE`/`ESTABLISHED SAMPLE` on the record, `SEASON SO FAR` on the live screener. **Absent:** any stale-price state (there are no prices), any per-card "insufficient data" verdict, any data-status page, any pending/graded distinction on the Desk beyond ledger badges.

### 2.17 Existing integrations and external data sources

MLB Stats API (`statsapi.mlb.com`, keyless): `/api/v1/schedule` (hydrate `probablePitcher,linescore`; also for the remaining schedule), `/api/v1/teams/{id}/stats`, `/api/v1/teams/stats`, `/api/v1/stats` (player pools, paginated), `/api/v1/teams`, `/api/v1/standings` (current and prior season), `/api/v1/teams/{id}/roster?rosterType=40Man`, `/api/v1/seasons`, `/api/v1/transactions`, `/api/v1.1/game/{pk}/feed/live`. Each call has a 10 s timeout, one retry, a browser-like `User-Agent`, and coalesced TTL caches (`AsyncTTLCache`: 600 s default; pools/rosters 21,600 s; wire sources 1,800 s). MLB RSS and ESPN news are coded in `feeds.get_news` but the module never defines `RSS_URL`, `ESPN_NEWS_URL`, or `_espn_dead`, so the function raises `NameError` on first call (reproduced), which `wire.get_wire` swallows into `sources_up.news = false`. Google Fonts is the only frontend external. No odds provider, no payments, no email, no analytics SDK.

### 2.18 Existing authentication, accounts, subscriptions, or billing

None. No auth middleware, session, token, user model, or billing code exists in `backend/` or the frontend; the only "user" state is URL query parameters. The `@replit/connectors-sdk` dependency at the workspace root is unused by the app.

### 2.19 Existing accessibility and mobile behavior

Present: `aria-live="polite"` on the Edge Finder verdict, the parlay result, and the H2H verdict; `role="alert"` on validation errors; `aria-label` on the search input; `aria-pressed` on parlay side buttons; `aria-current` on the active tab; keyboard activation on slate rows (`role="button"`, `tabIndex`, Enter/Space) with `focus-visible` outlines; `prefers-reduced-motion` handling; `color-scheme: dark` and pre-paint background to avoid a white flash. Gaps: many labels at 8–10 px; W/L conveyed by single letters in green/red badges; `index.html` sets `maximum-scale=1`, which blocks pinch zoom (WCAG 1.4.4); no skip link; no bottom navigation; charts have no text alternative. Responsive: Tailwind breakpoints stack the Desk to one column below `lg` (1024 px), the rail becomes full-width, header wraps; there is no mobile-specific navigation or sheet pattern; `useIsMobile` is unused by app code.

### 2.20 Additional findings worth recording

`GET /api/slate?date=YYYY-MM-DD` prices any date's games with current season inputs and reports `mode: "live"` whenever games exist, and the route persists the snapshot whenever `mode == "live"` — so a past date creates backdated picks with hindsight inputs and a future date creates picks under that date. The UI never passes `date`, but the ledger's integrity depends on that convention rather than a guard. The `MODEL SLIP OF THE DAY` is computed client-side in `tabs/parlay-lab.tsx::computeModelSlip` (highest EV 2–3-leg combination at −110 per leg) and shown by default. `StatusStrip` hard-codes `MODEL: 1962–2001-v1`. `BankrollPanel` carries a `SIMULATION` badge and footnotes; `TrackRecordPanel` shows the historical R², MAE, accuracy vs baseline, and calibration buckets.

---
## 3. Discrepancy report between the strategy and the current build

### 3.1 Status categories used below

1 Already implemented · 2 Partially implemented · 3 Implemented under a different name or route · 4 Frontend work only · 5 Backend work required · 6 Database or persistence work required · 7 External data-provider work required · 8 Authentication or billing work required · 9 Blocked by an unresolved product or technical question · 10 Not currently feasible without clarification.

A row can carry a current status and the status of the work needed (for example "2 → 4, 5" means partially implemented; completing it is frontend plus backend work).

### 3.2 Comparison table

| v3 proposal | Evidence in GitHub repository | Current status | Required changes | Dependencies | Risk |
|---|---|---|---|---|---|
| Today dashboard as default route with verdict-grouped game cards | `tabs/desk.tsx` is the default route `/`; `SlateRail` lists priced games with fair lines, probables, ADJ, flags; no grouping, no verdicts | 2 → 4, 5, 7 | New `/today` page over `GET /api/slate`; grouping requires a verdict, which requires prices | Odds feed for verdicts; without it, group by data readiness only | Cards without prices read as "lean = pick" unless copy is careful |
| Daily summary strip ("15 games · 2 worth a look…") | `slate.games[]` gives counts; nothing computes verdict counts | 2 → 4 (readiness counts) / 5, 7 (verdict counts) | Client-side counts of live/final/pricing_error/starters-missing now; verdict counts after prices | Odds feed | None for readiness counts |
| Game card three layers (answer / explanation / numbers) | Slate row shows fair lines + probabilities; `EdgeFinder` shows receipts; no card component | 4 (layers 1 and 3 from existing fields) / 5 (explanations) | New `GameCard` + `Disclosure` components; explanation fields from backend | Explanation generator | Layer 1 without a price must say "no price loaded" |
| Verdict engine (`Bet candidate`, `Marginal value`, `No value detected`, `Avoid at this price`, `Insufficient data`, `Price unavailable`, `Starters not confirmed`) | Only `POST /api/matchup` verdicts: `VALUE / INSIDE THE VIG — NO PLAYABLE EDGE / NO VALUE / NO LINE`, side A only, manual lines (`main.py` lines 543–553) | 3 (subset, different names) → 5, 7 | New pure `evaluate()` on both sides with published thresholds; wire into slate rows and a `POST /api/evaluate` | Prices for automatic verdicts; manual entry works today | Threshold choice; must be versioned |
| Signal strength (Strong/Moderate/Weak) | Nothing computes it; no model error constant exists | 5, 9 | Define σ from calibration; implement in evaluator | Verdict engine; decision on σ | Mislabeling; must be provisional |
| Risk row ("loses X% of the time", payout shape, uncertainty) | `model_prob_home` and `adj_prob` exist per row; `THRU N GP` via `/api/team-live` and `/api/teams-live` | 4 (chance to lose, uncertainty from GP and ADJ gap) / 7 (payout shape needs price) | Client computation from existing fields | — | None |
| Explanations: "why the model leans" from receipts | Receipts exist in `predict_from_inputs` and `/api/matchup`; slate rows return `away_inputs/home_inputs` but not predicted RS/RA; `adj_detail` exists | 2 → 5 | Add per-team `predicted{rs,ra}` and strength to slate rows; add templated `reasons` server-side (or compute client-side from `/api/price` per team, not recommended) | — | Templates must use priced inputs only |
| Explanations: "why worth reviewing" (price vs fair) | `edge_pp`, `break_even_rate`, `fair_line` in `/api/matchup` with manual line | 3 → 5, 7 | Part of evaluator output | Prices | — |
| Context chips: injuries, transactions, pulse, "not in the price" | `get_injury_flags`, `get_team_pulse`, wire items; slate rows carry `flags[]`; `hard_rule` copy exists | 1 → 4 (restyle, label) | Render as chips with the "not in the price" label | — | Pulse without evidence confuses; keep behind expansion |
| Odds feed: current, opening, closing prices per book | None; only manual `book_line_a/b` and parlay `book_odds`, never stored | 7 → 5, 6 | Provider integration in `feeds.py`, `line_snapshots` table, closing capture at first pitch | Provider contract, keys via env (not in repo), legal review | Cost, licensing, reliability |
| Best-price / multi-book comparison and preferred books | None | 7, 8 (preferences) | After odds feed; preferences store | Odds feed, accounts | — |
| Closing-line value (model and user) | None; `entered_line` column exists but is never written | 7 → 5, 6 | Store price used and closing price per pick; compute CLV | Odds feed | — |
| Line movement (open → now → close) | None | 7 → 5, 6 | `line_snapshots` | Odds feed | — |
| Candidates-only record graded at the price shown | Record grades leans at flat −110 (`grade_pick` default) | 7 → 5, 6 | New pick kind and price columns; grade at recorded price | Odds feed, verdict engine | Ledger continuity |
| All-leans record (every game, flat unit) | `GET /api/record` totals, `curve`, `entries`; "Units (Flat −110)" label in `live-record.tsx` | 1 → 4 (restyle, rename) | Present as "every game, flat one unit — a model check" | — | — |
| ADJ vs SEASON experiment record | `adj_record` in `get_record`; UI side by side | 1 → 4 | Rename to "with tonight's starters" vs "season strength" | — | — |
| Parlay record | `parlay_record` with `line` string; one global slip per day | 1 → 4 | Keep; note it is a single paper slip per day, not per user | — | — |
| Historical tests separated from live | `TrackRecordPanel` (backtest metrics) and `BankrollPanel` (paper backtest, `SIMULATION` badge) on the Desk | 2 → 4 | Move under a Track Record page with the historical banner; the backtest is −22u for the model and must stay visible | — | None |
| Live calibration by bucket | Not computed; `entries[]` carry `model_probability` and `result` | 4 | Compute buckets client-side from `/api/record` entries (or add server-side) | — | Small samples |
| Confidence intervals on ROI | None | 4 or 5 | Client-side interval from graded entries (units per pick) | — | Method must be documented |
| Model version registry and changelog | Hard-coded `model_version` in `/api/health`; `StatusStrip` literal | 2 → 5, 6 | Version constant in `precompute`/`inference`, stamped on snapshots; versions table or JSON | — | — |
| Home-field adjustment | `log5_probability` symmetric; no HFA anywhere | 5, 6, 9 | Model change, grading by version, decision on rollout | Decision | Changes the ledger going forward |
| Detail level (Essentials / Full detail) and Explain terms | No preferences anywhere; no `localStorage` in app code | 4 (local) → 6, 8 (synced) | Preference store in the client, later per-user | Accounts for sync | — |
| Terminology dictionary, sentence-case copy | Labels hard-coded uppercase mono across components | 4 | `terminology.ts` and a copy pass | — | — |
| Navigation: Today · Research · Parlay Check · Track Record · Bankroll | `TABS` in `command-bar.tsx`: DESK/PLAYERS/H2H/PARLAY/SEASON/WIRE; keyboard 1–6 | 4 | New shell, redirects from old paths, hub routes | — | Bookmark breakage without redirects |
| Research hub (Players, Matchups, Teams & Season, News & Context, Learn) | `/players`, `/h2h`, `/season`, `/wire` exist; Team Pricer and Screener live on `/` | 3 → 4 | Route wrappers and moves; no backend change | — | — |
| Parlay Check (verdict-first, singles comparison) | `tabs/parlay-lab.tsx` with `POST /api/parlay/price` (combined prob, fair odds, book edge/EV/½-Kelly, vig comparison at −110 reference) | 2 → 4 (verdict, layout) / 5 (per-leg book lines for a true singles comparison; ADJ basis option) | Reframe page; add optional per-leg lines to the API | — | — |
| Remove "model slip of the day" from default | Client-side `computeModelSlip` in `parlay-lab.tsx`, shown by default | 4 | Remove or gate | — | — |
| Bankroll setup, profiles, dollar stakes, caps, shrinkage | Only `half_kelly_fraction` (uncapped, side A) and the historical paper backtest | 4 (local paper bankroll with manual price) → 5 (`POST /api/stake`), 6, 8 (persisted) | Stake calculator; profile caps; persistence later | Prices or manual entry | Compliance guardrails |
| My bets with grading and CLV | None | 6, 8, 7 | Bets table, grading job extension, closing capture | Accounts, odds feed | — |
| Limits, cooling-off, paper mode | None | 4 (local) → 6, 8 | Client toggles first; server enforcement with accounts | Accounts | — |
| Onboarding, coach marks, education center | None | 4 → 6 (completion sync) | New screens and content | — | — |
| Share cards (server-rendered image) | H2H copies the URL only | 5 | Image endpoint | — | Must exclude stakes |
| Notifications | None | 8, 5 | Accounts, push infrastructure | Accounts | Urgency risk |
| Data status page | `/api/health`, `slate.cache`, `wire.sources_up`, `updated_at` fields | 2 → 5 | Expose cache ages per source | — | — |
| Stale-price states | None (no prices) | 7 → 4 | After odds feed | Odds feed | — |
| Light theme, token refresh, radius, type scale | Single palette in `index.css`; `--radius: 0`; `.dark` variant unused | 4 | Token pass; second palette | — | — |
| Mobile bottom nav, sheets, PWA manifest | None; responsive stacking only; `maximum-scale=1` | 4 | Shell rework; manifest and service worker | — | — |
| Fix dead news feed | `feeds.get_news` references undefined `RSS_URL`/`ESPN_NEWS_URL` | 5 (trivial) | Define constants; add a unit test | — | — |
| Guard ledger against `?date=` writes | `GET /api/slate` persists any `mode == "live"` payload | 5 (trivial) | Persist only when date is today (ET) and only pre-game rows | — | Ledger integrity |
| Always-on scheduler in production | `autoscale` target with an in-process loop | 9 | Reserved-VM, external scheduler, or accept visit-driven snapshots | Decision | Missed ledger days |
| Reconcile Drizzle schema with Python migration | `lib/db` stale; post-merge runs `db push` | 6 (small) | Update or remove the Drizzle schema; decide the single authority | Decision | Accidental column drops |

### 3.3 Major discrepancies, explained

**A. Sportsbook prices on every card.**
*Strategy assumes:* a price per side per book with timestamps, feeding verdicts, edges, expected return, stale flags, and line movement.
*Code does:* prices exist only as user-typed inputs (`EdgeFinder`, `ParlayLab`), evaluated on the fly and discarded; no provider, no storage, no timestamps.
*Why it matters:* every price-dependent element in v3 — verdict counts, "worth a look", expected return, stake, candidates record, CLV — is unbuildable until a feed exists, and building UI that implies prices exist would be dishonest.
*Incremental migration:* yes. Ship cards that show model chance, fair price, starters, sample, and an "Add a price" affordance (which exists functionally as manual entry) with `Price unavailable` as the verdict; add the feed behind the same card contract.
*Preserve existing behavior:* manual entry must survive forever as the fallback and as the "your price" path.
*Decision required:* provider, book coverage, budget, and legal review of commercial odds redistribution.

**B. The verdict engine.**
*Strategy assumes:* a two-sided, published-threshold evaluator producing seven labels, server-side, on every slate row.
*Code does:* `POST /api/matchup` returns a one-sided verdict (`VALUE` when edge exceeds half the vig) computed only for side A, plus half-Kelly for side A, only when a line is typed.
*Why it matters:* the "lean is not the value side" failure the strategy warns about is present today — with a slate game selected, the Edge Finder evaluates the away team only, so a favorable price on the home side is never surfaced.
*Incremental migration:* yes. Add a pure `evaluate(p_season, p_adj, price_home, price_away, gp, starters_confirmed, price_age)` in a new `backend/verdict.py`, unit-tested against the Appendix A fixtures, exposed as `POST /api/evaluate` and merged into slate rows when prices exist; leave `/api/matchup` untouched for the historical Matchups tool.
*Preserve:* `/api/matchup`'s shape and its three-way verdict for H2H.
*Decision required:* thresholds and σ; whether `/api/matchup` adopts the new labels or keeps the terminal ones behind a rename layer.

**C. Candidates record, price-graded units, and closing-line value.**
*Strategy assumes:* picks graded at the price shown when the verdict was issued, plus a closing price for CLV.
*Code does:* every pick is the lean, graded at −110 unless `entered_line` is set, and nothing sets it.
*Why it matters:* the live record is a model check, not a betting record; presenting it as the latter would overclaim. CLV is impossible without captured prices.
*Incremental migration:* yes, additively: new columns (`pick_kind`, `price_used`, `book`, `price_captured_at`, `closing_price`, `clv_pts`, `model_version`) with `IF NOT EXISTS`, new rows only from feed go-live; the all-leans record continues unchanged.
*Preserve:* existing rows, `game_pk` uniqueness (note: a candidate pick and a lean pick for the same game would collide on the unique index — the candidates record needs its own table or a composite key), the ADJ dual grading, `VOID` semantics.
*Decision required:* new table versus widening the picks table; whether the units curve keeps the −110 assumption for the leans record (recommended: yes, labeled).

**D. Home-field adjustment.**
*Strategy assumes:* absent, and recommends shipping it in Phase 1 as a dated model version.
*Code confirms:* absent (`log5_probability` symmetric; `_chain_probability` takes no venue input).
*Why it matters:* the model prices home sides too low by roughly three to four points at even matchups, which will bias any future candidates record toward road teams.
*Incremental migration:* possible in three ways — a third graded price (mirrors the ADJ pattern; UI already renders two prices side by side), a versioned change to both prices with the record split by `model_version`, or a display-only note. The record's history has no version column today, so the version must be added before any change.
*Preserve:* the existing SEASON and ADJ semantics and the graded history.
*Decision required:* the HFA value's source (a published constant justified from MLB history versus a fitted term — the bundle has no game logs to fit one), and the rollout pattern.

**E. Explanations.**
*Strategy assumes:* templated reasons generated from receipts, starter blend, and sample size, with context kept separate.
*Code does:* receipts and `adj_detail` exist, but slate rows omit each team's predicted runs and Pythagorean strength, and no reason text is generated anywhere.
*Why it matters:* the explanation layer is the cheapest high-value piece of v3, and it needs three additional numbers per row to be honest (predicted RS/G, RA/G, strength), which the server already computes and throws away in `_price_game`.
*Incremental migration:* yes; add `model_detail` to slate rows and a `reasons` object; the frontend renders whatever fields exist.
*Preserve:* the receipts format (`feature, value, coefficient, contribution`) used by `EdgeFinder`.
*Decision required:* none.

**F. Accounts, preferences, bankroll, user bets.**
*Strategy assumes:* per-user preferences, a persisted bankroll, a bet log, and later billing.
*Code does:* nothing per-user; no `localStorage`, no auth, no user tables; even the parlay slip is one global paper slip per day.
*Why it matters:* every "my" surface needs accounts; but the strategy's first-pass experiences (detail level, explain terms, a paper bankroll with manual prices, limits) can run entirely client-side in browser storage without accounts, which is the honest incremental path.
*Incremental migration:* yes — client-side first, server-side with accounts later, migrating local state on first sign-in.
*Preserve:* the global public record must stay separate from any user record.
*Decision required:* auth provider, billing processor policy on betting-information subscriptions.

**G. Track Record as a destination.**
*Strategy assumes:* a `/record` page with four visually distinct records.
*Code does:* four panels on the Desk: `LiveRecordPanel` (leans, ADJ, parlays), `TrackRecordPanel` (historical fit metrics and calibration), `BankrollPanel` (historical paper backtest, which shows the model at −22 units). All data needed exists on `/api/record`, `/api/track-record`, `/api/backtest`.
*Why it matters:* the page is frontend work only, and the negative backtest is a trust asset if labeled correctly and a liability if hidden.
*Incremental migration:* yes; compose existing panels under the new route, keep the Desk panels until the redirect period ends.
*Preserve:* the "GRADE PENDING" manual trigger, the ADJ note, the `SMALL SAMPLE` label.
*Decision required:* whether the paper backtest's selection rule (predicted wins ≥ prior + 5, paid even money on a playoff appearance) is still worth presenting as a "backtest" or relabeled as an educational simulation. Recommendation: relabel; it never priced a market.

**H. Navigation and routes.**
*Strategy assumes:* `/today`, `/research/*`, `/parlay`, `/record`, `/bankroll`, `/game/{gamePk}`.
*Code does:* `/`, `/players`, `/h2h`, `/parlay`, `/season`, `/wire`, with meaningful query strings and keyboard 1–6.
*Why it matters:* existing links and the H2H share URLs must keep working; `/parlay` already matches.
*Incremental migration:* yes; add new routes alongside, redirect old ones (`/players → /research/players`, `/h2h → /research/matchups`, `/season → /research/teams`, `/wire → /research/news`, `/ → /today` once Today exists), preserve query parameters in redirects.
*Preserve:* query-string state, keyboard shortcuts (remapped 1–5), omnisearch targets.
*Decision required:* none.

**I. Model version registry.**
*Strategy assumes:* a changelog with each version's record from its date.
*Code does:* a literal string in `/api/health` and `StatusStrip`; snapshots do not record a version.
*Why it matters:* any model change (HFA, threshold changes) is unattributable in the ledger without it.
*Incremental migration:* yes; add `MODEL_VERSION` to `precompute.py`, expose it, stamp new snapshot rows; old rows get the current version by default (documented).
*Preserve:* existing rows.
*Decision required:* none.

**J. Scheduler and deployment.**
*Strategy assumes:* the record grades itself daily.
*Code does:* an in-process loop that runs only while `backend.main` is alive; deployment target is `autoscale`, which the project's own note says can miss days; `GET /api/slate` also snapshots and grades, so a daily visitor keeps it alive in practice.
*Why it matters:* the public record's completeness is the product's trust asset; silent gaps are worse than errors.
*Incremental migration:* yes; either switch the API service to an always-on target or add an external scheduled call to `POST /api/record/grade` and a new `POST /api/record/snapshot` (today-only).
*Preserve:* idempotent snapshot/grade semantics.
*Decision required:* hosting choice.

**K. Two schema authorities.**
*Strategy assumes:* the Python migration is the only one.
*Code does:* `lib/db` Drizzle schema declares two tables without the v2 columns; `post-merge.sh` runs `drizzle-kit push`.
*Why it matters:* an un-forced push may propose dropping `probables` and `adj_*`; a forced one would.
*Incremental migration:* delete the Drizzle schema (and the push step) or bring it to parity and treat it as documentation only.
*Preserve:* every existing row and column.
*Decision required:* single authority (recommended: `record_store.ensure_schema`).

**L. Ledger integrity against the `date` parameter.**
*Strategy assumes:* snapshots are "frozen the morning of the game and never edited."
*Code does:* snapshots on any date requested, including past dates priced with current inputs and final games.
*Why it matters:* an outsider calling `/api/slate?date=2026-07-01` would write picks that are graded immediately with hindsight; the record's honesty claim would be false even though no one in the UI can trigger it.
*Incremental migration:* a two-line guard (persist only when the requested date equals today in Eastern time; skip rows whose status is not `Scheduled`/`Pre-Game`), plus a test.
*Preserve:* read-only behavior of `?date=` for research.
*Decision required:* none.

**M. Dead headline feed.**
*Strategy assumes:* the wire merges transactions, MLB headlines, and desk notes.
*Code does:* transactions and desk notes only; `get_news` raises `NameError` and the UI reports "NEWS FEED DOWN."
*Fix:* define `RSS_URL = "https://www.mlb.com/feeds/news/rss.xml"`, `ESPN_NEWS_URL`, `_espn_dead = False` in `feeds.py`; add a unit test that imports and calls the loader with a stubbed client.

---

## 4. Existing capabilities to preserve

These are the assets; the redesign wraps them and must not alter their semantics.

| Capability | Where | Preserve because |
|---|---|---|
| Chronological model fitting and artifact precompute | `backend/precompute.py`, `smoke_test.py`, `verified_stats.json` | Verified ground truth; the smoke test is the release gate |
| Load-once inference with receipts | `backend/inference.py` | Every price explains itself; explanations build on it |
| Odds mathematics | `backend/odds.py` | Unit-tested; the verdict engine composes these functions rather than replacing them |
| Season + ADJ dual pricing and the "record decides" doctrine | `feeds.py::_price_game`, `_blended_side`, `record_store.grade_pick` | The experiment pattern is the template for HFA |
| Append-only ledger, VOID semantics, tie/postponement handling, idempotent grading | `record_store.py`, `main.py::grade_pending_records`, `tests/test_grade_*` | Trust; extensively tested |
| Context-never-moves-a-price rule | `feeds.get_injury_flags`, `wire.get_team_pulse`, `hard_rule` fields | Doctrine; make it visible, never weaken it |
| Refusal states | `players.compare_players` boundary, `season_sim.next_season_refusal`, `salary_note` | Honesty assets; restyle copy only |
| Live-season contract | `feeds.current_season`, `/api/teams-live`, `tests/test_live_season_contract.py` | Prevents stale-year bugs; new surfaces must read the year from the API |
| Caching, coalescing, timeouts, per-row degradation | `feeds.AsyncTTLCache`, `_fetch_json`, `get_slate` | Keeps the slate alive under partial outages |
| Shareable query-string state | `desk.tsx`, `h2h.tsx`, `parlay-lab.tsx`, `wire.tsx` | Redirects must carry parameters |
| Keyboard shortcuts and omnisearch | `App.tsx`, `command-bar.tsx` | Power users |
| Error envelope and per-panel states | `main.py` handlers, `layout.tsx` | New components reuse them |
| Production process split | `serve_spa.py`, artifact configs, memory notes | Deployment stability |
| Historical panels and CSV exports | `track-record.tsx`, `bankroll-backtest.tsx`, `screener.tsx`, `season-desk.tsx` | Research value; relocate, do not remove |

---

## 5. Features that require new work

**Frontend only (existing data and APIs):** the three-layer `GameCard` for slate rows without prices; the Today page with readiness grouping; the daily summary of readiness counts; the terminology dictionary and sentence-case copy pass; token refresh and radius/type scale; the navigation shell, route wrappers, and redirects; the Research hub; a Track Record page composed from `/api/record`, `/api/track-record`, `/api/backtest` with client-computed live calibration and intervals; the Parlay Check reframe with the singles comparison at the −110 reference the API already returns; removal of the model slip; detail-level and explain-terms preferences in browser storage; onboarding, coach marks, and education content; a local paper bankroll and stake card that works with manually entered prices; the responsible-use toggles (local); mobile shell and PWA manifest; accessibility fixes (viewport zoom, font sizes, W/L words).

**Frontend work requiring new API fields:** explanations (`reasons`, `model_detail` on slate rows); verdicts and signal on slate rows; stale/price-age flags; model version stamps; data-status details.

**Backend:** fix `get_news`; guard `?date=` persistence; `backend/verdict.py` evaluator and `POST /api/evaluate`; explanation generator; `MODEL_VERSION`; `POST /api/stake` (pure); `POST /api/parlay/evaluate` with optional per-leg lines; share-card image endpoint; data-status endpoint; optionally an HFA term.

**Database and persistence:** version stamp on snapshots; candidate picks with price columns (new table recommended); `line_snapshots`; model versions; later users, preferences, bankrolls, bets; reconcile or remove the Drizzle schema.

**External provider:** odds feed (current, opening, closing; multiple books); possibly a licensed stats feed if MLB API terms require it for a paid product.

**Authentication and billing:** accounts and sync; subscription tier gating; processor review.

**Compliance and responsible use:** 21+ gate; helpline in footer and bankroll; limits and cooling-off (client first, server later); copy lint; share cards without stakes; no urgency notifications.

---
## 6. Critique of the current v3 strategy

The v3 document was written from the build specs rather than the code. Most of its product judgments hold; several of its technical assumptions do not. This section keeps what survives contact with the repository and corrects the rest.

### 6.1 Strongest ideas (confirmed by the code)

The three-layer card with a verdict first is still the right unit of design, and the code makes it cheaper than v3 assumed for everything except the price: `SlateGame` rows already carry probabilities, fair lines for both sides, probables, ADJ prices with `adj_detail`, IL flags, inputs, and status. The Track Record as a primary destination is a pure composition of `/api/record`, `/api/track-record`, and `/api/backtest`, and the existing UI already keeps the records apart (SEASON, ADJ, parlays, historical). The terminology dictionary is the highest-leverage change: the terminal feeling is mostly the ~40 uppercase monospace labels in `components/` and `tabs/`, not the layouts. The Parlay Check reframe is nearly free because `/api/parlay/price` already returns the fair line, the book edge and EV, ½-Kelly, and the vig-compounding comparison. The explanation layer is close: receipts and `adj_detail` exist; the missing per-team predicted runs are computed and discarded in `_price_game`.

### 6.2 Ideas that could confuse users

Unchanged from v3: global Beginner/Advanced modes, "Confidence" as a label, edge and expected value conflated, leading with the lean, price listed as a reason the model leans, and home/away or recent form as explanations. The code adds one more: the existing Edge Finder displays `edge_pp` with a `%` sign, so the current product already conflates points with percent; the dictionary must fix this in the same pass.

### 6.3 Ideas that are technically inaccurate based on the repository

- v3 wrote that the Live Record grades "at a stated odds assumption (flat 1 unit at −110 unless a real line was entered that day)". The column exists (`entered_line`) but nothing writes it; there is no "unless."
- v3's migration map referred to "Replit DB keys." The store is Postgres via psycopg (`record_store.py`), with a Drizzle schema on the side. Any persistence work must target Postgres and reconcile the Drizzle file.
- v3 proposed `GET /api/game/{gamePk}`, `POST /api/evaluate`, `POST /api/stake`, `GET /api/record?segment=…`, `GET /api/model/versions`, `GET /api/status`, `GET/PUT /api/me/*`. None exist. The per-game detail page can be built today from the slate row plus `POST /api/matchup` (with the row's `away_inputs`/`home_inputs`) and `GET /api/team-live/{id}`; the rest are additions.
- v3 said the explanation generator is "mostly a templating layer over numbers that exist." Partly: slate rows lack predicted RS/RA and strength; a small backend addition is required for honest run-based bullets.
- v3 assumed the daily snapshot is "frozen the morning of the game." The code snapshots whenever the first live slate load or scheduler tick happens and does not filter by game status; it also accepts `?date=`.
- v3 assumed a model version registry. The version is a literal in two places.
- v3's Phase 1 exit criterion "cold start under five seconds" is unrealistic on the current deployment: the memory note records ~25 s to open ports on the deploy machine, and the smoke test allows 30 s. The criterion should be "port opens and `/api/health` passes within the deployer's probe window," which the split-process design already achieves.
- v3's Parlay Check "singles comparison" per leg assumed per-leg book prices; the API's `vig_comparison` uses a −110 reference for singles and a single parlay price. Per-leg lines are an API addition.
- v3's Appendix F said keyboard shortcuts become 1–5 "documented in settings"; there is no settings surface. It must be created (local preferences first).
- v3 described "the four record types never share a number" as a design rule; the current `LiveRecordPanel` already separates SEASON, ADJ, and parlay totals, but the Desk places the historical `BankrollPanel` next to them with a `SIMULATION` badge only — the separation exists in data, less so visually.

### 6.4 Ideas that require new backend or database work

Verdict engine and signal (backend, plus persistence of the verdict issued); explanations (backend fields); model version stamps (backend + column); candidates record, price capture, closing lines, CLV (backend + tables + provider); stake service (backend, pure); per-leg parlay lines (backend); share-card images (backend + an image dependency); data-status endpoint (backend); HFA (backend model change + version registry); accounts, preferences, bankrolls, bets (backend + tables + auth); fixes to `get_news` and the `?date=` guard (backend, small).

### 6.5 Ideas that require an odds or data provider

Book price on cards; automatic verdict counts; expected return per $100; stake sizing without manual entry; candidates record; closing-line value; line movement; best-price flags; stale-price states; alerts about starters are provider-free, alerts about prices are not.

### 6.6 Legal, compliance, trust, and responsible-gambling concerns

Unchanged from v3, with three code-specific additions. The current product already exposes an uncapped ½-Kelly fraction as a "paper stake" (`kelly_fraction` in `/api/matchup`, `half_kelly` in parlay pricing); the redesign must cap and shrink before any dollar figure appears. The `MODEL SLIP OF THE DAY` banner ships by default in `parlay-lab.tsx` and should be removed from the default view now, independent of the redesign. And the public ledger's integrity hole (`?date=`) is a trust issue that should be closed before the record is promoted to a marketing surface. Data licensing for the keyless MLB Stats API and any odds provider remains the largest legal question for a paid product; nothing in the repository addresses it.

### 6.7 Ideas that should be combined

Card + modes + terminology + explanations remain one system. In this codebase they also share one implementation seam: `SlateGame` (`slate-rail.tsx`) is the type every surface already consumes (Desk, H2H teams mode, Parlay Lab), so the new `GameCard` should accept `SlateGame` plus optional `evaluation`/`reasons` fields and replace `SlateRail` rows in place. The Track Record page combines the three existing panels. The bankroll and stake card combine with the existing manual-line inputs: "Check a price" is the current Edge Finder input.

### 6.8 Ideas that should be delayed

Everything in 6.5 until the provider exists; accounts until the local-first versions prove the UX; native apps; alerts; a light theme until tokens are refactored (the current CSS has the variable structure but one palette); HFA until the version registry exists.

### 6.9 Ideas that should be removed or reframed

"Find an Edge" as a destination (remove); "Aggressive" profile (reframe as Higher variance, capped); "Confidence" (reframe as signal, provisional); the model slip (remove from default); the "cold start < 5 s" criterion (reframe); the "Phase 1 odds feed" as a single gate (reframe as a parallel track so honest UI work is not blocked); the paper bankroll backtest's framing as a "backtest" (reframe as an educational simulation with its losing result kept visible).

### 6.10 Important product ideas that were missing

From v3's list (odds feed, CLV, published verdict rules, risk row, pass rate, bet log, preferred books, line movement, changelog, HFA, share cards, responsible-use toolkit, accounts) all still apply. The code review adds: a ledger-integrity guard and snapshot status filter; an always-on or externally scheduled grading job; a single schema authority; a real data-status surface built from the cache metadata that already exists (`cache_hit`, `sources_up`, `updated_at`, `input_signature`, `computed_at`); frontend tests (none exist); and an explicit "price basis" on every parlay and stake (`price_basis` already exists for parlays and should be surfaced everywhere).

### 6.11 Recommendations implementable as UI improvements without backend change

Today page grouped by data readiness (scheduled with starters / scheduled without starters / in progress / final / pricing failed) with model chance, fair prices, and the lean; the three-layer card's answer and numbers layers (inputs, receipts via `/api/matchup` on demand, ADJ detail, flags); chance-to-lose and uncertainty chips; the terminology dictionary and sentence-case copy; the navigation shell with redirects; the Research hub; the Track Record page with client-computed live calibration and intervals; Parlay Check verdict copy, layout, and removal of the model slip; local detail-level and explain-terms preferences; onboarding and education; a local paper bankroll with a stake card driven by the manual price input (using the existing `kelly_fraction` only as a reference, with client-side shrinkage and caps until `POST /api/stake` exists); responsible-use toggles (local); mobile shell; accessibility fixes; token refresh and radius.

### 6.12 Recommendations that cannot be implemented truthfully until new data exists

Any card element that states a book price, an edge in points, expected return per $100, a stake in dollars without a user-entered price, a verdict other than `Price unavailable`/`Starters not confirmed`/`Insufficient data` without a price, "worth a look" counts, a candidates record, CLV, line movement, best-price flags, stale-price chips, and signal strength (which needs a price to measure disagreement). Each of these must render its honest absence state until the odds feed lands.

---
## 7. Refined target audience and positioning

The audience is unchanged: a primary regular recreational bettor who needs answers before arithmetic; a secondary disciplined bettor who will pay for a transparent model, receipts, and (once it exists) closing-line value; a tertiary analytics fan who keeps the research surfaces alive. Non-targets: anyone wanting picks, anyone under 21.

What the repository changes is the *sequence* of claims the product can make. Today, on current data, MONEYLINE is "a transparent model that prices every game, shows its arithmetic, and grades its own leans in public." It is not yet "compares the model's price with the sportsbook's" at scale — that sentence becomes true the day the odds feed lands, and until then the product should say "check any price you're offered" (which the manual inputs already support). The positioning statement therefore ships in two versions:

> **Launch (current data):** MONEYLINE prices every game with a transparent model, shows the arithmetic behind every number, lets you check any sportsbook price against the model's fair price, and grades its own record in public. Research, not picks.

> **After prices:** MONEYLINE prices every game with a transparent model, compares that price with the sportsbook's, tells you plainly when there is nothing worth betting, and grades its own record in public. Research, not picks.

Claims the code supports now: every number traces to public data or a stated formula (`receipts`, `formula`, `method` fields); the record is graded daily and never edited (append-only store, VOID semantics); the model's own historical paper simulation lost money and the product shows it. Claims that must wait: any statement about value found per day, any candidates record, any CLV.

| | |
|---|---|
| User problem | Bettors cannot tell whether a tool is research or a tout. |
| Why it improves usability | A positioning that matches what the screen can actually show avoids the "where is the price?" confusion on day one. |
| Advanced information preserved | All of it; positioning changes copy, not data. |
| Current code that supports it | `ResearchTag`, `EQUITY_CAVEAT` in `main.py`, `hard_rule` fields, the negative backtest. |
| New work required | Copy only, in two versions gated on feed availability. |
| Trust effect | High; the product never claims a comparison it cannot make. |
| Risks or limitations | Weaker marketing until prices exist. |
| Difficulty | Low. |

---

## 8. Refined information architecture

### 8.1 Target structure

```
Today                      /today            (new; becomes the default route after a migration period)
  Game detail              /game/{gamePk}    (new; built from the slate row + /api/matchup + /api/team-live)
Research                   /research         (new hub)
  Players                  /research/players  ← /players
  Matchups                 /research/matchups ← /h2h
  Teams & Season           /research/teams    ← /season, plus Team strength (PricerPanel) and Screener from /
  News & Context           /research/news     ← /wire
  Learn                    /research/learn    (new; glossary, how the model works, BA paradox, changelog)
Parlay Check               /parlay           (same path; reframed page)
Track Record               /record           (new; composes LiveRecordPanel, TrackRecordPanel, BankrollPanel)
Bankroll                   /bankroll         (new; local-first)
Settings                   /settings         (new; local-first preferences)
```

### 8.2 Route migration table

| Existing route | Decision | New route | Redirect | Query parameters | Compatibility | Rollback |
|---|---|---|---|---|---|---|
| `/` (Desk) | Preserve for one release as `/desk`, then redirect to `/today` | `/today` | `/` → `/today` after Today ships; `/?team=X&year=Y` → `/research/teams?team=X&year=Y` | `team`, `year` preserved | Omnisearch team hits currently navigate to `/?team=&year=`; update `command-bar.tsx` targets in the same change | Feature flag `TODAY_DEFAULT`; flipping it restores `/` |
| `/players` | Wrap | `/research/players` | 301-style client redirect in wouter, keep `?id=` | `id` | `SlateRail`'s `onSelectProbable` navigates to `/players?id=`; update | Keep old path registered until the redirect period ends |
| `/h2h` | Wrap | `/research/matchups` | keep `mode`, `a`, `b` | `mode`, `a`, `b` | H2H share links in the wild | Same |
| `/parlay` | Keep path; rename page | `/parlay` | none | `legs`, `book` | none | none |
| `/season` | Wrap | `/research/teams` | keep any | — | none | Same |
| `/wire` | Wrap | `/research/news` | keep `team`, `types` | `team`, `types` | none | Same |
| keyboard `1–6` | Remap | `1–5` primary destinations | — | — | Document in Settings and in the command bar hint | — |

All redirects are client-side (wouter `Redirect` with the search string carried), because the production web service is a static SPA server (`serve_spa.py`) whose fallback already returns `index.html` for deep links (`tests/test_serve_spa.py::test_deep_link_falls_back_to_index`). Stored records are unaffected by any route change.

### 8.3 Primary versus secondary

Primary (persistent navigation, five items): Today, Research, Parlay Check, Track Record, Bankroll. Secondary (inside Research): Players, Matchups, Teams & Season, News & Context, Learn. Settings sits behind an account/avatar affordance on desktop and inside Bankroll's overflow on mobile. Nothing from the six tabs is removed; the Desk's `PricerPanel` (with Front Office sliders), `ScreenerPanel`, and `BaParadoxPanel` move to Research → Teams & Season and Learn.

| | |
|---|---|
| User problem | Six tool-named tabs do not tell a newcomer where today's answer is. |
| Why it improves usability | Frequency-based navigation; five items fit a phone. |
| Advanced information preserved | Every tab survives under Research; query-string state carries through redirects. |
| Current code that supports it | wouter routing, `TABS`, lazy tabs, query-param state. |
| New work required | Shell, hub page, redirects, omnisearch target updates. |
| Trust effect | Track Record and Bankroll as primary destinations. |
| Risks or limitations | Old bookmarks; mitigated by redirects for a release. |
| Difficulty | Low–Medium (frontend only). |

---

## 9. Refined Today dashboard

### 9.1 What the page can be on current data, and what it becomes after prices

**Launch version (no odds feed).** Today answers "which games are ready to research?" not "which games have value?" Cards show the matchup, time (ET, from `time_et`), starters (from `probables`), the model lean and chance (from `model_prob_home`), both fair prices (`fair_lines`), the starter-adjusted price when present (`adj_fair_lines`), the sample chip (`THRU N GP`, from `/api/teams-live`), IL chips (`flags`), and a price slot reading "No price loaded — add one to check value," which opens the manual entry (today's `EdgeFinder` inputs) and produces a verdict labeled *your price*. Grouping is by data readiness: *Ready to research* (scheduled, starters confirmed), *Starters not confirmed*, *In progress*, *Final* (with graded results from `/api/record` entries matched on `game_pk`), *Pricing failed* (`pricing_error` rows). The summary strip counts those groups.

**After the odds feed.** The same cards gain the price row, edge in points, expected return per $100, verdict, and signal; grouping switches to verdict (*Worth a look*, *No value detected*, *Waiting on data*, *In progress and final*); the summary strip counts verdicts and states the pass rate.

The hierarchy in your brief (date selector; data status; summary; filters; groups; track-record summary; bankroll summary; context; disclaimer) is right, with two changes: the date selector should be read-only for research (the persistence guard in Part 6 ensures a past or future date never writes to the ledger), and "Context and news" should be a compact strip fed by `/api/wire?types=IL,TRADE&limit=…` rather than a panel, because the wire is a secondary destination.

### 9.2 Layout and states

Desktop: one card column (~760 px) with a right rail (summary, Track Record snapshot from `/api/record` totals with `sample_label`, bankroll chip when a local bankroll exists, context strip). Under 1,100 px the rail becomes a strip. Mobile: one column, sticky date bar and summary.

| State | Source in code | Launch rendering |
|---|---|---|
| Live slate | `slate.mode == "live"` | Groups as above |
| Historical fallback | `slate.mode == "historical"`, `reason` | "No games today" (or the `reason` text) with the famous-seasons research list under Research → Teams & Season, never a blank page |
| Pricing failed for a row | `pricing_error`, `FEED PARTIAL` | Card with matchup and time, "Model price unavailable for this game — team statistics did not load," no lean |
| Starters missing | `probables.away/home == null` or `adj_prob == null` | Season price only; chip "Starters not confirmed"; no ADJ line |
| In progress / final | `status` not in Scheduled/Pre-Game; `badges` contains `LIVE` | Pre-game lean frozen, no price entry; final shows score from record entries when graded |
| Small sample | `games_played` from `/api/teams-live` | Chip "Through N games — small sample" under 60; verdicts withheld under 30 once verdicts exist |
| No price (all cards at launch) | — | "No price loaded — add one to check value"; verdict slot reads *Price unavailable* |
| Stale price (later) | provider `updated_at` | Amber "as of" chip beyond 15 minutes |
| Feed down | `slate.feed_up == false` | Historical fallback plus a status line |

### 9.3 What Today does not include

No bet buttons, sportsbook links, countdowns, streak badges, hot-hand language, social proof, flashing odds, urgency notifications, or featured parlays. The `LIVE` `animate-pulse` dot in the command bar is replaced by a static status word with a timestamp.

| | |
|---|---|
| User problem | The Desk opens on OAK 2002 and a rail of prices with no answer to "which games matter today." |
| Why it improves usability | A card list grouped by readiness (now) or verdict (later) turns a scan into a decision. |
| Advanced information preserved | Every slate field; receipts one tap away via `/api/matchup` with the row's inputs. |
| Current code that supports it | `useSlate`, `SlateGame`, `useTeamsLive`, `useLiveRecord`, `useWire`, `EdgeFinder` inputs. |
| New work required | `GameCard`, grouping, summary strip, Today page (frontend); later the evaluator and prices. |
| Trust effect | "No price loaded" and readiness grouping are honest; verdict grouping only appears with prices. |
| Risks or limitations | Without prices the page can look like a lean sheet; the copy rules and the `Price unavailable` verdict slot mitigate. |
| Difficulty | Medium (frontend); High overall once prices are included. |

---

## 10. Refined game-card UX

### 10.1 Arithmetic and terminology validation of the proposed card

Your Part 5-B card: model chance 58%, fair price −138, book price −115, potential edge +4.5 points, expected return +$8.40 per $100, signal Moderate, "loses approximately 42% of the time."

- Fair price: −100 × 0.58 / 0.42 = −138.1. The app's `probability_to_moneyline` rounds to the nearest 5, so the product would display **−140** unless the rounding rule changes. Recommendation: keep the nearest-5 rule for displayed prices (it matches how books quote) and show the unrounded value in the numbers layer.
- Implied chance at −115: 115/215 = 53.49%. Edge: 58.0 − 53.5 = **+4.5 points**. Correct, and correctly labeled in points (the current `EdgeFinder` label "Model Edge …%" must change).
- Expected return per $100 at −115: 100 × (0.58 × 100/115 − 0.42) = **+$8.43**. Correct. Keep "expected return" separate from "edge."
- "Loses approximately 42% of the time": 1 − 0.58. Correct, and it should use the same probability the verdict used (ADJ when present, else season).
- Signal "Moderate": defensible only with a definition. With σ = 4 points, this gap ratio is 1.13 (Strong on the gap alone); Moderate would follow if starters were unconfirmed or the sample was short. The label must never appear without the tooltip definition and the provisional flag.
- Confidence in the game outcome is never shown as a label; the number is the model chance.

### 10.2 Are the verdict labels appropriate?

*Bet candidate* is the most useful and the most dangerous label. It should stay because "candidate" already implies review rather than instruction, but it must be a pill, never a button; the call to action must be "See full breakdown"; and "No value detected" cards must get equal design weight. If usability testing shows readers treating it as a pick, the fallback label is "Price looks favorable."

*Marginal value*, *No value detected*, *Avoid at this price*: appropriate; "avoid" is advice-like but it is advice *against* betting, which is the responsible direction.

*Insufficient data*, *Price unavailable*, *Starters not confirmed*: these are data states, not judgments, and two of them can coexist with a verdict (a season-price verdict can be issued while starters are unconfirmed). Recommendation: two slots on the card — a **verdict pill** (candidate / marginal / no value / avoid / insufficient data) and a **data-status chip row** (price unavailable, starters not confirmed, small sample, as-of). The evaluator emits both (`verdict` and `flags`), which is how Appendix A of v3 already structured it.

### 10.3 The card, mapped to fields that exist today

| Layer | Element | Source now | After prices |
|---|---|---|---|
| 1 Answer | Matchup, time, starters | `away_name/home_name`, `time_et`, `probables` | same |
| 1 | Verdict pill | *Price unavailable* (or *your price* verdict from manual entry via `/api/matchup`) | evaluator |
| 1 | Model chance, lean | `model_prob_home`, `adj_prob` | same |
| 1 | Fair prices | `fair_lines`, `adj_fair_lines` | same |
| 1 | Book price, edge, expected return | — | provider + evaluator |
| 1 | Chips: loses X%, sample, starters | `1 − p`, `/api/teams-live.games_played`, `probables` | + signal, as-of |
| 2 Explanation | Why the model leans | needs `model_detail` (new) + `adj_detail` (exists) | same |
| 2 | Why worth reviewing | manual-price result from `/api/matchup` | evaluator |
| 2 | Context, not in the price | `flags`, `/api/team-live.pulse`, `/api/wire?team=` | same |
| 2 | Risk detail | `1 − p`, ADJ gap, GP | + payout shape, break-even from price |
| 2 | Stake card | local bankroll + manual price | `POST /api/stake` |
| 3 Numbers | Inputs, receipts, Pythagorean, log5 | `away_inputs/home_inputs`; `/api/matchup` on demand | same |
| 3 | Season vs starter-adjusted | `fair_lines` vs `adj_fair_lines`, `adj_detail` | same |
| 3 | Line movement, Kelly chain | — | provider, `POST /api/stake` |

### 10.4 Launch-state example (no price)

```
NYY at BOS · 7:10 PM ET · Rodón (NYY) vs Crochet (BOS)

◌  Price unavailable                               Starters confirmed · Through 126 games
   Model lean: Red Sox, 58% (with tonight's starters; 57% on season strength).
   Add a sportsbook price to check whether it's worth a look.

   Fair price  BOS −140 · NYY +120        [ Add a price ]

   Loses 42% of the time
   ▸ Why the model leans Boston   ▸ Context   ▸ Numbers        [ See full breakdown ]
```

The card contract from v3 stands, with one added rule for this codebase: **the probability used for the lean, the chance-to-lose chip, the explanation, and any verdict is the same probability, stated on the card ("with tonight's starters" or "season strength").** Today the parlay pricer uses the season probability (`price_basis`) while the slate shows both; the card must say which one it used.

| | |
|---|---|
| User problem | A slate row shows two fair lines and two probabilities with no answer and no explanation. |
| Why it improves usability | One card answers in order; the launch state is honest about the missing price. |
| Advanced information preserved | Both prices, `adj_detail`, inputs, receipts, flags. |
| Current code that supports it | `SlateGame`, `formatOdds`, `formatProb`, `EdgeFinder` (manual entry), `/api/matchup` receipts. |
| New work required | `GameCard`, `Disclosure`, `VerdictPill`, chips; backend `model_detail`/`reasons`; later evaluator and prices. |
| Trust effect | Verdict and status separated; price basis stated; no fake prices. |
| Risks or limitations | Before prices, the lean is the most prominent number; copy must keep "lean ≠ bet." |
| Difficulty | Medium. |

---

## 11. Progressive disclosure strategy

One card system, three layers, two preferences. **Detail level** (Essentials / Full detail) sets which layers open by default and whether technical secondary labels and tables render; **Explain terms** (on/off) controls tooltips and coach marks. Both live in browser storage at launch (`localStorage` with try/catch; the app currently stores nothing client-side), with a settings page to change them, and migrate to per-user preferences when accounts exist. The same evaluation, numbers, and thresholds are rendered in both levels; a snapshot test asserts that switching the level changes no numeric text on a fixture card.

Honesty furniture that never collapses, mapped to what exists: `THRU N GP` → "Through N games"; `SMALL SAMPLE` → "Small sample (n)"; `slate.updated_at` → "as of h:mm ET"; `model_version` from `/api/health` (until the registry exists) → footer; `pricing_error` → the failed-row card; `ResearchTag` → the footer disclaimer on every route; `adj_detail == null` → "Starters not confirmed"; and, once prices exist, the price's own timestamp.

| | |
|---|---|
| User problem | Newcomers drown; experts are slowed by explanations; a mode switch destabilizes. |
| Why it improves usability | Layers keep the answer readable and the depth one tap away. |
| Advanced information preserved | All of it, open by default in Full detail. |
| Current code that supports it | Radix `Collapsible`/`Accordion` primitives already in `components/ui/`; `TooltipProvider` in `App.tsx`. |
| New work required | `Disclosure` component, preference store, settings page. |
| Trust effect | Same verdict in both levels; furniture never hidden. |
| Risks or limitations | Browser storage can be cleared; preferences must default sanely. |
| Difficulty | Low. |

---

## 12. Plain-English terminology strategy

One dictionary module (`src/lib/terminology.ts`) exports `{key, label, technical, tooltip, learnPath}` entries and a `<Term>` component; every component reads labels from it. Plain label primary, technical secondary in Full detail, one-sentence tooltip, "How this is calculated" expanders that substitute the actual numbers. A build-time lint over string resources enforces the prohibited list.

Rewrites of strings that exist in code today (file → current → new):

| File | Current | New |
|---|---|---|
| `edge-finder.tsx` / `main.py` | `VALUE` · `INSIDE THE VIG — NO PLAYABLE EDGE` · `NO VALUE` · `NO LINE` | Bet candidate · Inside the sportsbook's cut — no value · No value detected · Price unavailable (map in a display layer; the API strings stay until the evaluator ships) |
| `edge-finder.tsx` | `Model Edge +4.5%` | Edge +4.5 pts |
| `edge-finder.tsx` | `B/E Rate` · `½ Kelly` | Win rate needed to break even · Model-sized stake (½ Kelly) |
| `live-record.tsx` | `LIVE PUBLIC RECORD` · `Season Record` · `Units (Flat -110)` · `ADJ Record` · `GRADE PENDING` | Live record · Every game, season strength · Units (flat one unit at −110) · With tonight's starters · Grade pending picks |
| `live-record.tsx` | `W` / `L` / `VOID` / `PENDING` badges | Win / Loss / Void / Pending (words, with icons) |
| `slate-rail.tsx` | `ADJ` · `%H` · `%A` · `FEED PARTIAL` · `HISTORICAL MODE` | With tonight's starters · Home chance · Adjusted home chance · Model price unavailable · Season over — showing historical seasons |
| `parlay-lab.tsx` | `PARLAY LAB` · `MODEL SLIP OF THE DAY` · `LOG PAPER SLIP → LIVE RECORD` · `VIG COMPOUNDS — THE HOUSE TAKE, SIDE BY SIDE` · `½-Kelly Stake` · `0.00 — NO EDGE` | Parlay Check · (removed) · Log this paper slip · The sportsbook's cut, parlay vs singles · Model-sized stake · No stake — no value at this price |
| `player-card.tsx` | `WOULD BEANE BUY?` | Keep as a research badge with its caption; it lives under Research |
| `status-strip.tsx` / `research-tag.tsx` | `STATISTICAL RESEARCH · NOT WAGERING ADVICE` · `MODEL: 1962–2001-v1` | Research tool, not betting advice. 21+ · Model version from `/api/health` |
| `layout.tsx` | `LOADING MODELS… FITTING 1962–2001… PRICING SLATE…` | A plain loading state ("Loading the model…"); the terminal boot becomes optional |
| `screener.tsx` | `UNDERVALUED ASSET SCREENER` · `MISPRICED ▲` | Team screener · Above prior ▲ (badge kept; the word "mispriced" implies a market the screener does not price) |
| `season-desk.tsx` | `NOT PRICED — a season model needs an offseason roster model…` | Keep the sentence; sentence case |
| `pricer-panel.tsx` | `FRONT OFFICE` toggle | What-if sliders |

Number formatting: whole-percent chances in Essentials, one decimal in Full detail (`formatProb` currently always shows one decimal); American odds always signed in the price face; edge in points; expected return in dollars per $100 in Essentials and percent in Full detail; records as wins–losses with units to one decimal.

| | |
|---|---|
| User problem | `EDGE`, `B/E`, `½ KELLY`, `ADJ`, `%H` are meaningless to the primary persona. |
| Why it improves usability | Dual labels serve both personas; arithmetic with real numbers teaches. |
| Advanced information preserved | Technical labels remain in Full detail and tooltips. |
| Current code that supports it | `formatOdds`, `formatProb`, `TooltipProvider`; API `formula`/`method` strings. |
| New work required | Dictionary, `<Term>`, expander component, copy pass, lint. |
| Trust effect | Formulas with real figures are the strongest "nothing hidden" signal. |
| Risks or limitations | API strings (`verdict`, `sample_label`) are uppercase; map in a display layer to avoid breaking `smoke_test.py` assertions on API values. |
| Difficulty | Low. |

---

## 13. Explainable model strategy

### 13.1 Three sections, three data sources

**Why the model leans** — only priced inputs. Sources: per-team predicted runs and Pythagorean strength (new `model_detail` on slate rows, computed from the same `predict_from_inputs` calls `_price_game` already makes), `away_inputs`/`home_inputs` (exist), `adj_detail` (exists: starter name, innings share, OBP/SLG-against), and games played (exists via `/api/teams-live`). Bullets: offense (predicted RS per game and OBP/SLG), run prevention (predicted RA per game), tonight's starter (from `adj_detail`, with the season → adjusted price move), one counterweight when a component favors the other side, and the sample sentence last.

**Why this may be worth reviewing** — the price. Sources: at launch, the manual-price result from `/api/matchup` (`fair_line`, `implied_prob`, `edge_pp`, `break_even_rate`); later, the evaluator. One sentence naming the book, the price, and the fair price.

**Context, not in the price** — sources that exist and are already labeled as context by the backend: `flags[]` (IL, with `playing_time_rank` and the `tooltip` text), `/api/team-live.pulse` (score, item count, evidence list), `/api/wire?team=&types=IL,TRADE,SIGNING,ACTIVATED` (last 72 hours), and standing limitations that the code documents: "Home field: not priced" (no HFA term), "Bullpen: approximated by the team rate" (from `adj_detail.note`), "Lineups and weather: not priced" (from `EQUITY_CAVEAT`).

### 13.2 Rules

Templates render only with real values (the `_desk_notes` rule in `wire.py`); reasons never cite flags, pulse, transactions, form, or venue; the probability basis is stated; a maximum of three lean bullets ranked by run contribution converted with the fitted runs-per-win slope (`analytics.runs_per_win`); prohibited words are impossible by construction; if nothing clears the thresholds the list reads "The two teams are close on every input the model prices."

### 13.3 Where it runs

Server-side, in a new `backend/explain.py`, returning `reasons {lean[], review[], context[]}` on slate rows and on `POST /api/evaluate`, so every client renders identical text and the golden tests live next to `smoke_test.py`. Ten fixtures: clear favorite; split components; starter flips the lean; injury flag on the lean side (must not appear in the lean list); value on the underdog; early-season sample; ADJ missing; pricing failure; historical mode; a tie in inputs.

| | |
|---|---|
| User problem | A 58% with two fair lines does not tell anyone why. |
| Why it improves usability | A story a person can evaluate. |
| Advanced information preserved | Receipts remain the audit trail; reasons link to them. |
| Current code that supports it | `predict_from_inputs` receipts, `adj_detail`, `flags`, `pulse`, `EQUITY_CAVEAT`, `runs_per_win`. |
| New work required | `model_detail` on rows; `backend/explain.py`; `ReasonList` component. |
| Trust effect | High if the priced/context separation is enforced by tests. |
| Risks or limitations | Templates can sound repetitive; vary phrasing by magnitude, not by invention. |
| Difficulty | Medium (backend + tests + component). |

---
## 14. Parlay Check strategy

### 14.1 What the API already gives the page

`POST /api/parlay/price` returns `combined_prob`, `fair_odds`, `independence_note`, `price_basis` ("SEASON model probabilities (not ADJ)"), `vig_comparison` (`legs`, `leg_reference_line` −110, `standard_book_parlay_line`, `fair_parlay_line`, `parlay_house_take_pct`, `singles_house_take_pct`), and, when a book price is entered, `book` (`implied_prob`, `edge_pp`, `ev_per_unit`, `half_kelly`, `stake_label`). Same-game legs are refused with `correlated_legs`; more than six legs are refused by validation; a non-live slate returns `slate_unavailable`. Everything the reframe needs for a verdict-first page except two things: per-leg book prices (for a true "singles instead" comparison at the user's prices rather than the −110 reference) and an ADJ price basis option.

### 14.2 The reframed page

Order: verdict pill and takeaway; the three numbers (chance the slip wins, fair odds, book odds — entered, or the standard compounded −110 line shown as a labeled assumption); the sportsbook's cut, parlay versus singles (rendered from `vig_comparison`); "Singles instead" (at launch: the reference-line comparison plus each leg's model chance and fair line; after the API addition: each leg's expected return at its own price); expected return and chance of losing (`1 − combined_prob`); the independence note; correlation notes; stake only with positive expected return and a local bankroll, at the parlay cap; the numbers.

Verdict rules for a slip (published on the page): *Poor value* when `ev_per_unit < 0` or any leg has negative expected return at its own price (once per-leg prices exist); *Marginal* when `0 ≤ ev < 0.04`; *Candidate* when `ev ≥ 0.04` and every leg is non-negative. Takeaway examples: "This parlay pays +365; the model's fair price is +415 — you give up about 9.5 cents per dollar" and "Boston is the value here; adding two ordinary legs lowers the expected return and makes the outcome far more of a coin toss."

The `MODEL SLIP OF THE DAY` banner (`computeModelSlip` in `parlay-lab.tsx`) is removed from the default view in the first frontend release. The paper-slip log stays, with its limitation stated: it is one public paper slip per day (`slip_date UNIQUE`), not a personal log; personal slips wait for accounts.

| | |
|---|---|
| User problem | Parlays are the primary persona's favorite bet and the worst-priced one. |
| Why it improves usability | Verdict-first and singles-first make the comparison unavoidable. |
| Advanced information preserved | All API fields; the per-leg table; Kelly. |
| Current code that supports it | `/api/parlay/price`, `parlay_vig_comparison`, `useParlayPrice`, `useParlayLog`. |
| New work required | Page reframe (frontend); optional `legs[].book_line` and `basis` on the API; removal of the model slip. |
| Trust effect | A product that rates most parlays poor value earns credibility. |
| Risks or limitations | Singles comparison at the −110 reference is an assumption until per-leg prices exist; label it. |
| Difficulty | Low (frontend) + Low (API option). |

---

## 15. Bankroll and responsible-use strategy

### 15.1 Local-first, price-honest

Nothing per-user exists, so the first bankroll ships in browser storage: amount, risk profile, unit, paper mode (default on), weekly loss limit, and cooling-off. It works today because the manual price inputs exist: a stake appears only when the user has entered a price for the side (and, for de-vigging, the other side), the expected return at that price is positive, the model inputs exist, and the card labels the result "model-sized stake (paper)." When accounts arrive, local state migrates on first sign-in; when the odds feed arrives, prices come from the feed instead of the inputs.

### 15.2 Sizing rules (server-authoritative once `POST /api/stake` exists; identical client formula until then)

The existing `half_kelly_fraction` is uncapped and computed on the raw model chance; on the example card it yields 4.85% of bankroll (full Kelly 9.7%). The product must not show that as a stake. Rules: de-vig the market from both entered prices (if only one side is entered, use its raw implied chance and say "no de-vig — one price entered"); staking chance = 0.5 × model + 0.5 × market (published constant, movable only by a dated changelog decision); full Kelly on the staking chance; profile fraction and cap — Conservative ¼ Kelly, cap 1% (parlay 0.5%); Balanced ½ Kelly, cap 2% (parlay 1%); Higher variance ¾ Kelly, cap 3% (parlay 1.5%), not selectable during onboarding; rounded to the dollar; "no stake — no value at this price" whenever expected return ≤ 0 on the model's own chance. Worked example on $1,000 at model 58%, prices −115/+105: de-vigged 52.3%, staking chance 55.2%, full Kelly 3.6%, stakes $9 / $18 / $27. The stake card shows the whole chain in Full detail and a 100-bet projection at the staking chance (about +$57 mean, roughly one run in three ends down, median worst dip about 15% at Balanced).

### 15.3 Responsible-use toolkit

21+ attestation at first run (local until accounts; not a true age gate and labeled as an attestation), the helpline (1-800-GAMBLER) in the footer, the bankroll page, and the gate; weekly loss limit that hides stakes when reached; cooling-off (24 h / 7 d / 30 d) that hides all dollar figures immediately and delays turn-off; paper mode indefinitely; no notification ever carries a stake or a price move; no dollar figure on a share card; "model-sized stake," never "recommended" or "suggested."

### 15.4 What waits

Personal bet log with grading and CLV (accounts + closing prices); sync; server enforcement of limits; billing.

| | |
|---|---|
| User problem | Bettors size by feel; the app's only sizing number is an uncapped Kelly fraction. |
| Why it improves usability | Dollar stakes bounded by profile with consequences shown. |
| Advanced information preserved | Full Kelly, fraction, shrinkage, cap, projection in Full detail. |
| Current code that supports it | `half_kelly_fraction`, `market_vig`, `moneyline_to_probability`, the manual line inputs. |
| New work required | Local bankroll store, stake card, `POST /api/stake`, later tables and auth. |
| Trust effect | Shrinkage and caps show the product distrusts its own edge appropriately. |
| Risks or limitations | Local state is per-browser; the attestation is not verification. |
| Difficulty | Medium. |

---

## 16. Track Record and trust strategy

### 16.1 Four records, mapped to the code

| Record | Source | Treatment |
|---|---|---|
| Historical tests | `/api/track-record` (fit metrics, calibration), `/api/backtest` (paper simulation: model −22.0 units on 96 bets, baseline −9.0 on 87) | Own section under a persistent banner: "Historical, season-level, 2002–2012. Not bettable." The simulation is relabeled "educational paper simulation" with its selection rule and its losing result kept visible |
| Live paper record — every game | `/api/record` totals, `curve`, `entries`; ADJ via `adj_record` | Hero; labeled "every game, flat one unit at −110 — a model check, not a betting record" |
| Live paper record — candidates | none until prices; new table | Added from feed go-live with its own since-date |
| Parlays | `parlay_record` | Kept; "one public paper slip per day" |
| User-entered bets | none; accounts | Private, on the Bankroll page, later |
| Graded vs pending | `result` null/WIN/LOSS/VOID | Pending outlined and excluded from totals; VOID shown at 0 units (already the case) |

### 16.2 Page composition (frontend only at launch)

Hero: tracking since (`tracking_since`), picks, graded, record, units, hit rate, break-even (110/210), sample label; a 95% interval on units per pick computed client-side from `entries` (mean ± 1.96 × sd/√n, method stated on the page); "What this proves" with dynamic numbers (n, and the ±√n-unit luck swing). Season strength versus with-tonight's-starters side by side (existing). Parlays line (existing). Live calibration: buckets from `entries[].model_probability` and `result` (50–55, 55–60, 60–65, 65+), counts shown, buckets under 30 de-emphasized. Segments: favorites (model chance ≥ 0.5 is always the pick today, so the meaningful early segments are by probability bucket and by month). Historical section under the banner (existing panels restyled). Methodology from `formula`, `method`, `assumptions`, `EQUITY_CAVEAT`, and the parlay `independence_note`. Model version from `/api/health` until the registry exists. Per-pick table from `entries` with CSV export (the app already has CSV export code in `screener.tsx` and `season-desk.tsx`).

### 16.3 Trust mechanics from existing metadata

Data status: `slate.cache`, `slate.updated_at`, `wire.sources_up`, `wire.updated_at`, `season-sim.computed_at`/`input_signature`, `health.startup_ms`/`database_ready` — enough for a status line now and a status page after a small endpoint adds cache ages. Snapshot immutability: state the rule and back it with the `?date=` guard and a status filter; show `created_at` from snapshots on the per-pick table (already returned). Published verdict rules: on the page once the evaluator ships. Monthly honest note: template from the existing `_desk_notes` pattern.

### 16.4 Public by default

There are no accounts, so everything is public already; the change is making `/record` the marketing entry and linking it from the header and from every card's "see how the model has done."

| | |
|---|---|
| User problem | A curated-looking record is easy to distrust; the current record is a panel at the bottom of the Desk. |
| Why it improves usability | A destination with distinct treatments, intervals, and plain copy. |
| Advanced information preserved | All existing panels, entries, exports. |
| Current code that supports it | `/api/record` entries with probabilities and results; `/api/track-record`; `/api/backtest`; CSV patterns. |
| New work required | Page composition, client-side calibration and intervals; later candidates record and CLV. |
| Trust effect | The core of the product's trust. |
| Risks or limitations | The every-game record is a model check; copy must say so; the losing simulation must stay visible. |
| Difficulty | Low–Medium (frontend). |

---

## 17. Onboarding and education strategy

Four screens, under ninety seconds, skippable after the gate, all state local at launch: (0) 21+ attestation and "research tool, not a sportsbook, not betting advice," with the helpline; (1) what this is — prices every game with a transparent model, shows the arithmetic, lets you check any price, grades itself in public; a link to `/record`; (2) how to read a card — an annotated launch-state card (lean, fair price, "add a price," loses X%); (3) try it — the card with a price slider driven by the same evaluation the manual inputs use (`/api/matchup` on a fixed pair of inputs, or the client mirror), walking from *Avoid* through *No value* and *Marginal* to *Bet candidate* at 58% while the chance stays put; (4) setup — detail level, explain terms, time zone; optional paper bankroll with "Keep it paper for now."

Contextual lessons keyed to events the code already produces: first `pricing_error` row ("what happens when statistics don't load"); first `adj_detail == null` ("why starters matter, and why the price waits"); first manual price entry ("fair price vs your price"); first `INSIDE THE VIG` result ("the sportsbook's cut"); first Parlay Check ("why parlays compound the cut," using `vig_comparison`); first graded LOSS on a lean the user followed ("why a 58% side loses 42% of the time"); first `HISTORICAL MODE` day ("the off-season and what the model can't do"); first `flags` chip ("what the model can't see"). The education center (`/research/learn`) hosts ten lessons, the glossary generated from the dictionary, "how the model works" (built from `/api/track-record.models` and the BA paradox panel), and the changelog once it exists.

| | |
|---|---|
| User problem | Edge, fair price, and variance are unfamiliar; a course would be skipped. |
| Why it improves usability | Four screens plus lessons at the moment each concept appears. |
| Advanced information preserved | Nothing gated. |
| Current code that supports it | `/api/matchup` for the slider demo; `BaParadoxPanel`; `track_record.json` models block. |
| New work required | Screens, coach-mark system, lesson content, local completion state. |
| Trust effect | Expectations set before the first card. |
| Risks or limitations | Local completion state resets when storage clears. |
| Difficulty | Low–Medium. |

---

## 18. Visual and responsive design direction

### 18.1 Token refresh (edits to `artifacts/moneyline/src/index.css`)

Keep the HSL-variable structure and Tailwind 4 `@theme inline`; change values and add a second palette. Dark: page `#0f1318`, card `#161b22`, popover `#1c222b`, border `#262c36`, foreground `#e6e9ef`, muted `#9aa4b2`; `--radius: 0.75rem`; `--ring` moves from success-green to the accent (`#6FA8E0`). Light (new, under `[data-theme="light"]`, with `color-scheme: light`): page `#f6f7f9`, card `#ffffff`, border `#e3e6ea`, foreground `#14171c`, muted `#5b6472`, accent `#2457A0`. Semantic verdict colors as desaturated tints with AA-checked text: candidate `#276A4D`/`#4FB08A`, marginal `#8A5A12`/`#D9A441`, no value `#5B6472`/`#9AA4B2`, avoid `#9A4508`/`#E08A3C`, loss `#8F3A4C`/`#DD7F98` (light/dark). The `.dark` custom variant already exists; the default theme follows `prefers-color-scheme` once both palettes exist, with the `index.html` pre-paint block updated to avoid a flash in either theme.

### 18.2 Type and density

Inter for UI; JetBrains Mono only for odds, probabilities in tables, records, and timestamps (`font-mono` is currently applied to navigation, inputs, headers, and body copy — remove it there). Minimum 13 px for chips, 15–16 px body; the `text-[8px]`/`text-[9px]`/`text-[10px]` classes are replaced by dictionary-driven sizes. Section headers in sentence case at 14–16 px; the `.moneyline-section-header` utility keeps its rule but drops `uppercase tracking-widest`. Cards get 16/20 px padding and the new radius. Charts (Recharts) keep one accent series plus gray, plain-English titles, and a text summary.

### 18.3 Motion and status

Remove `animate-pulse` from the LIVE dot and the boot overlay; replace `TerminalBoot` with a plain loading state (keep the terminal boot behind a setting if the team is attached to it); no count-ups; 150–200 ms disclosure transitions; `prefers-reduced-motion` stays as implemented.

### 18.4 Mobile and accessibility

Remove `maximum-scale=1` from the viewport meta; add a five-item bottom bar under 768 px (the `useIsMobile` hook exists); game detail as a sheet (Radix `Sheet`/`Drawer` primitives exist under `components/ui/`); tables inside `overflow-x-auto` containers; a PWA manifest and service worker (none exist; `public/` holds only `favicon.svg` and `robots.txt`); 44 px targets; words next to every colored status (the current W/L letter badges become Win/Loss); a skip link; `aria-live` retained on verdict regions; chart alt summaries.

### 18.5 What it must not resemble

A sportsbook (odds boxes as buttons, promo banners, bright green filled buttons), a casino (gold, neon, confetti), a tout (flames, locks, countdowns), or the current terminal (flashing indicators, all-caps mono).

| | |
|---|---|
| User problem | The terminal style reads as "not for me" to the primary persona and its saturated red/green and animated indicators encourage impulse. |
| Why it improves usability | Calm surfaces, sentence case, readable sizes, a price face used sparingly. |
| Advanced information preserved | Tables, receipts, charts remain with better hierarchy. |
| Current code that supports it | Tailwind 4 tokens, shadcn primitives, Radix components, `prefers-reduced-motion`. |
| New work required | Token values, second palette, component pass, mobile shell, manifest. |
| Trust effect | Restraint reads as honesty. |
| Risks or limitations | Existing users may miss the terminal look; keep it as an optional theme. |
| Difficulty | Medium. |

---
## 19. Technical dependencies and risks

| Dependency or risk | Evidence | Effect on plan | Mitigation |
|---|---|---|---|
| No odds provider | No price ingestion anywhere; manual inputs only | Every price-dependent feature waits | Parallel provider track; honest absence states; manual entry forever |
| Data licensing for a paid product | Keyless `statsapi.mlb.com` and MLB RSS; no license files | Commercial risk | Legal review in Phase 0; budget a licensed provider as fallback |
| Scheduler on `autoscale` | `.replit` `deploymentTarget = "autoscale"`; in-process `grade_scheduler`; memory note | Missed ledger days | Reserved always-on API instance or an external scheduled call to `POST /api/record/grade` + a new today-only `POST /api/record/snapshot` |
| Ledger integrity via `?date=` | `GET /api/slate` persists any `mode == "live"` payload | Backdated picks possible | Guard: persist only when `date == today (ET)` and status is Scheduled/Pre-Game; test |
| Two schema authorities | `lib/db` Drizzle vs `record_store.ensure_schema`; `post-merge.sh` runs `db push` | Accidental column drops | Delete or align the Drizzle schema; remove the push from post-merge |
| Dead news feed | `RSS_URL` undefined | Wire is half empty | Define constants; test |
| Hard-coded model version | `/api/health`, `StatusStrip` | Model changes unattributable | `MODEL_VERSION` constant; stamp snapshots |
| `game_pk` uniqueness on picks | `moneyline_record_game_idx` | A candidates record cannot share the table | New `moneyline_candidate_picks` table |
| Uncapped Kelly exposed | `half_kelly_fraction`, `kelly_fraction`, `half_kelly` | Advice-like numbers already on screen | Cap and shrink in the display layer now; `POST /api/stake` later |
| No frontend tests | none | Redesign regressions undetected | Add Vitest + Testing Library for the card, dictionary, evaluator mirror, and preferences |
| Cold start ~25 s on deploy | memory note; smoke test allows 30 s | Health-probe fragility if startup grows | Keep new work post-startup; keep `serve_spa` light |
| Slate rows lack predicted runs | `_price_game` discards them | Explanations need a backend change | `model_detail` field |
| MLB API quirks | team-code mapping, innings notation, short names | Regressions when adding fields | Keep `TEAM_CODES` mapping; extend `notes/mlb_api_transcripts.md` |
| HFA absent | symmetric log5 | Candidates record biased toward road teams | Version registry first; HFA as a versioned change or third graded price |
| Cache TTLs vs freshness copy | 600 s slate cache; 5-minute client refetch | "As of" must reflect server cache time | Surface `updated_at` and cache status on the card |

---

## 20. Revised phased roadmap

Each phase lists its work by type (UI and styling; frontend requiring new API fields; backend; database and persistence; external provider; authentication and billing; compliance and responsible use; deferred). Phases 1 and 2 run in parallel after Phase 0; Phase 3 depends on a provider decision; Phase 4 on an auth decision. Estimates assume one full-stack engineer and one designer.

### Phase 0 — Stabilize the foundation (1–2 weeks)

- **Objective.** Close the integrity and correctness gaps before anything is built on top of them; establish single authorities for schema and model version.
- **User value.** The public record becomes defensible; the wire regains headlines; a version appears on every new pick.
- **Existing files involved.** `backend/feeds.py` (news constants), `backend/main.py` (`slate` route persistence guard; `MODEL_VERSION` in health), `backend/record_store.py` (`ensure_schema` adds `model_version text` to snapshots and picks), `backend/precompute.py` (`MODEL_VERSION`), `lib/db/*`, `scripts/post-merge.sh`, `.replit`, `tests/`.
- **New files.** `backend/version.py` (or a constant in `precompute.py`); `tests/test_slate_persistence_guard.py`; `tests/test_news_loader.py`.
- **Work by type.** Backend: define `RSS_URL`, `ESPN_NEWS_URL`, `_espn_dead`; guard persistence to today-only, pre-game rows; add `POST /api/record/snapshot` (today only, idempotent) for external scheduling; expose `MODEL_VERSION`. Database: `ALTER TABLE … ADD COLUMN IF NOT EXISTS model_version text` on both tables, default the current version. Persistence authority: remove the Drizzle push from `post-merge.sh` and either delete `lib/db` or mark it documentation-only. Deployment: decide always-on versus external scheduler and configure it. Compliance: none yet. Deferred: none.
- **Dependencies.** Access to the Replit deployment settings; `DATABASE_URL` for tests.
- **Risks.** A wrong guard could stop legitimate snapshots — the test must cover "today, pre-game" persisting and "yesterday" not persisting.
- **Fallback behavior.** If the news constants are wrong, `safe()` still degrades the wire; if the scheduler decision slips, `GET /api/slate` keeps snapshotting on visits.
- **Testing.** `python smoke_test.py` unchanged and green; new pytest cases; a manual `curl /api/slate?date=<yesterday>` must not change `/api/record` totals.
- **Definition of done.** Wire shows `MLB.COM` items; `?date=` cannot write; `model_version` present in `/api/health` and on new rows; one schema authority; grading verified to run without a page visit for two consecutive days.

### Phase 1 — Honest interface on current data (4–6 weeks, frontend track)

- **Objective.** Deliver the v3 experience that is truthful without prices: card system, Today (readiness grouping), navigation, Track Record page, Parlay Check, preferences, accessibility, tokens.
- **User value.** A calm, readable product that answers "which games are ready to research, what does the model think, and how has it done" — and lets a user check any price.
- **Existing files involved.** `src/index.css`, `index.html`, `App.tsx`, `command-bar.tsx`, `slate-rail.tsx` (source of `SlateGame`), `edge-finder.tsx` (manual price inputs reused inside the card), `live-record.tsx`, `track-record.tsx`, `bankroll-backtest.tsx`, `parlay-lab.tsx`, `desk.tsx`, `layout.tsx`, `status-strip.tsx`, `research-tag.tsx`, `api.ts`.
- **New files.** `src/lib/terminology.ts`, `src/lib/preferences.ts`, `src/components/game-card/*` (`GameCard`, `VerdictPill`, `StatusChips`, `Disclosure`, `ReasonList` placeholder, `PriceEntry`), `src/pages/today.tsx`, `src/pages/game-detail.tsx`, `src/pages/record.tsx`, `src/pages/research/*`, `src/pages/settings.tsx`, `src/components/bottom-nav.tsx`, `public/manifest.webmanifest`, `src/sw.ts`, frontend tests.
- **Work by type.** UI and styling: tokens, radius, type scale, sentence case, mono reduction, verdict palette, remove pulse and boot overlay, viewport fix, bottom nav, sheets, manifest. Frontend on existing APIs: Today with readiness groups and summary; `GameCard` layers 1 and 3; game detail via `/api/matchup` + `/api/team-live`; Track Record page with client-side calibration and intervals; Parlay Check reframe; model slip removed; navigation, hub, redirects; preferences; onboarding; local paper bankroll and stake card with shrinkage and caps (client formula) driven by manual prices; local limits and cooling-off. Frontend requiring new API fields: none in this phase (explanation layer shows "coming from the model receipts" placeholder only if Phase 2 has not landed — better: hide the layer until fields exist). Backend/DB/provider/auth: none. Compliance: 21+ attestation, helpline footer, copy lint.
- **Dependencies.** Phase 0 for the version footer; design tokens signed off.
- **Risks.** A lean-forward Today without prices; mitigated by the `Price unavailable` slot and copy. Route changes break bookmarks; mitigated by redirects with parameters.
- **Fallback behavior.** Feature flag `NEW_SHELL`; the six-tab shell remains behind `/desk` for one release.
- **Testing.** Vitest unit tests for the dictionary, the preference store, the stake formula (fixtures $9/$18/$27), the client calibration; component tests for `GameCard` states; an axe pass; `pnpm run typecheck`; `tests/test_serve_spa.py` green after a build.
- **Definition of done.** Every state in section 9.2 reachable with fixtures; no uppercase-mono labels outside tables; no dollar figure without a local bankroll and an entered price with positive expected return; `/players`, `/h2h`, `/season`, `/wire` redirect with parameters; Lighthouse accessibility ≥ 95 on Today and Record.

### Phase 2 — Explanations and the evaluator (3–4 weeks, backend track, parallel with Phase 1)

- **Objective.** Make the model explain itself and make verdicts two-sided, published, and price-basis-explicit — usable immediately with manual prices.
- **User value.** "Why does the model lean this way" on every card; a correct verdict for both sides of any price a user enters.
- **Existing files involved.** `backend/feeds.py::_price_game` (add `model_detail`), `backend/odds.py` (reused), `backend/main.py` (new routes), `backend/analytics.py` (`runs_per_win`), `smoke_test.py`, `src/api.ts`, the `GameCard` explanation layer.
- **New files.** `backend/verdict.py`, `backend/explain.py`, `backend/stake.py`, `tests/test_verdict.py`, `tests/test_explain.py`, `tests/test_stake.py`, `src/hooks/useEvaluate.ts`.
- **Work by type.** Backend: `model_detail` on rows; `POST /api/evaluate` (both sides; flags; signal placeholder computed only when a price exists); `reasons` on rows and on evaluate; `POST /api/stake`; `POST /api/parlay/evaluate` with optional per-leg lines and `basis` (season/adj); a data-status endpoint exposing cache ages. Frontend requiring new fields: `ReasonList`, verdict from the API for manual prices (replacing the client mirror), stake card switched to the server formula. Database: none. Provider: none. Compliance: thresholds published on the Record page.
- **Dependencies.** Phase 0 version constant (verdict payloads carry it).
- **Risks.** Explanation templates that overstate; mitigated by golden tests and the priced-only rule.
- **Fallback behavior.** If `reasons` are absent, the card hides layer 2's lean section; if `evaluate` fails, the card falls back to the `/api/matchup` verdict mapped through the dictionary.
- **Testing.** Appendix A fixtures (edge/EV/verdict) and Appendix B golden explanations; `smoke_test.py` extended with one evaluate case; contract tests on the slate row shape.
- **Definition of done.** Every live slate row carries `model_detail` and `reasons`; `POST /api/evaluate` matches fixtures; the H2H teams mode shows both sides' verdicts.

### Phase 3 — Odds feed and the priced ledger (5–6 weeks after the provider decision)

- **Objective.** Real prices on cards, automatic verdicts and grouping, a candidates record at recorded prices, closing-line value, stale states.
- **User value.** The seven questions answered without typing a price; a record that means something to a bettor.
- **Existing files involved.** `backend/feeds.py` (new provider client with the same TTL/coalescing pattern), `backend/record_store.py` (new table and columns), `backend/main.py` (slate enrichment, record segments), `backend/verdict.py`, `src/pages/today.tsx`, `GameCard`, `record.tsx`.
- **New files.** `backend/odds_feed.py`, `backend/closing.py` (capture at first pitch), `tests/test_odds_feed.py`, `tests/test_candidate_record.py`.
- **Work by type.** External provider: contract, keys via environment variables only, book list, rate limits, outage behavior. Backend: ingestion and caching; `prices{}` on slate rows with per-book timestamps; evaluator wired to prices with the user's book preference (local at first); closing capture; CLV; `GET /api/record?segment=candidates|leans|parlays&group_by=`. Database: `moneyline_line_snapshots(game_pk, book, side, american, captured_at, kind)`; `moneyline_candidate_picks(game_pk, side, verdict, signal, price_used, book, price_captured_at, closing_price, clv_pts, model_version, result, units_pnl, …)` with `(game_pk, side)` uniqueness; snapshot rows record the prices seen. Frontend requiring new fields: price row, edge, expected return, verdict grouping, summary counts, stale chips, line movement, candidates record and CLV on `/record`. Compliance: no book links; price display licensing per provider terms.
- **Dependencies.** Provider contract; legal review; Phase 2 evaluator; Phase 0 guards and version.
- **Risks.** Provider outages (design for absence); licensing; HFA bias in the candidates record (see Phase 5 and the open decisions — recommended to ship the HFA version before or with this phase).
- **Fallback behavior.** Feed down → cards revert to the launch state with "Prices unavailable since h:mm"; manual entry always works; the leans record continues.
- **Testing.** Fixture-driven ingestion tests; closing capture on a seeded game; candidates grading against real finals on a seeded past date in the isolated test schema; a "feed down" simulation.
- **Definition of done.** Today groups by verdict with prices from at least two books; every price shows book and time; the candidates record starts at go-live and grades at recorded prices; CLV computed for every graded candidate; no verdict without a price.

### Phase 4 — Accounts, personal bankroll, bets, billing (5–6 weeks after the auth decision)

- **Objective.** Move preferences, bankroll, limits, and a personal bet log server-side; introduce the Pro tier.
- **User value.** Sync across devices; a graded personal record with CLV; enforced limits.
- **Existing files involved.** `backend/main.py`, `record_store.py` (new tables), `src/lib/preferences.ts` (migration on sign-in), `src/pages/bankroll.tsx`, `settings.tsx`.
- **New files.** `backend/auth.py`, `backend/users.py`, `backend/bets.py`, `tests/test_bets.py`, billing integration module.
- **Work by type.** Authentication and billing: provider selection, sessions, tier gating, processor policy check. Database: `users`, `preferences`, `bankrolls`, `bets`. Backend: `GET/PUT /api/me/*`, bet grading extension, CLV per bet. Frontend: sign-in, sync, My bets. Compliance: server-enforced limits and cooling-off; 21+ attestation on the account; terms and privacy.
- **Dependencies.** Phase 3 for closing prices on bets (bets can be logged and graded on finals before that, with CLV pending).
- **Risks.** Processor rejection of betting-information subscriptions; scope creep.
- **Fallback behavior.** Local-first features keep working without an account.
- **Testing.** Auth flows; migration of local state; bet grading in the isolated schema; tier gating tests.
- **Definition of done.** A user can sign in on two devices and see the same bankroll, preferences, and bets; free tier unchanged; no dollar figure without a bankroll (server-enforced).

### Phase 5 — Depth and growth (6–8 weeks)

HFA as a versioned change (or third graded price) with the record split by version; notifications (informational, opt-in); share cards (server image endpoint); research hub restyle onto the card system; light theme polish and system default; data-status page; monthly honest note; multi-book comparison UI and preferred books; performance work on feed concurrency; full accessibility audit.

### Deferred

Native apps (after notifications and accounts prove out); additional bet types (run lines and totals need run distributions from the model, which is model work); additional sports (each needs its own graded model); community features (only without social proof on picks); price-movement alerts (urgency risk); any "model slip" resurrection (only as education, and only after the parlay record is large).

---
## 21. Implementation-ready task breakdown

Tasks are ordered by dependency. Each is scoped so that one engineer (or one agent) can own it without colliding with another: backend tasks touch `backend/` and `tests/`; frontend tasks touch `artifacts/moneyline/src`; tasks that must touch both are explicitly combined. Field abbreviations: **Files** = current files to start from; **Preserve** = existing behavior to preserve; **States** = loading, empty, error, stale, missing-data states; **A11y** = accessibility; **Mobile** = mobile requirements; **AC** = testable acceptance criteria; **Compat** = migration or compatibility; **Out** = out of scope.

### Task 1 — Restore the MLB headline feed

- **Objective.** Fix `backend/feeds.py::get_news`, which raises `NameError` because `RSS_URL`, `ESPN_NEWS_URL`, and `_espn_dead` are never defined.
- **User-facing outcome.** The Wire shows MLB.com headlines again; `sources_up.news` is true when the RSS fetch succeeds.
- **Files.** `backend/feeds.py` (lines 480–534), `backend/wire.py::get_wire`, `notes/mlb_api_transcripts.md`.
- **Preserve.** ESPN stays optional and silent on failure; the 1,800 s `wire_source_cache`; dedupe and sort in `get_wire`.
- **New behavior.** Module-level `RSS_URL = "https://www.mlb.com/feeds/news/rss.xml"`, `ESPN_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news"`, `_espn_dead = False`.
- **API/data dependencies.** None. **DB.** None. **External.** MLB RSS (keyless); ESPN optional.
- **States.** Feed down → existing `sources_up.news = false` path; malformed XML → `FeedUnavailable` handled by `safe()`.
- **A11y / Mobile.** Not applicable.
- **AC.** (1) `python -c "import asyncio; from backend.feeds import get_news; asyncio.run(get_news())"` returns a list or raises `FeedUnavailable`, never `NameError`. (2) New `tests/test_news_loader.py` stubs `httpx` with a two-item RSS document and asserts two `NEWS` items with `source == "MLB.COM"` and parsed Eastern dates. (3) `smoke_test.py` still passes. (4) Add the RSS transcript to `notes/mlb_api_transcripts.md` with the check date.
- **Compat.** None. **Out.** Any wire redesign.

### Task 2 — Guard the public ledger against off-day and in-progress writes

- **Objective.** Persist slate snapshots only for today (Eastern) and only for games not yet started; add an explicit today-only snapshot endpoint for external scheduling.
- **User-facing outcome.** The record can truthfully claim "frozen before first pitch, never backdated."
- **Files.** `backend/main.py::slate` (persistence block, lines 592–599), `backend/main.py::snapshot_live_slate`, `backend/record_store.py::store_slate_snapshot`, `backend/feeds.py::get_slate` (the `status` field), `tests/conftest.py`.
- **Preserve.** `GET /api/slate?date=` remains readable for research; idempotent `ON CONFLICT DO NOTHING` semantics; the scheduler's cadence; ADJ and probables captured as today.
- **New behavior.** `store_slate_snapshot` accepts `today: date` and returns `False` unless `slate["date"] == today`; rows whose `status` is not in `{"Scheduled", "Pre-Game", "Warmup"}` are skipped (documented list, extend from MLB `detailedState` values seen in `notes/`); `POST /api/record/snapshot` (today only) mirrors the scheduler's snapshot step and returns `{persisted, skipped_rows}`.
- **API/data dependencies.** None. **DB.** None (no schema change). **External.** None.
- **States.** Snapshot skipped → log line `record_snapshot_skipped reason=…`; the slate response's `record_persisted` reflects the truth.
- **A11y / Mobile.** Not applicable.
- **AC.** (1) `tests/test_slate_persistence_guard.py`: a live payload dated yesterday does not insert; a payload dated today inserts only pre-game rows; calling twice inserts once. (2) `curl "/api/slate?date=<yesterday>"` followed by `GET /api/record` shows unchanged `picks`. (3) `POST /api/record/snapshot` is idempotent across two calls. (4) Existing grading tests green.
- **Compat.** None for stored rows. **Out.** Scheduler hosting (Task 4).

### Task 3 — Model version constant, snapshot stamping, single schema authority

- **Objective.** Replace the hard-coded version literal with one constant, stamp new ledger rows, and remove the second (stale) schema authority.
- **User-facing outcome.** The footer and the Record page show a real version; future model changes can be attributed.
- **Files.** `backend/precompute.py` (add `MODEL_VERSION = "chronological-1962-2001-v1"`), `backend/main.py::health`, `backend/record_store.py::ensure_schema`, `store_slate_snapshot`, `store_parlay_slip`, `get_record`, `artifacts/moneyline/src/components/status-strip.tsx` (read from `useHealth`), `lib/db/**`, `scripts/post-merge.sh`, `tests/conftest.py` DDL.
- **Preserve.** Existing rows untouched; `ensure_schema` idempotent and `IF NOT EXISTS`; the joblib bundle format.
- **New behavior.** `ALTER TABLE moneyline_slate_snapshots ADD COLUMN IF NOT EXISTS model_version text`, same for picks and parlay slips; inserts write `MODEL_VERSION`; `get_record` returns `model_versions_present[]`; `/api/health.model_version` reads the constant; `post-merge.sh` no longer runs `pnpm --filter db push`; `lib/db/src/schema/moneyline.ts` either deleted or brought to parity with a header comment "documentation only — the Python migration is authoritative."
- **API/data dependencies.** None. **DB.** Three additive columns. **External.** None.
- **States.** Rows without a version display "v1 (pre-versioning)".
- **A11y / Mobile.** Footer text only.
- **AC.** (1) `tests/conftest.py` DDL updated; `pytest` green with `DATABASE_URL`. (2) Boot twice → columns exist once. (3) `StatusStrip` shows the API value, no literal remains (`grep -rn "1962–2001-v1" src` returns nothing). (4) `git grep "db push"` returns nothing in `scripts/`.
- **Compat.** Additive only. **Out.** HFA or any model change.

### Task 4 — Keep the grading loop alive in production

- **Objective.** Ensure the snapshot/grade cycle runs daily regardless of traffic.
- **User-facing outcome.** No missing ledger days.
- **Files.** `.replit` (`deploymentTarget`), `artifacts/api-server/.replit-artifact/artifact.toml`, `.agents/memory/background-scheduler-constraints.md`, `backend/main.py::grade_scheduler`.
- **Preserve.** In-process loop as the default; idempotent writes.
- **New behavior.** Either (a) switch the API service to an always-on deployment target, or (b) add an external scheduled job (Replit scheduled deployment or equivalent) that calls `POST /api/record/snapshot` at 10:00 ET and `POST /api/record/grade` at 03:00 ET, with logging.
- **Dependencies.** Task 2's endpoint for option (b). **DB.** None. **External.** Hosting configuration.
- **States.** Job failure → logged, retried next cycle; the Record page's "last graded" timestamp (from `graded_at` max) makes gaps visible.
- **AC.** (1) Two consecutive days with no page visits produce snapshots for both days. (2) `/api/record` `entries` show `graded_at` within 24 h of each final. (3) Memory note updated with the chosen mechanism.
- **Compat.** None. **Out.** Multi-region or queue infrastructure.

### Task 5 — Terminology dictionary and copy pass

- **Objective.** One source of labels, tooltips, and formats; sentence-case copy everywhere; a lint against prohibited words.
- **User-facing outcome.** Plain-English labels with technical secondaries; no more `B/E`, `½ KELLY`, `ADJ`, `%H`.
- **Files.** New `src/lib/terminology.ts`, new `src/components/term.tsx`; edit `edge-finder.tsx`, `live-record.tsx`, `slate-rail.tsx`, `parlay-lab.tsx`, `pricer-panel.tsx`, `screener.tsx`, `season-desk.tsx`, `wire.tsx`, `player-card.tsx`, `status-strip.tsx`, `research-tag.tsx`, `layout.tsx`, `command-bar.tsx`; new `scripts/copy-lint.mjs` wired into `pnpm run typecheck` or a `lint:copy` script.
- **Preserve.** API strings (`verdict` values, `sample_label`, `stake_label`) are mapped in the display layer, not changed, so `smoke_test.py` assertions hold; `formatOdds`/`formatProb` signatures.
- **New behavior.** Entries per section 12; `formatProb(p, {precision})`; the lint fails the build on `lock`, `guaranteed`, `free money`, `sure thing`, `can't lose`, `bet now`, `recommended bet`, `suggested bet`, `slip of the day`, `boost`, `risk-free`.
- **Dependencies.** None. **DB/External.** None.
- **States.** Unchanged.
- **A11y.** Tooltips are keyboard-reachable (Radix `Tooltip` with focusable triggers) and become tap popovers on touch.
- **Mobile.** Labels never truncate below 13 px.
- **AC.** (1) `grep -rn "uppercase tracking-widest" src --include=*.tsx` returns only table eyebrows. (2) Lint passes with zero hits and fails on a seeded fixture. (3) Snapshot test of `EdgeFinder` shows `Edge +4.5 pts` for the 58%/−115 fixture. (4) Every dictionary entry has a non-empty tooltip.
- **Compat.** None. **Out.** Layout changes.

### Task 6 — Design tokens, type scale, and motion

- **Objective.** Apply the calm visual system: refined dark palette, radius, type sizes, monospace only for prices, desaturated verdict colors, remove pulse and boot overlay, fix viewport zoom.
- **User-facing outcome.** The same product, readable and unhurried.
- **Files.** `src/index.css`, `index.html`, `src/components/ui/badge.tsx` (variants), `layout.tsx` (`TerminalBoot` → `LoadingState`), `command-bar.tsx` (status dot), all components using `font-mono` outside numeric contexts.
- **Preserve.** `prefers-reduced-motion` block; `color-scheme` and pre-paint background; the Tailwind 4 `@theme inline` structure; Recharts chart components.
- **New behavior.** Token values per section 18.1; `--radius: 0.75rem`; badge variants `candidate`, `marginal`, `novalue`, `avoid`, `waiting`, `win`, `loss` with tinted backgrounds; `maximum-scale=1` removed; `animate-pulse` removed from status indicators; boot overlay replaced by a one-line loading state (optional terminal theme flag).
- **Dependencies.** Task 5 for label sizes. **DB/External.** None.
- **States.** Loading state shows "Loading the model…" with the health poll; error state unchanged.
- **A11y.** Contrast ≥ 4.5:1 for text on tinted pills in both future palettes (values in 18.1 were checked); pinch zoom works; focus rings on the accent.
- **Mobile.** Minimum 13 px text; 44 px targets on buttons in `slate-rail.tsx` rows.
- **AC.** (1) `index.html` contains no `maximum-scale`. (2) An axe run on the Desk reports no contrast violations. (3) `grep -c "animate-pulse" src/components/command-bar.tsx` = 0. (4) Visual snapshot of `EdgeFinder`, `LiveRecordPanel`, and a slate row approved by design.
- **Compat.** None. **Out.** Light theme (Phase 5 polish, but the variable structure should be prepared here).

### Task 7 — Preferences store and Settings page

- **Objective.** Detail level, explain terms, theme, time zone, and onboarding/coach-mark flags in browser storage with a versioned schema.
- **User-facing outcome.** A settings page; the choice persists across reloads.
- **Files.** New `src/lib/preferences.ts` (`{version: 1, detailLevel, explainTerms, theme, timeZone, onboardingCompletedAt, coachMarksSeen[]}`), new `src/pages/settings.tsx`, `App.tsx` (provider), `command-bar.tsx` (quick toggle).
- **Preserve.** No behavior depends on preferences today; defaults must reproduce current numbers (Full detail shows one-decimal probabilities as `formatProb` does now).
- **New behavior.** `try/catch` around every read/write; defaults Essentials + explain on; a `usePreference` hook; the schema version enables a later server migration.
- **Dependencies.** None. **DB.** None (local). **External.** None.
- **States.** Storage unavailable → in-memory defaults and a note in Settings.
- **A11y.** Radio groups with labels; keyboard operable.
- **Mobile.** Settings reachable from the bottom bar overflow.
- **AC.** (1) Toggling detail level changes no numeric text in a `GameCard` fixture (snapshot diff limited to class names and visibility). (2) Reload preserves choices. (3) Private-mode simulation (storage throws) renders defaults without error.
- **Compat.** Schema version 1 documented for the future account migration. **Out.** Server sync.

### Task 8 — GameCard component system (launch state)

- **Objective.** Build the three-layer card over `SlateGame` with the verdict slot, data-status chips, price entry, and the numbers layer; explanation layer wired to optional `reasons`.
- **User-facing outcome.** Every game reads as a card: matchup, starters, lean and chance with its basis, fair prices, "add a price," chips, receipts on demand.
- **Files.** `src/components/slate-rail.tsx` (types and formatters; keep exporting `SlateGame`), `edge-finder.tsx` (extract `parseMoneyline`/`isMalformedMoneyline` and the `/api/matchup` call into `usePriceCheck`), `api.ts` (`useMatchup`, `useTeamLive`, `useTeamsLive`), `components/ui/collapsible.tsx`.
- **New files.** `src/components/game-card/GameCard.tsx`, `VerdictPill.tsx`, `StatusChips.tsx`, `Disclosure.tsx`, `PriceEntry.tsx`, `ReasonList.tsx` (renders `reasons` if present, else nothing), `NumbersLayer.tsx`, `fixtures.ts` (a live row with ADJ, a row without probables, a `pricing_error` row, a final row, a historical row).
- **Preserve.** `SlateRail`'s `onSelectGame`/`onSelectProbable` callbacks (Desk keeps working until Today replaces it); B-Ref codes with full names.
- **New behavior.** Layer 1 per section 10.4; the probability basis label ("with tonight's starters" when `adj_prob != null`, else "season strength"); `PriceEntry` posts the row's `away_inputs`/`home_inputs` plus entered lines to `/api/matchup` and renders a *your price* verdict mapped through the dictionary for **both** sides by calling the endpoint twice with A/B swapped until Task 16 lands; chips: loses X% (`1 − p`), through N games (`games_played` from `/api/teams-live` keyed by code), starters not confirmed, model price unavailable; layer 3: inputs, receipts (from the matchup response), season vs adjusted lines, `adj_detail`.
- **API/data dependencies.** Existing endpoints only. **DB/External.** None.
- **States.** Loading skeleton per card; `pricing_error` card; historical row card; final/in-progress card (no price entry, lean frozen); malformed line inline alert (`role="alert"`); matchup request error → "Couldn't check that price" with retry.
- **A11y.** Verdict pill has text and an icon; `aria-live="polite"` on the verdict region; disclosure buttons with `aria-expanded`; all chips have text.
- **Mobile.** Card fits 375 px with four lines collapsed; disclosures full-width; price entry inputs 44 px tall.
- **AC.** (1) Fixture cards render all five states without console errors (Vitest + Testing Library). (2) For the 58%/−115 fixture the your-price verdict reads *Bet candidate* with `Edge +4.5 pts` and `Expected return +$8 per $100`. (3) No edge or expected return text renders without an entered price. (4) The basis label matches `adj_prob` presence. (5) Keyboard: Tab reaches every disclosure and the price inputs.
- **Compat.** `SlateRail` remains until Task 9 replaces the Desk. **Out.** Server-side verdicts and reasons (Tasks 15–16), stakes (Task 13).

### Task 9 — Today page and game detail

- **Objective.** New default surface grouped by data readiness, with a read-only date bar, summary strip, right rail, and a game detail route.
- **User-facing outcome.** "Which games are ready to research today" in one screen; a full breakdown per game.
- **Files.** `src/tabs/desk.tsx` (patterns for slate/teams-live wiring), `api.ts` (`useSlate(date)`, `useLiveRecord`, `useWire`, `useTeamsLive`), Task 8 components.
- **New files.** `src/pages/today.tsx`, `src/pages/game-detail.tsx`, `src/components/summary-strip.tsx`, `src/components/date-bar.tsx`, `src/components/context-strip.tsx`, `src/lib/readiness.ts` (grouping rules).
- **Preserve.** `useSlate()` without a date for the live day; the 5-minute refetch; the Desk remains at `/desk` behind a flag for one release.
- **New behavior.** Groups: ready (Scheduled/Pre-Game with both probables), starters not confirmed, in progress, final (joined to `/api/record.entries` on `game_pk` for results), pricing failed; summary strip counts; date bar navigates `useSlate(date)` for yesterday/tomorrow in read-only mode with a note; rail: record snapshot (`picks`, `graded`, `wins–losses`, `sample_label`), context strip from `/api/wire?types=IL,TRADE&limit=8`; footer with disclaimer, helpline, model version, `updated_at`.
- **API/data dependencies.** Existing. **DB/External.** None.
- **States.** Historical mode → "No games today" with `reason`; feed down → status line; empty groups hidden; a group header explainer shown once (preference flag).
- **A11y.** Headings per group; summary counts as buttons with `aria-pressed` filters; skip link to the card list.
- **Mobile.** Sticky date bar and summary; rail collapses into a strip; one column.
- **AC.** (1) Fixture slates (live, historical, partial failure, all-final) render the correct groups and counts. (2) Yesterday's date renders graded results and never triggers a write (verified by `record.picks` unchanged; relies on Task 2). (3) Game detail deep link `/game/{gamePk}` renders from the slate row or shows "This game isn't on today's slate." (4) Lighthouse accessibility ≥ 95.
- **Compat.** Omnisearch live-team hits continue to open the team pricer (Task 10 updates targets). **Out.** Verdict grouping (Phase 3).

### Task 10 — Navigation shell, Research hub, redirects, mobile bar, PWA manifest

- **Objective.** Five primary destinations, a hub for the research tabs, parameter-preserving redirects, remapped shortcuts, bottom navigation, installability.
- **User-facing outcome.** Today · Research · Parlay Check · Track Record · Bankroll; old links keep working.
- **Files.** `App.tsx`, `command-bar.tsx` (`TABS`, omnisearch `go` targets), `desk.tsx`, `slate-rail.tsx` (`onSelectProbable` target), `hooks/use-mobile.tsx`, `index.html`, `public/`.
- **New files.** `src/components/app-shell.tsx`, `src/components/bottom-nav.tsx`, `src/pages/research/index.tsx` (hub), route wrappers for players/matchups/teams/news/learn, `src/lib/redirects.ts`, `public/manifest.webmanifest`, `src/sw.ts` (cache the shell and last slate response with an "as of" note).
- **Preserve.** Query strings (`team`, `year`, `id`, `mode`, `a`, `b`, `legs`, `book`, `team`, `types`); the H2H share URL; `/` shortcut for search.
- **New behavior.** Routes per section 8.1; `<Redirect>` with `window.location.search` appended; keyboard 1–5; `/` → `/today` only when the `NEW_SHELL` flag is on; the Desk's `PricerPanel`, `ScreenerPanel`, `BaParadoxPanel` mounted under `/research/teams` and `/research/learn`.
- **API/data dependencies.** None. **DB/External.** None.
- **States.** Offline: service worker serves the shell and the last slate with "as of."
- **A11y.** `nav` landmarks with `aria-label`; `aria-current`; bottom bar items with text labels.
- **Mobile.** Bottom bar under 768 px; 44 px items; safe-area insets.
- **AC.** (1) Each old route redirects with parameters (table-driven test). (2) `1–5` switch destinations; `6` does nothing. (3) Manifest validates; Lighthouse PWA installable. (4) `/desk` still renders the six-panel layout while the flag is on.
- **Compat.** Flag-controlled cutover; rollback by flag. **Out.** Native apps.

### Task 11 — Track Record page

- **Objective.** Compose the four records under `/record` with intervals, live calibration, proof copy, and the historical banner; relabel the paper simulation.
- **User-facing outcome.** A public page that says what the numbers prove and do not prove.
- **Files.** `live-record.tsx`, `track-record.tsx`, `bankroll-backtest.tsx`, `api.ts` (`useLiveRecord`, `useTrackRecord`, `useBacktest`, `useGradeRecord`), `screener.tsx` (CSV pattern).
- **New files.** `src/pages/record.tsx`, `src/lib/record-stats.ts` (interval, calibration buckets, luck swing), `src/components/record/*` (`RecordHero`, `ProofStatement`, `CalibrationChart`, `HistoricalBanner`, `PickTable`).
- **Preserve.** `GRADE PENDING` trigger (renamed); SEASON/ADJ side-by-side; parlay line; VOID at 0 units; `SMALL SAMPLE` threshold (100) as the label rule.
- **New behavior.** Interval: mean ± 1.96 × sd/√n over `units_pnl` of decided entries, method stated; calibration buckets from `model_probability` (50–55, 55–60, 60–65, 65+) versus `result`; "What this proves" with n and ±√n; historical section under the banner; the paper simulation retitled "educational paper simulation" with its rule and its −22.0-unit result unchanged; per-pick table with CSV export; model version footer.
- **API/data dependencies.** Existing fields. **DB/External.** None.
- **States.** `database_ready == false` → the existing unavailable message; `entries` empty → "No graded picks yet — tracking since …"; buckets under 30 → de-emphasized with "too small to read."
- **A11y.** Chart has a text summary; table semantics; Win/Loss words.
- **Mobile.** Hero stacks; table scrolls horizontally in its container.
- **AC.** (1) With a fixture of 40 decided entries the interval and buckets match a Python cross-check. (2) The historical banner is visible whenever any historical figure is on screen (scroll test). (3) The simulation's −22.0 units renders. (4) CSV re-parses with the documented columns.
- **Compat.** Desk panels remain until cutover. **Out.** Candidates record and CLV (Task 20).

### Task 12 — Parlay Check reframe

- **Objective.** Verdict-first parlay page over the existing API; remove the model slip from the default view.
- **User-facing outcome.** "This parlay has poor value; the individual bets may be better," said plainly.
- **Files.** `src/tabs/parlay-lab.tsx` (rename to `src/pages/parlay-check.tsx`), `api.ts` (`useParlayPrice`, `useParlayLog`).
- **Preserve.** URL state (`legs`, `book`); leg toggling; same-game refusal and six-leg cap messages; the paper-slip log with its one-per-day note; `price_basis` display.
- **New behavior.** Verdict rules per 14.2 computed client-side from `book.ev_per_unit` (until Task 17 moves them server-side); the three numbers; house-cut bar from `vig_comparison`; "singles instead" from `legs[].probability` and `fair_line` with the reference-line note; chance of losing; stake only via Task 13's bankroll at the parlay cap; `computeModelSlip` and its banner removed (code deleted, not hidden).
- **API/data dependencies.** Existing. **DB/External.** None.
- **States.** `slate_unavailable` → "Parlays price only against today's live slate"; `correlated_legs`; pricing in flight; no book price → verdict withheld with "enter the book's parlay price."
- **A11y.** `aria-live` on the verdict; buttons keep `aria-pressed`.
- **Mobile.** Leg picker and slip stack; sticky verdict.
- **AC.** (1) Fixtures: three favorites at −150/−160/−140 with 58/60/56% → *Poor value*, −$9.50 per $100 at +365; BOS −115/SD +125/CHC −130 → *Marginal*, +$6.80 per $100. (2) `grep -n "MODEL SLIP" src` returns nothing. (3) The independence note renders in both detail levels.
- **Compat.** `/parlay` path unchanged. **Out.** Per-leg book lines (Task 17).

### Task 13 — Local paper bankroll, stake card, limits, cooling-off, attestation

- **Objective.** Bankroll-first sizing that only ever uses an entered price, with shrinkage and caps, plus the responsible-use toolkit, all in browser storage.
- **User-facing outcome.** "$18 model-sized stake (paper), 1.8% of $1,000" on a candidate with an entered price; limits and cooling-off that hide stakes.
- **Files.** `edge-finder.tsx` / Task 8 `PriceEntry` (line inputs), `odds` mirror in `src/lib/odds.ts` (new; port of `moneyline_to_probability`, `decimal_odds`, Kelly, de-vig with unit tests against `smoke_test.py` values), `preferences.ts`.
- **New files.** `src/lib/bankroll.ts`, `src/lib/stake.ts`, `src/pages/bankroll.tsx`, `src/components/stake-card.tsx`, `src/components/gate.tsx` (21+ attestation), footer helpline in `app-shell.tsx`.
- **Preserve.** The API's `kelly_fraction` stays visible in Full detail as "½ Kelly on the raw model chance (reference)."
- **New behavior.** Profiles and caps per 15.2; de-vig requires both entered lines, else "no de-vig — one price entered"; stake only when expected return > 0 at the model chance and the staking chance; parlay cap; weekly loss limit and cooling-off toggles that hide all dollar figures; paper mode default; the gate stored locally and labeled an attestation; helpline on the gate, bankroll page, and footer.
- **API/data dependencies.** None. **DB/External.** None.
- **States.** No bankroll → no dollar figures anywhere (test); cooling-off active → stake slots read "Stakes hidden until <date>"; limit reached → same with the limit name.
- **A11y.** Currency inputs labeled; profile as radio group; cooling-off switch with description.
- **Mobile.** Stake card full-width; inputs 44 px.
- **AC.** (1) Unit tests: $1,000, 58%, −115/+105 → $9/$18/$27; one-line entry → raw implied; no-value → no stake. (2) Rendering every stake surface with `bankroll = null` produces zero currency strings (regex test). (3) Copy lint: "recommended" absent from bankroll files. (4) Cooling-off hides figures within one render.
- **Compat.** Local schema versioned for later migration. **Out.** Server enforcement, bet log, CLV.

### Task 14 — Onboarding, coach marks, Learn hub

- **Objective.** Four-screen onboarding, contextual coach marks, and a Learn hub with the glossary and "how the model works."
- **User-facing outcome.** Expectations set in ninety seconds; concepts explained when they appear.
- **Files.** `preferences.ts` (flags), Task 8 card (annotated fixture), `api.ts` (`useMatchup` for the slider), `ba-paradox.tsx`, `track-record.tsx` (models block).
- **New files.** `src/pages/welcome.tsx`, `src/components/coach-mark.tsx`, `src/pages/research/learn.tsx`, `src/content/lessons/*.md` (ten lessons), `src/lib/glossary.ts` (from the dictionary).
- **Preserve.** Nothing gated behind onboarding.
- **New behavior.** Screens per section 17; the slider demo calls `/api/matchup` with fixed inputs (or the `src/lib/odds.ts` mirror) and walks Avoid → No value → Marginal → Bet candidate at 58% between −160 and −105; coach marks keyed to the triggers listed in 17, shown once per flag.
- **API/data dependencies.** Existing. **DB/External.** None.
- **States.** Offline → the slider uses the local mirror.
- **A11y.** Focus management between screens; skip button always visible after the gate.
- **Mobile.** Full-screen steps; slider with 44 px thumb.
- **AC.** (1) Slider fixture yields *Avoid* at −160, *No value detected* at −140, *Marginal value* at −130, *Bet candidate* at −120. (2) Completion under 90 s in a scripted walkthrough. (3) Each coach mark shows once and never again after dismissal (storage test).
- **Compat.** None. **Out.** Server-synced completion.

### Task 15 — `model_detail` on slate rows and the explanation generator (backend + `ReasonList`)

- **Objective.** Return per-team predicted runs and strength on every slate row and generate priced-only reasons.
- **User-facing outcome.** "Why the model leans Boston" with real numbers on every card.
- **Files.** `backend/feeds.py::_price_game` (add `model_detail {away: {rs_pg, ra_pg, strength}, home: {...}}` from the `predict_from_inputs` results already computed in `_chain_probability` — refactor it to return the predictions), `backend/analytics.py::runs_per_win`, `backend/main.py::slate`, `smoke_test.py`, `src/components/game-card/ReasonList.tsx`.
- **New files.** `backend/explain.py`, `tests/test_explain.py`.
- **Preserve.** Existing row fields and `smoke_test.py`; `adj_detail`; the context-never-in-price rule.
- **New behavior.** `reasons {basis, lean: [{text, inputs}], review: [], context: [{kind, text, ref}]}` built per section 13; `context` from `flags` plus the standing limitations; `review` empty until a price exists.
- **API/data dependencies.** None. **DB/External.** None.
- **States.** Missing `adj_detail` → no starter bullet; `pricing_error` rows → no reasons; near-equal inputs → the "close on every input" sentence.
- **A11y.** List semantics; numbers with units.
- **Mobile.** Bullets wrap; no tables.
- **AC.** (1) Ten golden fixtures pass. (2) A fixture with an IL flag on the lean side never mentions it in `lean`. (3) Row payload size increase under 2 KB per game. (4) `smoke_test.py` green.
- **Compat.** Additive fields. **Out.** Price-dependent `review` sentences.

### Task 16 — Two-sided verdict engine and `POST /api/evaluate`

- **Objective.** A pure, tested evaluator with published thresholds, usable with manual prices now and feed prices later; both sides evaluated.
- **User-facing outcome.** Correct verdicts for whichever side is priced favorably; the H2H teams mode shows both sides.
- **Files.** `backend/odds.py` (reused functions), `backend/main.py` (new route; `/api/matchup` unchanged), `src/hooks/useEvaluate.ts` (new), Task 8 `PriceEntry` (switch from double `/api/matchup` calls), `h2h.tsx` teams mode.
- **New files.** `backend/verdict.py`, `tests/test_verdict.py`.
- **Preserve.** `/api/matchup` shape and terminal verdict strings for existing consumers; `smoke_test.py`.
- **New behavior.** `evaluate(p_season, p_adj, price_home, price_away, gp_home, gp_away, starters_confirmed, price_age_s, book=None)` → per-side `{edge_pts, ev_per_100, breakeven, chance_lose, verdict, flags}` and a game-level `{side, verdict, avoid_note, signal, signal_provisional}`; thresholds per v3 Appendix A (`AVOID ev ≤ −0.05`; `NO_VALUE ev ≤ 0 or edge < 0.01`; `MARGINAL`; `CANDIDATE ev ≥ 0.04 and edge ≥ 0.03 and agree`); gates for missing price, `min(gp) < 30`, stale price, `p_adj` missing; signal computed only with a price and marked provisional; `thresholds` returned in the payload with `MODEL_VERSION`.
- **API/data dependencies.** Task 3 version; Task 15 for `reasons.review`. **DB/External.** None.
- **States.** No price → `INSUFFICIENT_DATA (no_price)`; early season → `INSUFFICIENT_DATA (early_season)`.
- **A11y / Mobile.** Via Task 8.
- **AC.** (1) The ten Appendix A fixtures pass (`58%/−115 → CANDIDATE, edge 4.5, EV 8.4`; `55% at −150 → AVOID, EV −8.3`; `45% at +125 → NO_VALUE`; `53% no price → INSUFFICIENT_DATA`; `60% at +150 → CANDIDATE`; `52% at −110 → NO_VALUE`; `58% at −130 → MARGINAL`; `season 0.58 / adj 0.54 at −115 → NO_VALUE` with a note; `gp 18 → INSUFFICIENT_DATA`; stale and starters-missing flags). (2) `PriceEntry` makes one request per check. (3) H2H teams mode renders both sides' verdicts.
- **Compat.** Additive route. **Out.** Prices from a feed.

### Task 17 — Stake service, parlay evaluate with per-leg lines, data-status endpoint

- **Objective.** Move stake sizing server-side, add per-leg lines and a price basis to parlay pricing, expose cache ages.
- **User-facing outcome.** Identical stake numbers everywhere; a true singles comparison at the user's prices; a data-status line with real cache ages.
- **Files.** `backend/main.py` (`_price_parlay_payload`, `ParlayInput`), `backend/odds.py`, `backend/feeds.py` (cache introspection), `src/lib/stake.ts` (switch to server), `parlay-check.tsx`, `today.tsx` status line.
- **New files.** `backend/stake.py`, `tests/test_stake.py`, `tests/test_parlay_evaluate.py`.
- **Preserve.** `POST /api/parlay/price` unchanged for compatibility; `POST /api/parlay/log` unchanged.
- **New behavior.** `POST /api/stake` per Appendix C (fixture $9/$18/$27; projection cached per (chance, price, fraction)); `POST /api/parlay/evaluate` accepting `legs[].book_line?` and `basis: "season"|"adj"`, returning per-leg `ev_per_100` and the slip verdict; `GET /api/status` with per-cache age from `AsyncTTLCache` (add a `describe()` method), `sources_up`, `updated_at`s, `model_version`.
- **API/data dependencies.** Task 16 evaluator thresholds. **DB/External.** None.
- **States.** `basis: "adj"` with any leg lacking `adj_prob` → 400 `adj_unavailable`.
- **AC.** (1) Stake fixtures pass; client and server agree on fixture outputs (contract test). (2) Parlay fixtures from Task 12 reproduce server-side. (3) `/api/status` lists every cache key family with ages.
- **Compat.** Additive routes. **Out.** Accounts.

### Task 18 — Odds provider adapter spike (decision task with concrete scope)

- **Objective.** Prove one provider against the `feeds.py` pattern and produce the decision inputs (cost, books, latency, terms).
- **User-facing outcome.** None yet; a go/no-go with evidence.
- **Files.** `backend/feeds.py` (`AsyncTTLCache`, `_fetch_json` pattern), `notes/mlb_api_transcripts.md` (transcript format), `.agents/memory/`.
- **New files.** `backend/odds_feed.py` with an interface `fetch_prices(date) -> {game_pk: {book: {home: american, away: american, updated_at}}}` and a stub implementation; `notes/odds_provider_spike.md`.
- **Preserve.** Keyless doctrine becomes "no secrets in the repository": provider keys only via environment variables; nothing committed.
- **AC.** (1) The stub passes a contract test with a fixture payload. (2) The note records: matching rate of provider game ids to MLB `gamePk` (must exceed 98% on a live day), latency, rate limits, price age distribution, terms on display and redistribution, cost. (3) A legal checklist (data licensing, affiliate rules if links are ever added, processor policy) is attached.
- **Out.** Production ingestion (Task 19).

### Task 19 — Line snapshots and prices on slate rows

- **Objective.** Ingest prices from the chosen provider, store opening/current/closing snapshots, attach prices to slate rows, and run the evaluator on them.
- **User-facing outcome.** Book prices, edge, expected return, verdicts, stale chips, and verdict grouping on Today.
- **Files.** `backend/feeds.py::get_slate` (enrich rows), `backend/verdict.py`, `backend/record_store.py::ensure_schema`, `backend/main.py` (scheduler step for closing capture at first pitch), `today.tsx`, `GameCard`, `record.tsx` status.
- **New files.** `backend/odds_feed.py` (real implementation), `backend/closing.py`, `tests/test_odds_feed.py`, `tests/test_closing_capture.py`.
- **Preserve.** Manual entry (always); the leans record unchanged; the 600 s slate cache (prices use their own 300 s cache).
- **New behavior.** `moneyline_line_snapshots(id, game_pk, book, side, american, captured_at, kind)`; rows gain `prices {home: [{book, american, implied, updated_at, opening}], away: [...]}` and `evaluation` from the evaluator using the user's books (local preference sent as a query parameter) with best-available reported separately; `flags.stale` beyond 15 minutes; closing = last snapshot before `gameDate`.
- **External.** The provider from Task 18. **DB.** One new table, additive.
- **States.** Provider down → rows without `prices`, evaluator returns `no_price`, the status line names the outage time; partial coverage → per-row absence.
- **A11y / Mobile.** Via Task 8 (price row, chips).
- **AC.** (1) A live day shows prices on ≥ 95% of rows from ≥ 2 books. (2) Every price shows book and time. (3) A simulated outage renders the launch-state cards with no errors. (4) Closing snapshots exist for every final game the next morning.
- **Compat.** Additive fields; the leans record is untouched. **Out.** Candidates record (Task 20).

### Task 20 — Candidates record and closing-line value

- **Objective.** Record every `BET_CANDIDATE` (and `MARGINAL`) verdict with the price shown, grade at that price, compute CLV, and expose record segments.
- **User-facing outcome.** A candidates record with its own since-date, units at recorded prices, and CLV, on the Track Record page.
- **Files.** `backend/record_store.py`, `backend/main.py::grade_pending_records` (extend), `backend/verdict.py`, `record.tsx`, `tests/conftest.py` DDL.
- **New files.** `backend/candidates.py`, `tests/test_candidate_record.py`.
- **Preserve.** `moneyline_record_picks` untouched (unique `game_pk` stays); VOID semantics mirrored; `adj_record` and `parlay_record` unchanged.
- **New behavior.** `moneyline_candidate_picks(id, snapshot_id, game_pk, side, team, verdict, signal, basis, model_probability, price_used, book, price_captured_at, closing_price, clv_pts, model_version, final_away, final_home, result, units_pnl, graded_at, UNIQUE(game_pk, side))`; written by the today-only snapshot step when the evaluator issues a candidate or marginal verdict; graded with the existing final-score path at `price_used`; `clv_pts = implied(closing) − implied(price_used)` for the pick side (sign convention documented); `GET /api/record?segment=candidates&group_by=verdict|signal|month|version` with n and interval.
- **DB.** One new table. **External.** Task 19.
- **States.** Before go-live → the segment shows "starts when prices went live on <date>"; buckets under 50 → "too small to read."
- **AC.** (1) Seeded candidate on a real past date in the isolated schema grades correctly at its price and computes CLV against a seeded closing snapshot. (2) Totals are internally consistent and idempotent across two grading runs. (3) The Record page shows the candidates record separately from the leans record with no shared totals.
- **Compat.** Additive. **Out.** Personal bets (accounts).

---
## 22. Open product decisions

1. **Odds provider and books.** Which provider, which books, at what cost, and under what display terms. Everything in Phase 3 waits on this. Recommendation: run Task 18 now; choose a provider whose game identifiers map cleanly to MLB `gamePk`.
2. **Data licensing for a paid product.** Whether commercial use of the keyless MLB Stats API and RSS is acceptable, or whether a licensed stats provider is required before charging. Recommendation: legal review during Phase 0; design the `feeds.py` adapter boundary so a licensed source can replace endpoints without touching pricing.
3. **Scheduler hosting.** Always-on API instance versus an external scheduled job hitting `POST /api/record/snapshot` and `POST /api/record/grade`. Recommendation: external schedule plus keeping the in-process loop; it is cheaper and makes gaps visible in logs.
4. **Schema authority.** Delete `lib/db` or keep it as documentation. Recommendation: delete; `record_store.ensure_schema` and `tests/conftest.py` DDL are the authority, and the post-merge push is removed either way.
5. **Home-field adjustment rollout.** Versioned change to both prices versus a third graded price; the value's source (a published historical constant versus a fitted term the bundle cannot support). Recommendation: version registry first (Task 3), then a third graded price for one month mirroring the ADJ experiment, then fold in as `v2` with the record split by version — and do not launch the candidates record without one of these in place.
6. **Verdict thresholds and σ.** The candidate thresholds (edge ≥ 3 pts and expected return ≥ 4%) and the signal σ (4 pts) are starting values. Recommendation: publish them on the Record page and change them only with a dated changelog entry; report the record by bucket so tuning is visible.
7. **Staking-chance weight.** The 50/50 blend and the rule for moving it. Recommendation: fixed until the candidates record has 300 graded picks with positive CLV; then a documented decision.
8. **Whether `/api/matchup` adopts the new labels.** Keep the terminal strings for API compatibility and map in the display layer, or change the API. Recommendation: keep and map; H2H and the smoke test depend on them.
9. **The paper simulation's framing.** Keep the historical `BankrollPanel` as "backtest" or relabel as an educational simulation with its losing result. Recommendation: relabel; it never priced a market and the −22-unit result is more useful as a lesson than as a claim.
10. **Accounts and billing.** Auth provider, processor policy on betting-information subscriptions, free-tier limits on research surfaces. Recommendation: defer until Phase 1–3 prove the UX; keep everything local-first with versioned schemas so migration is mechanical.
11. **The terminal look.** Retire, or keep as an optional theme for existing users. Recommendation: keep behind a theme setting for one release, then decide from usage.
12. **The public parlay slip.** One global paper slip per day is a v2 artifact; with accounts it becomes personal. Recommendation: keep it public and labeled until accounts exist, then migrate.

---

## 23. Final recommendation

Keep the doctrine and the mathematics exactly as they are; they are the product. Spend the first two weeks closing the three integrity gaps the audit found (the dead headline feed, the `?date=` ledger hole, the schema and version authorities) and settling how the grading loop stays alive in production, because the public record is the asset every later phase leans on.

Then build the v3 experience in the order the code allows rather than the order the strategy imagined. The three-layer card, the readiness-grouped Today page, the navigation with redirects, the Track Record page with client-side calibration and intervals, the Parlay Check reframe, local preferences and a local paper bankroll, onboarding, tokens, and accessibility fixes are all honest on today's data and need no backend change beyond the Phase 0 fixes. In parallel, add the two backend pieces that make the card explain and judge — `model_detail` with the explanation generator, and a two-sided evaluator that already works with the manual price inputs the product has always had. Only then, and only after a provider decision and a legal review, wire real prices in, and let the candidates record and closing-line value start on the day the feed goes live, with a home-field version in place so that record is not biased from its first pick.

Do not ship a book price, an edge, an expected return, a stake, a "worth a look" count, a candidates record, or a signal label before the data that makes each of them true exists. Do not ship "Beginner mode," "Find an Edge," "Aggressive," "Confidence," or a featured parlay at all. What remains is a product that can say, on its first redesigned day, exactly what it can prove — the model's price, the arithmetic, the option to check any price you are offered, and a public record that has never been edited — and that grows one honest claim at a time.

---

*End of document.*
