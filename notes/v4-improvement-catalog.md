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
