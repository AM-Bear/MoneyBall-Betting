# MONEYLINE — v4 Build Plan

Written 2026-08-24, downstream of `notes/v4-improvement-catalog.md` and the ruling that the
original keyless-data / no-market-prices doctrine is scratched. MONEYLINE is repositioning
from a sports-research product to a **gambler's product**.

This file supersedes `notes/v3-plan.md` for *sequencing*. `v3-plan.md` remains authoritative
for what is broken and what is verified healthy in the existing tree — read it first.

**Doc discipline, inherited from `v3-plan.md` and learned the hard way:** a status line in
this file is a claim, not evidence. Verify against code before acting on any ✅.

---

## The one-paragraph version

Six phases. The ordering is driven by a single constraint: **nothing that recommends a bet
ships before something can measure whether the recommendation was any good.** Phase 1 buys
market contact almost for free from data the UI already collects. Phase 2 builds the
measurement harness, and it is the gate on everything after it. Phase 3 fixes the four
structural model errors. Phase 4 builds the betting workflow. Phase 5 buys real odds and
ships the screener. Phase 6 is LLM surface and growth. Phases 1 and 4 can run alongside 2
and 3 — they touch different code and neither depends on model work.

---

## Task 0 — Correct the doctrine documents (do before anything else)

**Effort: S. Blocking.** `notes/build-history/replit.md` and `CLAUDE.md` still state the doctrine this plan
supersedes:

- `notes/build-history/replit.md` — *"Keyless data only: MLB Stats API + MLB RSS ... no salary data served"*
- `notes/build-history/replit.md` — *"Media pulse and injury flags are disclosed context only; they NEVER move
  a price (doctrine)"*
- `CLAUDE.md` — inherits both by reference

Until these are updated, a fresh Claude session reads the old rules and enforces them
against this plan. Rewrite both to state the new position, and state explicitly which parts
of the old doctrine **survive**, because most of it does:

- Calibration, the graded record, and refusals stay — as competitive assets, not principles.
- Receipts on derived numbers stay. No hardcoded coefficients stays.
- What is scratched is data purity: odds feeds, third-party sources, and context signals
  moving prices are all now in scope.

Also update: the price-math verification rule in `CLAUDE.md` still requires a byte-identical
`/api/price` diff. Phase 3 deliberately moves prices. Replace "prove no number moved" with
"prove the number moved *only* where intended, and land it as a graded challenger first."

---

## Phase 1 — Market contact for free

**Goal: make the product know what a book thinks, using only what the UI already collects.**
No vendor, no spend, no new dependency. Highest value-per-line-of-code in the plan.

| # | Task | From | Effort | Notes |
|---|---|---|---|---|
| 1.1 | **Persist `entered_line`** | M1 | S | The user already types it (`game-card.tsx:264`); the grading path already reads it (`record_store.py:357,369`); nothing writes it. One column on insert. **2026-09-02:** no insert to attach to — pick rows come from `store_slate_snapshot` (server-side, before any price is typed) and the typed price only reaches `/api/evaluate`; A (write onto the shared row) vs C (pull 4.2 forward): **Asher chose C, 2026-09-02** — built as `moneyline_bets` (user_id + game_pk, `line_home`/`line_away`, `entered_at`, `model_version`), `PUT /api/bets/{game_pk}`, card writes on blur; `moneyline_record_picks` untouched (tested byte-identical). **Clearing, Asher 2026-09-02:** an emptied input clears that side (explicit `null`; an absent side keeps); a row with both sides cleared is deleted — a cleared line is not a bet. 1.5 reads from here. |
| 1.2 | **De-vig both entered prices** | M2 | S | `novig_home = implied_home/(implied_home+implied_away)`. One line over three tested functions (`odds.py:21-25`, `:33-39`). **2026-09-02:** done in code at c083645 (`no_vig_probabilities`, `no_vig_edge`, `tests/test_no_vig.py`), verified; surfacing is 1.3/1.4. |
| 1.3 | **True edge vs no-vig, in the verdict** | M2 | M | `verdict.py:331` already receives `price_home` and `price_away` and does not use them together. Vigged-price edge understates every favourite edge. |
| 1.4 | **Show hold % per game** | M2 | S | "Your book charges 5.2% here." Free, and immediately legible as a bettor's tool. |
| 1.5 | **Closing-line entry + CLV** | M3 | M | The metric that converges fast enough to be meaningful. ⛓ 1.1 |
| 1.6 | **Store the full price series** | D2 | S | Today one snapshot per date. Line movement (M4) and honest freshness need timestamps. |

**Verification:** `python smoke_test.py` green, `python -m pytest -q` no new failures,
`pnpm typecheck` green. 1.3 changes verdict output — add fixtures to
`tests/test_verdict_engine.py` and hand-checked cases to `verified_stats.json`.
1.1 touches the ledger: rows already graded at −110 stay at −110, marked as a distinct era
via `model_version`. **Never rewrite existing rows** (`notes/build-history/replit.md` gotcha).

**Ships:** a product that can say "you are getting −135; the no-vig market says 56.1%; the
model says 58.4%; that is a 2.3-point edge" — with no odds vendor.

---

## Phase 2 — Measurement (the gate)

**Goal: be able to answer "did that change help?" Nothing in Phase 3 or the Phase 5 screener
may ship before this exists.**

| # | Task | From | Effort | Notes |
|---|---|---|---|---|
| 2.1 | **Historical game database** | D1 | L | Retrosheet/Lahman + MLB Stats API. **Point-in-time** team stats as of each game date. End-of-season stats leak the future and produce fictional edges — this is the step most sports backtests get wrong. |
| 2.2 | **Game-level backtest harness** | A2/B1 | L | Walk-forward by season. **Log loss and Brier, never hit rate.** Today `/api/backtest` (`main.py:1040`) serves a static file backtesting the *season* models, not game prices. |
| 2.3 | **Calibration + reliability curves** | B2 | M | Turn the existing Track Record machinery (`components/record/`) inward onto model development. Kelly consumes probability directly, so miscalibration mis-sizes every bet. |
| 2.4 | **Champion–challenger registry** | B3 | M | N bundles, each `MODEL_VERSION`-stamped, each priced and graded independently, leaderboard on log loss / calibration / CLV / units. `MODEL_VERSION` and `model_version` columns already exist — this is a shorter step than it looks. |
| 2.5 | **Drift + accuracy observability** | B8/D4 | M | Rolling log loss and calibration drift in production, with alerts. |

**Verification:** 2.2's own correctness is the deliverable — it needs a known-answer test
(a deliberately biased synthetic model must score worse than an unbiased one). A backtest
harness nobody has tested is worse than none, because it will be believed.

**Gate:** 2.4 must land before any Phase 3 item touches a live price.

---

## Phase 3 — Fix the model

**Goal: close the four structural errors from catalog §0.2.** Every item lands as a graded
challenger under 2.4 first, and is promoted to the headline price only on evidence.

Ordered by lift per effort:

| # | Task | From | Effort | Notes |
|---|---|---|---|---|
| 3.1 | **Home-field advantage** | A1 | M | `log5_probability` (`odds.py:138-146`) is symmetric. ~4 points of probability, biased against every home side, on every price ever quoted. Fit δ, don't hardcode it. |
| 3.2 | **Injuries and scratches move the price** | A0 | M | Newly unlocked. `get_injury_flags` (`feeds.py:1014`) already fetches; `_blended_side` (`feeds.py:862`) already recomputes. Only the trigger is missing. Keep the disclosure as a receipt line. ⛓ 3.0 below |
| 3.0 | **Fix the feed bugs A0 depends on** | D6 | S | **Do this before 3.2.** `get_transactions` sends no `sportId` (`feeds.py:787`) → phantom MiLB codes; pulse lexicon double-counts and `_matches` (`analytics.py:282-285`) matches "torn" inside "tornado". Display bugs today; *correctness* bugs the moment they move money. |
| 3.3 | **Shrinkage on early-season rates** | A6 | M | Empirical Bayes toward the league mean, `k` fit not guessed. Replaces the binary `gp_hard_floor` gate (`verdict.py:117`) with the continuous correct version. Makes the model more honest *and* more useful. |
| 3.4 | **Park factors** | A5 | M | Two corrections — neutralize inputs, then re-inflate for venue. Doing only the second double-counts. Essential prerequisite for totals. |
| 3.5 | **Refit RA off 90 rows** | A3 | M | `precompute.py:158` trains the run-prevention half of every price on 1999–2001, 90 team-seasons. |
| 3.6 | **Modern-era challenger bundle** | A4 | M | `classic-1962-2001` stays as the story and teaching artifact; `modern-2012-2025` prices the bets. Let the ledger decide. ⛓ 2.4 |
| 3.7 | **Uncertainty intervals** | B4 | M | Feeds bet sizing — uncertainty must shrink stakes, and today nothing does. Replaces the tuned `_uncertainty` heuristic with a derived posterior. |
| 3.8 | **Bullpen modelling** | A7 | L | The pen throws ~40% of innings, is currently charged at a team average that *includes the starter*, and varies more between teams over one game than rotations do. |
| 3.9 | **Statcast inputs** | A12 | L | xwOBA/barrel rate stabilize fast — partial substitute for 3.3 in April. Newly unlocked. |
| 3.10 | **Pythagenpat** | A10 | S | Cheap. Moves the 2002 A's chain that `smoke_test` pins — needs a hand-checked replacement in `verified_stats.json`. |
| 3.11 | Real lineups → platoons | A8/A9 | L | Creates a two-tier price; the ledger must record which tier it graded. |
| 3.12 | Weather / umpire / travel | A13 | M | **Only with a pre-registered hypothesis under 2.2.** These are small effects on small samples and all of them look significant if you go looking. |

**Verification for every item:** `smoke_test.py`, `pytest -q`, `pnpm typecheck`. Price math
additionally requires the 2.2 backtest showing improvement on held-out seasons, and a
`/api/price` diff proving the number moved *only* where intended — the byte-identical rule in
`CLAUDE.md` no longer applies here and must be rewritten (Task 0).

---

## Phase 4 — The betting workflow

**Goal: close Gap 4. A bettor's day is check → shop → size → place → log → watch → review;
the product covers step one.** Independent of Phases 2–3; can run in parallel.

| # | Task | From | Effort | Notes |
|---|---|---|---|---|
| 4.1 | **Cap the Kelly stake** ⚠️ | S4 | S | `half_kelly_fraction` (`odds.py:49-56`) is **uncapped despite its docstring**. A display curiosity under the old doctrine; a safety defect in a product telling people how much to risk. Cap in the display layer (1–2% of bankroll), visible and adjustable. Do **not** mutate `odds.py` — `smoke_test` asserts current behaviour. |
| 4.2 | **Bet slip / one-tap logging** | S1 | M | New `moneyline_bets` table keyed to `user_id`. **Separate from `moneyline_picks`** — the model's record must not be contaminated by user behaviour. |
| 4.3 | **Bankroll management** | S3 | M | Balance, drawdown, ROI, stakes sized off real balance not abstract units. `bankroll-backtest.tsx` is a marketing artifact, not a tool. |
| 4.4 | **Alerts: push + email** | S7 | M | Scratches (⛓ 3.2), lineups, line thresholds, edge thresholds, bet graded. Largest retention lever in the category. `backend/mailer.py` exists. |
| 4.5 | **Rebuild the screener as the primary surface** | S8 | M | `screener.tsx` is mounted only in `tabs/desk.tsx`, which `v3-plan.md` schedules for retirement. Filter by edge, Kelly, uncertainty, starters-confirmed, book. |
| 4.6 | **My record vs the model's record** | S2 | M | ⛓ 4.2. The most interesting screen in the product, and almost nobody does it well. |
| 4.7 | **PWA + mobile** | S9 | L | Betting happens on a phone before first pitch. PWA over native: installable, push-capable, no App Store gambling review (§6.4). |
| 4.8 | **Surface debt** | §3.3 | S | Keyboard `1`–`6` still binds the old tabs; `EQUITY_CAVEAT` renders nowhere; route names diverge from docs; **two `test_serve_spa.py` failures have been red throughout** — fix that first, a permanently-red suite is the same as no suite. |

---

## Phase 5 — Real odds

**Goal: line shopping, +EV screening, steam. The first phase that costs money and adds an
external dependency.**

| # | Task | From | Effort | Notes |
|---|---|---|---|---|
| 5.1 | **Odds vendor decision + integration** | M5 | L | Start with The Odds API (~$30–200/mo). **Pinnacle's no-vig line is the benchmark, not another shopping option** — beating Pinnacle's close is the real test. |
| 5.2 | **Feed resilience** | D3 | M | Reuse the `FEED_DEADLINE_SECONDS` pattern from `c565770`. **Critical difference: a stale odds price must fail loudly, not serve quietly.** Stale stats degrade a price; a stale odds line recommends a bet at a number that no longer exists. |
| 5.3 | **"My books" configuration** | S6 | S | State-dependent. Line shopping is noise without it. |
| 5.4 | **Line shopping** | M6 | M | The #1 reason people pay for OddsJam. Worth more than most model edges: −105 vs −115 is ~2.3% of EV. |
| 5.5 | **+EV screener** 🔒 | M7 | M | **GATED ON PHASE 2.** A screener on an unvalidated model is a machine for losing money confidently. This is the most important gate in the plan. |
| 5.6 | **Line movement history** | M4 | M | ⛓ 1.6. "Model had it at −128 this morning; market opened −115, closed −135" is the most persuasive artifact this product could produce. |
| 5.7 | **Grade against the closing line** | T1 | M | Replaces "we grade at −110" with something strictly stronger. Nobody can fake CLV. |
| 5.8 | **Steam / RLM detection** | M8 | M | RLM needs public ticket/handle %, a separate purchase. |
| 5.9 | **Cost controls** | D5 | S | Two metered dependencies arrive at once (odds + LLM). Per-user accounting, caching, rate limits by tier, or the $19 plan's unit economics invert. |
| 5.10 | Arbitrage / middles | M9 | M | Converts trials; warn honestly about account limiting. |

---

## Phase 6 — Surface, trust, and growth

| # | Task | From | Effort | Notes |
|---|---|---|---|---|
| 6.1 | **`explain.py` + `model_detail`** | C1 | M | The deterministic core. v3 Tier 3 item 4, never started; design already exists in `notes/explain-design.md`. With 3.2 shipped the key bullet becomes *"−1.8 pts: Cole scratched."* |
| 6.2 | **LLM number validator** | Lane C | S | **Before any generated prose ships.** Extract every numeral, assert each appears in the source payload, fall back to deterministic text. Two hours; protects the only asset the product has. |
| 6.3 | **Reason bullets, generated** | C1 | S | ⛓ 6.1 + 6.2. |
| 6.4 | **Daily brief** | C4 | M | Best answer to "why open this every day?" |
| 6.5 | **Chat with the desk** | C2 | L | Tool-use over the 29 existing routes. The natural Pro-tier feature; gated by `has_feature`. |
| 6.6 | **News classifier** | C3 | M | Replaces the "torn"/"tornado" lexicon. With 3.2, upgrades from decoration to a timing edge — needs a confidence floor below which it discloses rather than prices. |
| 6.7 | **Tamper-evident ledger** | T2 | M | Daily chained hash. Every tout claims a record; this one can be verified. |
| 6.8 | **Segment the record** | T3 | M | By edge bucket, favourite/dog, home/away, month, model version. Will produce unflattering slices; publishing them is the point. |
| 6.9 | **Free calculator tools** | §6.3 | S | No-vig, Kelly, parlay EV, hold. Trivial given `odds.py`, and they rank. |
| 6.10 | **SEO targets** | §6.3 | S | `notes/build-history/seo_strategy.md` lists primary keywords as "Unknown". |
| 6.11 | **Repricing the tiers** | §6.1 | M | ⛓ Phase 2. Current tiers split by research surface, not betting value. `parlay` is a 🎲 feature sitting in the top 🎯 tier. **The backtest is a pricing decision.** |

---

## Decisions needed from Asher

**All six answered by Asher on 2026-09-02.** The answer is stated first; the original framing
follows it so the reasoning survives.

1. **Sharp, with a recreational on-ramp.** *(catalog §0.4)* As recommended. The most consequential
   product decision, and it changes the priority of roughly half this plan: MONEYLINE's existing
   assets — the verifiable ledger, calibration, refusals — are worth nothing to a recreational
   bettor and a great deal to a sharp one.
2. **Stripe: research first; no marketing copy change until Stripe answers in writing.** ⚠️
   Billing shipped at `49ad107`. Stripe restricts gambling-related businesses and handicapping sits
   in a grey zone; enforcement arrives as a frozen account, not a warning. The finding, the copy
   constraints it implies, and a ready-to-send support question are in
   `notes/stripe-classification.md`, which is **gitignored on purpose — this repo is public and
   preparation for a conversation with Stripe should not be published to Stripe**; Asher sends the
   question himself. Cheapest item on this list and the
   highest-probability way the repositioning hurts.
3. **No affiliate revenue.** *(catalog §6.2)* It is how this category actually makes money, and it
   conflicts directly with honest line-shopping rankings — which are the product's whole claim.
   **This constrains M6:** book comparison ships neutral, with no affiliate links.
4. **No odds vendor yet.** $30/mo validates the thesis and four figures/mo runs it properly, but
   nothing is spent until Phase 2 can measure whether the feed pays for itself. Revisit when the
   backtest harness and calibration curves exist.
5. **The classic 1962–2001 fit stays the headline model.** As recommended: keep it as the story and
   the teaching artifact, run the modern bundle as a graded challenger under 2.4, and let the
   ledger decide (3.6).
6. **ESPN host swap: go ahead — decided 2026-09-02, build after the commit.** The doctrine
   objection was the only argument against it and that doctrine is scratched (Task 0). Not built in
   the 2026-09-02 sessions: the working tree already carries a full commit's worth of review
   surface for a public repo, so this lands in the session after Asher commits, alongside 1.5.

---

## Explicitly deferred

- **Live / in-game betting** (S10) — XL, a genuinely different engineering problem, and it
  would consume everything. Not before pregame is proven.
- **Player props** (M10) — where the soft markets are, and a completely different modelling
  problem. After totals and F5.
- **Multi-sport** (Part VII) — but make the two cheap decisions now: carry a `sport` key in
  the ledger, model registry, and odds tables from the start, and keep sport-specific
  modelling behind the existing `strength → log5 → price` interface.
- **Native mobile apps** — PWA first (4.7).
- **Catcher framing, baserunning, sequencing** (A14).

---

## Standing rules for every phase

Inherited from `CLAUDE.md`, with the one amendment Task 0 covers:

- `python smoke_test.py` green and `python -m pytest -q` with no new failures, before *and*
  after every backend change. `pnpm typecheck` green if any TS changed.
- New formulas need a hand-checked case in `verified_stats.json`. Green tests prove no
  regression against known values; they do not prove new math is right.
- Price-math changes need the Phase 2 backtest showing improvement on held-out seasons, plus
  a `/api/price` diff proving the number moved only where intended.
- Ledger migrations stay `IF NOT EXISTS`; never rewrite existing rows.
- Deploy preconditions unchanged: green tests, committed tree, no peer session mid-edit.
- **Never invoke Replit Agent or Assistant.** `publish_app` is the Deploy button and is fine.

## The single most important line in this plan

**Task 5.5 is gated on Phase 2.** A +EV screener on a model that has never been backtested is
a machine for confidently losing other people's money, and it is precisely the product this
codebase was originally built in opposition to. Scratching the data doctrine does not scratch
that.
