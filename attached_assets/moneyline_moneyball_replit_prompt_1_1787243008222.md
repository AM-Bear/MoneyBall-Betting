# Build "MONEYLINE — a Moneyball Trading Desk"

Build a production-quality web app around my Moneyball regression project. Work in phases, in order. Do not skip Phase 0.

**The product in one paragraph:** A Bloomberg-style trading terminal for baseball, where teams are the assets and betting lines are the prices. The model stack is the classic Moneyball pipeline — runs scored from OBP and SLG, runs allowed from opponent OBP/SLG, wins from run differential, playoff odds from wins — trained on historical team seasons. The app prices any team the way a trader prices a stock: model-fair odds vs the market's line, with the gap shown as EDGE. Dark, dense, monospace, green/red — a betting desk that runs on regression, not vibes.

**The bar:** a tool a sharp bettor or a front office would actually open, built on the sharp's own doctrine: **every number on screen is real, and advice must be earned by a track record, never claimed in advance.** That means: a slate of today's actual games priced on load from live 2026 stats, every prediction showing its regression receipts, an audited historical backtest with calibration, edge math (fair line, implied probability, vig, break-even rate, Kelly stake) done exactly right — and a **Live Record panel where the desk grades its own picks against real final scores, in public, every day**. The app states prices and probabilities; it never urges a wager. The UI carries a visible "STATISTICAL RESEARCH · NOT WAGERING ADVICE" tag — not because the numbers are fake (they are all real), but because a season-aggregate model has not yet earned a game-level edge against closing lines, and the Live Record is the honest instrument that would prove one. This app demonstrates the Moneyball template: find the measurable signal, price the market against it, and let the record speak.

---

## Phase 0 — Verify the bundle (before writing any app code)

If `moneyline_upload_pack.zip` is in the project root, unzip it there first. Either way you should end up with exactly these project files in the root: `model_setup.py`, `model_config.json`, `requirements.txt`, `baseball.csv`, and `verified_stats.json`. There are no pretrained model files and nothing downloads from a hub (`model_config.json` has `hub_repo_id: null`) — **the models are fit at build time from `baseball.csv`**, and `verified_stats.json` contains the exact numbers a correct fit produces, computed in advance from this same CSV. Your job in Phase 0 is to reproduce them.

1. Read `model_setup.py` — load every bundled file only through `model_setup.paths["<filename>"]` (e.g., `model_setup.paths["baseball.csv"]`), never by raw path.
2. The dataset is the classic Moneyball team-seasons table, verified: **1,232 rows × 15 columns**, seasons **1962–2012**, columns `Team, League, Year, RS, RA, W, OBP, SLG, BA, Playoffs, RankSeason, RankPlayoffs, G, OOBP, OSLG`. `Playoffs` is 0/1; `RankSeason`/`RankPlayoffs` are NaN for non-playoff teams; **`OOBP` and `OSLG` exist only from 1999 onward** — handle that explicitly (offense-only pricing for earlier seasons, labeled in the UI).
3. **Fit the canonical stack in `precompute.py` with a chronological split — train ≤ 2001 (902 rows), test ≥ 2002 (330 rows).** Never a random split; this is a time-series claim: "could you have called it in 2002?" Deterministic fits, saved with joblib, loaded once at startup:
   - `RS ~ OBP + SLG` (linear regression)
   - `RS ~ OBP + SLG + BA` (fit solely for the BA-paradox demo panel)
   - `RA ~ OOBP + OSLG` (train is 1999–2001 only, 90 rows — small but honest; say so in the UI footnote)
   - `W ~ RD` where RD = RS − RA
   - `Playoffs ~ W` (logistic regression → a probability)
4. **Cross-check every fit against `verified_stats.json`.** The expected results (already verified on this exact CSV and split):
   - RS model: `RS ≈ −804.6 + 2737.8·OBP + 1584.9·SLG` — R² 0.93 train, **0.88 test**. OBP's coefficient is ~1.7× SLG's: the Moneyball insight, quantified.
   - BA paradox: adding BA gives `coef(BA) ≈ −369` while R² stays ~0.93.
   - RA model: `RA ≈ −837.4 + 2913.6·OOBP + 1514.3·OSLG` — R² 0.88 test.
   - Wins: `W ≈ 80.88 + 0.1058·RD` — R² 0.876 test, **MAE 3.25 wins**.
   - Playoffs: **89.4% test accuracy vs a 72.7% majority baseline** (27.3% of test team-seasons made the playoffs). Calibration on test: model says 50–60% → 76.5% actually made it (n=17); 60–70% → 100% (n=12); 70%+ → 100% (n=34). The model runs under-confident at the top — surface that honestly.
   - Full chain on the 2002 A's (OBP .339, SLG .432, OOBP .315, OSLG .384): predicted **RS 808 / RA 662 / 96.4 wins / 76.4% playoff odds** vs actual **800 / 654 / 103 wins, made playoffs**.
   If your numbers differ materially from the file, your split or columns are wrong — fix that before building anything.
5. Write `smoke_test.py`: load data and models end-to-end, run the 2002 A's chain, assert each output within tolerance of `verified_stats.json` (±2 runs, ±1 win, ±2pp on playoff odds), and run the odds-math unit tests below. Do not start building the app until it passes. Its load/predict code becomes `backend/inference.py` — the single module everything else imports.
6. Use every bundled file. `.replit_prompt.txt`, if present, is a stale template from an earlier project — ignore its contents; THIS document is the spec.

**Build order after Phase 0:** backend endpoints verified with curl → precomputed artifacts → frontend → deployment config → final checklist.

## Architecture

- A Python backend runs the models. Preferred stack: **FastAPI backend + React (Vite) frontend** — the design bar below is hard to hit with stock Streamlit/Gradio. Those are acceptable only if you fully theme them to the spec.
- In production, one process serves everything on one port: `vite build` produces `frontend/dist`, FastAPI serves those static files (SPA fallback to index.html, long cache headers on hashed assets) plus the API.
- Keep the layout boring and legible:

```
backend/
  main.py         # FastAPI app: routes, static serving, lifespan startup
  inference.py    # model load + prediction chain (smoke_test.py imports this)
  odds.py         # probability <-> moneyline conversion, edge, Kelly
  feeds.py        # MLB Stats API fetching, fallbacks, caching
  precompute.py   # build-time: fits models, writes track_record.json + backtest.json + ba_paradox.json
  static_data/    # the precomputed JSON artifacts + saved models
frontend/         # Vite + React app
smoke_test.py
```

- API (adapt field names to what Phase 0 revealed):
  - `GET /api/health` → `{"model_loaded": bool}` — the frontend boot screen polls this.
  - `GET /api/team/{team}/{year}` → the full model chain for that team-season: `{"inputs": {obp, slg, oobp, oslg, payroll?}, "predicted": {rs, ra, rd, wins, playoff_prob}, "actual": {rs, ra, wins, playoffs}, "fair_line": int, "receipts": [{"feature", "value", "coefficient", "contribution"}]}`
  - `POST /api/matchup` — body `{"team_a": {...stats}, "team_b": {...stats}, "book_line_a": int|null}` → `{"model_prob_a", "implied_prob_a", "edge_pp", "verdict": "VALUE"|"NO VALUE"|"NO LINE", "kelly_fraction", "fair_line_a", "fair_line_b"}`
  - `GET /api/slate` → today's real MLB games priced by the model (see Live data), each `{"away", "home", "model_prob_home", "fair_lines", "badges"}`
  - `GET /api/screener?year=YYYY` → ranked mispricing list for that season (see Feature 6).
  - `GET /api/track-record` (includes `"calibration"` buckets), `GET /api/backtest`, `GET /api/ba-paradox` → serve the precomputed JSON artifacts.
  - `GET /api/record` → the live pick record: every stored slate snapshot with its grade once final scores exist, plus running totals `{"picks", "graded", "wins", "losses", "hit_rate", "units_pnl"}`.
  - `POST /api/record/grade` → idempotent: fetches final scores for any ungraded past snapshots and grades them (also triggered automatically on boot and on slate refresh — no cron required).
- Errors use one envelope: `{"error": {"code", "message"}}` with real status codes (400 bad team/year, 404 not in dataset, 503 live feed down). The frontend maps codes to styled states — raw error text never reaches the UI.

## Infrastructure rules

- **Load models once**, at startup, in FastAPI's lifespan hook — never per request. Predictions are vectorized; pricing a whole season's teams is one matrix op, not a loop.
- **Precompute at build time, don't compute at runtime.** Model fitting, the track record (with calibration), the bankroll backtest, and the BA-paradox coefficients all depend only on bundled data, which never changes. `precompute.py` runs in the deployment build step and writes the JSONs and joblib files; the API just reads them. If artifacts are missing at boot, compute once at startup and cache — but the build step is the primary path.
- **The app must be fully functional offline.** Every core feature runs from bundled data alone. The live slate is a bonus layer: if the MLB API is unreachable, the SlateRail falls back to a curated list of famous seasons (2002 OAK, 1998 NYY, 2001 SEA 116-win team, 2004 BOS…) — styled as "HISTORICAL MODE", never an error.
- **Cache and coalesce.** In-memory TTL cache (~10 min) for live slate and team-stat fetches; a per-resource lock so concurrent requests hit the API once. Bounded concurrency (2–3 at a time) when pricing a slate; one dead request renders as a per-row failure and never stalls the rest.
- **Assume the deployment sleeps between requests** (Replit Autoscale scales to zero). Cold start to a healthy `/api/health` should be under ~5 seconds: precomputed artifacts, lazy heavy imports, tiny linear models.
- **The Live Record must survive restarts and redeploys.** Autoscale's local disk is ephemeral — never store the record in local files. Use Replit's built-in database (the key-value store or managed Postgres) for slate snapshots and grades. Grading is lazy and idempotent: on boot and on each slate refresh, grade any past snapshots whose games have final scores. One snapshot per date — re-opening the app the same day must not duplicate picks.
- Every outbound call: ≤10s timeout, one retry, browser-like User-Agent. Config via env vars with defaults (`PORT`, `CACHE_TTL_SECONDS`, `FEED_TIMEOUT_SECONDS`); no secrets anywhere — every data source is keyless. Log one line per request (path, team, ms, cache hit/miss). CORS only for the Vite dev origin — production is same-origin.

## The odds math — get it exactly right (`odds.py`, unit-tested)

- Probability → American moneyline: p ≥ 0.5 → line = −100·p/(1−p); p < 0.5 → line = +100·(1−p)/p. Round to the nearest 5.
- American moneyline → implied probability: negative line L → |L|/(|L|+100); positive line L → 100/(L+100).
- Edge = model probability − implied probability, shown in percentage points. Note the book's vig plainly (implied probabilities across both sides sum to >100%).
- Matchup probability from two teams' predicted RS/RA: use Pythagorean expectation for each team's strength, combined with log5 — standard, defensible, and explainable in a tooltip.
- Kelly stake: f = edge/odds in decimal form — display **fractional Kelly (½)** as the suggested paper stake with the full formula shown. Never suggest stakes above the paper bankroll.
- Every formula above gets a unit test in `smoke_test.py` with a hand-checked example (e.g., −150 ⇄ 60%).

## Features — seven, each earning its place on a betting desk

1. **Team Pricer (main).** Pick any team-season from the dataset (searchable "OAK 2002" style input; team codes render like tickers) → the model chain runs and displays as a pipeline: OBP/SLG → predicted RS · OOBP/OSLG → predicted RA · RD → predicted WINS → PLAYOFF ODDS on the big gauge, with the fair moneyline for a generic matchup vs an average team. Predicted-vs-actual shown side by side with a colored delta — for the default team that reads "MODEL 96W · ACTUAL 103W ▲+7 — even the model underpriced them; the market missed by far more." **Front Office mode:** sliders unlock on the four inputs so the user can build a hypothetical team and watch the whole chain re-price live — "can you assemble a 95-win team?" Defaults to the **2002 Oakland A's** on first load, the founding example.
2. **Edge Finder — the betting twist.** Pick two team-seasons (or two slider-built teams) → model win probability for each side via Pythagorean + log5 → fair lines for both. Then an input for **the moneyline a sportsbook is actually offering** (manual entry — no odds API needed): the app converts it to implied probability and renders the verdict with real-bettor math shown in full: the edge in percentage points, the book's vig quantified (both sides' implied probabilities summing past 100%), the **break-even win rate at that line**, and the ½-Kelly fraction. Three possible verdicts, honestly graded: **VALUE** (model edge clears the vig), **INSIDE THE VIG — NO PLAYABLE EDGE** (model disagrees with the book by less than the juice), and **NO VALUE** (the book's side is better than the model's). A one-line caveat under every verdict: game-level lines also price pitchers, injuries, and lineups this season-level model cannot see. This is the financial core: two prices for the same asset, the full cost of the market, and what the model can and cannot know.
3. **The BA Paradox — the signature demo.** An interactive panel that reproduces the famous result: a toggle between `RS ~ OBP + SLG` and `RS ~ OBP + SLG + BA`, with the coefficients drawn as labeled bars. Flip it and batting average's coefficient swings to **≈ −369** (verified on this data) while R² stays at 0.93. One caption line: "In 2002 the market paid for BA. Once you know OBP and SLG, BA adds nothing — so walk-heavy players were on sale." Both fits precomputed; the toggle animates the bars. This panel is the punchline of the whole project — make it land.
4. **Model Track Record — with calibration.** From the chronological backtest (trained ≤2001, tested 2002–2012), displaying the verified numbers: runs models at **R² 0.88** on unseen seasons, win totals within **±3.25 wins** on average, playoff calls right **89.4%** of the time vs the **72.7%** majority baseline (state the base rate honestly — only 27% of teams make the playoffs, so beating "always say no" is the real bar). The calibration strip is the headline: **when the model priced a team's playoff odds at 70%+, those teams made it 100% of the time (34 of 34, 2002–2012)** — and even its 50–60% calls hit at 76%. The model is under-confident at the top; say so. That answers the only question a bettor asks: *when should I trust it?* Every number traces to `verified_stats.json` and your own precompute — never fabricate, never hide the baseline.
5. **Bankroll Backtest.** A paper-$1,000 simulation across the test seasons: each year, "buy" the teams the model prices meaningfully above their naive market prior (previous season's wins — a fair stand-in for where casual money sits), flat one unit each, paid out when the team makes the playoffs or beats its prior by the stated threshold. Chart the bankroll curve vs a "bet the big names" baseline (prior-year winners), end-of-line value labels, stats row (units won, hit rate, ROI). State every assumption in a footnote: paper units, no vig, market prior = last season. No lookahead: each season priced only with data available before it. Prior-year joins by team code cover 326 of 330 test rows; bridge the four franchise rebrands with an explicit map — ANA→LAA (2005), FLA→MIA (2012), TBD→TBR (2008), MON→WSN (2005) — so no team silently drops out.
6. **Live Record — the desk grades itself.** The feature that separates real statistics from talk. Every day, the first slate load stores an immutable snapshot: date, each game, the model's win probability and fair line, and its pick (the side it prices above 50%). From the next day on, the app fetches actual final scores from the MLB API and grades every stored pick: WIN or LOSS, with a running record (e.g., "23–19, 54.8%"), a cumulative units curve at a stated odds assumption (flat 1 unit at −110 unless a real line was entered that day), and the break-even line (52.4% at −110) drawn on the chart so the viewer can see at a glance whether the model is above or below water against the market's cost. No cherry-picking, no resets, no deletions — losses display exactly like wins. If the record is young, say so ("TRACKING SINCE AUG 2026 · SMALL SAMPLE"). This panel is the app's integrity: the only honest path from "model" to "advice" runs through it.
7. **Undervalued Asset Screener.** A stock-screener-styled table for any season: every team with model-predicted wins vs naive prior, sorted by mispricing; columns for OBP, SLG, predicted W, actual W, and a MISPRICED badge on the biggest gaps. If the bundle includes salary/payroll data, add the true Moneyball column — **payroll per predicted win ($/W)** — and rank by it: the 2002 A's should sit at the top of the value list with the Yankees at the bottom; make that contrast the default view. CSV export button on the table (columns: year, team, inputs, predicted, actual, mispricing).

## Live data — free, no API keys (bonus layer, never a dependency)

- **Today's slate:** MLB's official Stats API is free and keyless — schedule from `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD` (verified working and returning live 2026 games with away/home teams, gameDate, status, and venue per game), current team stats via the standings and team-stats endpoints. Pull each team's season OBP/SLG (and defensive equivalents where available), run them through the model chain, and price today's real games with fair lines. Re-verify from inside this Replit environment before wiring the UI; adapt fields to what the API really returns.
- August 2026 is mid-season — the slate should be full of live games. Off-season or outage → HISTORICAL MODE fallback (famous seasons), styled identically, labeled clearly.
- Display all game times in US Eastern with an "ET" suffix.
- Every external call follows the Infrastructure rules; a dead feed degrades the SlateRail to fallback content — never a blank panel, never a stack trace.

## Preloaded examples

- Source every example from the bundled dataset only — real team-seasons, never invented numbers. The model was trained on this data; made-up stat lines produce meaningless demos.
- Default load: **OAK 2002**. Quick-pick famous seasons in the SlateRail's historical mode: 2002 OAK, 1998 NYY, 2001 SEA, 2004 BOS, 1962 NYM (the worst — show the model handles the floor too).
- The inputs are numeric, so users never type raw numbers from scratch: they pick a real team-season and tweak it with sliders (Front Office mode). Slider ranges come from the dataset's actual min/max per column.

## Design system

- Background layers: page `#0b0e14`, panel `#11151d`, raised elements `#161b26`, 1px borders `#1f2530`. Set `color-scheme: dark` and the body background in index.html so there is never a white flash on load.
- Semantic color: value/win green `#16c784`, fade/loss red `#ea3943`, neutral/warning amber `#f5a623`, primary text `#e6e9f0`, muted `#8b95a7`. Color is never the only signal — pair it with ▲▼ icons and VALUE / NO VALUE / MISPRICED text tags, and check contrast against the dark background.
- Type: JetBrains Mono (or IBM Plex Mono) for team codes, odds, stats, timestamps; Inter for labels. `font-variant-numeric: tabular-nums` wherever numbers align; fixed formats (probabilities 1dp, moneylines as −150/+130, wins as integers). Uppercase 11px letter-spaced section headers over thin rules.
- Team codes styled exactly like stock tickers (NYY, OAK, BOS); a small diamond glyph ◆ as the app's motif where a finance app would put ▲▼.
- Dense, data-forward spacing on a 4px grid — a trading desk, not a sports blog. No big empty hero sections, no rounded pastel cards, no default framework styling, no team logos or MLB trademarks (codes and colors only). Page title "MONEYLINE — Moneyball Trading Desk" with a simple ◆ favicon.

## Layout and components (desktop-first grid)

1. **CommandBar** (top): app name "MONEYLINE ◆", team-season search input (autofocused, "OAK 2002" format with autocomplete from the dataset, Enter submits, "/" focuses it), blinking green LIVE dot when the slate feed is up, last-updated ET timestamp.
2. **SlateRail** (left, narrow): today's real games priced by the model — away @ home, model probability, fair lines, VALUE badge when a manually entered line diverges — or HISTORICAL MODE famous seasons when the feed is down. Click a row to load it. This rail is what makes the layout read as a live desk instead of a static class project.
3. **PricerPanel** (hero left): the model chain as a horizontal pipeline with the four stages and their live numbers, ending in the big playoff-odds gauge (semicircular needle, red → amber → green) with the fair line beneath; predicted-vs-actual delta chips; Front Office sliders collapse beneath. `aria-live="polite"` on the verdict; needle animates with easing.
4. **EdgeFinder** (hero right): matchup picker, book-line input, and the verdict card — VALUE/NO VALUE in huge type, edge in pp, ½-Kelly paper stake. The receipts list beneath: each feature's value × coefficient → contribution, so every price explains itself.
5. **BAParadoxPanel** (full width, slim): the animated coefficient toggle with its one-line caption.
6. **TrackRecordPanel** (with the calibration strip) and **BankrollPanel** (bottom row, side by side) as specified in Features.
7. **LiveRecordPanel** (full width, above the screener): the graded pick table (date · matchup · model prob · pick · final score · W/L), the running record in big type, and the units curve with the break-even line marked. Sample-size label always visible.
8. **ScreenerPanel** (full width): the season mispricing table with year selector and CSV export.
9. **StatusStrip** (footer): model versions (four fits + test R²), data-source dots (SLATE ● DATA ● RECORD ●), last response ms, and a muted "STATISTICAL RESEARCH · NOT WAGERING ADVICE" tag. Terminal credibility, real values only.

Responsive: under ~1200px the SlateRail collapses into a horizontal strip below the CommandBar; under ~900px the grid stacks to one column. Charts use a real library (Recharts / Chart.js / Plotly) themed to the system — dark grid, green/red series. Never default-styled matplotlib PNGs, never ASCII gauges.

## States and motion

- **Boot:** show a terminal-style boot sequence over the dark background ("LOADING MODELS… OK / FITTING 1962–2001… OK / PRICING SLATE…"), driven by polling `/api/health` — never a frozen or white page.
- **Loading:** per-panel skeletons; every panel owns its own loading, empty, and error state so one failure never blanks the others.
- **Empty/edge states, designed not defaulted:** unknown team/year ("NOT IN DATASET — 1962–2012 SEASONS ONLY"), missing OOBP/OSLG years (price with the offense-only chain and label it), amber HISTORICAL MODE banner on the rail, inline red error for malformed lines in the Edge Finder.
- **Motion, subtle:** count-up numbers, needle easing, the BA-paradox bars animating on toggle, slight row stagger on first load. Honor `prefers-reduced-motion`. Visible focus rings on all interactive elements.
- Every model output is visualized — gauges, pipelines, coefficient bars, deltas, tags. No plain unstyled text dumps.

## Anti-patterns — do none of these

- Random train/test split (leaks the future into the past) — the split is chronological, always.
- Fabricated numbers anywhere: accuracy, odds, payouts, historical stats. Everything traces to the bundled data or a stated formula.
- Tout framing: no "lock of the day", no "bet this now", no sportsbook signup links or logos, no rocket emojis. The desk states real prices, probabilities, and its own graded record; it never urges a wager. The RESEARCH tag stays visible, and the Live Record never hides a loss.
- Claiming an edge the record hasn't shown: the UI must never describe the model as "beating the books" unless the graded Live Record actually clears the break-even line over the displayed sample.
- Refitting models per request, or a slate that blocks on its slowest fetch.
- A failed feed blanking the page, raw exception text in the UI, light-mode flash, default framework styling, MLB logos/trademarks.

## Replit requirements — non-negotiable

- Server binds `0.0.0.0` and reads the `PORT` env var (sensible dev fallback) so the web preview loads.
- Install the bundled `requirements.txt` if present, plus what the app needs (fastapi, uvicorn, scikit-learn, pandas, joblib, httpx…). If a pinned version conflicts with this environment, use the nearest compatible version.
- Two explicit workflows: **dev** = uvicorn with reload + Vite dev server proxying `/api`; **production** = build the frontend, run `precompute.py`, then one run command starts FastAPI serving the API and `frontend/dist` on `$PORT`. Every process must run in production, not just development — a backend with only a dev run config fails when published.
- **Configure the deployment config now, before finishing** — not just the dev Run workflow. Deployment build command: install frontend deps, `vite build`, run `precompute.py`. Deployment run command: the production server. Publishing uses the deployment config, not the Run button; if it's missing, Publish fails with "Run command not found" / "Invalid run command". Test the production path yourself — build, run the prod command, load the app — before calling the job done.

## Done means every box checks

- [ ] `smoke_test.py` passes: models reproduce `verified_stats.json` within tolerance (2002 A's chain → RS 808, RA 662, 96.4 W, 76.4% playoff odds), and every odds-math unit test (probability ⇄ moneyline: 60% ⇄ −150, +130 → 43.5%; Kelly) is green.
- [ ] `/api/health` goes healthy in under ~5s from a cold start; the boot sequence shows, then clears.
- [ ] The app opens on OAK 2002 with the full pipeline priced and the predicted-vs-actual delta visible.
- [ ] The SlateRail shows today's real games priced by the model — or HISTORICAL MODE, styled, when the feed is down.
- [ ] Front Office sliders re-price the whole chain live; the Edge Finder returns a correct VALUE/NO VALUE verdict for a hand-checked example (e.g., model 60% vs a +150 line ≈ 20pp edge).
- [ ] The BA Paradox toggle animates and shows the negative BA coefficient from the real fit.
- [ ] Track Record shows test-set R², win MAE, playoff accuracy vs the stated baseline, and the calibration strip — all from precomputed artifacts.
- [ ] Bankroll Backtest renders both curves with its assumptions footnoted; the Screener ranks mispricings (with $/W if salary data exists) and its CSV export downloads a valid file.
- [ ] The Live Record stores exactly one snapshot for today's slate, grading a seeded past-date snapshot against real final scores produces correct W/L marks, totals survive a restart (stored in Replit's database, not local files), and the Edge Finder's three-way verdict (VALUE / INSIDE THE VIG / NO VALUE) triggers correctly on hand-checked lines.
- [ ] Unknown team, malformed line, missing OOBP years, and dead feed each produce a styled in-app state; other panels stay alive.
- [ ] No white flash, charts themed, layout stacks cleanly under 900px, focus rings and reduced-motion respected, the SIMULATION tag is visible.
- [ ] Deployment config has a valid production build + run command — publishable with no "Run command not found".
- [ ] Zero unused bundle files, or an explicit stated reason a file isn't needed.
