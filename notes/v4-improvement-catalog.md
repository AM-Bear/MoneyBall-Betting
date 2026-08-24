# MONEYLINE — v4 Improvement Catalog

**A gambler's product.** Written 2026-08-24, after the ruling that the original
"keyless data / no market prices / context never moves a price" doctrine is scratched.

This is a deliberately exhaustive ideation pass. It optimizes for coverage, not sequencing.
The ranked, dependency-ordered build plan is `notes/v4-plan.md`.

Companion reading: `notes/v3-plan.md` (what is broken, what is verified healthy),
`notes/map-model.md` (the price chain formula by formula), `notes/map-data.md`,
`notes/map-surface.md`.

> ⚠️ **`replit.md` and `CLAUDE.md` are now out of date.** Both still state the doctrine
> this document supersedes — "keyless data only", "media pulse and injury flags NEVER move
> a price", "no salary data served". Updating them is task 0 in the plan; until then, a
> fresh session will read the old rules and enforce them.

---

## How to read this document

| Mark | Meaning |
|---|---|
| **Lift 1–5** | How much this improves the product *for a bettor*. 5 = changes what MONEYLINE is. |
| **Effort S/M/L/XL** | S = a session. M = a few days. L = a couple weeks. XL = its own spec. |
| **🎯 Sharp** / **🎲 Rec** | Which customer it serves. These are different products; see Part 0. |
| **⛓ Needs** | Hard dependency that must ship first. |

---

# Part 0 — Thesis

## 0.1 What the product is today

MONEYLINE prices MLB games with a season-long team-rate model fit on 1962–2001 data, and
it does not know what any sportsbook thinks:

```
OBP, SLG        → RS       (linear, fit on 902 team-seasons ≤ 2001)   precompute.py:154
OOBP, OSLG      → RA       (linear, fit on  90 team-seasons 1999–01)  precompute.py:158
RS, RA          → strength (Pythagorean, exponent hardcoded 2)        odds.py:131-135
S_a, S_b        → p        (log5, no home-field term)                 odds.py:138-146
p               → line     (American, snapped to nearest 5)           odds.py:8-18
```

Around that sits an unusually good honesty apparatus: a graded pick and parlay ledger with
model-version stamping, Wilson intervals, calibration buckets, a verdict engine that names
the value side and refuses when it can't (`verdict.py:331`), and provable receipts on every
coefficient.

**That is a sports-research product with a betting-shaped UI.** The gap to a gambler's
product is not a skin. It is four things:

## 0.2 The four gaps

**Gap 1 — No market.** The product cannot compute the only number a bettor actually needs:
*edge versus the price you can get*. It computes edge versus its own opinion. Zero
sportsbook references exist in `backend/`.

**Gap 2 — The model is not sharp enough to beat a market it can't see.** Four structural
problems, none of them bugs:

1. **No home-field advantage.** `log5_probability` is symmetric. MLB home teams win ~53–54%.
   Every price MONEYLINE has ever quoted is biased against the home side by roughly four
   points of win probability. This is the largest known error in the system.
2. **Half the chain is fit on 90 rows.** `precompute.py:158` trains opponent-rates → RA on
   `Year ≤ 2001` after dropping nulls, and `baseball.csv` carries OOBP/OSLG only from 1999.
   Three seasons, ninety team-seasons, setting the run-prevention half of every price.
3. **No park, bullpen, lineup, platoon, defense, or weather.** Coors and Petco are the same
   building to this model. The ADJ path blends one starting pitcher's opponent rates
   (`analytics.py:191-213`) and stops; the bullpen throws ~40% of innings and is invisible.
4. **Season rates consumed as truth.** A team 18 games in with a .360 OBP is not a .360 OBP
   team. The verdict engine handles this with a binary games-played gate
   (`verdict.py:117`); the correct answer is continuous shrinkage, which exists nowhere.

**Gap 3 — Nothing can measure whether a change helped.** `/api/backtest` (`main.py:1040`)
serves `static_json("backtest.json")` built by `precompute._backtest` (`precompute.py:76`),
which backtests the *wins* and *playoff* models on team-seasons. **No game price has ever
been backtested.** There is no evidence the model beats a coin, let alone a book.

**Gap 4 — The product has no workflow.** A bettor's day is: check the slate, shop the line,
size the bet, place it, log it, watch it, review CLV. MONEYLINE covers "check the slate".
There is no bet slip, no bankroll, no alerts, no line shopping, no closing-line tracking,
no mobile story.

## 0.3 The finding to fix this week

`GameCard` already asks the user to type both sides' book prices (`game-card.tsx:264`,
label `:93`, disclosure `:446`). Those prices go to `POST /api/evaluate` and are scored by
the verdict engine. **Then they are discarded.** Nothing writes `entered_line`. The grading
path reads it (`record_store.py:357,369`) and falls back to −110.

So today a user enters −135, MONEYLINE tells them whether −135 is value, the pick enters the
ledger, and the ledger grades it as if they got −110. The record is wrong — sometimes in the
user's favour, sometimes against — and the product is already collecting the number that
would make it right.

`v3-plan.md` Tier 1 argued that *synthesising* `entered_line = fair_line` would be fake
precision. That reasoning was correct and is unchanged. But it predates the UI that collects
a real price. Persisting a number the user actually typed is not fake precision; it is the
only honest thing to do with it. One `INSERT` column. **Highest value-per-line-of-code in
this entire document.**

## 0.4 The strategic fork: sharp or recreational

This is now the most important product decision, and it matters more than any feature below.

| | 🎯 **Sharp** | 🎲 **Recreational** |
|---|---|---|
| Buys | Edge, calibration, speed, CLV | Confidence, entertainment, action |
| Proof they want | Verifiable record, log loss | Recent hot streak, big wins |
| Price tolerance | $50–200/mo if it makes money | $10–30/mo, churns fast |
| Volume | Low count, high LTV, brutal churn if edge dies | High count, high churn regardless |
| Cares about parlays | Almost never (worst EV on the board) | Almost exclusively |
| Killed by | An honest record showing no edge | Boredom |
| Competitors | OddsJam, Unabated, Outlier, Pinnacle-adjacent tools | Action Network, Covers, tout Discords |

**MONEYLINE's existing assets point at sharp.** The verifiable ledger, the calibration
buckets, the refusal boundaries, the receipts — a recreational bettor does not want any of
those and will not pay for them. A sharp bettor will pay a lot for them, but *only* if the
model is actually sharp, which brings you back to Gap 2 and Gap 3.

**The honest risk of the sharp path:** you build the measurement harness, you fix the model,
you run it for a season, and the record says there is no edge. That is a real outcome and
this product is uniquely constructed to be unable to hide it. The recreational path never
faces that test.

**Recommendation: sharp positioning, recreational on-ramp.** The free and Analyst tiers
serve the curious fan with education and the daily read. Pro is a genuine sharp tool. The
honest record is the marketing for both, and the model gets a real season to prove itself
before the price goes up. Every item below is tagged 🎯 or 🎲 so this fork stays visible.

## 0.5 What survives from the old doctrine, and why

Not on principle — on competitive grounds:

- **Calibration and the graded record.** This is the moat. Every competitor claims an edge;
  almost none publish a verifiable one. Keep it, and make it *harder* to fake, not softer.
- **Receipts on derived numbers.** A sharp bettor who cannot see why a model disagrees with
  the market will not trust it enough to bet size on it.
- **Refusals when the sample is thin.** A model that says "I don't know" in April is worth
  more than one that guesses, because the user's bankroll is real.

What is scratched: the *data* purity rules. Odds feeds, injury signals moving prices, news
moving prices, salary data, third-party sources — all now in scope.

---

# Part I — The Market Layer

The foundation of a gambler's product. Nothing else in this document matters as much.

## 1.1 The manual-entry ladder (do this first — it is nearly free)

Four rungs, each shippable alone, none requiring an odds feed. This is the fastest path from
"sports research" to "betting tool" and it costs almost nothing.

### M1. Persist the price the user typed — Lift 5, Effort S, 🎯🎲
Write `entered_line` on pick insert from the value already flowing through
`game-card.tsx:264`. The read path, the grading math, and the CSV export
(`record-stats.ts:188,212`) all already exist and already handle it. See §0.3.

Backfill policy: rows already graded at −110 stay at −110 and are marked as a distinct era
via `model_version`. Never rewrite history.

### M2. De-vig the user's two prices — Lift 5, Effort S, 🎯
**The single best idea in this document per unit of effort.**

The user is already typing *both* sides into the card. Two prices is all you need to strip
the vig and recover the book's true opinion:

```
implied_home = implied(price_home)          odds.py:21-25   (exists)
implied_away = implied(price_away)          odds.py:21-25   (exists)
hold         = implied_home + implied_away - 1               odds.py:33-39 (exists)
novig_home   = implied_home / (implied_home + implied_away)  ← the missing line
```

That is one line of new arithmetic over three functions that are already written and
tested. It unlocks, immediately and with no external data:

- **The book's true probability**, not its vig-inflated one.
- **True edge**: `p_model − novig_market`. Today's verdict engine compares the model to the
  *vigged* price, which understates every edge on the favourite and overstates every edge
  on the dog. `verdict.py` already receives both prices (`price_home`, `price_away` at
  `verdict.py:331`) and does not currently use them together.
- **Hold %**, shown per game. "Your book is charging 5.2% on this game; the market average
  is 4.4%" is a genuinely useful, genuinely sharp piece of information.
- **A real disagreement metric** for the daily brief: rank the slate by
  `|p_model − novig_market|`.

⛓ Needs: nothing. Every primitive exists.

### M3. Closing line and CLV — Lift 5, Effort M, 🎯
Prompt the user to enter the closing price (or capture it automatically once M4 lands), then
report **Closing Line Value**: did you beat the number the market settled on?

CLV is the metric sharp bettors actually track, because it is the only one that converges
fast enough to be meaningful. Win rate needs thousands of bets to distinguish skill from
noise; CLV needs dozens. A product that reports CLV honestly is speaking the language.

This also fixes the deepest measurement problem in the ledger: with ~500 graded picks you
cannot statistically distinguish a 2% edge from zero. With CLV over the same 500, you can.

### M4. Line-movement history per game — Lift 4, Effort M, 🎯
Once prices are captured (manually or by feed), store the time series. Opening → current →
closing. Then: which way did the market move, and did the model see it first?

"The model had the Rays at −128 this morning; the market opened −115 and closed −135" is the
single most persuasive artifact this product could produce, and it is entirely derivable
from data the product will already have.

## 1.2 Odds ingestion (the former 🔴, now the main event)

### M5. An odds feed — Lift 5, Effort L, 🎯🎲
The options, honestly compared:

| Source | Cost | Books | Notes |
|---|---|---|---|
| **The Odds API** | ~$30–200/mo tiered | 30+ US/intl | Easiest start. Good docs, clean REST, generous free tier for dev. Latency measured in tens of seconds — fine for pregame, useless for live. |
| **OddsJam / OddsBlaze API** | $$$ (enterprise) | 100+ | Fast, deep, expensive. This is what the serious tools use. |
| **SportsGameOdds / SportsDataIO** | $$ mid | 20+ | Middle ground, bundles stats + odds. |
| **Pinnacle (unofficial)** | free-ish | 1 | The sharpest book, lowest hold (~2%). Its no-vig line is the closest thing to a true probability that exists. Scraping is ToS-hostile; some aggregators resell it. |
| **Scraping books directly** | free | varies | ToS violation, IP bans, brittle. Do not build the product on this. |

**Recommendation: start with The Odds API.** Cheap enough to validate the whole thesis, wide
enough for line shopping, and if the product outgrows it that is a good problem.

**The Pinnacle question is separate and more important than the vendor question.** For a
sharp product, the no-vig Pinnacle line is not "another book" — it is the benchmark. A
model's real test is not "does it beat DraftKings" (it might, DK's line is shaded toward
public money) but "does it beat Pinnacle's closing number", which is very close to the true
probability. Get Pinnacle in whatever way is legitimately available, and treat it as the
reference series rather than as a shopping option.

⛓ Needs: M2 (de-vig math), and a decision on vendor.

### M6. Line shopping across books — Lift 5, Effort M, 🎲🎯
"Best available price on each side, across your books." Trivially valuable, immediately
legible to any bettor, and the number-one reason people pay for OddsJam.

The honest framing MONEYLINE can uniquely add: line shopping is worth *more* than most
models. Getting −105 instead of −115 on a coin flip is ~2.3% of EV — larger than almost any
realistic model edge. A product that says so, and quantifies it against its own model's
measured edge, is being more useful than one that sells the model.

Requires: user says which books they have access to (state-dependent, see §6.4).

### M7. +EV screener across the full board — Lift 5, Effort M, 🎯
⛓ Needs M5 + M2 + a model that has passed a backtest.

Rank every game on the slate by `p_model − novig_best_available`, filter by threshold, sort
by Kelly stake. This is the core screen of every sharp tool that exists, and MONEYLINE
already has `screener.tsx` and `/api/screener` to build on.

**Do not ship this before the backtest.** A +EV screener on an unvalidated model is a
machine for losing money confidently, and it is exactly the product this codebase was built
in opposition to.

### M8. Steam and reverse-line-movement detection — Lift 4, Effort M, 🎯
⛓ Needs M4 + M5.

Steam: a line moving fast and in the same direction across many books = sharp money.
Reverse line movement: the line moves *against* the public betting percentage = sharp money
on the unpopular side. Both are among the few genuinely predictive market signals.

RLM needs public ticket/handle percentages, which are a separate data purchase (Action
Network and a few others sell or display them).

### M9. Arbitrage and middles — Lift 3, Effort M, 🎲
⛓ Needs M5 + M6.

Real, findable, and mostly a customer-acquisition feature rather than a business: arbs are
small, fleeting, and get accounts limited fast. Worth building because it demos well and
because "this tool found me a guaranteed $40" converts trials.

Be honest in the UI about limiting risk — a tool that gets a user's account restricted
without warning them has cost them more than it made them.

### M10. Alternate markets: totals, run lines, first five, props — Lift 5, Effort XL, 🎯🎲
The moneyline is one market on a board with dozens, and it is the *most* efficiently priced
one. The model's structure actually suits totals better than moneylines — it predicts RS
and RA directly, and a total is `RS_a + RS_b` with a park and weather adjustment. That is a
shorter path from the existing chain than the moneyline was.

- **Totals (O/U)**: closest to the existing model. Highest priority after moneylines.
- **Run line (−1.5/+1.5)**: needs a run-margin distribution, not just a win probability.
  Derivable by simulating from RS/RA (`season_sim.py` already runs Monte Carlo and could be
  repurposed per-game).
- **First five innings**: arguably *easier* than the full game, because it removes bullpen
  variance — the thing the model models worst. A strong candidate for the first market
  where MONEYLINE genuinely beats the book.
- **Player props**: the softest market on the board and where the money currently is. Also
  a completely different modelling problem (`players.py` is a start). XL.

**Strategic note:** if this model is ever going to beat a market, it will not be the MLB
moneyline. F5 and totals are softer and better matched to what the chain already computes.

## 1.3 What the market layer costs

- **Money**: $30–200/mo to start, scaling to four figures if it works.
- **A new failure mode**: the product now has a hard dependency on a paid third party.
  `feeds.py` already has the deadline/stale-serve pattern (`FEED_DEADLINE_SECONDS`, fixed in
  `c565770`) — reuse it, and make sure a dead odds feed degrades to "no market data" rather
  than to a silently stale price. A stale odds line is worse than none.
- **Freshness becomes correctness.** `verdict.py` already accepts `price_age_s` and
  currently omits it deliberately because prices are user-typed. With a feed it becomes
  real, and a 90-second-old price on a moving line is a wrong answer.

---

# Part II — The Model

Three lanes, ranked internally, then ranked against each other. With the doctrine scratched,
two categories that were previously forbidden are now open: **context signals may move
prices** (§2.1 A0) and **any data source is fair game**.

## Lane A — Better baseball modelling

### A0. Let injuries, scratches, and lineups move the price — Lift 5, Effort M, 🎯🎲
**Newly unlocked.** Previously prohibited outright: *"Media pulse and injury flags are
disclosed context only; they NEVER move a price."* `get_injury_flags` (`feeds.py:1014`)
already fetches IL status and the data reaches the UI as decoration.

For a bettor this was the strangest thing about the product. A scratched ace is worth
~2–4 points of win probability and is the most common reason a real line moves. A model that
watches the starter get scratched and does not change its number is not a betting model.

Implementation, in order of value:
1. **Late scratch of a probable starter** → recompute the ADJ blend with the replacement.
   The machinery exists (`_blended_side`, `feeds.py:862`); only the trigger is missing.
2. **Key position player on the IL** → subtract their mWAA contribution from the team's
   rates. `analytics.py:63-116` already computes exactly this per player.
3. **Bullpen availability** → yesterday's usage, from game logs.

Keep the disclosure. The old rule's *good* half was that the user could always see what
moved a number; that survives as a receipt line ("−1.8 pts: Gerrit Cole scratched"), and it
is a better feature with the price movement attached than without it.

### A1. Home-field advantage — Lift 5, Effort M, 🎯🎲
`log5_probability` (`odds.py:138-146`) is symmetric; there is no home term anywhere. MLB home
teams win ~53–54% (measure it in the pitch-clock era, don't assume the old number).

Fit the bump from data — a logistic on (strength differential, home indicator), or
`p_home = log5(S_h, S_a) + δ` with δ fitted and versioned. Do not hardcode it; the
"coefficients come from `load_models()`" rule is worth keeping for a reason unrelated to
doctrine: hardcoded constants are how models silently rot.

Cost: rewrites every price ever quoted. `MODEL_VERSION` (v3 Tier 3 item 2) has landed, so
run it as a graded challenger before it becomes the headline number.

### A2. Game-level backtest harness — Lift 5, Effort L, 🎯
**Not a model improvement. The precondition for every model improvement here, and the gate
on the +EV screener (M7).**

Needs: historical game results (Retrosheet, Lahman, or MLB Stats API `/schedule` with
`hydrate=linescore` back N seasons); team rate stats **as they stood on each game date**;
walk-forward evaluation by season scored with log loss and Brier.

The trap that invalidates most sports backtests: using end-of-season stats to "predict" an
April game leaks the future into every prediction and produces a beautiful, fictional edge.
Point-in-time reconstruction or nothing.

Once M3/M5 exist, extend it to backtest against **closing lines**, which is the only test
that matters: did the model beat the number?

### A3. Refit RA off 90 rows — Lift 4, Effort M, 🎯
`precompute.py:158` fits opponent-rates → RA on 1999–2001 (90 team-seasons) because
`baseball.csv` has OOBP/OSLG for no earlier year. That sets the run-prevention half of every
price. Source the full panel from Retrosheet/Lahman, or refit on modern data (A4). At
minimum, disclose it.

### A4. Refit on the modern run environment — Lift 4, Effort M, 🎯
Training panel is 1962–2001. Since: the offensive spike and collapse, three-batter minimum,
universal DH, shift ban, pitch clock, a juiced-then-dejuiced ball. OBP/SLG → runs is not
era-invariant.

With the doctrine scratched the counter-argument ("the 1962–2001 fit *is* the product's
identity") loses most of its force — but not all of it, because the Moneyball provenance is
genuinely good marketing. Resolution that keeps both: **ship two bundles**,
`classic-1962-2001` and `modern-2012-2025`, as parallel graded challengers (B3), and let the
ledger decide. The classic fit stays as the story and the teaching artifact; the modern fit
prices the bets.

### A5. Park factors — Lift 4, Effort M, 🎯🎲
Not modeled at all. Two distinct corrections, and doing only the second double-counts:
1. **Neutralize the inputs** — deflate a team's rates by its home park factor so the model
   sees true talent, not Coors talent.
2. **Re-inflate for the venue** — apply the *game's* park factor before Pythagorean.

Derivable from MLB Stats API game logs, or take a published table with a citation.
Essential for totals (M10), where park is the dominant term.

### A6. Shrinkage on early-season rates — Lift 4, Effort M, 🎯
`OBP_est = (n·OBP_obs + k·OBP_lg)/(n + k)`, with `k` fit from the historical variance
decomposition rather than guessed. The verdict engine's `gp_hard_floor` gate
(`verdict.py:117`) is the binary approximation; shrinkage is the continuous, correct version
and lets the product say something useful in April with correctly widened uncertainty
instead of refusing outright.

Highest-integrity item in Lane A: it makes the model more honest *and* more useful, using
only data already in hand.

### A7. Bullpen modelling — Lift 4, Effort L, 🎯
`_blended_side` (`feeds.py:862`) blends the starter's opponent rates against the team's,
weighted by `IP/(GS×9)` clamped to [0.4, 0.8] (`analytics.py:191-196`). Everything after the
starter exits is charged at the team season average — which *includes* the starter. The pen
is simultaneously under-represented and double-counted.

Correct: three-way blend — starter (projected IP), bullpen (remainder, relievers-only
aggregates), and a rest/usage adjustment for a pen that threw four innings yesterday.
Bullpen quality varies more between teams over a single game than rotation quality does.
Probably the largest un-modelled real effect after home-field and park.

### A8. Real lineups instead of team season rates — Lift 4, Effort L, 🎯🎲
Lineups post 2–4 hours before first pitch. A team resting three regulars is a different
offense. `_probable` (`feeds.py:960`) and the ~6h roster cache (`feeds.py:633`) are the
starting points.

Honest cost: creates a two-tier price (pre-lineup, post-lineup) and the ledger must record
which one it graded. Pairs naturally with a lineup-drop push alert (Part III), which is
worth as much in retention as in accuracy.

### A9. Platoon splits and handedness — Lift 3, Effort L, 🎯
A LHP against six left-handed bats is not the team's overall rates. Refinement of A8; do not
attempt first.

### A10. Pythagenpat — Lift 2, Effort S, 🎯
`odds.py:131-135` hardcodes exponent 2. Pythagenpat uses `exp = ((RS+RA)/G)^0.287` — better
at run-environment extremes, identical in the middle. Tiny effort. Also removes one of the
two magic literals `v3-plan.md` flags (the other, the −110 overround at `main.py:557`, is a
one-liner derivable from `market_vig(-110,-110)`).

Caution: `smoke_test.py` pins the 2002 A's chain; this moves it. Needs a hand-checked
replacement in `verified_stats.json` per CLAUDE.md.

### A11. Separate defense from pitching — Lift 3, Effort L, 🎯
OOBP/OSLG conflate pitcher and defense. Splitting them (DRS/OAA, or FIP-vs-ERA reasoning)
makes the ADJ starter blend materially more accurate: the pitcher's component travels with
the pitcher, the defense stays with the team.

### A12. Statcast inputs — Lift 4, Effort L, 🎯
xwOBA, barrel rate, exit velocity stabilize far faster than outcome stats and are more
predictive at small samples — precisely MONEYLINE's April problem, and a partial substitute
for A6. Available via `pybaseball` / Baseball Savant. Previously blocked by the keyless-only
rule; now open.

### A13. Weather, umpire, travel, rest, altitude — Lift 3, Effort M, 🎯
Wind at Wrigley moves totals more than most model terms. Home-plate umpire zones vary
measurably. West-to-east travel with no off day is documented. Individually small,
collectively perhaps half a point of win probability — and considerably more on totals.

The one real caution: these are small effects on small samples and **every one of them looks
significant if you go looking.** Gate behind A2 with a pre-registered hypothesis, or skip.

### A14. Catcher framing, baserunning, sequencing — Lift 1, Effort L
Listed for completeness. Not before everything above is done and measured.

---

## Lane B — Modern ML method

The estimators are fine. The methodology around them is what is missing.

### B1. Walk-forward validation and proper scoring — Lift 5, Effort M, 🎯
Today: one chronological split on the *season* models (`precompute.py:146-152`), nothing on
game prices. Needed: season-by-season walk-forward CV scored with **log loss and Brier**,
never hit rate.

Hit rate is the metric that makes bad probability models look good — a model that says 55%
on every game and goes 55% is perfectly calibrated and completely worthless. Log loss
catches that. Every tout service in the world reports hit rate for exactly this reason.

Same project as A2 viewed from the modelling side.

### B2. Calibration as a first-class output — Lift 5, Effort M, 🎯
Track Record already ships calibration buckets and Wilson intervals (`components/record/`).
Turn that machinery inward onto model development: reliability curves on held-out seasons,
plus an explicit calibration layer (Platt or isotonic) fit out-of-sample if the raw chain
proves over- or under-confident.

For a betting product this is not cosmetic. **Kelly consumes the probability directly**, so
miscalibration does not merely cost accuracy — it mis-sizes every single bet, and
over-confidence compounds into ruin faster than a bad edge does.

### B3. Champion–challenger model registry — Lift 5, Effort M, 🎯
Already practiced by hand: ADJ is a challenger graded alongside SEASON with the app refusing
to claim it is better. Formalize it — N bundles, each with a `MODEL_VERSION`, each priced on
every game, each graded independently, with a leaderboard reporting log loss, calibration,
CLV, and units against a common baseline. Promotion happens on evidence.

`MODEL_VERSION` is done, `model_version` is on all three ledger tables, `get_record` reports
`model_versions_present`. This is a shorter step than it looks, and it is the mechanism that
makes A1, A4, and every other price-moving change *safe to attempt at all*.

### B4. Uncertainty intervals, not point estimates — Lift 4, Effort M, 🎯
Every price is a point estimate. Team rates are estimated with error, coefficients are
estimated with error, the model is estimated with error. Propagating that yields a credible
interval on the fair price.

Feeds directly into correct bet sizing: uncertainty should shrink stakes, and currently does
not at all (see §3.2 — Kelly is uncapped). `_uncertainty` (`verdict.py:117`) is a heuristic
over games-played and the season-vs-adjusted spread; a real posterior replaces it with
something derived rather than tuned. `v3-plan.md` records that this heuristic's Moderate arm
was ambiguous enough in the spec to require a judgment call — deriving it removes the
ambiguity permanently.

### B5. Gradient boosting / hierarchical Bayes — Lift 3, Effort L, 🎯
The obvious "modernize the model" move, deliberately ranked below the boring items.

Honest assessment: with ~2430 games a season into an efficient market, **the feature set
matters far more than the estimator.** XGBoost on OBP and SLG will not beat linear regression
on OBP and SLG by anything that survives a backtest. XGBoost on park-adjusted, shrunk,
bullpen-aware, home-field-aware features might — but then Lane A did the work.

A **hierarchical Bayesian team-strength model** is the more interesting choice for this
product specifically: latent team strength with a prior, updated game by game. It gives B4's
uncertainty natively and handles A6's shrinkage as a consequence of the prior rather than a
bolted-on correction. Cost: it is much harder to explain, and the per-feature contribution
receipts (`inference.py:64-81`) become SHAP values, which is a weaker claim to a user
deciding whether to trust a number with their money.

### B6. Ensemble SEASON and ADJ — Lift 3, Effort M, 🎯
Today the user gets two numbers and no guidance, which is honest but unhelpful. Once the
ledger can say which is better *and under what conditions* (starters confirmed? late season?
wide spread?), output one price from a weighted blend with the weights derived from the
record and disclosed. Requires real sample size; do not attempt early.

### B7. Feature importance and ablation reporting — Lift 2, Effort S, 🎯
Once A2 exists, running the chain with each feature ablated and reporting the log-loss delta
is nearly free — and it is good content, because "here is what each input is actually worth"
is both a research artifact and proof of the transparency claim.

### B8. Retraining cadence and drift monitoring — Lift 3, Effort M, 🎯
Coefficients are baked at build time (`precompute.py:186`) and loaded once
(`inference.py:18-22`, `lru_cache`). Nothing detects that the run environment has drifted
away from the fit. A scheduled job computing current-season residuals against model
expectations, alerting on drift, is cheap insurance — and with a paid odds feed the same job
should alert when model-vs-market divergence changes regime, which is usually a bug, not an
edge.

---

## Lane C — Actual LLM features

Ranked, with the framing the product should keep even without the doctrine:

> **None of this creates predictive edge.** Not one Lane C item makes a price more accurate.
> Lane C buys comprehension, retention, conversion, and research speed. Those are worth real
> money — but marketing an LLM as a model improvement is the exact species of claim that,
> when a sharp user catches it, costs the trust the record was built to earn.

Model selection: `claude-sonnet-5` for interactive paths, `claude-haiku-4-5` for
high-volume classification, `claude-opus-5` only where reasoning depth genuinely pays.

### The guardrail that makes all of Lane C safe

**The LLM never produces a number.** Every figure in generated prose must exist in a
structured payload computed by the deterministic engine and passed in as context. Enforce
mechanically: a post-generation validator extracts every numeral and asserts each appears in
the source payload; on failure, return the deterministic text. Temperature 0.

Without that validator, one hallucinated fair line destroys the receipts claim. With it,
Lane C is safe throughout — and it is a two-hour piece of code.

### C1. Reason bullets on every price — Lift 4, Effort M, 🎯🎲
Highest-value Lane C item, and **mostly not an LLM feature.**

`v3-plan.md` Tier 3 item 4 (`model_detail` on slate rows + `backend/explain.py`) is the
deterministic core: `_chain_probability` discards the `predict_from_inputs` receipts, so
there are no reason bullets anywhere. Build that first — the ranking design already exists
in `notes/explain-design.md` (659 lines).

The LLM's only job is turning `{feature, value, coefficient, contribution}` tuples into a
sentence someone enjoys reading. `explain.py` without the LLM is a good feature. The LLM
without `explain.py` is a hallucination machine.

With A0 shipped, the highest-value bullet becomes the *movement* bullet: "−1.8 pts: Cole
scratched" — the thing a bettor actually opens the app to find out.

### C2. Chat with the desk — Lift 4, Effort L, 🎯🎲
Tool-use over the 29 existing API routes. *"Who does the model like tonight?"* *"Why the
Rays?"* *"Every game where we disagree with my book by more than 3 points."* *"What's my
record on road favourites?"* *"Should I have taken that line?"*

The most natural Pro-tier feature in the catalog: expensive per call, obviously valuable,
cleanly gated by `has_feature` (`billing.py:59`), and it turns the existing API surface into
product with almost no new backend. Every answer is grounded in a tool call, which enforces
the guardrail structurally rather than by convention.

### C3. News → structured signal, replacing the keyword lexicon — Lift 4, Effort M, 🎯
The pulse lexicon (`analytics.py:26-35`) is a keyword matcher with defects recorded in
`v3-plan.md`: "streak" and "losing streak" double-count, and `_matches` (`:282-285`) has a
leading word boundary but no trailing one, so **"torn" matches "tornado"**.

A small classifier is strictly better. And with A0, this graduates from decoration to a
price input: extracting *"Cole scratched with forearm tightness"* from a beat-writer tweet
30 minutes before the official transaction posts is a genuine, timing-based edge — one of
the few places an LLM contributes real betting value rather than comprehension.

That upgrade needs care: an LLM-extracted signal that moves money must be conservative,
logged, and reversible, with a confidence floor below which it only disclosly rather than
prices.

### C4. Daily brief, written and delivered — Lift 4, Effort M, 🎯🎲
One generated page each morning: the slate, biggest model-vs-market disagreements, what
changed overnight, what the record did, what your open bets are doing. Email
(`backend/mailer.py` exists) or push.

The best answer to "why would I open this every day?", and the habit loop that makes a
subscription renew. With M2 in place the disagreement ranking is real rather than
model-vs-itself.

### C5. Parlay critique in plain language — Lift 2, Effort S, 🎲
The correlation refusal (`main.py:1001-1007`, doubleheader-extended in `bf1e7ab`) is correct
and terse. An LLM explaining *why* correlated legs are mispriced, using the user's own slip,
turns a rejection into a lesson. Good onboarding.

### C6. Onboarding and jargon explainer — Lift 3, Effort S, 🎲
"What is log5?" "What does −150 mean?" "What's CLV?" "Why is it refusing?" MONEYLINE's
vocabulary is dense; this is the ramp from 🎲 to 🎯 and directly serves the on-ramp strategy
in §0.4.

### C7. Auto-generated SEO research content — Lift 2, Effort M, 🎲
`seo_strategy.md` lists primary keywords as "Unknown". Per-team and per-matchup research
pages would rank.

Grudging: mass-generated content is a low-trust move and Google has gotten good at detecting
it. If done, generate from real computed model output — which is genuinely unique data — and
never from a prompt alone.

### C8. Natural-language bet logging — Lift 2, Effort S, 🎲
"Took the Rays −120 for two units" → structured ledger row. Convenience only, but it removes
the friction that kills betting logs, and a dead log means a dead record.

---

## Part II ranked — all three lanes against each other

| # | Item | Lane | Lift | Effort | Serves |
|---|---|---|---|---|---|
| 1 | **Game-level backtest harness** (A2/B1) | A+B | 5 | L | 🎯 |
| 2 | **Injuries & scratches move the price** (A0) | A | 5 | M | 🎯🎲 |
| 3 | **Home-field advantage** (A1) | A | 5 | M | 🎯🎲 |
| 4 | **Calibration layer** (B2) | B | 5 | M | 🎯 |
| 5 | **Champion–challenger registry** (B3) | B | 5 | M | 🎯 |
| 6 | **Shrinkage on early rates** (A6) | A | 4 | M | 🎯 |
| 7 | **Park factors** (A5) | A | 4 | M | 🎯🎲 |
| 8 | **Refit RA off 90 rows** (A3) | A | 4 | M | 🎯 |
| 9 | **Modern-era challenger bundle** (A4) | A | 4 | M | 🎯 |
| 10 | **Statcast inputs** (A12) | A | 4 | L | 🎯 |
| 11 | **Uncertainty intervals** (B4) | B | 4 | M | 🎯 |
| 12 | **Bullpen modelling** (A7) | A | 4 | L | 🎯 |
| 13 | **Reason bullets / `explain.py`** (C1) | C | 4 | M | 🎯🎲 |
| 14 | **Chat with the desk** (C2) | C | 4 | L | 🎯🎲 |
| 15 | **News classifier → price signal** (C3) | C | 4 | M | 🎯 |
| 16 | **Daily brief** (C4) | C | 4 | M | 🎯🎲 |
| 17 | Real lineups (A8) → platoons (A9) | A | 4/3 | L | 🎯🎲 |
| 18 | Weather/umpire/travel (A13) | A | 3 | M | 🎯 |
| 19 | Drift monitoring (B8) | B | 3 | M | 🎯 |
| 20 | Defense/pitching split (A11) | A | 3 | L | 🎯 |
| 21 | Ensemble SEASON/ADJ (B6) | B | 3 | M | 🎯 |
| 22 | Boosting / hierarchical Bayes (B5) | B | 3 | L | 🎯 |
| 23 | Onboarding explainer (C6) | C | 3 | S | 🎲 |
| 24 | Pythagenpat (A10) | A | 2 | S | 🎯 |
| 25 | Everything else | — | 1–2 | — | — |

**Item 1 is worth more than items 6–25 combined**, and it is not a model change.

---

# Part III — The Gambler's Surface

Gap 4 from §0.2. A bettor's day is: **check the slate → shop the line → size the bet →
place it → log it → watch it → review CLV.** MONEYLINE covers step one.

## 3.1 The bet slip and the log

### S1. One-tap bet logging from the card — Lift 5, Effort M, 🎯🎲
There is no way to record a bet. The pick ledger is populated from *slate snapshots*
(`store_slate_snapshot`, `record_store.py:238`) — it records what the model liked, not what
the user backed. Those are different products: the first is a model track record, the second
is a betting log, and a gambler needs both.

Build: a bet slip that captures side, price, stake, book, and timestamp, writing to a new
`moneyline_bets` table keyed to `user_id`. Distinct from `moneyline_picks`, which should
stay exactly as it is — the model's own record must not be contaminated by user behaviour.

⛓ Needs: M1 (`entered_line` persistence) establishes the pattern.

### S2. My record vs the model's record — Lift 4, Effort M, 🎯
Once S1 exists, the two ledgers can be compared, and the comparison is the most interesting
screen in the product: *the model went 54% and you went 49%, because you skipped its
underdogs and doubled its favourites.* Behavioural feedback is what betting logs are for, and
almost nobody does it well.

### S3. Bankroll management — Lift 5, Effort M, 🎯
Nothing tracks a bankroll. `bankroll-backtest.tsx` displays a *simulated* historical curve
from `static_json("backtest.json")` — it is a marketing artifact, not a tool.

Needed: starting bankroll, unit definition, running balance, drawdown, ROI, per-bet stake
recommendations sized off the current balance rather than off abstract "units".

### S4. Fix the uncapped Kelly — Lift 4, Effort S, 🎯 ⚠️
`half_kelly_fraction` (`odds.py:49-56`) is **uncapped despite its docstring saying
otherwise**, flagged in `v3-plan.md`'s price-math danger list.

Under the old doctrine this was a display curiosity. In a product that tells people how much
money to risk it is a safety defect: an uncapped Kelly on an overestimated edge recommends a
ruinous stake, and model error at the tails is exactly where edges are overestimated. A
model that thinks it has a 15% edge on a +400 dog will size like it is certain.

Fix in the display/sizing layer with an explicit cap (1–2% of bankroll is the standard
practitioner ceiling regardless of what Kelly says), and make the cap visible and
user-adjustable. Do **not** mutate `odds.py` — `smoke_test` asserts current behaviour.
Pairs with B4: uncertainty should shrink the stake, and today nothing does.

### S5. Import from the books — Lift 4, Effort L, 🎲🎯
Manual logging dies within two weeks; every betting-log product learns this. The retention
answer is import: CSV from books that offer it, or an integration in the style of
Pikkit/Betstamp. Expensive and partly outside your control, but it is the difference between
a log people keep and a log people abandon.

## 3.2 Shopping, sizing, and alerts

### S6. "My books" configuration — Lift 4, Effort S, 🎲🎯
⛓ Needs M5. A user in Ohio has different books than one in Arizona. Line shopping is noise
unless it is filtered to books they can actually bet. Cheap to build, and it makes every
market feature meaningfully better.

### S7. Push and email alerts — Lift 5, Effort M, 🎯🎲
The single largest retention lever in this category, and the reason betting tools live on
phones. Alert on:
- **Lineups posted** for a game you're watching (pairs with A8)
- **Starter scratched** (pairs with A0) — the highest-urgency alert there is
- **Line moved past your threshold** — "the Rays hit −120, your target"
- **Model edge exceeded X%** on any game
- **Steam detected** (pairs with M8)
- **Your bet graded**

`backend/mailer.py` exists. Push needs a PWA or a real app (S9).

### S8. Slate filters and a real screener — Lift 4, Effort M, 🎯
`screener.tsx` and `/api/screener` exist but are mounted only in `tabs/desk.tsx`, which
`v3-plan.md` schedules for retirement — three endpoints lose their only home when it goes.

Rebuild the screener as the primary 🎯 surface: filter by edge threshold, Kelly stake,
uncertainty band, starters-confirmed, book availability, market type. Sort by EV. This is the
screen a sharp bettor lives in, and today's Today page is not it.

### S9. Mobile — Lift 5, Effort L, 🎲🎯
Betting happens on a phone, at the ballpark, in the twenty minutes before first pitch. The
current app is a dense desktop research terminal — `useIsMobile` exists and is used only by
an unused `ui/sidebar.tsx` (`v3-plan.md`).

Cheapest real answer: a **PWA** — installable, push-capable, no app store. A native app is
the better product and drags in App Store gambling-category review (see §6.4), which is a
real cost, not a formality.

### S10. Live / in-game — Lift 4, Effort XL, 🎲
The fastest-growing segment of the market and the softest lines. Also a completely different
engineering problem: sub-second odds, win-probability updated per plate appearance, a state
model MONEYLINE does not have. `season_sim.py`'s Monte Carlo is a distant starting point.

Deliberately ranked XL and late. Do not attempt before pregame is proven.

## 3.3 Surface debt that now matters more

Carried from `v3-plan.md`, re-prioritized because a betting workflow makes them worse:

- **Keyboard `1`–`6` still binds the old six tabs.** `1` does not reach Today; nothing
  reaches `/track-record` or `/settings`. In a product used under time pressure before first
  pitch, broken navigation is a real cost. — Lift 2, Effort S
- **`/` is dual-purpose and undocumented** (`App.tsx:165` renders Desk if `?team`/`?year`,
  else Today). — Lift 1, Effort S
- **`/desk` retirement orphans `ScreenerPanel`, `BaParadoxPanel`, `PricerPanel`,
  `SlateRail`.** S8 is the answer for the screener; decide the other three. — Lift 2, Effort M
- **`EQUITY_CAVEAT` (`main.py:87`) is the exact text the "not priced" chips need and renders
  nowhere.** — Lift 1, Effort S
- **Route names diverge from the docs** (`/track-record` vs `/record`, `/research/parlay` vs
  `/parlay`). Settle before Track Record becomes the marketing entry point. — Lift 2, Effort S
- **Two committed-`dist` test failures** (`tests/test_serve_spa.py`) have been red
  throughout. A permanently-red suite trains everyone to ignore red. — Lift 3, Effort S

---

# Part IV — Trust as the Competitive Weapon

The one part of the old doctrine worth keeping, and the reason a sharp bettor would choose
this over a better-funded competitor. This section is about making the record *harder to
fake*, not softer.

### T1. Grade against the closing line — Lift 5, Effort M, 🎯
⛓ Needs M3. The strongest honesty claim available to any betting product: not "we went
54%" but "our picks beat the closing number by 1.8 points on average." Nobody can fake CLV,
and the market cannot be gamed by cherry-picking which bets to report.

This replaces "we ingest no odds, so we grade at −110" with something strictly stronger, and
it is the direct upgrade path from the doctrine being scratched.

### T2. Make the ledger tamper-evident — Lift 4, Effort M, 🎯
Every tout claims a record; the claim is worthless because the record is editable. Publish a
daily hash of the pick set, chained to the previous day's, so a reader can verify no row was
added, removed, or altered after the fact. Cheap to implement, and it is a genuine,
checkable differentiator rather than a marketing adjective.

Pairs with the existing `model_version` stamping: prove *which model* made each call, and
prove the call predates the result.

### T3. Segment the record honestly — Lift 4, Effort M, 🎯
ROI and calibration broken out by: edge bucket, favourite vs dog, home vs away, month,
starters-confirmed, model version, market type. The Track Record page already computes
Wilson intervals and calibration buckets (`components/record/`) — extend the dimensions.

This will produce unflattering slices. Publishing them anyway is the entire point, and it is
what separates this from every competitor's cherry-picked "documented" record.

### T4. Say what the sample can and cannot prove — Lift 3, Effort S, 🎯
Already partly done ("what this proves", v3 Tier 3 item 5). Extend with the number that
matters: **how many more graded bets before a 2% edge is distinguishable from zero at 95%
confidence?** (Roughly 2,000–3,000 at MLB moneyline variance.) A product that tells you its
own record is not yet conclusive is making the most credible statement available to it.

### T5. Third-party verification — Lift 3, Effort M, 🎲🎯
Pikkit, Betstamp, and similar services verify records independently. Being verified there
is the market's existing trust primitive; it converts skeptics far more efficiently than any
in-app claim.

### T6. Publish the model, not just the record — Lift 3, Effort S, 🎯🎲
The coefficients, the training data, the fit method, the backtest results — all of it. This
is already the codebase's instinct (`verified_stats.json`, `notes/map-model.md`,
`notes/mlb_api_transcripts.md`). Formalized into public methodology pages it is both content
marketing and the thing that makes T1–T4 believable.

Counter-argument worth weighing: publishing an edge erodes it. In practice the edge here
will be in data freshness and execution, not in a regression anyone could refit — and the
trust is worth more than the secrecy at this stage.

---

# Part V — Data and Infrastructure

### D1. Historical game database — Lift 5, Effort L
⛓ Blocks A2, which blocks everything. Retrosheet or Lahman for deep history, MLB Stats API
for recent. The hard requirement is **point-in-time reconstruction** of team stats as they
stood on each game date; end-of-season stats leak the future and produce fictional edges.

### D2. Store every price the product ever quotes — Lift 4, Effort S
Slate snapshots persist once per date (`ON CONFLICT (snapshot_date) DO NOTHING`,
`record_store.py`). That is one price per game per day. For line-movement analysis (M4) and
for honest freshness claims, store the full series with timestamps.

Cheap, and the data becomes irreplaceable — a proprietary history of model-vs-market that
compounds and that no competitor can backfill.

### D3. Odds-feed resilience — Lift 4, Effort M
⛓ Needs M5. Reuse the deadline/stale-serve pattern from `c565770`
(`FEED_DEADLINE_SECONDS`, shielded shared task). Critical difference: **a stale odds price
must fail loudly, not serve quietly.** Stale stats degrade a price; a stale odds line
produces a confident recommendation to bet a number that no longer exists.

### D4. Observability on price accuracy — Lift 3, Effort M
No production metric tracks whether prices are any good. Rolling log loss, calibration
drift, model-vs-market divergence by regime, alerting when any moves. B8 is the model-side
version; this is the ops-side one.

### D5. Cost controls — Lift 3, Effort S
⛓ Needs M5 + Lane C. Two new metered dependencies (odds API, LLM API) arrive at once.
Per-user cost accounting, caching, and rate limits by tier, or the unit economics of the
$19 plan quietly invert.

### D6. Backfill and reconcile MLB data gaps — Lift 2, Effort M
`get_transactions` sends no `sportId` (`feeds.py:787`) so MiLB affiliates produce phantom
team codes; the pulse lexicon double-counts and matches "torn" inside "tornado"
(`analytics.py:26-35`, `:282-285`). Display-only today; with A0 and C3 these feed prices, and
then they are correctness bugs. **Fix before A0 ships, not after.**

---

# Part VI — Business

### 6.1 Pricing

Current: Free / Analyst $19 / Pro $49, gated by `has_feature` (`billing.py:20-64`), features
split `today, desk, track_record` → `+players, matchups, wire` → `+parlay, season`.

Observations:

- **The tiers are split by research surface, not by betting value.** Nothing in the ladder
  says "this tier makes you money." A gambler's ladder is: free = the daily read; mid = line
  shopping, alerts, the log; top = the +EV screener, CLV analytics, API, chat.
- **$49 is under-priced for a working sharp tool and over-priced for a research toy.**
  OddsJam is $99–$199/mo. If MONEYLINE genuinely produces +EV, $49 is leaving money on the
  table; if it does not, $19 is too much. **The backtest (A2) is a pricing decision, not just
  an engineering one.**
- **`parlay` sits in the top tier.** Parlays are the worst-EV product on the board and are a
  🎲 feature; putting them behind the most expensive 🎯 tier gets the segmentation backwards.
- **Annual plans and trials.** `ACTIVE_STATUSES` already includes `trialing`
  (`billing.py:19`) and nothing uses it. Annual billing is the standard fix for the brutal
  churn in this category.

### 6.2 The affiliate question — Lift 5, Effort M, ⚠️
Sportsbook affiliate deals ($50–500 CPA per funded signup) are how essentially every
profitable product in this space actually makes money. Subscriptions are the visible
business; affiliate revenue is usually the larger one.

**The conflict is direct and worth naming plainly:** a product paid by books to send them
users has an incentive to recommend betting more, at whatever book pays best — which is
precisely opposed to a product whose value proposition is telling you honestly when there is
no edge. Line shopping (M6) is where it bites hardest: the "best price" ranking is exactly
the surface an affiliate deal corrupts.

Workable version, if taken: disclose every affiliate relationship in-product, never let
commercial terms influence the recommendation ranking, and keep the ranking logic auditable.
Unworkable version: quiet affiliate links inside a "best price" table. That trade is worth
real money and costs the one asset that makes this product different — go in with eyes open.

### 6.3 Growth

- **The record is the marketing.** T1–T6 are growth features as much as trust features. A
  public, verifiable, unflattering-when-it-should-be record is a content engine.
- **SEO**: `seo_strategy.md` lists primary keywords as "Unknown" — that is task one. Real
  targets exist: "[team] vs [team] prediction", "MLB model picks", "CLV calculator",
  "no-vig calculator", "MLB betting model". The de-vig calculator (M2) is a genuinely useful
  free tool that ranks and converts.
- **Free tools as acquisition**: no-vig converter, Kelly calculator, parlay EV calculator,
  hold calculator. All are trivial given `odds.py` and all rank.
- **Distribution**: Discord/Telegram bot for the daily brief; a public daily-brief page;
  posting the model's calls publicly before games, which is both marketing and the strongest
  possible form of T2.

### 6.4 Legal and platform reality — ⚠️ **read before repositioning**

Genuine, concrete business risks that arrive with the repositioning, not caveats:

1. **Stripe.** Billing shipped three commits ago (`49ad107`). Stripe restricts
   gambling-related businesses; sports handicapping and tout services sit in a grey zone that
   has gotten stricter, and enforcement usually arrives as a frozen account with funds held,
   not as a warning. **Confirm MONEYLINE's classification with Stripe before marketing
   copy changes**, and know the alternatives (Paddle as merchant-of-record, or a
   gambling-tolerant processor). This is the highest-probability way the repositioning
   actually hurts, and it is cheap to check.
2. **App Store / Play Store.** Both treat gambling-adjacent apps as a restricted category
   with extra review, geo-restrictions, and sometimes a licensing requirement. Relevant to
   S9 — and one more reason a PWA is the cheaper first move.
3. **State-by-state legality.** Sports betting is legal in ~38 US states with different
   rules. An information product is not a sportsbook and is broadly fine, but "my books"
   (S6) and any affiliate arrangement (6.2) are state-dependent, and affiliate programs
   generally require registration in several states.
4. **Responsible gambling.** Deposit/loss limits, self-exclusion signposting, and
   help-resource links are a legal requirement for licensed operators and a practical
   requirement for affiliates and app stores. Beyond compliance: a bankroll tool (S3) that
   surfaces drawdown and tilt patterns is a genuinely good feature that also happens to
   discharge this obligation.
5. **"Guaranteed"/"lock" language.** Actionable under consumer-protection law in several
   states. MONEYLINE's instincts here are already correct; the marketing copy needs to stay
   that way once there is a growth incentive pushing the other direction.

---

# Part VII — Multi-Sport (later, but design for it now)

Out of scope for the current build. Two decisions made now cost nothing and save a rewrite.

**What generalizes:** log5, the moneyline conversions, the ledger, the verdict engine, the
market layer (M1–M9 are entirely sport-agnostic), bankroll, alerts, CLV, the whole trust
apparatus. Roughly 70% of this document is not baseball-specific.

**What does not:** OBP/SLG → runs is baseball-only. Every sport needs its own strength model.

**Order, when the time comes:**
1. **NBA** — many games (1230), stats-rich, high correlation between team ratings and
   outcomes, soft player-prop markets. Easiest transfer and best model-fit.
2. **NFL** — biggest handle by far, but 17 games per team is a brutal sample and the market
   is the sharpest in existence. Highest revenue, hardest problem.
3. **NCAA** — softest lines anywhere, worst data, huge slates. Genuine edge is findable if
   the data problem is solved.

**Two cheap decisions to make now:** (1) keep `sport` out of the URL but *in* the data model
— ledger tables, model registry, and odds records should carry a sport key from the start,
because retrofitting one into a graded ledger is painful and `record_store.py` already
carries the scar of externally-created tables. (2) Keep sport-specific modelling behind the
`strength → log5 → price` interface that already exists, so a second sport is a new strength
model rather than a new pipeline.

---

# Part VIII — What Not To Do

Anti-features, each of which would make this product worse in a way that is hard to reverse.

1. **Do not ship the +EV screener before the backtest.** A screener on an unvalidated model
   is a machine for losing other people's money confidently. This is the single most
   important line in the document.
2. **Do not synthesise `entered_line = fair_line`.** Persist the typed price (M1) or leave
   it null. Grading every pick at the model's own number makes the record systematically
   optimistic — the original reasoning in `v3-plan.md` Tier 1 survives the doctrine change
   intact.
3. **Do not claim ADJ (or any challenger) is better before the ledger says so.** The
   champion–challenger discipline (B3) is the mechanism; using it is the point.
4. **Do not report hit rate as the headline metric.** It is the number that makes bad
   probability models look good, which is exactly why every tout leads with it. Log loss,
   calibration, CLV.
5. **Do not let the LLM emit a number.** The validator in Lane C is two hours of work and it
   protects the only asset the product has.
6. **Do not build a "lock of the day."** MODEL SLIP OF THE DAY was deliberately deleted
   during Phase 1 (`v3-plan.md`) and should stay deleted. It is the single feature most
   corrosive to a calibrated product, and the repositioning is not a reason to revive it —
   it makes it more tempting and no less wrong.
7. **Do not uncap Kelly in a product that recommends stake sizes.** S4.
8. **Do not hide the losing slices of the record.** T3 will produce unflattering numbers.
   Publishing them is the differentiator; suppressing them makes this identical to every
   competitor.
9. **Do not take affiliate money that influences the line-shopping ranking.** §6.2. Take the
   money if you want, but not that way.
10. **Do not chase live betting before pregame is proven.** S10 is XL, is a different
    engineering problem, and would consume everything.
11. **Do not let the tests stay red.** Two `test_serve_spa.py` failures have been red
    throughout; a permanently-red suite is the same as no suite, and this product is about to
    start moving money.
