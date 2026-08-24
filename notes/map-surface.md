# MONEYLINE — Surface Map (Recon Lane 3)

**Scope:** API route inventory, what v3 asks for, the gap in dependency order, dead ends.
**Read order followed:** `attached_assets/MONEYLINE_v3_Product_Strategy_and_UX_Plan_1787528143354.md` → `attached_assets/MONEYLINE_Repository_Audit_and_v3_Strategy_1787533744890.md` → `backend/main.py`, `backend/seo.py`, `backend/serve_spa.py`, `artifacts/moneyline/src/**`.
**Working tree state:** branch `main` @ `6eda109`. Read-only pass; nothing edited outside this file.

> **Important correction to the audit doc.** The audit was written against commit `cef8cab`. `main` is now ~9 commits ahead (`9591b01` "Build the Today experience…" → `f74d034` "Standardize research URLs and redirect legacy routes" → the SEO commits → `6eda109`). A material slice of the audit's "Phase 1 frontend" work **has already shipped**: a Today page, a three-layer `GameCard`, a Research hub, a Track Record page, a Settings page with a localStorage preference store, parameter-preserving redirects, and the removal of the model slip. Every "not implemented" claim in the audit's §3.2 table has been re-verified against the current tree below. The audit's three Phase 0 defects, by contrast, are **all still open**.

---

## 1. Route inventory

22 `/api/*` routes + `/sitemap.xml` = the 23 routes; plus one SPA catch-all. All in `backend/main.py` unless noted. Error envelope `{"error":{"code","message"}}` (`backend/main.py:152`, handlers at `:392–414`).

| # | Method · Path | Defined | Purpose | Inputs | Response shape (key fields) | Frontend hook | Consuming component → page |
|---|---|---|---|---|---|---|---|
| 1 | `GET /api/health` | `main.py:437` | boot probe | — | `model_loaded`, `startup_ms`, `database_ready`, `model_version` (**hardcoded literal**, `:443`) | `useHealth` (`api.ts:32`, polls 1 s until loaded) | `App.tsx:180` → `TerminalBoot`, `StatusStrip` (global shell) |
| 2 | `GET /api/teams` | `main.py:447` | historical team-season directory | — | `teams[{team,year,label}]` | `useTeams` | `edge-finder.tsx`, `command-bar.tsx` (omnisearch), `h2h.tsx` |
| 3 | `GET /api/team/{team}/{year}` | `main.py:462` | v1 historical chain (1962–2012 only) | path: team code, year | `inputs`, `predicted{rs,ra,rd,wins,playoff_prob}`, `fair_line`, `receipts[]`, `actual`, `data_ranges` | `useTeamPrice` | `desk.tsx` (PricerPanel), `edge-finder.tsx`, `h2h.tsx` → `/desk`, `/research/matchups` |
| 4 | `POST /api/price` | `main.py:489` | chain for arbitrary inputs | `{obp,slg,oobp?,oslg?}` | same as #3 minus `actual` | `usePrice` (mutation), `usePriceInputs` (query flavour) | `desk.tsx` (what-if sliders, live pricer) → `/desk` |
| 5 | `POST /api/matchup` | `main.py:507` | two input sets + optional manual lines | `team_a`, `team_b`, `book_line_a?`, `book_line_b?` | `model_prob_a/b`, `implied_prob_a/b`, `edge_pp`, `vig_pp`, `break_even_rate`, `verdict` (4 values, `:560–566`), `kelly_fraction` (**side A only**, `:569`), `fair_line_a/b`, `formula`, `receipts`, `caveat` | `useMatchup` | `edge-finder.tsx` **only** → `/desk`, `/research/matchups`, and inside `GameCard`'s advanced layer (`game-card.tsx:210`) |
| 6 | `GET /api/slate` | `main.py:601` | today's priced games | `?date=YYYY-MM-DD` (optional) | `mode`(live/historical), `feed_up`, `date`, `updated_at`, `cache`, `record_persisted`, `games[]` (`game_pk`, `status`, `time_et`, `away/home` B-Ref codes, `*_name`, `model_prob_home`, `fair_lines`, `probables`, `adj_prob`, `adj_fair_lines`, `adj_detail`, `flags[]`, `*_inputs`, `badges`, `pricing_error`) | `useSlate` (5-min refetch; **`date` never passed by the app**) | `today.tsx` → `/`; `desk.tsx` → `/desk`; `parlay-lab.tsx` → `/research/parlay`; `h2h.tsx` teams mode; `App.tsx` status strip |
| 7 | `GET /api/screener?year=` | `main.py:693` | mispricing table | `year` (1962–2012 or live) | `year`, `rows[]`, `offense_only`, `payroll_available:false`, `season_so_far`, `sample_label`, `method` | `useScreener` | `screener.tsx` → **`/desk` only** |
| 8 | `GET /api/track-record` | `main.py:770` | precomputed fit metrics | — | R², MAE, accuracy vs baseline, calibration buckets, `models` | `useTrackRecord` | `track-record.tsx` → `/track-record`, `/desk` |
| 9 | `GET /api/backtest` | `main.py:775` | paper $1,000 season simulation | — | series; committed result **model −22.0 u / 96 bets** | `useBacktest` | `bankroll-backtest.tsx` → `/track-record`, `/desk` |
| 10 | `GET /api/ba-paradox` | `main.py:780` | BA-paradox demo artifact | — | regression comparison | `useBaParadox` | `ba-paradox.tsx` → **`/desk` only** |
| 11 | `GET /api/record` | `main.py:803` | live paper ledger | — | `picks`, `graded`, `wins/losses/voided`, `hit_rate`, `units_pnl`, `break_even_rate`, `tracking_since`, `sample_label`, `curve[]`, `entries[]`, `adj_record{}`, `parlay_record{}`, `database_ready` | `useLiveRecord` (60-min refetch) | `live-record.tsx` → `/track-record`, `/desk` |
| 12 | `POST /api/record/grade` | `main.py:814` | manual grading trigger | — | grading counts + full `record` | `useGradeRecord` | `live-record.tsx` "GRADE PENDING" |
| 13 | `GET /api/players` | `main.py:828` | pool search | `group`, `pool`, `q` | `players[]`, `floor_note` | `usePlayers` | `player-desk.tsx`, `player-search.tsx` → `/research/players` |
| 14 | `GET /api/compare/players` | `main.py:880` | comparison / refusal | `a`, `b` (player ids) | `mode`(hitting/pitching/**boundary**), `deltas`, `percentile_pairs`, `verdict{}` | `useComparePlayers` | `h2h.tsx` → `/research/matchups` |
| 15 | `GET /api/wire` | `main.py:904` | merged feed | `team?`, `types?`, `limit` | `items[]`, `sources_up{transactions,news,desk}`, `updated_at` | `useWire` | `wire.tsx` → `/research/wire` |
| 16 | `POST /api/parlay/log` | `main.py:917` | one paper slip per day | `legs[]`, `book_odds?` | `stored`, `already_logged`, `slip_id`, `priced`, `note` | `useParlayLog` | `parlay-lab.tsx` → `/research/parlay` |
| 17 | `GET /api/team-live/{team_id}` | `main.py:946` | live inputs + context | path: MLB team id | `inputs`, `sample_label` (`THRU N GP`), `flags[]`, `pulse{}`, `hard_rule` (`:970`) | `useTeamLive` | `desk.tsx`, `h2h.tsx` |
| 18 | `POST /api/parlay/price` | `main.py:973` | price 2–6 legs off today's slate | `legs[{gamePk,side}]`, `book_odds?` | `legs[]`, `combined_prob`, `fair_odds`, `independence_note`, `price_basis`, `vig_comparison{}`, `book{edge_pp,ev_per_unit,half_kelly,stake_label}`\|null; 400 `correlated_legs`, 404 `leg_not_found`, 503 `slate_unavailable` | `useParlayPrice` | `parlay-lab.tsx` → `/research/parlay` |
| 19 | `GET /api/player/{player_id}` | `main.py:978` | player card | path: player id | stat line, percentiles, `model{delta_rs/ra,mwaa,receipts,wins_formula}`, `fair_odds_framing`, `would_beane_buy`, `salary{available:false}` | `usePlayerCard` | `player-desk.tsx`, `h2h.tsx` |
| 20 | `GET /api/season-sim` | `main.py:1042` | seeded Monte Carlo standings | — | `rows[]`, `assumptions[]`, `seed`, `iterations`, `input_signature`, `next_season{status:"NOT PRICED"}` | `useSeasonSim` | `season-desk.tsx` → `/research/season` |
| 21 | `GET /api/season-sim/team/{team_id}` | `main.py:1055` | team outlook | path: team id | `next_10[]`, `mean_opponent_rating` | `useTeamOutlook` | `season-desk.tsx` |
| 22 | `GET /api/teams-live` | `main.py:1072` | live team directory + **live-season contract** | — | `season`, `teams[{team_id,team,name,wins,losses,games_played}]` | `useTeamsLive` / `useLiveSeason` | `command-bar.tsx`, `desk.tsx`, `wire.tsx`, `h2h.tsx`, `screener.tsx`, `layout.tsx`, `player-search.tsx`, `ba-paradox.tsx`, `season-desk.tsx` |
| 23 | `GET /sitemap.xml` | `main.py:1106`, also `serve_spa.py:97` | crawler sitemap | — | XML from `seo.sitemap_xml` (`seo.py:359`) | — | crawlers only (by design) |
| — | `GET /{path:path}` | `main.py:1115`, `serve_spa.py:98` | SPA fallback | — | `dist/public/index.html` with per-route SEO injected (`seo.render_index`, `seo.py:393`); 404 for unknown `api/` and non-public routes (`seo.is_public_client_route`, `seo.py:351`) | — | browser navigation |

**Client routes** (`App.tsx:219–238`): `/` (Today, or Desk when `?team`/`?year` present — `RootExperience`, `App.tsx:165`), `/desk`, `/research`, `/track-record`, `/settings`, `/research/{players,matchups,parlay,season,wire}`, plus redirects `/players`, `/h2h`, `/parlay`, `/season`, `/wire` (`ResearchRedirect`, `App.tsx:173`, carries the search string). Nav is 6 items (`command-bar.tsx:7–14`): Today · Research · Track record · Desk · Parlay check · Settings, with legacy keyboard `1–6` still bound to the **old six tabs** (`LEGACY_SHORTCUTS`, `command-bar.tsx:17–23`).

---

## 2. What v3 asks for — itemized

Distilled from both docs. Each line is a hand-off-able unit. `[S]` = strategy doc, `[A]` = audit doc task number.

### Data & integrity foundations
1. Define `RSS_URL`, `ESPN_NEWS_URL`, `_espn_dead` in `feeds.py`; add a stubbed-client unit test. `[A T1]`
2. Guard ledger writes: `store_slate_snapshot` persists only when `slate["date"] == today (ET)` **and** row status ∈ {Scheduled, Pre-Game, Warmup}; add `POST /api/record/snapshot` (today-only, idempotent). `[A T2]`
3. `MODEL_VERSION` constant in `precompute.py`; `ALTER TABLE … ADD COLUMN IF NOT EXISTS model_version text` on snapshots/picks/parlay slips; `/api/health` and `StatusStrip` read it; `get_record` returns `model_versions_present[]`. `[A T3]`
4. Single schema authority: drop `pnpm --filter db push` from `scripts/post-merge.sh`; delete or freeze `lib/db/src/schema/moneyline.ts`. `[A T3]`
5. Keep the grading loop alive: always-on deploy target **or** external cron hitting `POST /api/record/snapshot` (10:00 ET) and `POST /api/record/grade` (03:00 ET). `[A T4]`

### Terminology, tokens, a11y
6. `src/lib/terminology.ts` + `<Term>` component: `{key,label,technical,tooltip,learnPath}`; every component reads labels from it. `[S §8.2, A T5]`
7. Copy pass to sentence case; specific rewrites — `VALUE`→"Bet candidate", `INSIDE THE VIG…`→"Inside the sportsbook's cut — no value", `Model Edge +4.5%`→"Edge +4.5 pts", `B/E Rate`→"Win rate needed to break even", `½ Kelly`→"Model-sized stake (½ Kelly)", `ADJ`→"With tonight's starters", `%H`→"Home chance", W/L letter badges → words. `[S Appx D, A §12]`
8. Copy lint (`scripts/copy-lint.mjs`) failing the build on: lock, guaranteed, free money, sure thing, can't lose, bet now, recommended/suggested bet, slip of the day, boost, risk-free, hot, streak, best bet, play of the day, fade, expert, insider, emoji, countdown language. `[S Appx D, A T5]`
9. Design tokens: dark palette `#0f1318/#161b22/#1c222b/#262c36/#e6e9ef/#9aa4b2`, `--radius: 0.75rem`, accent ring `#6FA8E0`; light palette under `[data-theme="light"]`; desaturated verdict palette (candidate/marginal/no-value/avoid/win/loss) as tinted pills with icon + word, AA-checked. `[S §14.2–14.4, A §18.1]`
10. Type & density: Inter for UI, mono **only** for odds/probabilities-in-tables/records/timestamps; ≥13 px chips, 15–16 px body; retire `uppercase tracking-widest` outside table eyebrows; retire `text-[8px]/[9px]/[10px]`. `[S §14.3, A §18.2]`
11. Motion/status: remove `animate-pulse` from the LIVE dot; replace `TerminalBoot` with a plain loading state (optional terminal theme flag); 150–200 ms disclosures. `[S §14.6, A §18.3]`
12. A11y/mobile: remove `maximum-scale=1`; 5-item bottom bar under 768 px (`useIsMobile` already exists); tables in `overflow-x-auto`; 44 px targets; skip link; chart text summaries; PWA manifest + service worker. `[S §13, A §18.4]`

### Preferences & progressive disclosure
13. Versioned local preference store `{version:1, detailLevel, explainTerms, theme, timeZone, onboardingCompletedAt, coachMarksSeen[]}` with try/catch on every read/write, `usePreference` hook, Settings page. `[S §7, A T7]`
14. Rule: switching detail level changes **no numeric text** — enforced by a snapshot test. `[S §7.3, A T7 AC1]`

### The card system
15. `GameCard` three layers (answer / explanation / numbers) over `SlateGame`, with `VerdictPill`, `StatusChips`, `Disclosure`, `PriceEntry`, `ReasonList`, `NumbersLayer`, plus a fixtures file (live+ADJ, no probables, `pricing_error`, final, historical). `[S §6.2, A T8]`
16. Card contract, 10 rules: verdict computed for **both sides** and names the value side; no edge/EV without price+book+timestamp; no stake without bankroll+profile+positive EV; lean bullets from priced inputs only; sample/staleness/disclaimer never collapsible; same verdict in both detail levels; never colour-only; no book links or urgency; verdict frozen once live; every number has a definition and a "how this is calculated" expander with real figures. `[S §6.4]`
17. Probability-basis rule: the lean, the chance-to-lose chip, the explanation and the verdict must all use the **same** probability, named on the card ("with tonight's starters" vs "season strength"). `[A §10.4]`
18. Risk row: "loses X% of the time" = `1 − p`; payout shape ("risk $115 to win $100"); break-even at the offered price; volatility tag (Lower ≤ −200 / Higher ≥ +150 / Typical); uncertainty (High if `min(gp)<60` or `|p_adj − p_season| ≥ 0.05`). `[S §6.6, Appx A]`
19. Signal strength = `edge / σ` (σ published, initially 0.04): Strong ≥1.0 + agree + complete data; Moderate ≥0.5 or ≥1.0 with one ingredient missing; else Weak. Fixed tooltip ("disagreement, not certainty"); marked *provisional* until 200 graded candidates in the bucket. `[S §6.5, Appx A]`
20. Two slots, not one: a **verdict pill** and a separate **data-status chip row** (price unavailable, starters not confirmed, small sample, as-of). `[A §10.2]`

### Today
21. `/today` as default route: read-only date bar (yesterday/today/tomorrow), data-status line, summary strip with tappable count filters, filter/sort bar, card sections, right rail (record snapshot, bankroll chip, context strip from `/api/wire?types=IL,TRADE`), honesty footer. `[S §5.2, A T9]`
22. Launch grouping is by **data readiness** (ready / starters not confirmed / in progress / final / pricing failed); it switches to **verdict** grouping only once prices exist. `[A §9.1]`
23. Designed states: no candidates; feed unavailable; stale price; starters unconfirmed; small sample (<30 gp → verdict withheld); off-season; postponed; in progress. `[S §5.4, A §9.2]`
24. Today deliberately excludes: bet buttons, book links, countdowns, streak badges, hot-hand copy, social proof, flashing odds, featured parlays. `[S §5.5]`

### Game detail
25. `GET /api/game/{gamePk}` + page `/game/{gamePk}`: `GameCardDTO` + both-teams `receipts`, `line_history`, `both_sides` evaluation table, `kelly` (with bankroll), `links`. Buildable today from the slate row + `POST /api/matchup` + `/api/team-live`. `[S P1 Page 2, A §6.3]`
26. `GET /api/share/game/{gamePk}.png` — server-rendered share card, disclaimer and as-of baked in, **never** a stake. `[S P2.2]`

### Explanations
27. `model_detail {away:{rs_pg,ra_pg,strength}, home:{…}}` on every slate row — refactor `feeds._chain_probability` to return the `predict_from_inputs` results it currently discards. `[A T15]`
28. `backend/explain.py` returning `reasons {basis, lean[], review[], context[]}` on slate rows and on `/api/evaluate`. Templates: offense (|Δ| ≥ 0.15 R/G), prevention (|Δ| ≥ 0.15), starter (|Δ| ≥ 1 pt), one counterweight, sample sentence last; max three lean bullets ranked by run contribution via `analytics.runs_per_win`; fallback line "The two teams are close on every input the model prices." `[S Appx B, A §13]`
29. Hard rule, test-enforced: `reasons.lean` never cites flags, pulse, transactions, form, or venue. Ten golden fixtures. `[S Appx B, A §13.2–13.3]`
30. Context chips carry the standing limitations: "Home field: not priced", "Bullpen: approximated by the team rate", "Lineups/weather: not priced" (from `EQUITY_CAVEAT`, `main.py:87`). `[A §13.1]`

### Verdict engine
31. `backend/verdict.py` — pure `evaluate(p_season, p_adj, price_home, price_away, gp_home, gp_away, starters_confirmed, price_age_s, book=None)` → per-side `{edge_pts, ev_per_100, breakeven, chance_lose, verdict, flags}` + game-level `{side, verdict, avoid_note, signal, signal_provisional}`, returning `thresholds` and `MODEL_VERSION` in the payload. Exposed as `POST /api/evaluate`. `[S Appx A, A T16]`
32. Published thresholds: `AVOID ev ≤ −0.05`; `NO_VALUE ev ≤ 0 or edge < 0.01`; `MARGINAL ev > 0 and edge ≥ 0.01`; `CANDIDATE ev ≥ 0.04 and edge ≥ 0.03 and (p_adj null or agree)`. Gates: live/final → no verdict; no price → `INSUFFICIENT_DATA(no_price)`; `min(gp) < 30` → `INSUFFICIENT_DATA(early_season)`; price >15 min → `stale` flag; `p_adj` null → verdict on season, signal capped Moderate; `min(gp) < 60` → `small_sample`. `[S Appx A]`
33. Ten fixtures must pass before it ships (58%/−115 → CANDIDATE edge 4.5 EV 8.4 gap 1.13; 55% at −150 → AVOID; 45% at +125 → NO_VALUE; 53% no price → INSUFFICIENT_DATA; 60% at +150 → CANDIDATE; 52% at −110 → NO_VALUE; 58% at −130 → MARGINAL; season .58/adj .54 at −115 → NO_VALUE; gp 18 → INSUFFICIENT_DATA; stale; adj-null). `[S Appx A]`
34. `/api/matchup` keeps its shape and terminal strings; the new labels are a display-layer map. `[A §22 Q8]`

### Parlay Check
35. Reframe `/parlay` verdict-first: verdict pill + takeaway; the three numbers; house-cut bar from `vig_comparison`; "singles instead"; expected return + chance of losing; independence note; correlation notes; conditional stake at the parlay cap; the numbers. `[S §9.2, A T12]`
36. Slip verdict rules: *Poor value* if `ev_per_unit < 0` or any leg negative at its own price; *Marginal* if `0 ≤ ev < 0.04`; *Candidate* if `ev ≥ 0.04` and every leg non-negative. `[A §14.2]`
37. `POST /api/parlay/evaluate` accepting `legs[].book_line?` and `basis: "season"|"adj"`, returning per-leg `ev_per_100` and the slip verdict; `basis:"adj"` with a leg lacking `adj_prob` → 400 `adj_unavailable`. `/api/parlay/price` stays for compatibility. `[A T17]`
38. Remove `MODEL SLIP OF THE DAY` from the default view — code deleted, not hidden. `[S §9.4, A T12]`

### Bankroll & responsible use
39. Local-first bankroll: amount, risk profile, unit, paper mode (default on), weekly loss limit, cooling-off. `[A T13]`
40. Stake sizing (Appendix C): de-vig from both entered prices; `p_stake = 0.5·p_model + 0.5·q_devig` (published constant); full Kelly on `p_stake`; profile fraction+cap — Conservative ¼ / 1% (parlay 0.5%), Balanced ½ / 2% (1%), Higher variance ¾ / 3% (1.5%); round to the dollar; "no stake — no value at this price" when EV ≤ 0. Fixture: $1,000 @ 58%, −115/+105 → devig 52.3%, staking 55.2%, full Kelly 3.6%, **$9 / $18 / $27**. `[S Appx C, A §15.2]`
41. `POST /api/stake` (pure) + a 100-bet projection at the staking chance (≈ +$57 mean, ~1 in 3 runs end down, median worst dip ~15% at Balanced), cached per (chance, price, fraction). `[S Appx C, A T17]`
42. The existing uncapped `half_kelly_fraction` must be capped and shrunk **before any dollar figure appears**; it survives in Full detail only as "½ Kelly on the raw model chance (reference)". `[A §6.6, T13]`
43. Responsible-use toolkit: 21+ attestation gate (labelled an attestation, not verification), 1-800-GAMBLER in the footer/gate/bankroll page, weekly loss limit that hides stakes, cooling-off (24 h / 7 d / 30 d, instant on, delayed off), indefinite paper mode, no stake or price move in any notification, no dollar figure on a share card. `[S §10.6, A §15.3]`
44. `/bankroll` page + `My bets` log with grading and CLV (waits on accounts + closing prices). `[S P1 Page 4]`

### Track Record
45. `/record` composing four visually distinct records that share **no number, chart series, or colour**: historical tests (under a persistent "Historical, season-level, 2002–2012. Not bettable." banner), live all-leans, candidates-only, parlays; plus "My bets" once accounts exist. `[S §11.1, A §16.1]`
46. Hero: tracking-since, picks, graded, record, units, hit rate, break-even (110/210), sample label, and a **95% interval on units per pick** computed client-side (`mean ± 1.96·sd/√n`, method stated on the page). `[A §16.2]`
47. Live calibration buckets (50–55, 55–60, 60–65, 65+) from `entries[].model_probability` vs `result`, with counts; buckets under 30 de-emphasised. `[A §16.2]`
48. "What this proves" standing copy with dynamic n and the ±√n luck swing; "how many bets it takes" explainer (≈1,600 bets at 5% ROI, ≈4,400 at 3%). `[S §11.2–11.3]`
49. Per-pick table + CSV export; methodology from `formula`/`method`/`assumptions`/`EQUITY_CAVEAT`/`independence_note`; model version footer; published verdict thresholds once the evaluator ships. `[A §16.2–16.3]`
50. Relabel the paper backtest as an **educational paper simulation**, keeping its −22.0-unit result visible. `[A §22 Q9]`
51. `GET /api/record?segment=candidates|leans|parlays&group_by=`, `GET /api/record/calibration`, `GET /api/model/versions`. `[S P2.2]`
52. Track Record is the public/marketing entry point, linked from the header and from every card. `[S §11.4]`

### Onboarding & education
53. Four screens under 90 s, skippable after the gate: (0) 21+ gate; (1) what this is; (2) annotated card; (3) price-slider demo walking Avoid → No value → Marginal → Bet candidate at a fixed 58%; (4) setup. `[S §12.2, A §17]`
54. Coach marks keyed to events the code already emits: first `pricing_error`, first `adj_detail == null`, first manual price entry, first `INSIDE THE VIG`, first Parlay Check, first graded LOSS, first `HISTORICAL MODE` day, first `flags` chip. `[A §17]`
55. `/research/learn`: ten lessons, glossary generated from the dictionary, "how the model works", BA paradox, model changelog. `[S §12.4]`

### Prices & the priced ledger (external dependency)
56. Odds-provider spike: `backend/odds_feed.py` interface `fetch_prices(date) -> {game_pk:{book:{home,away,updated_at}}}`, stub + contract test, and `notes/odds_provider_spike.md` recording gamePk match rate (>98%), latency, rate limits, price-age distribution, display/redistribution terms, cost, plus a legal checklist. `[A T18]`
57. Ingestion: `prices{}` on slate rows with per-book timestamps, own 300 s cache, `flags.stale` beyond 15 min; `moneyline_line_snapshots(game_pk, book, side, american, captured_at, kind)`; closing capture at first pitch (`backend/closing.py`). `[A T19]`
58. `moneyline_candidate_picks(… side, verdict, signal, basis, price_used, book, price_captured_at, closing_price, clv_pts, model_version …)` with `UNIQUE(game_pk, side)` — a **separate table**, because `moneyline_record_picks` has unique `game_pk`. Graded at `price_used`; `clv_pts = implied(closing) − implied(price_used)`. `[A T20]`
59. Home-field adjustment as a **dated model version** (or a third graded price mirroring the ADJ experiment) — must be in place before the candidates record launches, or that record is biased toward road teams from pick one. `[S §16.1, A §3.3 D]`
60. `GET /api/status` — per-cache ages via a new `AsyncTTLCache.describe()`, `sources_up`, `updated_at`s, `model_version`. `[A T17]`

### Accounts (deferred)
61. `users`, `preferences`, `bankrolls`, `bets` tables; `GET/PUT /api/me/{preferences,bankroll}`, `POST/GET /api/me/bets`; local→server migration on first sign-in; tier gating and processor policy review. `[S P1 Page 4, A Phase 4]`

### Explicitly **not** to be built
62. Beginner/Advanced as modes; "Find an Edge" as a destination; an "Aggressive" profile; "Confidence" as a label; a featured/daily parlay; price-movement alerts; social proof; sportsbook links or affiliate revenue. `[S §17, A §6.9]`

---

## 3. THE GAP

### 3.1 Item-by-item status

Legend: **✅ exists** · **◐ partial** · **✗ absent**. Every ◐/✅ is cited against the current tree.

| # | v3 item | Status | Evidence / what's missing |
|---|---|---|---|
| 1 | News feed constants | **✗** | `RSS_URL` used at `backend/feeds.py:488`, `ESPN_NEWS_URL` at `:509` — **zero assignments** in the module (verified by regex over the file). `_espn_dead` is only assigned inside the function via `global` (`:506,530`), so the first read raises `NameError` too. `wire.get_wire`'s `safe()` swallows it into `sources_up.news=false`. **Still broken.** |
| 2 | `?date=` ledger guard | **✗** | `backend/main.py:601–618`: `if data.get("mode") == "live": store_slate_snapshot(data)` with no date or status check. `record_store.store_slate_snapshot` (`:67–74`) filters only `pricing_error` rows. `POST /api/record/snapshot` does not exist. **Still open.** |
| 3 | `MODEL_VERSION` constant + stamping | **✗** | Literal at `backend/main.py:443` and again at `artifacts/moneyline/src/components/status-strip.tsx:18`. No `model_version` column, no `MODEL_VERSION` symbol anywhere in `backend/`. |
| 4 | Single schema authority | **✗** | `lib/db` + `scripts/post-merge.sh` unchanged since the audit. |
| 5 | Always-on grading | **✗** | `.replit` `deploymentTarget = "autoscale"`; `grade_scheduler` still in-process (`main.py:313`). |
| 6 | Terminology dictionary | **✗** | No `src/lib/terminology.ts`; `src/lib/` holds only `game-status.ts`, `structured-data.ts`, `utils.ts`. Labels are hardcoded per component. |
| 7 | Copy pass | **◐** | Today/GameCard/Research/Track-record/Settings are already sentence case and plain-English (`today.tsx:33–37`, `game-card.tsx:102–106`). But `edge-finder.tsx:214–232` still renders `Model Edge`/`+4.5%` (points shown with a `%`), `B/E Rate`, `½ Kelly`; the raw API verdict strings render at `edge-finder.tsx:205`; `status-strip.tsx:39` still reads "Statistical research · not wagering advice". `slate-rail.tsx`, `screener.tsx`, `parlay-lab.tsx`, `season-desk.tsx`, `player-card.tsx` untouched. |
| 8 | Copy lint | **✗** | No `scripts/copy-lint.mjs`, no lint script. |
| 9 | Tokens + light theme | **◐** | New page-level classes exist (`page-wrap`, `game-card`, `data-tile`, `status-label-*`, `guide-pill`) so a token refresh has partly landed for the new surfaces. Not verified: whether `:root`/`.dark` are still a single palette, whether `--radius` moved off 0, and whether the verdict palette exists — **this is Lane 1/2 territory if they own `index.css`; flagged here as unresolved.** No `[data-theme="light"]`. |
| 10 | Type/density | **◐** | New surfaces use sentence-case headings and ≥12 px text; legacy panels still carry `text-[8px]/[9px]/[10px]` and `font-mono` on non-numeric text. |
| 11 | Motion/boot | **✗** | `TerminalBoot` still mounted globally (`App.tsx:212`); LIVE pulse dot still in the command bar. |
| 12 | A11y/mobile/PWA | **◐** | `aria-pressed` filters and `aria-labelledby` groups on Today (`today.tsx:147–159,170`); `data-testid` coverage is good. No bottom nav, no manifest, no service worker; `maximum-scale=1` in `index.html` not verified as removed. |
| 13 | Preference store | **◐** | **Shipped** — `components/presentation-preferences.tsx` with `localStorage`, try/catch on read (`:19–34`), sane defaults, and a Settings page (`tabs/settings.tsx`). **Gaps:** no `version` field (so the future account migration has no schema hook), the **write** at `:40` is *not* wrapped in try/catch (throws in private mode / storage-disabled browsers), and only 3 keys exist (`detailLevel`, `explainTerms`, `guideDismissed`) — no theme, time zone, or coach-mark flags. |
| 14 | "Detail level changes no number" | **◐** | True by construction today (`game-card.tsx:136,176` gate only *visibility*), but there is **no test** — no frontend test infrastructure exists at all. |
| 15 | GameCard three layers | **◐** | **Shipped** — `components/game-card.tsx`: answer (`:59–94`), explanation/context disclosure (`:137–173`), advanced numbers + receipts + embedded `EdgeFinder` (`:177–237`). **Missing:** `VerdictPill` (there is no verdict slot at all — only a "Model only" status label at `:98`), `ReasonList`, a fixtures file, and a `Disclosure` component (raw `<details>` is used). |
| 16 | Card contract (10 rules) | **◐** | Rules honoured: no edge/EV/stake without an entered price (`game-card.tsx:204`, `EdgeFinder deferUntilBookLine`), verdict frozen once live/final (`lib/game-status.ts:17–26`, rendered `:218–232`), no book links, no urgency, context labelled "does not move a price" (`:159`). **Violated / missing:** verdict is **one-sided** (still `/api/matchup` side-A only, `main.py:569`); no verdict at all pre-price; the disclaimer *is* collapsible-adjacent but present (`today.tsx:189`); no "how this is calculated" expanders. |
| 17 | One probability, named on the card | **◐** | The card shows the season probability in the answer layer (`game-card.tsx:80`) and the ADJ probability separately in the explanation layer (`:151`) — it never states **which** one anything downstream used, and `EdgeFinder` evaluates on the season chain. This is the specific honesty rule the audit added for this codebase, and it is unmet. |
| 18 | Risk row | **✗** | No "loses X% of the time", no payout shape, no volatility or uncertainty tags anywhere. |
| 19 | Signal strength | **✗** | Nothing computes it; σ undefined. Correctly blocked on prices. |
| 20 | Verdict pill + separate status chip row | **◐** | Status chips exist (`game-card.tsx:96–101`: "Model only", "Starter-adjusted available", "Starter data incomplete"). The verdict pill does not. |
| 21 | Today page | **◐** | **Shipped** at `/` (`tabs/today.tsx`, mounted `App.tsx:220` via `RootExperience:165`). Has: hero with live/historical status + `updated_at` (`:100–117`), historical-fallback notice (`:119`), welcome guide (`:126`), summary counts (`:139–144`), tappable group filters (`:147–160`), grouped card sections (`:168–186`), honesty footer (`:188–191`). **Missing:** date bar (no yesterday/tomorrow), data-status line naming sources and model version, right rail (record snapshot, context strip from `/api/wire`), sort control, and persistence of filter choice. |
| 22 | Readiness grouping | **◐** | Four groups exist (`today.tsx:32–37`): Ready to review / Needs attention / In progress / Final, via `groupFor` (`:24–30`) over `lib/game-status.ts`. The audit spec wants **five**: "starters not confirmed" and "pricing failed" are currently **collapsed into one** "Needs attention" bucket (`:28`), which merges a data-quality failure with a normal pre-game state. |
| 23 | Designed states | **◐** | Covered: historical fallback (`today.tsx:119`), feed down (`:59–63`), empty slate (`:162–166`), pricing failed (`game-card.tsx:87–91,103`), starters missing (`:100`), in-progress/final/postponed price-check refusals (`:218–232`). **Missing:** small-sample chip (nothing reads `games_played` — `useTeamsLive` is not wired into Today or GameCard), stale price, no-candidates state. |
| 24 | Today's exclusions | **✅** | No bet buttons, book links, countdowns, streaks, or social proof. Model slip already deleted (`grep "MODEL SLIP\|computeModelSlip"` → zero hits repo-wide). |
| 25 | Game detail `/game/{gamePk}` | **✗** | No route, no page, no endpoint. The card's advanced layer is the closest surrogate. |
| 26 | Share-card image endpoint | **✗** | H2H copies a URL only. |
| 27 | `model_detail` on slate rows | **✗** | `feeds._chain_probability` still discards the `predict_from_inputs` results; slate rows carry raw `away_inputs`/`home_inputs` but no predicted RS/RA or strength. Confirmed by `game-card.tsx:193–196`, which can only render raw OBP/SLG. |
| 28 | `backend/explain.py` | **✗** | Does not exist. `game-card.tsx` has no reason bullets — the closest is `adj_detail.method` echoed verbatim at `:170`. |
| 29 | Priced-only rule, test-enforced | **✗** | No explanation layer to test. The *display* separation is correct today (`game-card.tsx:157–168` isolates flags under "Context only · does not move a price"). |
| 30 | Standing limitations as chips | **✗** | `EQUITY_CAVEAT` (`main.py:87`) is returned by `/api/matchup` but never surfaced as "Home field: not priced" etc. |
| 31–34 | Verdict engine + `/api/evaluate` | **✗** | `backend/verdict.py` absent. The only verdict logic is `main.py:555–566`, one-sided, manual-line-only, four terminal strings. |
| 35 | Parlay Check reframe | **◐** | `tabs/parlay-lab.tsx` still the v2 lab (322 lines) at `/research/parlay`. Model slip removed ✅; verdict-first layout, house-cut bar, singles comparison, chance-of-losing not done. |
| 36 | Slip verdict rules | **✗** | Nothing computes a slip verdict; the page shows raw `ev_per_unit`/`stake_label` from `main.py:864–872`. |
| 37 | `POST /api/parlay/evaluate` | **✗** | Absent; `/api/parlay/price` has no per-leg lines and no `basis`. |
| 38 | Model slip removed | **✅** | Done. |
| 39–44 | Bankroll, stake, limits, gate, `/bankroll`, My bets | **✗** | No `/bankroll` route, no bankroll state, no 21+ gate, no helpline anywhere. `half_kelly_fraction` (`odds.py:49–56`) is still **uncapped** — its docstring says "capped" but it only floors at 0 — and it is exposed to the UI as `kelly_fraction` (`main.py:584`) and `half_kelly` (`:867`). |
| 45 | Four records, no shared numbers | **◐** | `/track-record` exists (`tabs/track-record-page.tsx`) composing `TrackRecordPanel` + `BankrollPanel` in one grid (`:30–33`) and `LiveRecordPanel` below (`:34`), with a "Public record" callout (`:26–29`). **Missing:** the *persistent* historical banner (the callout is one line at the top and scrolls away), and the historical simulation still sits in the same visual grid as the fit metrics. |
| 46 | 95% interval on units | **✗** | Not computed; `entries[]` has everything needed. Pure client arithmetic. |
| 47 | Live calibration buckets | **✗** | Not computed. Pure client arithmetic over `entries[].model_probability` + `result`. |
| 48 | "What this proves" + bets-needed explainer | **✗** | Absent. |
| 49 | Per-pick table + CSV + methodology + version footer | **◐** | `live-record.tsx` renders a ledger list with W/L/VOID/PENDING badges; no CSV export (the pattern exists in `screener.tsx`/`season-desk.tsx`), no methodology block, no real version footer. |
| 50 | Relabel the backtest | **◐** | `track-record-page.tsx:28` says "Historical backtests are simulations, not live performance" — the framing is right; the panel itself still reads "backtest". |
| 51 | Record segments/calibration/versions endpoints | **✗** | Absent (all three are additive and only needed once candidates exist). |
| 52 | Track Record as public entry | **◐** | It is in the nav (`command-bar.tsx:10`) and has JSON-LD (`lib/structured-data.ts`), but no card links to it and it is not the logged-out landing page. |
| 53–55 | Onboarding, coach marks, Learn | **◐** | A single dismissible `WelcomeGuide` banner exists (`presentation-preferences.tsx:50–71`) with the three right pills ("Probability = model estimate / Fair price = model translation / Book price = your manual input"). No 21+ gate, no price-slider demo, no coach marks, no `/research/learn` (the hub has 4 tiles, `research-hub.tsx:9–14`). |
| 56–58 | Odds provider, line snapshots, candidates record | **✗** | Blocked on a provider decision. |
| 59 | Home-field adjustment | **✗** | `odds.py:138–147` `log5_probability` is symmetric; `_chain_probability` takes no venue input. |
| 60 | `GET /api/status` | **✗** | The metadata exists (`slate.cache`, `wire.sources_up`, `updated_at`, `input_signature`) but no endpoint aggregates it. |
| 61 | Accounts | **✗** | None; correctly deferred. |
| 62 | Things not to build | **✅** | None of them present. |

### 3.2 What's missing, in dependency order

Each tier must be substantially complete before the next is honest or safe. **⚠ PRICE MATH** marks anything that reads, extends, or mutates `backend/odds.py` / `backend/analytics.py` and therefore needs `python smoke_test.py` green before *and* after, plus new fixtures.

---

**TIER 0 — Integrity. Nothing else should ship first.**
These are cheap, they are all still open, and every later tier writes to or cites the artefacts they protect.

| Order | Item | Why it's first | Price math |
|---|---|---|---|
| 0.1 | **`?date=` ledger guard** (item 2) — `store_slate_snapshot(slate, today)` returning `False` unless `slate["date"] == today (ET)`, skipping rows whose status ∉ {Scheduled, Pre-Game, Warmup}; add `POST /api/record/snapshot` | The record is the trust asset every later claim leans on. Today's UI can't trigger the hole, but nothing *prevents* it, and Tier 4's candidates record inherits the same write path. Also: `today.tsx` already exposes a refresh button and the audit wants a date bar — the moment a date bar ships, the hole becomes user-reachable. | No |
| 0.2 | **`MODEL_VERSION` constant + `model_version` column** (item 3) | Blocks item 59 (HFA) outright, and any verdict payload must carry it. Two literals to kill: `main.py:443`, `status-strip.tsx:18`. | No |
| 0.3 | **Single schema authority** (item 4) — drop `db push` from `post-merge.sh` | A `drizzle-kit push` can propose dropping the `adj_*`/`probables` columns the ledger depends on. Must land before 0.2 adds columns. | No |
| 0.4 | **Grading loop survives production** (item 5) — depends on 0.1's endpoint if the external-cron option is chosen | Missing ledger days are silent and unrecoverable. | No |
| 0.5 | **News feed constants** (item 1) | Trivial, independent, restores `/research/wire` and the context strip Today wants in item 21. | No |

**TIER 1 — Frontend truth on today's data. No backend dependency beyond Tier 0.**
Roughly half of this tier has shipped. What remains is ordered by what other frontend work consumes it.

| Order | Item | Depends on | Price math |
|---|---|---|---|
| 1.1 | **Terminology dictionary + `<Term>`** (item 6) | — | No |
| 1.2 | **Copy pass over the legacy components** (item 7) — `edge-finder.tsx` first (it is embedded in `GameCard`, so its `Model Edge +4.5%` / `B/E Rate` / `½ Kelly` labels are already on the new Today surface), then `slate-rail`, `parlay-lab`, `screener`, `season-desk`, `status-strip` | 1.1 | No |
| 1.3 | **Copy lint** (item 8) | 1.1 | No |
| 1.4 | **Preference store hardening** (item 13) — add `version: 1`, wrap the write at `presentation-preferences.tsx:40` in try/catch, add theme/tz/coachMarks keys | — | No |
| 1.5 | **Split "Needs attention"** (item 22) into *Starters not confirmed* and *Pricing failed* — `today.tsx:28` currently merges them; the predicates already exist (`isPartial`, `isMissingStarter`, `today.tsx:16–22`) | — | No |
| 1.6 | **Wire `useTeamsLive` into Today/GameCard for the sample chip** (item 23) — "Through N games", amber under 60 | — | No |
| 1.7 | **Track Record page completion** (items 45–50) — persistent historical banner, 95% interval, calibration buckets, "What this proves", per-pick CSV, methodology block, version footer (needs 0.2) | 0.2 for the footer | Reads `/api/record` only — **no** |
| 1.8 | **Today page completion** (item 21) — date bar (**must not ship before 0.1**), data-status line, right rail, sort control, filter persistence | 0.1, 0.5 (context strip), 1.4 | No |
| 1.9 | **Tokens, type scale, motion, light theme** (items 9–11) | 1.1 for label sizes | No |
| 1.10 | **A11y / mobile shell / PWA** (item 12) | 1.9 | No |
| 1.11 | **Frontend test infrastructure** (Vitest + Testing Library) — required by item 14's "no number changes" assertion and by every card fixture in item 15 | — | No |

**TIER 2 — Backend explanation + evaluation. Parallel with Tier 1, gated on Tier 0.2.**
This is where the card stops being a data dump and starts answering. It is also the first tier that touches price math.

| Order | Item | Depends on | Price math |
|---|---|---|---|
| 2.1 | **`model_detail` on slate rows** (item 27) — refactor `feeds._chain_probability` to *return* the `predict_from_inputs` results and Pythagorean strengths it currently throws away, rather than recomputing | — | **⚠ PRICE MATH (indirect but real).** This is a refactor of the live pricing path itself. It must not change a single output digit: `_chain_probability` feeds `_price_game` → `model_prob_home` → `fair_lines` → the ledger. Gate: `python smoke_test.py` green, plus a byte-identical `/api/slate` payload diff on a fixture before/after. `pythagorean_strength` and `log5_probability` (`odds.py:131–147`) must not be edited. |
| 2.2 | **`backend/explain.py`** (items 28–30) + `ReasonList` | 2.1 | **⚠ PRICE MATH (read-only).** Ranks bullets by run contribution converted through `analytics.runs_per_win()` (`analytics.py:49`). Read-only use, but a wrong conversion produces confidently wrong prose. Needs the ten golden fixtures. |
| 2.3 | **`backend/verdict.py` + `POST /api/evaluate`** (items 31–34) | 0.2 (version in payload), 2.2 for `reasons.review` | **⚠⚠ PRICE MATH — highest-risk non-model change.** Composes `moneyline_to_probability`, `decimal_odds`, `edge_probability`, `market_vig` from `odds.py`. Must be **additive only** — `odds.py` functions unchanged, `/api/matchup` shape and its four terminal strings unchanged (`main.py:555–566`), thresholds published and versioned. The ten Appendix A fixtures (item 33) are the gate. Note the one-sidedness bug this fixes: with a slate game selected, `EdgeFinder` evaluates **away only**, so a favourable home price is invisible today. |
| 2.4 | **`VerdictPill` + two-slot card head** (items 16, 20) — replaces the double-`/api/matchup` workaround | 2.3, 1.1 | No |
| 2.5 | **Risk row** (item 18) | 2.3 | Client-side arithmetic mirroring `odds.py` — **⚠ mirror must be fixture-tested against the server** |
| 2.6 | **Same-probability rule** (item 17) — the card names the basis it used, and everything downstream uses it | 2.3 | No, but it is a correctness rule the evaluator must enforce |
| 2.7 | **Parlay Check reframe** (items 35–36) — client-side verdict from `book.ev_per_unit` | 1.1, 1.2 | No (reads existing `vig_comparison`) |
| 2.8 | **`POST /api/parlay/evaluate`** (item 37) + **`POST /api/stake`** (item 41) + **`GET /api/status`** (item 60) | 2.3 for thresholds | **⚠ PRICE MATH.** `parlay/evaluate` adds per-leg EV using `odds.py` parlay functions; `stake` is the de-vig + shrinkage + cap chain. `/api/parlay/price` must stay byte-compatible. Fixtures: $9/$18/$27 (item 40) and the two worked slips (item 36). |
| 2.9 | **Game detail `/game/{gamePk}`** (item 25) | 2.1–2.3 | No |

**TIER 3 — Local money surfaces. Gated on 2.3 + 2.8, and on the Kelly cap.**

| Order | Item | Depends on | Price math |
|---|---|---|---|
| 3.1 | **Cap and shrink the exposed Kelly** (item 42) — display layer first | — | **⚠⚠ PRICE MATH.** `odds.py:49–56` `half_kelly_fraction` is uncapped despite its docstring. The audit's position is that this number is already advice-shaped on screen. Two safe options: (a) cap in the display layer only, leaving `odds.py` untouched and `smoke_test.py` unaffected; (b) add a *new* capped function and leave the old one for the smoke test. **Do not change the existing function's return values** — `smoke_test.py` asserts on them. |
| 3.2 | **21+ gate + helpline footer** (item 43) | — | No |
| 3.3 | **Local bankroll + stake card + limits + cooling-off** (items 39–40, 43) | 3.1, 2.8, 1.4 | **⚠ PRICE MATH.** `src/lib/odds.ts` will be a client port of `moneyline_to_probability` / `decimal_odds` / Kelly / de-vig. It must be contract-tested against the server fixtures, or the same bet gets two stakes. |
| 3.4 | **`/bankroll` page** (item 44, log/CLV parts deferred) | 3.3 | No |
| 3.5 | **Onboarding, coach marks, Learn hub** (items 53–55) — the price-slider demo needs 2.3 to walk Avoid → Candidate correctly | 2.3, 1.1, 3.2 | Slider uses the evaluator — **⚠ read-only** |

**TIER 4 — Prices. Blocked on an external decision, not on engineering.**

| Order | Item | Depends on | Price math |
|---|---|---|---|
| 4.0 | **Provider decision + legal review** — the single largest gate in the plan | — | — |
| 4.1 | **Odds-provider spike** (item 56) | 4.0 | No |
| 4.2 | **Home-field adjustment as a dated version** (item 59) | 0.2 | **⚠⚠⚠ HIGHEST RISK.** This is a change to `odds.py:138–147` `log5_probability` or to `feeds._chain_probability`'s use of it. It changes every price the product has ever quoted and splits the ledger. The audit's recommendation stands: version registry first, then run it as a **third graded price** for a month mirroring the ADJ experiment, then fold in as v2 with the record split by version. **Must land before 4.4**, or the candidates record is biased toward road teams from its first pick. |
| 4.3 | **Ingestion + `line_snapshots` + prices on rows + stale flags** (item 57) | 4.1, 2.3 | **⚠ PRICE MATH** — evaluator now runs on real prices; the leans record must stay untouched |
| 4.4 | **Candidates record + CLV** (item 58) | 4.2, 4.3, 0.1 | **⚠ PRICE MATH** — grading at `price_used`, `clv_pts = implied(closing) − implied(price_used)` |
| 4.5 | **Verdict grouping on Today, summary verdict counts, `/api/record?segment=`** (items 22, 51) | 4.3, 4.4 | No |
| 4.6 | **Share cards** (item 26), notifications, multi-book UI | 4.3 | No |

**TIER 5 — Accounts** (item 61). Gated on an auth decision; every Tier 3 surface was built local-first with migration in mind, so this is mechanical if 1.4's `version` field lands.

### 3.3 Everything that touches price math, in one list

For Lane 1 / whoever owns verification:

| Work item | File(s) | Nature | Gate |
|---|---|---|---|
| 2.1 `model_detail` | `feeds.py::_chain_probability`, `_price_game` | Refactor of the live pricing path | `smoke_test.py` + byte-identical `/api/slate` fixture diff |
| 2.2 explanation ranking | `analytics.py::runs_per_win` (read) | Read-only | 10 golden fixtures |
| 2.3 verdict engine | new `backend/verdict.py` composing `odds.py` | Additive; `odds.py` unchanged | 10 Appendix A fixtures + `smoke_test.py` |
| 2.5 client risk mirror | new `src/lib/odds.ts` | Duplicate of server math | Contract test vs server fixtures |
| 2.8 stake + parlay evaluate | new `backend/stake.py`, `odds.py` parlay fns | Additive | $9/$18/$27 fixture; two worked slips; `/api/parlay/price` unchanged |
| 3.1 Kelly cap | `odds.py:49–56` `half_kelly_fraction` | **Do not mutate** — cap in display or add a new function | `smoke_test.py` asserts current values |
| 4.2 home-field | `odds.py:138–147` `log5_probability` | **Mutation of the core pricing formula** | Version registry first; third-graded-price experiment; ledger split by version |
| 4.4 CLV | `odds.py::moneyline_to_probability` (read) | Read-only | Sign convention documented and tested |
| — | `probability_to_moneyline` nearest-5 rounding (`odds.py:8`) | **Leave as is.** The audit (§10.1) recommends keeping the nearest-5 rule for displayed prices and showing the unrounded value in the numbers layer. Changing the rounding changes `fair_line` in every stored pick. | — |

---

## 4. Dead ends

**Backend routes with no frontend consumer:** none. All 22 `/api/*` routes are reachable from at least one mounted component; `/sitemap.xml` is intentionally crawler-only (`main.py:1106`, `serve_spa.py:97`).

**Frontend calls to endpoints that don't exist:** none. Every `api.ts` hook maps to a live route, and there are no raw `fetch('/api/…')` calls outside `api.ts` (verified by grep across `*.ts`/`*.tsx`).

**Genuinely dead or orphaned surfaces found:**

1. **`/desk` is the only home for three panels.** `ScreenerPanel` (`/api/screener`), `BaParadoxPanel` (`/api/ba-paradox`), `PricerPanel` (`/api/team/{team}/{year}`, `/api/price`) and `SlateRail` are mounted **only** in `tabs/desk.tsx`. Both docs move them to `/research/teams` (Team strength, Screener) and `/research/learn` (BA paradox); neither route exists, so if `/desk` is retired on schedule, three endpoints lose their only consumer. The Research hub currently offers four tiles — Players, Matchups, Season outlook, Wire (`research-hub.tsx:9–14`) — with **no Teams & Season and no Learn**.

2. **`/` is dual-purpose and undocumented.** `RootExperience` (`App.tsx:165–171`) renders `DeskTab` when `?team` or `?year` is present and `TodayTab` otherwise. This preserves old share links, but neither doc describes it, and it means the default route silently renders a completely different page depending on a query string.

3. **Keyboard shortcuts point at the old world.** `LEGACY_SHORTCUTS` (`command-bar.tsx:17–23`) still binds `1–6` to `/desk`, `/research/players`, `/research/matchups`, `/research/parlay`, `/research/season`, `/research/wire` — i.e. `1` does **not** go to Today, and no key reaches `/track-record` or `/settings`. Both docs specify `1–5` over the primary destinations.

4. **Route naming diverges from both docs.** Shipped: `/track-record` and `/research/parlay`. Both docs specify `/record` and `/parlay` (audit §8.2 explicitly says "Keep path; rename page" for `/parlay`). `/parlay` currently *redirects away* to `/research/parlay`, and Parlay Check is meant to be a **primary** destination, not a Research child. Deciding this now is cheap; deciding it after `/track-record` is the marketing entry point is not.

5. **`hooks/use-mobile.tsx`** (`useIsMobile`, 768 px) is still consumed only by the unused `components/ui/sidebar.tsx`. It is the hook the bottom-nav work (item 12) needs.

6. **`lib/api-client-react`** remains a workspace dependency of the frontend and is imported nowhere in `artifacts/moneyline/src`; the app talks to the API exclusively through `src/api.ts`.

7. **`artifacts/api-server/` is an Express scaffold that runs Python.** Its `start` script is `NODE_ENV=production python -m backend.main`. Not a bug, but a trap for anyone reading `src/app.ts` expecting the API.

8. **`EQUITY_CAVEAT`** (`main.py:87`) is returned by `/api/matchup` and rendered nowhere in the new card. It is the exact source text item 30 needs for the "not priced" chips.

---

## 5. Three things worth a decision now

1. **The Phase 0 defects are still open while Phase 1 UI has shipped.** The build order inverted relative to both docs' recommendations. The `?date=` hole (0.1) is the one that matters: the Today page's date bar is the next obvious feature, and it turns an API-only hole into a user-reachable one.
2. **The card has no verdict slot.** Everything else about `GameCard` matches the spec, but the one structural element the spec is built around — a verdict pill with a separate data-status chip row — is absent, and `EdgeFinder`'s one-sided `/api/matchup` verdict is what fills the space today. That is the "lean is not the value side" failure the strategy warns about, live in the product.
3. **Route names (`/track-record`, `/research/parlay`) diverge from both documents** before either was ratified. Worth settling before Track Record becomes the public entry point (item 52).
