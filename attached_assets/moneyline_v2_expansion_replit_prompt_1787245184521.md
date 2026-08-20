# MONEYLINE v2 — Expand the Desk: Players, Matchups, Parlays, 2026 Projections, and the Wire

This app already exists: **MONEYLINE — a Moneyball Trading Desk**, a Bloomberg-style terminal that prices baseball teams with the classic Moneyball regression stack (RS ~ OBP+SLG, RA ~ OOBP+OSLG, W ~ RD, Playoffs ~ W), shows fair lines vs the market, and grades its own picks in public. v2 expands it from a team desk into a full research floor: **individual player assessment, head-to-head comparisons (player vs player, team vs team), an honest parlay pricer, rest-of-season 2026 projections, and a live news wire** — all running on free, keyless, real 2026 data.

**The doctrine does not change.** Every number on screen is real and traceable to a public data source or a stated formula. The desk states prices, probabilities, and its own graded record; it never urges a wager. The "STATISTICAL RESEARCH · NOT WAGERING ADVICE" tag stays visible everywhere, including every new panel. Where a new feature tempts you to fake something (a salary, an injury, a sentiment score, a hitter-vs-pitcher matchup the model can't actually price), the correct move is to display the honest boundary instead. v2's job is to make the desk *bigger*, never to make it *looser*.

Work in phases, in order. Do not skip Phase 0.

---

## Phase 0 — Audit the existing desk before adding anything

1. **Read the codebase first.** Map what exists against the v1 spec: `backend/inference.py` (single model-loading module), `odds.py`, `feeds.py`, `precompute.py`, the seven panels (Pricer, Edge Finder, BA Paradox, Track Record, Bankroll, Live Record, Screener), the SlateRail, the error envelope `{"error": {"code", "message"}}`, the Replit DB–backed Live Record, and the deployment config.
2. **Run `smoke_test.py`.** It must pass before and after everything you do in v2: models reproduce `verified_stats.json` (2002 A's chain → RS ≈ 808, RA ≈ 662, ≈ 96.4 W, ≈ 76.4% playoff odds) and all odds-math unit tests stay green. If anything from the v1 done-checklist is broken, **repair it first** — v2 built on a cracked v1 is worthless.
3. **Fix before extending.** Anything that regressed (boot > ~5s, dead panels, missing deployment config, record not persisting in Replit DB) gets fixed in this phase.
4. New code follows the existing patterns: models load once at startup, precompute over runtime compute, per-panel error states, TTL caches with request coalescing, no secrets, everything keyless.
5. **Non-negotiable regression rule for the whole build:** the v1 experience is untouched — same boot speed, same panels, same math. New panels lazy-load so they can never slow the desk's cold start.

**Build order after Phase 0:** data layer verified with curl → new math in `analytics.py` + unit tests → API endpoints verified with curl → frontend panels → deployment config update → final checklist.

---

## The 2026 data layer — free, keyless, verified

This answers the standing question: *how do we get data as recent as 2026?* MLB's official Stats API (`statsapi.mlb.com`) is free, keyless, and live — every endpoint below was verified working on **August 20, 2026** with the sample values shown, so you can sanity-check your own fetches against reality. Re-verify each one with curl from inside Replit before wiring the UI, and adapt to the fields the API actually returns.

| # | What | Endpoint | Verified today |
|---|---|---|---|
| 1 | Team hitting (season) | `/api/v1/teams/stats?season=2026&group=hitting&stats=season&sportId=1` | 30 teams; e.g. Rays OBP .332, SLG .408, 578 runs |
| 2 | Team pitching (season) | same with `group=pitching` | OBP-against / SLG-against per team — this is **live OOBP/OSLG**; e.g. Yankees .295 / .362, 470 RA |
| 3 | Player stats, league-wide | `/api/v1/stats?stats=season&group=hitting&season=2026&sportId=1&playerPool=qualified` (and `group=pitching`) | Real 2026 lines, e.g. Luis Arraez OBP .353 / SLG .440 over 533 PA; Jacob Misiorowski 1.75 ERA, .215 OBP-against, 139 IP. Paginate with `limit`/`offset`; `playerPool=all` exists for deeper pools |
| 4 | Schedule + probable pitchers + scores | `/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,linescore` | 9 games today with both probables named; yesterday's finals returned with scores (grading source, already used by v1) |
| 5 | Standings | `/api/v1/standings?leagueId=103,104&season=2026&standingsTypes=regularSeason` | W-L, RS/RA, games played per team; e.g. Rays 76-50 through 126 games → 36 remaining |
| 6 | Rosters + injury status | `/api/v1/teams/{teamId}/roster?rosterType=40Man&season=2026` | `status.description` flags the IL; e.g. Yankees currently show Aaron Judge (60-day IL) and Cody Bellinger (10-day IL) |
| 7 | Transactions — trades, signings, IL moves | `/api/v1/transactions?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD` | 1,103 transactions in the past 7 days, each with date, `typeDesc` (Trade, Signed as Free Agent, Released, Assigned…) and a full sentence description |
| 8 | League news headlines | `https://www.mlb.com/feeds/news/rss.xml` (RSS/XML) | Verified live; parse titles, links, pub dates |
| 9 | ESPN public JSON (optional) | `site.api.espn.com/apis/site/v2/sports/baseball/mlb/news` and `/scoreboard` | **Not verified — returned 403 from the build sandbox.** Try it once from Replit; if it works, use it as a second headline source; if not, skip it silently. It must never be a dependency |

Data-layer rules, extending v1's infrastructure rules:

- All fetching stays in `feeds.py`. One in-memory TTL cache + coalescing lock per resource: slate/team stats ~10 min (as in v1), player pools ~6 h, rosters ~6 h, transactions and news ~30 min. Bounded concurrency; a dead feed degrades that panel to a styled cached/empty state, never an error page and never a blank desk.
- 2026 numbers are a **season in progress**. Any price computed from in-season rates carries a sample-size label ("THRU 126 GP") and the UI never presents a partial season as a finished one.
- The nightly team-input snapshot the Live Record already stores stays the source of truth for "what did the desk know that morning" — extend it to also snapshot the probable starters used, so graded picks remain reproducible.
- Player identity is `player.id` from the API, never name strings. Display names exactly as the API returns them.
- No salary data exists on these keyless endpoints. Therefore the app shows **no 2026 salary figures anywhere** — the historical $/W screener column (if the v1 bundle included payroll) stays historical. The Player Desk may include a "paste a salary" input where the *user* supplies a number to see $/win math on their own responsibility, clearly labeled "USER-SUPPLIED".

---

## New math — `backend/analytics.py`, every formula unit-tested in `smoke_test.py`

All of it derives from the models the app already fit. That's the point: v2 doesn't bolt on a new black box, it **cashes out more consequences of the same audited regressions**.

**1. Player run value and mWAA (model Wins Above Average).** The team RS model is linear: `RS ≈ −804.6 + 2737.8·OBP + 1584.9·SLG` (use your actual fitted coefficients from `verified_stats.json`, never these literals). Team OBP is (to a close approximation) the playing-time-weighted mean of player OBPs, so swapping a league-average hitter for player *p* over his share of team plate appearances moves the team inputs by his deltas times his share:

- share `s` = player PA ÷ league-average team PA (hitters) or player IP ÷ league-average team IP (pitchers), computed from the live 2026 pools
- `ΔRS = s · (β_OBP·(OBP_p − OBP_lg) + β_SLG·(SLG_p − SLG_lg))` — hitters, vs the qualified-pool league mean
- `ΔRA = s · (β_OOBP·(OBPa_p − OBPa_lg) + β_OSLG·(SLGa_p − SLGa_lg))` — pitchers, from the RA model, sign flipped so run *prevention* is positive value
- `mWAA = ΔRD × slope(W~RD)` — with the v1 fit that slope is ≈ 0.1058 wins per run, i.e. **≈ 9.5 runs ≈ 1 win, the famous sabermetric rule, rediscovered by this app's own regression**. Put that sentence in the UI as a receipt — it's the best possible evidence the stack is sane.

Show the full arithmetic as receipts (delta × coefficient × share) exactly like the v1 pricer does. Label the metric honestly wherever it appears: *offense (or run prevention) only — no defense, no baserunning, no park adjustment; "average" means the 2026 qualified pool.* Never call it WAR.

**2. Starter-adjusted game pricing.** v1's standing caveat was that a season-aggregate model can't see pitchers. v2 partially answers it, and does so as an experiment the record can grade rather than a silent upgrade. For a game with probable starters:

- starter innings share `w` = his own 2026 IP ÷ (games started × 9), a real per-pitcher number (cap to [0.4, 0.8])
- blended team defense inputs: `OBPa_blend = w·OBPa_starter + (1−w)·OBPa_team`, same for SLG-against — team rate as the bullpen proxy, and say so in the tooltip
- run the same chain (RA model → Pythagorean → log5) with blended inputs → the **ADJ price**, alongside the unchanged season price

Every slate row now shows both: `SEASON −132 · ADJ −118`. The Live Record grades **both** prices on every pick from now on and displays their records side by side. The UI never claims ADJ is better — the record is the only thing allowed to say that. This is the doctrine turned into a feature: two hypotheses, one public scoreboard.

**3. Parlay math — `odds.py` additions.** For legs with model probabilities `p_1…p_n`:

- combined probability `P = Π p_i`, **under an independence assumption the UI states out loud**; legs from the same game are refused (correlated — the math would be dishonest)
- fair American odds from `P` via the existing conversion; book parlay payout from the entered per-leg American lines: convert each to decimal, multiply, convert back
- edge = `P − implied(book parlay odds)`; EV per 1 unit = `P·(decimal payout − 1) − (1−P)`; ½-Kelly only when EV > 0, else the stake reads `0.00 — NO EDGE`
- the **vig-compounding demo**: alongside every parlay, show the book's total margin vs the same legs bet singly. This is the teachable heart of the panel — parlays multiply the house edge, and the desk proves it with the user's own legs.

Unit tests with hand-checked examples: two independent 55% legs → P = 30.25%, fair ≈ +230; two −110 legs paid at the standard +264 vs true-fair +300 → the margin is visible; a 60%/60% parlay priced at +250 → positive EV; same-game legs → rejected with the styled error.

**4. Rest-of-season simulation.** For each of the ~36 remaining games per team (from the schedule endpoint, today through season end): win probability from the current-rating chain (Pythagorean + log5, season inputs). Monte Carlo the remaining league schedule **with a fixed seed** (store the seed; re-run only when inputs refresh) — N = 2,000 iterations is plenty and takes negligible time. Outputs per team: expected final wins, a final-wins distribution, and **playoff odds = share of simulations finishing in a playoff spot under the actual 2026 format (top 6 per league: 3 division winners + 3 wild cards), computed from the simulated standings** — not from the historical `Playoffs ~ W` logistic, which was fit on 1962–2012 formats and would be miscalibrated here; keep that logistic where it belongs, in the historical panels, and note the distinction in a footnote. Stated assumptions, printed under the table: current team rates persist; no trade/injury/fatigue modeling; ties broken randomly.

**5. What the model must refuse to predict.** Next *season* (2027) is off-season roster construction — this stack has no roster model, so the Season Desk says so in one styled line ("2027: NOT PRICED — a season model needs an offseason roster model; this desk doesn't fake what it can't fit") instead of inventing numbers. Same honesty for hitter-vs-pitcher "who wins" comparisons (different y-variables — show each player's run impact side by side instead) and for injuries (the model can't price them; the desk *discloses* them — see the Wire).

---

## Media analysis — signals beside the model, never inside it

"Predictions based on media analysis" is implemented the only honest way: media becomes **disclosed context**, and the regression prices stay pure and auditable.

- **INJURY FLAGS.** From roster `status` + IL transactions: any team with a player on the IL who ranks in that team's top 5 by playing time (PA or IP from the live pools) gets a red flag chip on its slate row and pricer header — e.g. `NYY ⚑ JUDGE 60-DAY IL`. Tooltip: "The season model prices the roster's season-to-date average, including games this player missed and played. It cannot see tomorrow's lineup — you can."
- **MEDIA PULSE.** A per-team tone score from the last 7 days of wire items: a small, visible lexicon (positive: *walk-off, streak, sweep, activated, returns, career-high…*; negative: *injured, IL, surgery, skid, eliminated, designated for assignment…*) applied to headline + transaction text, normalized to −100…+100. Displayed as a tiny amber meter with the item count ("PULSE +34 · 12 items") and, on click, the exact items and matched words that produced the score. No black-box sentiment, no external model — a scoring rule a reader can audit in ten seconds.
- **The hard rule:** neither flags nor pulse ever move a price. If a game's media context contradicts its model price, that tension is *shown* ("MODEL LIKES NYY · MEDIA PULSE −41") — that's the "models + scouts" thesis on screen, and it's more interesting than a fudged number.

---

## New features — six more panels, each earning its place

*(Numbered 8–13, continuing the v1 seven. The v1 seven stay exactly where they are.)*

8. **Player Desk — individual player assessment.** Omnisearch any 2026 hitter or pitcher (autocomplete over the live pools: qualified players by default, expandable to everyone with ≥ 100 PA or ≥ 30 IP via `playerPool=all`). The card: real stat line (hitters: PA, BA, OBP, SLG, HR, BB%, K% as available; pitchers: IP, ERA, WHIP, K, BB, OBP/SLG-against), **percentile bars vs the qualified pool** computed live, then the model section — ΔRS (or ΔRA), mWAA, and the receipts arithmetic, ending with the fair-odds framing v1 users already know: "adding this bat to an average team reprices it from −100 to −108 vs average." Two signature touches: the **9.5-runs-per-win receipt** line, and the **"WOULD BEANE BUY?" badge** — lit when a hitter's OBP percentile exceeds his BA percentile by 20+ points, the 2002-style walk-heavy profile the market historically underpaid, with one caption line tying it to the BA-paradox panel. Optional "USER-SUPPLIED salary" input → $/mWAA, labeled as such.
9. **Head-to-Head — player vs player, team vs team.** One panel, two modes. *Players:* two search slots (hitter-hitter or pitcher-pitcher), columns side by side with a delta column and paired percentile bars, verdict strip on mWAA with its margin ("ARRAEZ +1.9 mWAA — but check the receipts: it's all OBP"). Hitter vs pitcher → the styled boundary state from the math section, showing each player's own run impact instead of a fake duel. *Teams:* the v1 Edge Finder chain now accepts **any two 2026 teams with live inputs** alongside historical seasons and slider teams — with starter context, IL flags, and both SEASON and ADJ prices when probables exist. A share button copies a URL that reproduces the exact comparison (state in query params).
10. **Parlay Lab.** Build a 2–6 leg slip from today's slate: click legs on, each showing its model probability and pick side, then the math panel — combined probability, fair parlay odds, an input for the book's offered parlay payout, and the verdict: edge in pp, EV per unit, ½-Kelly paper stake (or `0.00 — NO EDGE`), plus the **vig-compounding strip** comparing house margin on the parlay vs the same legs single. The desk also surfaces one **MODEL SLIP OF THE DAY** — the 2–3 leg combination with the highest model-fair probability-weighted EV at standard −110 pricing — presented with full receipts and the standing research tag, never as a "lock," never with urgency. Slips can be **logged to the Live Record** (paper only): graded all-or-nothing when finals arrive, with a separate parlay record line ("PARLAYS 3–9, −4.2u") — if the record shows parlays bleeding units while singles tread water, the desk has taught the most valuable lesson it owns, in its own data.
11. **Season Desk — 2026 projections.** The projected-standings table, all 30 teams: current W-L (live standings), expected final wins from the simulation, a final-wins distribution sparkline, playoff odds %, division odds %, and delta vs naive current-pace extrapolation — sortable, with the biggest model-vs-pace risers and fallers called out as chips. Drill into a team: remaining-schedule difficulty (mean opponent rating, next 10 games listed with win probabilities), and the assumptions footnote. The 2027 line renders the honest refusal state. CSV export like the Screener.
12. **The Wire — the desk's news feed.** A full-height terminal-style feed, filterable by team and by type chips — `TRADE` `SIGNING` `IL` `ACTIVATED` `RESULT` `NEWS` — merging three real streams: MLB transactions (majors-relevant types only: trades, MLB signings, releases, IL placements/activations — filter out the minor-league assignment noise), MLB RSS headlines, and **desk notes the app writes itself from structured data it already has**: final-score recaps with the model's grade attached ("`DET 3 @ PIT 4 — FINAL · DESK HAD PIT 54% · GRADED ✓W`") and daily record summaries. Every item: ET timestamp, source tag (`MLB.COM` / `TRANSACTION` / `DESK`), and a link when one exists. Monospace slugs, uppercase type tags, green/red tint only for results — wire-service *style*, no outlet's branding or trade dress, no images. Desk notes are template-generated from real fields only; if a template lacks a real value, the note isn't written.
13. **Upgrades to the existing seven.** *SlateRail:* rows gain probable starters, IL flags, and the dual SEASON/ADJ prices; clicking a probable's name opens his Player Desk card. *Live Record:* dual-price grading side by side (the ADJ experiment), the parlay record line, and a CLV note on any day the user logged a real book line. *Team Pricer:* omnisearch accepts "NYY 2026" — live-input pricing with the THRU-N-GP label — while historical seasons behave exactly as before. *Screener:* year selector gains "2026 (SEASON SO FAR)" using live inputs vs preseason naive priors (last year's wins), labeled partial. *Edge Finder:* stays on the DESK tab exactly as is; Head-to-Head's team mode reuses its chain and components rather than duplicating them. *BA Paradox:* one new caption line linking it to the WOULD-BEANE-BUY badge so the historical punchline visibly powers a live feature. *Everything:* URL state for shareable views; the boot sequence gains one line ("SYNCING 2026 FEEDS… OK") only if it stays under the 5s health budget.

---

## API additions (same envelope, same error discipline, all verified with curl before frontend work)

- `GET /api/players?group=hitting|pitching&pool=qualified|all&q=` → search/autocomplete over cached pools
- `GET /api/player/{id}` → stat line, percentiles, ΔRS/ΔRA, mWAA, receipts, badge flags
- `GET /api/compare/players?a={id}&b={id}` → both cards + deltas + verdict (or the boundary state)
- `GET /api/team-live/{teamId}` → 2026 inputs (OBP/SLG/OBPa/SLGa, GP) + IL flags + pulse
- `POST /api/parlay/price` — body `{"legs": [{"gamePk", "side"}], "book_odds": int|null}` → combined prob, fair odds, edge, EV, kelly, vig comparison; 400 on correlated legs
- `POST /api/parlay/log` → store today's slip in the record (idempotent per day)
- `GET /api/season-sim` → the cached simulation table + assumptions + seed + input timestamp
- `GET /api/wire?team=&types=&limit=` → merged, deduped, cached feed
- Extend `GET /api/slate` rows with `probables`, `adj_prob`, `flags`; extend `/api/record` with the dual and parlay records

---

## Design system — unchanged, extended

Same tokens, same grid, same type stack, same ◆. New elements inherit: percentile bars are thin 4px tracks in `#1f2530` with the value segment in semantic color and the pool median ticked; player identity renders as `ARRAEZ · PHI · 1B` in mono caps — **no headshots, no team logos** (initial-block avatars in team-ish hues are fine); the Wire uses 1px-rule separated rows, 11px uppercase type tags, muted timestamps. Navigation becomes a CommandBar tab row — `DESK · PLAYERS · H2H · PARLAY · SEASON · WIRE` — keyboard-switchable (1–6), with DESK rendering the entire v1 layout untouched. Tabs lazy-mount; `/` still focuses the (now global) omnisearch, which returns teams, players, and historical seasons in one ranked dropdown. Under 900px everything still stacks to one clean column.

States and motion follow v1 exactly: per-panel skeletons, styled empty/edge states for every new failure mode (player below qualification floor, no probables yet, sim inputs stale, wire feeds down → cached items with an amber "AS OF" stamp), count-ups and bar animations honoring `prefers-reduced-motion`, visible focus rings, `aria-live` on verdicts.

---

## Anti-patterns — v1's list still binds; add these

- No invented salaries, sentiment scores, injuries, or news items — every wire item and every flag traces to an API response; every pulse score expands to its evidence.
- No headshots, logos, or another outlet's trade dress. "ESPN-style" means *wire-desk energy*, achieved with type and layout, not borrowed branding.
- No hitter-vs-pitcher winner, no 2027 predictions, no "lock/boost/can't-miss" parlay language, no urgency copy anywhere.
- Media Pulse and injury flags never alter a price. The ADJ price is never presented as superior until the Live Record shows it.
- No per-request refits or sims; the simulation is seeded, cached, and refreshed only when inputs refresh.
- Do not break v1: if a v2 change would force a v1 checklist item to fail, the v2 change is wrong.

---

## Replit requirements — non-negotiable, updated

- Everything stays keyless; no secrets, no signup walls.
- New Replit DB keys for parlay slips and dual-price grades, versioned so existing record data migrates forward untouched (write a tiny one-time migration that runs at boot, idempotently).
- `precompute.py` additions stay build-time where inputs allow; live-data derivatives (pools, percentiles, sims) compute on first fetch and cache with TTLs — never per request.
- Both workflows updated: dev and production run the full v2 app; the **deployment config** (build + run commands) is updated and production-tested — build the frontend, run precompute, boot the prod server, load every tab — before the job is called done.
- Cold start to healthy `/api/health` stays under ~5s: new panels and feeds are lazy; nothing new blocks boot.

---

## Done means every box checks

- [ ] Phase 0 audit done; the entire **v1 checklist still passes**, including `smoke_test.py` against `verified_stats.json`.
- [ ] New unit tests green, each with a hand-checked example: mWAA arithmetic (a +.050 OBP hitter at a 10% PA share prices out to the receipts' exact ΔRS and wins), runs-per-win derived from the fitted W~RD slope, parlay combined probability / fair odds / EV (55%×55% → 30.25%, ≈ +230 fair), same-game legs rejected, blended ADJ inputs, sim determinism (same seed + inputs → same table).
- [ ] Player Desk loads a real 2026 hitter and pitcher with percentiles, receipts, the 9.5-runs-per-win line, and a WOULD-BEANE-BUY badge that fires for at least one real player in the current pool.
- [ ] Head-to-Head compares two live players and two 2026 teams; hitter-vs-pitcher renders the boundary state; the share URL reproduces the view.
- [ ] Parlay Lab prices a hand-built slip correctly, shows the vig-compounding strip, rejects correlated legs, surfaces a MODEL SLIP OF THE DAY with receipts, and logs slips that later grade correctly against real finals.
- [ ] Season Desk shows all 30 teams simulated under the 2026 playoff format with assumptions footnoted, sortable, exportable; the 2027 refusal state renders.
- [ ] The Wire merges transactions, RSS headlines, and desk notes with team/type filters, ET timestamps, and source tags; each feed dying degrades to a styled cached/empty state.
- [ ] SlateRail shows probables, IL flags (a currently-injured star like the Judge example should appear while true), and dual SEASON/ADJ prices; the Live Record grades both and shows the parlay line; records survive a restart in Replit DB.
- [ ] Media Pulse opens to its evidence list; no price anywhere moves because of pulse or flags.
- [ ] Every tab keyboard-reachable, lazy-mounted, styled to the system; no white flash; stacks under 900px; research tag visible on all six new surfaces.
- [ ] Deployment config updated and production-tested; publish works with no "Run command not found."
- [ ] `curl` transcripts (or equivalent) exist in the repo notes for every data-layer endpoint actually used, with the date checked.

