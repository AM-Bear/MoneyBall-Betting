# MONEYLINE — v4 Improvement Catalog

Written 2026-08-24. A deliberately exhaustive ideation pass: every way I can find to make
this product better, with the model, the market layer, the surface, and the business each
taken to depth.

**This is a catalog, not a plan.** It optimizes for coverage, not for sequencing. The
ranked, dependency-ordered plan is `notes/v4-plan.md`. Read this to know what exists;
read that to know what to do Monday.

Companion reading: `notes/v3-plan.md` (what is broken and what is verified healthy),
`notes/map-model.md` (the price chain formula by formula), `notes/map-data.md`,
`notes/map-surface.md`.

---

## How to read this document

Every item carries three marks.

| Mark | Meaning |
|---|---|
| **Lift 1–5** | How much this actually improves the product. 5 = changes what MONEYLINE is. 1 = polish. |
| **Effort S/M/L/XL** | S = a session. M = a few days. L = a couple weeks. XL = a project with its own spec. |
| 🟢 / 🟡 / 🔴 | Doctrine cost. See below. |

**Doctrine marks**, per the ruling that the no-odds doctrine is on the table but every
break must be priced:

- 🟢 **SAFE** — consistent with the doctrine as written in `replit.md`. Ship it without a
  conversation.
- 🟡 **STRAINED** — does not break a stated rule, but changes what the product implicitly
  claims. Needs new disclosure text, not a new philosophy.
- 🔴 **BREAK** — contradicts a rule currently enforced in code. Requires an explicit
  ruling from Asher, and the doc says exactly what honesty claim is being spent.

The three rules that generate every 🔴 in this document:

1. *"Keyless data only: MLB Stats API + MLB RSS ... no salary data served"* (`replit.md`).
2. *"Media pulse and injury flags are disclosed context only; they NEVER move a price."*
3. *"Honest refusals ... return boundary payloads, not fake numbers."*

---

## Part 0 — The thesis, stated plainly

Before the list, the thing the list is downstream of.

**MONEYLINE currently prices MLB games with a season-long team-rate model fit on
1962–2001 data, and it does not know what any sportsbook thinks.** The price chain is:

```
OBP, SLG        → RS      (linear, fit on 902 team-seasons ≤ 2001)   precompute.py:154
OOBP, OSLG      → RA      (linear, fit on  90 team-seasons 1999–01)  precompute.py:158
RS, RA          → strength (Pythagorean, exponent hardcoded 2)       odds.py:131-135
S_a, S_b        → p       (log5, no home-field term)                 odds.py:138-146
p               → line    (American, snapped to nearest 5)           odds.py:8-18
```

That chain is a beautiful *teaching* artifact and an honest one. As a **betting** model it
has four structural problems, none of which is a bug:

1. **No home-field advantage.** `log5_probability` has no home term. MLB home teams win
   roughly 54% of games. Every price MONEYLINE has ever quoted is biased against the home
   side by something on the order of 4 points of win probability. This is the single
   largest known error in the system and it is flagged in `v3-plan.md`'s price-math danger
   list precisely because fixing it rewrites every number.
2. **Half the chain is fit on 90 rows.** The run-*prevention* model — the RA half of every
   price — trains on `Year ≤ 2001` after dropping nulls in OOBP/OSLG, which in
   `baseball.csv` exist only from 1999. That is three seasons, 90 team-seasons, for one of
   the two coefficients that determines every game price.
3. **No park, no bullpen, no lineup, no platoon, no weather, no defense.** Team season
   OBP/SLG are park-contaminated inputs priced as if neutral. Coors and Petco are the same
   building to this model. The ADJ path blends in one starting pitcher's opponent rates
   (`analytics.py:191-213`) and stops; the bullpen throws ~40% of innings and is invisible.
4. **Season rates are not game predictions.** A season-to-date OBP is a noisy estimate of
   team quality, and the model consumes it as if it were true. The verdict engine handles
   this with a binary games-played gate (`verdict.py:117`); the statistically correct
   answer is continuous shrinkage, which does not exist anywhere in the codebase.

And the market it would be betting into is one of the most efficient in sports. MLB
moneyline hold is ~4.5%; Pinnacle's is closer to 2%. A model must be right by more than the
vig to make money, and this model does not currently have a demonstrated edge because
**there is no game-level backtest anywhere in the repo.** `/api/backtest` (`main.py:1040`)
serves `static_json("backtest.json")`, built by `precompute._backtest` (`precompute.py:76`),
which backtests the *wins* and *playoff* models on team-seasons. Nothing has ever measured
whether a MONEYLINE game price beats a coin, let alone a book.

**So the honest framing of this whole document is:**

> The gap between MONEYLINE and a product a sports gambler pays for is not features. It is
> (a) a measurement harness that can tell whether a change helped, (b) the four modelling
> corrections above, and (c) some contact with market prices. Everything else in this
> catalog is downstream of those three.

That is not a criticism of what has been built. The provenance discipline, the graded
ledger, the refusal boundaries, and the verdict engine are unusually good and are the
things that would make the model credible *if* the model were sharp. Most competitors have
the model and lie about the record. MONEYLINE has the record and has not yet sharpened the
model.

### The one finding that should be fixed this week

`GameCard` already asks the user to type in both sides' book prices
(`game-card.tsx:264`, label at `:93`, disclosure at `:446`). Those prices are sent to
`POST /api/evaluate` and scored by the verdict engine (`verdict.py:331`). Then **they are
thrown away.** Nothing writes `entered_line`. The grading path reads it
(`record_store.py:357,369`) and falls back to −110.

So today: a user enters −135, MONEYLINE tells them whether −135 is value, the pick lands in
the ledger, and the ledger grades it as if they got −110. The record is wrong in the user's
favour or against it, at random, and the product already collects the number that would
make it right.

`v3-plan.md` Tier 1 item 1 correctly argues that *synthesising* `entered_line = fair_line`
would be fake precision. That reasoning is sound and unchanged. But it was written when
there was no UI collecting a real price. There is one now. **Persisting a price the user
actually typed is the opposite of fake precision — it is the only honest thing to do with
it.** See Part II §2.1.

---

# Part I — The Model

Three lanes, as requested, each ranked internally, then ranked against each other at the
end of the Part.

## Lane A — Better baseball modelling

Real predictive lift on the existing chain. Ranked by lift per unit effort.

### A1. Home-field advantage — Lift 5, Effort M, 🟡
`log5_probability` (`odds.py:138-146`) is symmetric. There is no home term anywhere in the
price chain. MLB home win rate has been ~53–54% for two decades (it dipped to ~52% in the
pitch-clock era; measure it, do not assume it).

Implementation: fit the home-field bump from data rather than hardcoding it — a logistic on
(strength differential, home indicator) over historical games, or the simpler
`p_home = log5(S_h, S_a) + δ` with δ fit and versioned. **Do not hardcode 0.04**; that
violates "all model coefficients come from `load_models()`".

Cost: this rewrites every price the app has ever quoted. `v3-plan.md` is right that
`MODEL_VERSION` must land first (it has, item 2) and that it should run as a third graded
price experiment alongside SEASON and ADJ before it becomes the headline number. 🟡 because
the product must say clearly that prices before version N had no home-field term.

### A2. A game-level backtest harness — Lift 5, Effort L, 🟢
**Not a model improvement. The precondition for every model improvement in this document.**

Today nothing can answer "did that help?" You need: historical game results
(Retrosheet / Lahman / MLB Stats API `/schedule` with `hydrate=linescore` back N seasons),
the team rate stats *as they stood on each game date* (this is the hard part — point-in-time
reconstruction, not end-of-season stats, or you leak the future into every prediction), and
a walk-forward evaluation by season with log loss and Brier score.

Every item in Lanes A and B is unverifiable without this. Build it before you tune anything.

Trap to avoid: using end-of-season OBP to "backtest" an April game is the single most common
way sports models fake a result. Point-in-time or nothing.

### A3. Refit RA on more than 90 rows — Lift 4, Effort M, 🟢
`precompute.py:158` fits opponent-rate → RA on 1999–2001 only, because `baseball.csv`
carries OOBP/OSLG for no earlier year. Ninety observations, three run environments, and the
resulting coefficients set the run-prevention half of every price.

Options, best first: (a) source OOBP/OSLG for 1962–2001 from Retrosheet/Lahman and refit on
the full panel; (b) refit on 2000–2025 instead, which is a smaller doctrinal question than
it looks (see A4); (c) at minimum, *disclose* the 90-row fit — the product's whole claim is
receipts, and "this coefficient rests on three seasons" is a receipt currently missing.

### A4. Refit on the modern run environment — Lift 4, Effort M, 🟡
The training panel is 1962–2001. Since then: the 2000s offensive spike and its collapse,
three-batter minimum, universal DH, shift ban, pitch clock, humidor standardization, a
juiced-then-dejuiced ball. The mapping OBP/SLG → runs is not era-invariant; the run
environment it was fit in averaged materially different R/G than 2026.

The counter-argument is real and should be respected: **the 1962–2001 fit is the product's
identity.** "We refit the Moneyball regressions on the original data" is the story. Breaking
that to chase 0.3% of accuracy is a bad trade for a teaching product and a good trade for a
betting product.

Recommended resolution, which keeps both: **ship two model bundles.** `MODEL_VERSION`
already exists and the ledger already stamps it. Run `classic-1962-2001` and `modern-2010-2025`
as parallel graded experiments, exactly as SEASON/ADJ are run today, and let the record
decide. This is the doctrine working as designed rather than an exception to it. 🟡 only
because the UI must never imply the modern fit is better before the ledger says so.

### A5. Park factors — Lift 4, Effort M, 🟢
Not modeled at all. Team OBP/SLG are park-contaminated on the way in and the game price is
computed as if the venue were neutral. Coors inflates run scoring ~15–25%; Petco and the
Trop suppress it.

Two separate corrections, and they are not the same thing:
1. **Neutralize the inputs** — deflate a team's season rates by its home park factor so the
   model sees true talent.
2. **Re-inflate for the venue** — apply the *game's* park factor to expected runs before
   Pythagorean, since a game at Coors has a different run environment than the same two
   teams at Oracle.

Both are needed; doing only (2) double-counts. Park factors are derivable from MLB Stats
API game logs (keyless — 🟢) or takeable from a public table with a citation.

### A6. Shrinkage / regression to the mean on early-season rates — Lift 4, Effort M, 🟢
A team 18 games in with a .360 OBP is not a .360 OBP team. The correct treatment is
empirical-Bayes shrinkage toward the league mean with a weight that grows with games
played: `OBP_est = (n·OBP_obs + k·OBP_lg) / (n + k)`, where `k` is fit from the historical
variance decomposition rather than guessed.

The verdict engine's `gp_hard_floor` gate (`verdict.py:117`) is the binary, conservative
approximation of this: below the floor, refuse. Shrinkage is the continuous version and is
strictly better — it lets the product say something useful in April instead of nothing, and
it says it with correctly widened uncertainty.

This is arguably the highest-integrity item in Lane A: it makes the model *more* honest,
not less, and it is pure math over data already in hand.

### A7. Bullpen modelling — Lift 4, Effort L, 🟢
`_blended_side` (`feeds.py:862`) blends the *starter's* opponent rates against the team's,
weighted by `IP/(GS×9)` clamped to [0.4, 0.8] (`analytics.py:191-196`). Everything after the
starter leaves is charged at the team's season average, which includes the starter. So the
bullpen is both under-represented and double-counted.

Correct version: three-way blend — starter (weighted by projected IP), bullpen (weighted by
the remainder, using *relievers-only* aggregate rates), and a rest/usage adjustment for a
pen that threw four innings yesterday. Reliever workload over the prior 2–3 days is
available from MLB Stats API game logs.

Bullpen quality varies more between teams than rotation quality does over a single game.
This is probably the largest un-modelled real effect after home-field and park.

### A8. Actual lineups instead of team season rates — Lift 3, Effort L, 🟢
MLB posts lineups ~2–4 hours before first pitch. A team resting three regulars is a
materially different offense than its season line. The infrastructure exists — the slate
already hydrates probables (`feeds.py:960` `_probable`), and rosters are cached at ~6h
(`feeds.py:633`).

Note the honest cost: lineups arrive late, so this creates a two-tier price (pre-lineup and
post-lineup) and the ledger needs to know which one it graded. That is a real complication,
not a free win. It also pairs naturally with a "lineups are out" push notification (Part
III), which is a retention feature more than an accuracy one.

### A9. Platoon splits and handedness — Lift 3, Effort L, 🟢
A LHP facing a lineup with six left-handed bats is a different matchup than the team's
overall rates suggest. Split stats are available from the Stats API. This is a refinement of
A8 and should not be attempted before it.

### A10. Pythagenpat instead of a fixed exponent 2 — Lift 2, Effort S, 🟢
`odds.py:131-135` hardcodes exponent 2. Pythagenpat uses `exp = ((RS+RA)/G)^0.287`, which
is meaningfully better at run-environment extremes (Coors games, low-scoring pitcher duels)
and identical in the middle.

Small lift, tiny effort, and it removes one of the two hardcoded literals `v3-plan.md` flags
as non-coefficient magic numbers (the other, the −110 overround at `main.py:557`, is a
one-line fix to derive from `market_vig(-110,-110)`).

Caution: `smoke_test.py` pins the 2002 A's chain. Changing the exponent moves that number.
This needs a hand-checked replacement case in `verified_stats.json`, per CLAUDE.md.

### A11. Separate defense from pitching — Lift 3, Effort L, 🟢
OOBP/OSLG conflate pitcher quality and team defense. A pitcher in front of a great defense
posts better opponent rates than his true talent. Splitting them (DRS/OAA-style, or
FIP-vs-ERA reasoning) makes the ADJ starter blend meaningfully more accurate, because you
can carry the *pitcher's* component with the pitcher and leave the defense with the team.

### A12. Statcast underlying metrics — Lift 3, Effort L, 🟡
xwOBA, barrel rate, and exit velocity stabilize far faster than outcome stats and are more
predictive at small samples — which is exactly MONEYLINE's April problem. Available via
`pybaseball` / Baseball Savant.

🟡 not 🟢 because Savant is a different source than the two named in `replit.md`, so the
"keyless data only: MLB Stats API + MLB RSS" line needs updating. It remains keyless and
free; this is a disclosure change, not a philosophy change.

### A13. Weather, umpire, travel, rest, altitude — Lift 2, Effort M, 🟡
Wind at Wrigley is worth real runs. Home-plate umpire zones vary measurably. West-to-east
travel with no off day is a documented effect. Each is small; collectively they are perhaps
half a point of win probability.

🟡 for a specific reason worth naming: **umpire and weather effects are the natural home of
overfitting.** Each is a small effect measured on small samples, and every one of them looks
significant if you go looking. Gate these behind A2's backtest with a pre-registered
hypothesis, or do not do them.

### A14. Catcher framing, baserunning, and the long tail — Lift 1, Effort L, 🟡
Named for completeness. Do not build these until everything above is done and measured.

---

## Lane B — Modern ML method

The estimators are fine. The *methodology* around them is what is missing.

### B1. Walk-forward validation and proper scoring — Lift 5, Effort M, 🟢
There is currently a single chronological split (`train ≤ 2001 / test ≥ 2002`, asserted at
`precompute.py:146-152`) on the *season* models and no evaluation at all on game prices.

What is needed: season-by-season walk-forward CV, scored with **log loss and Brier**, never
accuracy and never hit rate. Hit rate is the metric that makes bad probability models look
good — a model that says 55% on every game and goes 55% is perfectly calibrated *and*
worthless. Log loss catches that; hit rate does not.

Pairs with A2 and is really the same project viewed from the modelling side.

### B2. Calibration as a first-class output — Lift 4, Effort M, 🟢
Track Record already ships calibration buckets and a Wilson interval (v3 Tier 3 item 5,
`components/record/`). That machinery should be turned inward, onto model development:
reliability curves on held-out seasons, and an explicit calibration layer (Platt or
isotonic) fit on out-of-sample data if the raw chain proves systematically over- or
under-confident.

A well-calibrated 56% is worth more to a bettor than a poorly-calibrated 60%, because Kelly
sizing consumes the probability directly. Miscalibration does not just cost accuracy; it
mis-sizes every bet.

### B3. Champion–challenger model registry — Lift 4, Effort M, 🟢
This is the doctrine MONEYLINE already practices, formalized. ADJ is currently "an
experiment graded alongside SEASON, and the app never claims it's better" — that is exactly
a challenger model, run by hand.

Formalize it: N model bundles, each with a `MODEL_VERSION`, each priced on every game, each
graded independently in the ledger, and a leaderboard that reports each one's log loss,
calibration, and units against a common baseline. Promotion to "the price" happens only on
evidence.

`MODEL_VERSION` (v3 Tier 3 item 2) is done, `model_version` is on all three ledger tables,
and `get_record` already reports `model_versions_present`. The registry is a smaller step
from here than it looks, and it is the mechanism that makes A1 and A4 safe to attempt.

### B4. Uncertainty intervals, not point estimates — Lift 4, Effort M, 🟢
Every price is a point. A team's OBP is estimated with error; the coefficients are estimated
with error; the model is estimated with error. Propagating that gives a *credible interval*
on the fair price.

This matters more here than in most products because MONEYLINE's identity is refusal.
"We think 56%, ±6" is a far more honest refusal than a gate, and it feeds directly into
correct Kelly sizing (uncertainty should shrink stakes, and currently does not at all).

The verdict engine's `_uncertainty` (`verdict.py:117`) is a heuristic over games-played and
the season-vs-adjusted spread. A real posterior would replace it with something derived
rather than tuned — and `notes/v3-plan.md` already records that this heuristic's Moderate
arm was ambiguous enough in the spec to need a judgment call. Deriving it removes the
ambiguity.

### B5. Gradient boosting / hierarchical Bayes on game-level features — Lift 3, Effort L, 🟡
The obvious "modernize the model" move, and deliberately ranked below the boring items.

Honest assessment: with ~2430 games a season and a market this efficient, **the feature set
matters far more than the estimator.** XGBoost on OBP and SLG will not beat linear
regression on OBP and SLG by anything that survives a backtest. XGBoost on park-adjusted,
shrunk, bullpen-aware, home-field-aware features might beat linear regression on the same —
but then it was Lane A that did the work.

A hierarchical Bayesian model (team strength as a latent parameter with a prior, updated
game by game) is the more interesting choice for this product specifically, because it gives
B4's uncertainty for free and handles A6's shrinkage natively as a consequence of the prior
rather than as a bolted-on correction. It is also much harder to explain, which costs the
product its receipts.

🟡: a boosted tree cannot produce the per-feature contribution receipts that
`inference.py:64-81` emits today. If the model becomes a black box, "every derived number
ships a receipt" becomes "here is a SHAP value", which is a materially weaker claim. That
trade should be made consciously or not at all.

### B6. Ensemble SEASON and ADJ rather than reporting two prices — Lift 3, Effort M, 🟢
Today the user gets two numbers and no guidance on which to use, which is honest but not
helpful. Once the ledger has enough graded rows to say which is better *and under what
conditions* (starters confirmed? late season? large spread?), the correct output is one
price from a weighted blend, with the weights themselves derived from the record and
disclosed.

Requires real sample size. Do not attempt before the ledger is deep.

### B7. Feature-importance and ablation reporting — Lift 2, Effort S, 🟢
Once A2 exists, running the chain with each feature ablated and reporting the log-loss delta
is nearly free, and it is genuinely good content — "here is what each input is worth" is
both a research artifact and marketing for the product's transparency claim.

### B8. Retraining cadence and drift monitoring — Lift 2, Effort M, 🟢
Coefficients are baked into a joblib at build time (`precompute.py:186`) and loaded once
(`inference.py:18-22`, `lru_cache`). Nothing detects that the run environment has drifted
away from the fit. A scheduled job that computes current-season residuals against the
model's expectations and alerts on drift is cheap insurance.

---

## Lane C — Actual LLM features

Ranked, and prefaced with the honest framing the product's own doctrine demands:

> **None of this creates predictive edge.** Not one item in Lane C will make a price more
> accurate. Lane C buys comprehension, retention, conversion, and speed of research. Those
> are worth real money — but a product built on refusing fake precision must not market an
> LLM as if it were a model improvement.

Use `claude-sonnet-5` for the interactive paths and `claude-haiku-4-5` for the
high-volume classification ones; `claude-opus-5` only where reasoning depth actually pays.

### The non-negotiable guardrail for all of Lane C

**The LLM never produces a number.** Every figure in generated prose must be present in a
structured payload computed by the deterministic engine, passed in as context. Enforce it
mechanically: a post-generation validator extracts every numeral from the output and asserts
each appears in the source payload; a failure returns the deterministic text, not the
generated text. Temperature 0.

Without that validator, one hallucinated fair line destroys the receipts claim the entire
product is built on. With it, Lane C is 🟢 throughout.

### C1. Reason bullets on every price — Lift 4, Effort M, 🟢
The highest-value Lane C item, and it is **mostly not an LLM feature.**

`v3-plan.md` Tier 3 item 4 (`model_detail` on slate rows + `backend/explain.py`) is the
deterministic core: `feeds._chain_probability` currently discards the `predict_from_inputs`
receipts, so there are no reason bullets anywhere in the product. Build that first —
ranking contributions by `analytics.runs_per_win` is read-only and already designed
(`notes/explain-design.md`, 659 lines of it).

The LLM's job is only to turn `{feature, value, coefficient, contribution}` tuples into a
sentence a human enjoys reading. That is a genuine improvement over a template, and it is a
thin, safe wrapper over a deterministic engine.

Order matters: `explain.py` without the LLM is a good feature. The LLM without `explain.py`
is a hallucination machine.

### C2. Chat with the desk — Lift 4, Effort L, 🟢
Tool-use over the 29 existing API routes. "Who does the model like tonight?" "Why is it on
the Rays?" "Show me every game where we disagree with my book by more than 3 points."
"What's my record on road favourites?"

This is the most natural Pro-tier feature in the catalog: it is expensive per call, it is
obviously valuable, it is gated cleanly by `has_feature` (`billing.py:59`), and it turns the
existing API surface into product without new backend work. Every answer is grounded in a
tool call, which is exactly the guardrail C1 needs, structurally enforced.

### C3. News → structured signal, replacing the keyword lexicon — Lift 3, Effort M, 🟢
The pulse lexicon (`analytics.py:26-35`) is a keyword matcher with known defects recorded in
`v3-plan.md`: "streak" and "losing streak" both match and double-count, and `_matches`
(`:282-285`) has a leading word boundary but no trailing one, so **"torn" matches
"tornado"**. A small classifier does this strictly better.

Doctrine is untouched: pulse is disclosure-only and provably never reaches a price (traced
and verified in `v3-plan.md`). Replacing the classifier does not change that, and it should
be re-verified after the change so the claim stays checkable by inspection.

Use `claude-haiku-4-5` — this is high-volume, low-difficulty classification.

### C4. Daily brief, written and delivered — Lift 3, Effort M, 🟢
One generated page each morning: the slate, where the model disagrees most, what changed
since yesterday, what the record did. Email (`backend/mailer.py` already exists) or push.

Retention feature, and the single best answer to "why would I open this app every day?" It
also creates the habit loop that makes a subscription renew.

### C5. Parlay critique in plain language — Lift 2, Effort S, 🟢
The correlation refusal (`main.py:1001-1007`, extended for doubleheaders in `bf1e7ab`) is
correct and terse. An LLM explaining *why* correlated legs are mispriced — with the user's
actual slip as the example — turns a rejection into a lesson. Good onboarding, low risk.

### C6. Onboarding and jargon explainer — Lift 2, Effort S, 🟢
"What is log5?" "What does −150 mean?" "Why is the model refusing?" Inline, contextual.
MONEYLINE's vocabulary is genuinely dense; this lowers the bar to the Analyst tier.

### C7. Auto-generated SEO research content — Lift 2, Effort M, 🟡
`seo_strategy.md` currently lists primary keywords as "Unknown". Generated per-team and
per-matchup research pages would rank.

🟡 and grudging: mass-generated content is exactly the low-trust move MONEYLINE's whole
posture is against, and Google has gotten good at detecting it. If done at all, generate
from real computed model output (which is genuinely unique data) and never from a prompt
alone.

### C8. Natural-language pick logging — Lift 1, Effort S, 🟢
"I took the Rays −120 for two units" → structured ledger row. Convenience only, but it
removes the friction that makes betting logs die.

---

## Part I ranked — all three lanes against each other

Lift-per-effort, best first. This is the ordering the plan document uses.

| # | Item | Lane | Lift | Effort | Doctrine |
|---|---|---|---|---|---|
| 1 | **Game-level backtest harness** (A2/B1) | A+B | 5 | L | 🟢 |
| 2 | **Home-field advantage** (A1) | A | 5 | M | 🟡 |
| 3 | **Shrinkage on early-season rates** (A6) | A | 4 | M | 🟢 |
| 4 | **Refit RA off 90 rows** (A3) | A | 4 | M | 🟢 |
| 5 | **Park factors** (A5) | A | 4 | M | 🟢 |
| 6 | **Calibration layer + reliability** (B2) | B | 4 | M | 🟢 |
| 7 | **Champion–challenger registry** (B3) | B | 4 | M | 🟢 |
| 8 | **Reason bullets / `explain.py`** (C1) | C | 4 | M | 🟢 |
| 9 | **Uncertainty intervals** (B4) | B | 4 | M | 🟢 |
| 10 | **Chat with the desk** (C2) | C | 4 | L | 🟢 |
| 11 | **Bullpen modelling** (A7) | A | 4 | L | 🟢 |
| 12 | **Modern-era challenger bundle** (A4) | A | 4 | M | 🟡 |
| 13 | Pythagenpat (A10) | A | 2 | S | 🟢 |
| 14 | Lineups (A8) → platoons (A9) | A | 3 | L | 🟢 |
| 15 | Statcast inputs (A12) | A | 3 | L | 🟡 |
| 16 | News classifier (C3) | C | 3 | M | 🟢 |
| 17 | Defense/pitching split (A11) | A | 3 | L | 🟢 |
| 18 | Daily brief (C4) | C | 3 | M | 🟢 |
| 19 | Ensemble SEASON/ADJ (B6) | B | 3 | M | 🟢 |
| 20 | Boosting / Bayes (B5) | B | 3 | L | 🟡 |
| 21 | Weather/umpire/travel (A13) | A | 2 | M | 🟡 |
| 22 | Everything else | — | 1–2 | — | — |

**The top two are worth more than items 3–22 combined,** and the first one is not a model
change at all.
