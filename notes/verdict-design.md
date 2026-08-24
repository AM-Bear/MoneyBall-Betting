# Verdict engine — design groundwork

Tier 3 item 3: `backend/verdict.py` + `POST /api/evaluate` + the GameCard verdict slot.

Written 2026-08-24, read-only lane. **No code exists yet.** This document is the thing to
review before any is written. Every number below was reproduced against the live
`backend/odds.py` (transcript in §2.3), not copied from a doc.

**Source correction up front.** Appendix A is **not** in the v2 spec
(`attached_assets/moneyline_v2_expansion_replit_prompt_1787245184521.md` — 165 lines, no
appendices, no verdict engine). It is in
`attached_assets/MONEYLINE_v3_Product_Strategy_and_UX_Plan_1787528143354.md:1305-1350`.
The v2 spec is superseded here and contributes nothing to this item. Line references below
are to the v3 strategy doc (`[S:nnn]`) and the repository audit
(`attached_assets/MONEYLINE_Repository_Audit_and_v3_Strategy_1787533744890.md`, `[A:nnn]`).

---

## 1. Composition over `odds.py`

### 1.1 The rule

`evaluate()` is **pure over probabilities and prices**. It does not touch team inputs, does
not load models, does not fetch, and does not re-run the price chain. `p_season` and
`p_adj` arrive already computed by `feeds._chain_probability` (`feeds.py:302-314`) or by
whatever caller has them. `odds.py` is imported and **not modified** — no new function, no
signature change, no docstring fix.

### 1.2 Exact arithmetic, per side

Given a side's evaluation probability `p_eval` and an American price `price`:

| Quantity | Expression | Existing function |
|---|---|---|
| `q` (implied / breakeven) | `abs(price)/(abs(price)+100)` if `price<0` else `100/(price+100)` | `odds.moneyline_to_probability(price)` — `odds.py:21-25` |
| `edge` | `p_eval − q` | `odds.edge_probability(p_eval, price)` — `odds.py:28-30` |
| `decimal` | `1 + 100/abs(price)` if `price<0` else `1 + price/100` | `odds.decimal_odds(price)` — `odds.py:42-46` |
| `ev` (per 1 unit) | `p_eval·(decimal − 1) − (1 − p_eval)` | `odds.parlay_ev(p_eval, odds.decimal_odds(price))` — `odds.py:92-96` |
| `fair` (display) | probability → American, nearest 5 | `odds.probability_to_moneyline(p_eval)` — `odds.py:8-18` |
| `chance_lose` | `1 − p_eval` | none needed |
| `gap` (signal) | `edge / σ`, σ = 0.04 | none needed |

Payload fields are the scaled forms: `edge_pts = edge × 100`, `ev_per_100 = ev × 100`.
Both are **rounded for display only** — see §1.5.

`p_eval = p_adj if p_adj is not None else p_season` `[S:1309]`.
`agree = (ev_season > 0) == (ev_adj > 0)`, defined only when both exist `[S:1309]`.
For that, `ev_season` and `ev_adj` are each computed by the same `parlay_ev(·, decimal)`
call against the same `price` — one `decimal_odds(price)` call reused, not two.

### 1.3 Where I would otherwise be tempted to re-derive — do not

Five places. Each is a number `odds.py` already computes; re-deriving it is how a second,
silently divergent implementation of the price math gets born.

1. **EV.** `odds.parlay_ev` (`odds.py:92-96`) is literally
   `probability * (decimal_payout - 1) - (1 - probability)` — Appendix A's EV formula
   `[S:1309]` character for character. Its *name* says parlay; its *body* is generic
   per-unit EV and the parlay path only ever hands it a compounded decimal. **Reuse it.**
   Writing `p*(d-1)-(1-p)` inline in `verdict.py` would be a second copy of the EV
   definition, and the two would drift the first time anyone touches either.
   The alternative — adding a `single_ev` alias to `odds.py` — is cleaner naming but
   violates "odds.py unchanged". Recommendation: reuse `parlay_ev` and carry a one-line
   comment at the call site saying why a parlay-named function appears here.
   *Reviewer's call; flagging it rather than deciding it.*
2. **Implied probability.** Never hand-write `abs(line)/(abs(line)+100)`.
   `moneyline_to_probability` already handles the sign split and the zero/non-finite guard.
3. **Edge.** `edge_probability(p, line)` is exactly `p − implied(line)`. Do not compute
   `p_eval - q` locally even though `q` is already in hand for `breakeven` — call
   `edge_probability` and let `q` come from the same `moneyline_to_probability` call, so
   `edge` and `breakeven` provably agree.
4. **Fair price.** `probability_to_moneyline` rounds to the nearest 5 (`odds.py:18`). The
   plan says leave that rounding alone; the `INSUFFICIENT_DATA (no_price)` state has to
   print a fair line `[S:1343]` and it must be this one, not an unrounded variant.
5. **`p_season` / `p_adj` themselves.** `pythagorean_strength` (`odds.py:131-135`) and
   `log5_probability` (`odds.py:138-147`) belong to the price chain upstream. `verdict.py`
   must **not** import or call them. If it did, the desk would have two independent chains
   producing "the model's chance" and the `/api/slate` diff would stop being a proof of
   anything. They are the coordinator's list but they are not this module's dependencies.

### 1.4 Two functions on the coordinator's list that Appendix A does not use

- **`market_vig`** (`odds.py:33-39`). Appendix A never references the overround. Vig enters
  v3 at Appendix C step 1 as the *de-vig* for stake sizing (`q_side/(q_side+q_other)`,
  `[S:1382]`), which is `POST /api/stake`, a different item. Reporting `vig_pp` alongside
  the verdict as information is defensible, but it is **display, not a threshold input**.
  This matters: the *current* `/api/matchup` verdict is built on
  `vig_threshold = max((vig or 0.0476)/2, 0)` (`main.py:557`). Appendix A's thresholds are
  absolute (`ev ≤ −0.05`, `edge ≥ 0.03`), **not vig-relative**. The new engine must not
  inherit the half-the-vig rule. Two different rulesets, and mixing them silently is the
  most likely way this ships wrong.
- **`half_kelly_fraction`** (`odds.py:49-56`). Appendix A produces no stake. Staking is
  Appendix C `[S:1380-1389]` with *full* Kelly on a shrunk chance and a profile
  fraction+cap — a different formula, a different endpoint (`POST /api/stake`).
  `/api/evaluate` should return **no Kelly field at all.**
  The uncapped-Kelly hazard is real and confirmed live:
  `half_kelly_fraction(0.99, +1000) → 0.4945` — 49% of bankroll, despite the docstring
  saying "capped". `smoke_test` pins that behavior, so the function stays as-is and the cap
  lives in whatever display layer shows a stake. Since `/api/evaluate` shows no stake, the
  cleanest respect for that constraint is **not to call `half_kelly_fraction` here.**

### 1.5 Rounding discipline — decide before writing

Thresholds are in raw probability units (`0.01`, `0.03`, `0.04`, `0.05`); the fixtures are
stated in display units (points, per-$100). **Compare raw, round for display.** Rounding
first creates a boundary lie: a raw edge of `0.0096` displays as `+1.0` points, which reads
as satisfying `edge ≥ 0.01` while the raw comparison correctly fails it. Fixture 2's SD leg
is the near-miss that proves the point — raw `0.005556` displays `+0.6`, and it is
`NO_VALUE` because `0.005556 < 0.01`.

`round(x, 1)` for `edge_pts` and `ev_per_100`; `round(gap, 2)`; probabilities `round(·, 4)`
to match the existing convention (`main.py:585-590`, `feeds.py:347`).

### 1.6 Thresholds are data, not literals

`AVOID_EV = -0.05`, `NO_VALUE_EDGE = 0.01`, `CANDIDATE_EV = 0.04`, `CANDIDATE_EDGE = 0.03`,
`SIGMA = 0.04`, `STALE_SECONDS = 900`, `GP_HARD_FLOOR = 30`, `GP_SMALL_SAMPLE = 60`,
`GP_MODERATE = 100`, `SIGNAL_PROVISIONAL_N = 200` live in one `THRESHOLDS` dict in
`verdict.py` and are **returned in every response** `[A:1196]`, published so a reader can
audit the rubric `[S:220]`.

These are **not** model coefficients and do not come from `load_models()`. The no-hardcoded-
coefficients doctrine binds the regression stack (`analytics.py:38-46`,
`inference.py:42-71`); verdict thresholds are declared policy, which is why the spec says
they are changeable "only with a changelog entry" `[S:1322]`. The honest handling is to ship
them in the payload with the model version, not to launder them through the model loader.

**`MODEL_VERSION` is a dependency.** `[A:1196]` requires the thresholds block to carry it.
Today it is the literal `"chronological-1962-2001-v1"` at `main.py:449` and again at
`status-strip.tsx:18`. Tier 3 item 2 (`MODEL_VERSION` constant) is ordered before this item
in `notes/v3-plan.md` and should stay that way — otherwise this adds a third copy.

### 1.7 Doctrine check

`evaluate()`'s inputs are: two probabilities, two prices, two games-played counts, a
starters-confirmed boolean, a price age, and a game status. **No pulse, no injury flags, no
wire.** `game.flags` and pulse render in the card's context row as "not in the price"
(`game-card.tsx:157-168`, already labeled "Context only · does not move a price") and never
reach this module. That is checkable by inspection: `verdict.py` imports only `odds` and the
stdlib — no `wire`, no `feeds`, no `analytics`.

---

## 2. The ten Appendix A fixtures

`[S:1337-1350]`. **There are exactly ten.** All ten reproduce exactly against `odds.py`.
Ambiguities are recorded in §2.2 — none of them required inventing a number.

### 2.1 Transcribed

Common defaults where the fixture is silent: `gp 126/126`, starters confirmed, price fresh,
status scheduled, `p_adj` absent (so `p_eval = p_season`). σ = 0.04.

| # | Spec line | Inputs | Expected output |
|---|---|---|---|
| 1 | `[S:1341]` | `p 0.58`, price `−115`, `gp 126/126`, starters confirmed, fresh | `edge +4.5` pts, `EV +8.4`/100, `BET_CANDIDATE`, `gap 1.13` → **Strong** |
| 2 | `[S:1342]` | LAD `p 0.55` at `−150`; SD `p 0.45` at `+125` | LAD: `edge −5.0`, `EV −8.3` → `AVOID_AT_THIS_PRICE`. SD: `edge +0.6`, `EV +1.25` → `NO_VALUE`. Game: `NO_VALUE` + `avoid_note` naming LAD |
| 3 | `[S:1343]` | `p 0.53`, no price | `INSUFFICIENT_DATA (no_price)`; fair `−115` still shown |
| 4 | `[S:1344]` | `p 0.60` at `+150` | `edge +20.0`, `EV +50.0`, `BET_CANDIDATE`, **Strong** |
| 5 | `[S:1345]` | `p 0.52` at `−110` | `edge −0.4`, `EV −0.7`, `NO_VALUE` |
| 6 | `[S:1346]` | `p 0.58` at `−130` | `edge +1.5`, `EV +2.6`, `MARGINAL_VALUE`, `gap 0.37` → **Weak** |
| 7 | `[S:1347]` | `p_season 0.58`, `p_adj 0.54`, price `−115` | evaluated on `0.54`: `edge +0.5` → `NO_VALUE`; note that the season price alone would have shown value |
| 8 | `[S:1348]` | `gp 18/20` | `INSUFFICIENT_DATA (early_season)`; model chance still displayed |
| 9 | `[S:1349]` | fixture 1, price 40 minutes old | `BET_CANDIDATE` + `stale` flag |
| 10 | `[S:1350]` | fixture 1, `p_adj` null | `BET_CANDIDATE`, signal capped **Moderate**, flag `starters_unconfirmed` |

### 2.2 Underspecification — stated, not filled

Nine gaps. None invalidates a fixture; each is a decision the reviewer should make before
code, not a number I should invent.

1. **Fixture 4 states no `gp`, no starter status, no price age**, yet expects **Strong** —
   which `[S:1333]` grants only with `agree` *and* complete data. The fixture is only
   consistent if unstated fields default to complete. Stated as an assumption above, not
   silently absorbed.
2. **Fixture 7's note has no field name.** `[S:1347]` says "note that the season price alone
   would have shown value"; `[A:1196]` calls fixture 7 "`NO_VALUE` with a note". The
   `EvaluationDTO` `[S:~1290]` has `verdict_reason` and `avoid_note` but no season-vs-adj
   note field. Proposal: `basis_note`, emitted when the season-price verdict would have
   been `BET_CANDIDATE` or `MARGINAL_VALUE` while the evaluated verdict is not. **Naming
   and trigger condition need sign-off.** This is also *not* `prices_disagree`: at
   0.58/0.54 both EVs are positive, so `agree` is true.
3. **Fixture 9 does not state the signal.** By `[S:1333]` a stale price is a missing
   ingredient, so `gap 1.13` with one ingredient missing → **Moderate**. Derivable, but the
   fixture does not assert it, so the test should assert what the spec derives and the
   review should confirm that reading.
4. **Rule precedence within the verdict table.** `[S:1324-1329]` lists `AVOID` first and its
   rule (`ev ≤ −0.05`) is a strict subset of `NO_VALUE`'s (`ev ≤ 0`). Table order is the
   only thing implying precedence. Must be evaluated top-down; fixture 5 (`ev −0.007`) is
   the case that separates them, and it is `NO_VALUE`, confirming the reading.
5. **Fixture 2 mixes precision conventions** — SD's `EV +1.25` is 2 d.p. while every other
   fixture is 1 d.p. The raw value is exactly `+1.250`, so this is presentational only. The
   test should assert the raw value, not the string.
6. **Both sides candidate simultaneously.** `[S:1331]` says "best side by `ev` among
   candidates and marginals" but does not define the tie-break, and with user-supplied
   prices (§3.1) nothing forbids two positive-EV sides — a real book's vig forbids it, a
   typo does not. Proposal: highest `ev`, ties broken by higher `edge`, then home. **Needs
   sign-off.**
7. **"−200 or shorter" / "+150 or longer"** `[S:1335]`. Betting idiom: shorter = bigger
   favorite, so `price ≤ −200` → Lower volatility; `price ≥ +150` → Higher. Reading is
   confident but the phrasing is directional-ambiguous in code review, so pin it in a
   comment.
8. **Signal for `agree` when `p_adj` is null.** `[S:1333]` requires `agree` for Strong;
   `agree` is undefined without `p_adj`. Fixture 10 resolves it: cap at Moderate. Good — but
   that means "undefined `agree`" and "`agree` false" behave differently, and the spec never
   says so in prose. Worth an explicit branch and a comment.
9. **Status gate needs a status vocabulary.** `[S:1315]` freezes the verdict when status is
   live, final, or postponed. The frontend already owns exactly these predicates in
   `lib/game-status.ts:5-15` (regex over `game.status`). The backend has no equivalent. Do
   not write a second regex — either the caller passes a normalized enum
   (`scheduled|live|final|postponed`) in the request body, or a shared helper is extracted.
   **Recommend the request-body enum**, which keeps `evaluate()` pure and keeps status
   parsing in one place.

### 2.3 Verification transcript

Reproduced 2026-08-24 against `backend/odds.py` at `bb4d90f`, σ = 0.04:

```
F1 p.58 @-115      q=0.534884  edge= +4.51pts  ev= +8.435/100  gap=1.128  fair=-140
F2 LAD .55 @-150   q=0.600000  edge= -5.00pts  ev= -8.333/100            fair=-120
F2 SD  .45 @+125   q=0.444444  edge= +0.56pts  ev= +1.250/100  gap=0.139 fair=+120
F4 p.60 @+150      q=0.400000  edge=+20.00pts  ev=+50.000/100  gap=5.000 fair=-150
F5 p.52 @-110      q=0.523810  edge= -0.38pts  ev= -0.727/100            fair=-110
F6 p.58 @-130      q=0.565217  edge= +1.48pts  ev= +2.615/100  gap=0.370 fair=-140
F7 p_adj .54 @-115 q=0.534884  edge= +0.51pts  ev= +0.957/100            fair=-115
F7 p_szn .58 @-115 q=0.534884  edge= +4.51pts  ev= +8.435/100  (both EV > 0 → agree)
F3 fair(0.53) = -115
```

Every displayed expectation in Appendix A matches at 1 d.p. Fixture 6's `gap 0.370` matches
the spec's stated `0.37` exactly, which is a good independent check that σ = 0.04 and
`gap = edge/σ` were read correctly. Fixture 1's `1.128` rounds to the spec's `1.13`.

**No fixture had to be invented, and no gap was filled with my own arithmetic.**

### 2.4 The one thing the fixtures do not cover

There is no fixture for `min(gp) < 60` (`small_sample` flag, uncertainty ≥ Moderate)
`[S:1320]`, none for `prices_disagree` (a would-be candidate with `agree` false)
`[S:1328]`, and none for the volatility bands `[S:1335]`. Those rules ship untested by
Appendix A. Recommend adding hand-checked cases for all three and saying in the test file
that they are **desk-authored, not Appendix A** — so a later reader can tell which
expectations carry spec authority and which carry ours.

---

## 3. `POST /api/evaluate`

### 3.1 The premise this endpoint rests on — read this first

**MONEYLINE ingests no odds provider.** Verified in the Tier 1 work
(`notes/v3-plan.md`, `entered_line` reframe): zero sportsbook references in `backend/`, and
the UI says so outright (`presentation-preferences.tsx:64`, "Book price = your manual
input"). Appendix A is written assuming a live feed — "prices per side per book with
timestamps", "the user's selected books determine `price_used`" `[S:1307]`, and a
15-minute staleness gate `[S:1318]`.

So: **every price reaching `/api/evaluate` today is user-typed.** That has three
consequences the design must carry rather than paper over.

- `price_age_s` is meaningful only once a feed exists. For manual entry it should be
  **omitted**, and the `stale` flag simply never fires. Do **not** synthesize an age from
  request arrival time — that would be a fabricated freshness claim, which is the same
  species of error as writing `entered_line = fair_line`.
- `book` is optional and, when present, is a user-supplied label. Appendix B's copy
  templates say "{Book} has {X} at {price}" `[S:1368]`; with no book, the phrasing must fall
  back to "your price", matching the existing `evaluationLabel` convention
  (`edge-finder.tsx:208`).
- Fixture 9 is therefore **testable but not currently reachable in production.** It should
  still be implemented and tested — the field is designed for the feed that Decision A
  `[A:~580]` is about — but the design should say plainly that it is dormant.

### 3.2 Request

```
POST /api/evaluate
{
  "p_season_home": 0.58,          // required, 0 < p < 1
  "p_adj_home":    0.54,          // optional, null when starters unconfirmed
  "price_home":   -115,           // optional; |x| >= 100, != 0
  "price_away":    105,           // optional; independent of price_home
  "gp_home":       126,           // optional int >= 0; null => early_season gate fires
  "gp_away":       126,
  "starters_confirmed": true,     // optional, default false
  "price_age_s":   null,          // optional; null => no staleness claim (see §3.1)
  "status": "scheduled",          // scheduled | live | final | postponed
  "book": null                    // optional user-supplied label
}
```

Two prices, not one. The DTO table `[S:~1268]` shows `POST /api/evaluate` taking a single
`price`; `[A:1196]` shows `evaluate(..., price_home, price_away, ...)`. **The two docs
disagree and the audit is right** — a one-price endpoint would reproduce the exact
one-sidedness this item exists to fix (§5). Both sides, always.

Only home probabilities are supplied: away is `1 − p_home`, matching `_price_game`
(`feeds.py:378-380`) and `matchup` (`main.py:538`). Passing both would let a caller submit
an incoherent pair.

Pydantic model `EvaluateInput` next to `MatchupInput` (`main.py:143-156`), reusing its
moneyline validator idea verbatim — `line == 0 or abs(line) < 100` raises, which the
existing `RequestValidationError` handler (`main.py:403-410`) turns into
`{"error": {"code": "invalid_request", ...}}` at 400. `p` bounds go on the field
(`Field(gt=0, lt=1)`) exactly like `TeamStats` (`main.py:103-106`), so
`probability_to_moneyline`'s own `ValueError` (`odds.py:10-11`) is unreachable from HTTP.

### 3.3 Response

```
{
  "sides": {
    "home": { "p_eval", "p_basis": "adj"|"season", "price", "implied", "breakeven",
              "edge_pts", "ev_per_100", "fair_line", "chance_lose",
              "verdict", "verdict_reason", "signal", "signal_provisional",
              "volatility", "uncertainty", "flags": [...], "basis_note": null },
    "away": { ...same shape... }
  },
  "game": {
    "side": "home"|"away"|null,      // the value side; null when no side qualifies
    "verdict": "...",
    "lean_side": "home"|"away"|null, // from p_eval alone, price-independent
    "lean_differs_from_value": bool, // the whole point — see §5
    "avoid_note": null,
    "takeaway": "..."                 // Appendix B; may be deferred to item 4
  },
  "sample": { "gp_home", "gp_away", "label": "THRU 126 GP" },
  "thresholds": { ...§1.6..., "sigma": 0.04 },
  "model_version": "...",
  "caveat": EQUITY_CAVEAT
}
```

`verdict` ∈ `BET_CANDIDATE | MARGINAL_VALUE | NO_VALUE | AVOID_AT_THIS_PRICE |
INSUFFICIENT_DATA`. `flags` ⊆ `no_price | early_season | stale | starters_unconfirmed |
small_sample | prices_disagree`, per `[S:~1290]`.

`EQUITY_CAVEAT` (`main.py:88-91`) is the exact text the "not priced" chips need and
currently renders nowhere (`notes/v3-plan.md`, UI debt). Returning it here gives it its
first home.

### 3.4 Envelope and placement

Nothing new. `_error_response` (`main.py:158-162`) and the three registered handlers
(`main.py:398-418`) already produce `{"error": {"code", "message"}}` for every path:
validation → 400 `invalid_request`; `MoneylineError` → its own code; anything else → 500
`internal_error`. `evaluate()` should raise `MoneylineError` for nothing — every degenerate
input is either a validation error or a gated `INSUFFICIENT_DATA` payload, which is a 200.
That is the honest-refusal shape: a refusal is a result, not an error.

**Placement: immediately after `POST /api/matchup`, i.e. after `main.py:606`, before
`GET /api/slate` at `main.py:610`.** It is the successor to `/api/matchup`'s verdict block
and belongs next to it for diffing. `EvaluateInput` goes after `MatchupInput`
(`main.py:156`).

**`/api/matchup` is not touched** — same shape, same four terminal verdict strings
(`main.py:565-573`), same `evaluation_side`, same vig-relative threshold. It keeps serving
the historical Matchups tool and H2H `[A:~586]`. Two rulesets coexist by design; see §1.4.

### 3.5 What the verdict must refuse

Honest refusals over fake numbers:

- **No price on a side** → that side is `INSUFFICIENT_DATA (no_price)`. It still publishes
  `p_eval` and `fair_line`. It does **not** publish `edge_pts`, `ev_per_100`, or a signal —
  there is nothing to be edgy against. `EdgeStat` is "hidden entirely when no price"
  `[S:~1270]`.
- **`min(gp) < 30`, or gp unknown** → `INSUFFICIENT_DATA (early_season)`, both sides, no
  verdict, model chance still shown `[S:1317, 1348]`. Missing gp must gate, not default to
  a large number.
- **Live / final / postponed** → no verdict at all `[S:1315]`. Pre-game evaluation is frozen
  for grading. The card already has the copy for this (`game-card.tsx:218-232`).
- **Signal strength is provisional** until 200 graded candidates in the bucket `[S:1333]`.
  `signal_provisional: true` ships hardcoded true until the record can compute the count —
  and the *reason* it is true must be in the payload, not just the flag.
- **σ = 0.04 is a placeholder** — "revised from live calibration" `[S:1333]`. The `gap`
  number is therefore not a calibrated statistic. It should carry that in the thresholds
  block rather than being presented as measured.
- **No stake, no Kelly** (§1.4). Not a refusal of the user, a scope boundary: staking is
  `POST /api/stake`.
- **No 2027, no hitter-vs-pitcher** — inherited boundaries, unaffected.

### 3.6 Data prerequisite: games played is not on slate rows

`_team_inputs` (`feeds.py:~245`) returns `obp/slg/oobp/oslg` and nothing else, so
`_price_game`'s row (`feeds.py:365-393`) carries **no `gp`**. The `min(gp)` gates therefore
have no source in the slate payload today.

For `POST /api/evaluate` this is fine — gp arrives in the request body. But `[A:257]` also
wants verdicts "merged into slate rows", and that step needs gp plumbed into `_price_game`.
It exists in the codebase already: `games_played` from standings (`feeds.py:721`) and the
`THRU {n} GP` label (`feeds.py:949`). **Treat that as a separate change** with its own
byte-identical `/api/price` and `/api/slate` diff — do not smuggle it into this item.

---

## 4. Where the verdict slot mounts

`artifacts/moneyline/src/components/game-card.tsx`. Rendered only from
`tabs/today.tsx:180`.

### 4.1 The three layers as they exist today

| Layer | `[S:404-412]` | In code | Lines | CSS |
|---|---|---|---|---|
| 1 — the answer | identity, **verdict pill + takeaway**, comparison line, edge line, chip row | identity + time + status + lean + fair price | `54-94` | `.game-card-answer` (`index.css:229`) |
| 2 — the explanation | why the lean, why a candidate, context chips, risk | "Explanation and context" `<details>` | `136-174` | `.game-card-disclosure` |
| 3 — the numbers | two-side table, receipts, blend, Kelly | "Advanced numbers and receipts" `<details>` | `176-238` | `.game-card-advanced` |

Between layers 1 and 2 there is an unnamed summary band, `.game-card-summary`
(`index.css:241`), at `game-card.tsx:96-134`. It currently holds status labels
(`98-101`), a paragraph (`102-106`), starter links (`107-127`), and the "Model values are
estimates" hint (`128-132`).

Layer 1 has **no verdict pill and no takeaway.** That is the structural absence
`notes/v3-plan.md` describes.

### 4.2 Insertion point

**Two slots, per `[A:587]`** — a verdict pill and a separate data-status chip row, because
"insufficient data" is a data state, not a judgment, and the two can coexist.

- **Verdict pill + takeaway → `game-card.tsx:82`**, immediately after the `modelLean`
  paragraph (`77-82`) and still inside the `min-w-0` column that closes at line 83, so it
  sits under the matchup headline and above the fold, inside `.game-card-answer`. It must
  be *below* the lean line, not replacing it: showing the lean and the value side adjacently
  is precisely what makes "lean is not the value side" legible rather than hidden.
- **Data-status chip row → `game-card.tsx:101`**, appended to the existing flex row at
  `97-101` that already renders `Model only` / `Starter-adjusted available` /
  `Starter data incomplete`. Those are already data-status chips in everything but name;
  `stale`, `small_sample`, `no_price` join them rather than starting a competing row.
- **`.game-card-verdict` is a new class in `index.css`** beside `.game-card-price-block`
  (`index.css:238-240`). Not color-only — icon plus sentence-case text, `aria-label`
  including the side `[S:~1266]`.

Everything else on the card is left alone. The `game.flags` context block
(`157-168`) already carries "Context only · does not move a price" — that stays exactly
where it is, in layer 2, and the verdict never reads it.

### 4.3 The paragraph at `game-card.tsx:102-106` becomes wrong

> "A value comparison appears only after you enter a valid book price."

Accurate today. Once the pill exists it needs rewording, because the pill will render
`INSUFFICIENT_DATA (no_price)` — a verdict slot that is populated and honest — before any
price is typed. Small, but it is user-facing copy that the change invalidates, so it belongs
on the checklist rather than being discovered later.

---

## 5. The failure this fixes, concretely

**Claim: with a slate game selected, the card evaluates the away side only, and prints its
one-sided answer in the position a game-level verdict occupies.**

The chain, in order:

1. `game-card.tsx:210-215` mounts `<EdgeFinder activeSlateGame={game} deferUntilBookLine />`
   inside layer 3, gated on `priceCheckState === "available"` (`204`).
2. `edge-finder.tsx:58-63`: with `activeSlateGame` set, **A is bound to away**
   (`inputsA = activeSlateGame.away_inputs`) and **B to home**. Not user-selectable — the
   opponent picker is suppressed at `152` whenever `activeSlateGame` is truthy.
3. **`edge-finder.tsx:95` — the defect:**
   ```js
   evaluation_side: isValidA ? "a" : "b",
   ```
   The evaluated side is "a" whenever the away price parses. **Entering both prices still
   evaluates away only.** The home price survives solely as `book_line_b`, and
   `main.py:559-566` uses it for one thing: `market_vig`. It is never scored.
4. `main.py:543-544`: `evaluated_probability` / `evaluated_line` collapse to the single
   selected side. `main.py:565-573` produces one string. `main.py:576-579` produces one
   half-Kelly, for that same side.
5. `edge-finder.tsx:204-206` renders that string in a `text-lg` badge, alone, centered, in a
   panel headed `EDGE FINDER` (`126`) — visually the card's answer, with only an 11-px
   caption at `208` ("Your price: {label}") naming which side it refers to. The three
   stat tiles at `212-227` — Model Edge, B/E Rate, ½ Kelly — are all that one side too.

**The live failure.** Take a game where the model leans home. `game-card.tsx:77-82`
prints "*{home} has the model lean* · 58% home". The user types both prices. The card then
shows a large `NO VALUE` badge — computed for **away**, the side the model does *not* lean —
next to a lean line naming home. The reader has no way to tell that:

- the badge answers a different question than the lean line above it;
- the home price they entered was never evaluated;
- if the home price were the one with value, nothing on the card would say so.

`[A:586]` states the same finding independently: *"with a slate game selected, the Edge
Finder evaluates the away team only, so a favorable price on the home side is never
surfaced."*

**Two distinct errors, both fixed by the same change.** (a) A one-sided verdict is presented
in a game-level slot. (b) The value side is never *identified* — Appendix A's game verdict
is "the best side by `ev` among candidates and marginals" `[S:1331]`, and the takeaway is
required to name the value side *and say when it differs from the lean* `[S:1370]`. Today
the card has no concept of a value side at all; it has a lean and a badge, and silently
invites the reader to fuse them.

That is why `lean_side` and `lean_differs_from_value` are explicit fields in §3.3 rather
than something the frontend infers. The failure is that the two got conflated; the payload
should make separating them the path of least resistance.

**Not being fixed here:** `/api/matchup` keeps its one-sided `evaluation_side` contract for
the historical Matchups tool and H2H `[A:~586]`. The card stops depending on it.

---

## 6. Open decisions for review

1. §1.3(1) — reuse `parlay_ev` for single-bet EV, or accept one additive function in
   `odds.py`? Recommend reuse.
2. §2.2(2) — name and trigger for fixture 7's season-vs-adjusted note. Proposed `basis_note`.
3. §2.2(6) — tie-break when both sides qualify. Proposed `ev`, then `edge`, then home.
4. §2.2(9) — game status as a request-body enum vs. a shared backend predicate. Recommend
   the enum.
5. §2.4 — add desk-authored tests for `small_sample`, `prices_disagree`, and volatility,
   labeled as not-Appendix-A?
6. §3.1 — confirm `price_age_s` stays null under manual entry and the `stale` path ships
   dormant.
7. §1.6 — this item depends on Tier 3 item 2 (`MODEL_VERSION`) landing first. Confirm order.

## 7. Scope boundary

Not in this item: `POST /api/stake` (Appendix C), `backend/explain.py` and the takeaway
generator (Appendix B, Tier 3 item 4), merging verdicts into slate rows (needs §3.6's gp
plumbing), the odds provider (Decision A), and home-field (needs the version registry).
