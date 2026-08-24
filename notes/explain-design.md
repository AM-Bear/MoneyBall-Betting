# Explanation generator — design groundwork

Tier 3 item 4: `model_detail` on slate rows + `backend/explain.py` + `reasons` on rows and
on `POST /api/evaluate`.

Written 2026-08-24, read-only lane. **No code exists yet.** This document is the thing to
review before any is written. Every number in §3 was reproduced against the live
`backend/inference.py` / `backend/analytics.py` / `backend/odds.py` at `bb4d90f`, not copied
from a doc.

**Source.** Appendix B is `attached_assets/MONEYLINE_v3_Product_Strategy_and_UX_Plan_1787528143354.md:1354-1378`
(`[S:nnn]` below). Supporting: the repository audit
(`attached_assets/MONEYLINE_Repository_Audit_and_v3_Strategy_1787533744890.md`, `[A:nnn]`),
whose §698 and §710 already sketch this item and are more specific than Appendix B in two
places. Appendix D (copy rules, `[S:1393-1417]`) and §8.3 (number formatting, `[S:606-608]`)
bind the output strings. Companion docs: `notes/verdict-design.md` (item 3, shipped) and
`notes/gp-plumbing-design.md` (the games-played prerequisite, §7.1 below).

`backend/main.py` and `backend/verdict.py` are being edited live by the coordinating
session; their line numbers will drift. `feeds.py`, `inference.py`, `analytics.py`,
`odds.py`, `wire.py` are clean at `bb4d90f` and their numbers are stable.

---

## 0. Verdict up front

**The same shape as the gp find, one layer deeper.** `_chain_probability`
(`feeds.py:302-314`) calls `predict_from_inputs` twice and `pythagorean_strength` twice —
producing every single number Appendix B's bullets need — and returns **one float**,
discarding all of it. `_price_game` then calls it twice more for the ADJ blend
(`feeds.py:326, 347`).

So `model_detail` is not new arithmetic. It is **stopping the throw-away.** The
recommendation is a sibling function `_chain_detail` that returns the components, with
`_chain_probability` reduced to a one-line delegation so its signature, return type, and six
direct test call sites are untouched.

Three things the reviewer should decide before code:

1. **The additive win-probability proxy is a *ranker*, not a decomposition** (§3.3). It is
   accurate to within 0.8 points across the three cases I ran, which is a trap: it is close
   enough to look like the model's own attribution and it is not one. Pythagorean + log5 is
   not additive. It must never be published as "this component is worth X points."
2. **`predicted.rs` is a 162-game season total, not runs so far** (§3.1). Appendix B asks
   for "runs per game", and the only honest derivation is `rs / 162`, a *projected rate*.
   Meanwhile `get_standings` already carries `runs_scored` — the team's **actual** runs —
   under a near-identical name. Mixing them is one careless line away and would be invisible.
3. **Appendix D's prohibited-word lint collides with the pulse lexicon** (§7.3). `"streak"`
   is a prohibited word `[S:1399]` and also a published `PULSE_POSITIVE` entry
   (`analytics.py:27`). The lint must scope to product copy or the lexicon loses detection
   words.

---

## 1. Composition over the price chain

### 1.1 The rule

`explain()` is **pure over `model_detail`, `adj_detail`, gp, the evaluation, and context
items.** It does not load models, does not fetch, and does not run the price chain. Like
`verdict.py`, that is checkable by inspection: `backend/explain.py` should import
`backend.analytics` (for `runs_per_win` only) and the stdlib — **no `feeds`, no
`inference`, no `odds`, no `wire`.**

`analytics.runs_per_win` is the one exception to "imports only the stdlib", and it is the
right one: the plan's price-math danger list already blesses it — "`explain` ranking via
`analytics.runs_per_win` is read-only" (`notes/v3-plan.md:227`). It reads
`load_models()["wins"].coef_[0]` through `_coefficients()` (`analytics.py:38-47`), so the
slope is a fitted coefficient with a receipt, never a literal — the no-hardcoded-coefficients
doctrine is satisfied by construction.

### 1.2 Where the numbers come from today

| Appendix B input `[S:1356]` | Where it lives now | Status |
|---|---|---|
| OBP, SLG, OBP-against, SLG-against | `away_inputs` / `home_inputs` on the row (`feeds.py:385-386`) | **exists** |
| predicted runs scored / allowed | `predict_from_inputs(...)["predicted"]["rs"/"ra"]` (`inference.py:121-124`) | **computed and discarded** (`feeds.py:306-307`) |
| Pythagorean strength | `pythagorean_strength(...)` (`odds.py:131-135`) | **computed and discarded** (`feeds.py:308-313`) |
| starter OBP-against / SLG-against, blend weight | `adj_detail[side]` (`feeds.py:876-883`) | **exists on the row** |
| `p_season`, `p_adj` | `model_prob_home`, `adj_prob` (`feeds.py:375, 381`) | **exists** |
| games played | standings → `context["directory"]` | **`notes/gp-plumbing-design.md`** |
| the evaluation | `verdict.evaluate` output | **exists** (item 3) |
| IL flags | `flags` on the row (`feeds.py:384`, built `feeds.py:1032-1058`) | **exists** |
| transactions | `wire.get_wire` / `feeds.get_transactions` (`feeds.py:779`) | exists, **wrong window** (§7.2) |
| media pulse + item count | `wire.get_team_pulse` (`wire.py:165-190`) | exists, **wrong window and wrong place** (§7.2) |

Two rows are the whole backend change. Everything else is already on the wire.

### 1.3 The discard, verbatim (`feeds.py:302-314`)

```python
def _chain_probability(
    away_inputs: dict[str, float], home_inputs: dict[str, float]
) -> float:
    """Season chain: inputs → RS/RA models → Pythagorean → log5 (home prob)."""
    away_model = predict_from_inputs(**away_inputs)
    home_model = predict_from_inputs(**home_inputs)
    away_strength = pythagorean_strength(
        away_model["predicted"]["rs"], away_model["predicted"]["ra"]
    )
    home_strength = pythagorean_strength(
        home_model["predicted"]["rs"], home_model["predicted"]["ra"]
    )
    return log5_probability(home_strength, away_strength)
```

`away_model` and `home_model` are full prediction dicts — `rs`, `ra`, `rd`, `wins`,
`playoff_prob`, `receipts` — and both strengths are named locals. All six values die at the
`return`. The audit reached the same conclusion independently: "Slate rows lack predicted
runs | `_price_game` discards them" `[A:888]`.

### 1.4 Where I would otherwise be tempted to re-derive — do not

Four places, same species as `notes/verdict-design.md` §1.3.

1. **Recomputing `predict_from_inputs` inside `explain.py`.** It is a pure function of
   `(obp, slg, oobp, oslg)` over `@lru_cache`d models (`inference.py:18-22`), so a second
   call returns bit-identical numbers *today*. That is exactly what makes it dangerous: it
   creates a second execution of the price chain that agrees by coincidence of purity
   rather than by construction. The first person to change `_chain_probability` — home-field
   is explicitly queued to mutate `log5_probability` (`notes/v3-plan.md`, danger list) —
   makes the explanation silently describe a price the desk no longer quotes. **One
   execution, passed forward.**
2. **`pythagorean_strength` / `log5_probability`.** Same rule `verdict.py` follows: they
   belong to the chain upstream. `explain.py` must not import `backend.odds` at all.
3. **`p_adj − p_season`.** Both are already on the row (`adj_prob`, `model_prob_home`).
   Subtract the row's values; do not re-blend and re-chain to "check".
4. **The runs-per-win slope.** `analytics.runs_per_win()` (`analytics.py:49-52`) is
   `1 / wins_per_run`. Do not write `9.45`, and do not write `1/0.1058`. The receipt string
   `runs_per_win_receipt()` (`analytics.py:54-61`) already exists and should ship in the
   payload beside any contribution figure.

### 1.5 Doctrine check

Appendix B's own words: **"Templates (priced inputs only)"** `[S:1361]`, **"Chips are
labeled 'not in the price' and never appear in the lean list"** `[S:1372]`. And the strategy
doc's assumption 2 `[S:33]`: home/away performance and recent form "describe things the
model does not price. They can appear only as context, never as reasons the model leans a
side."

The structural guarantee: `reasons.lean[]` is built **only** from `model_detail` and
`adj_detail`. `flags`, transactions and pulse are built into `reasons.context[]` by a
separate function that cannot write to `lean`. Not a convention — two functions, and a test
that feeds a game with a screaming IL flag and asserts the flag's player name appears
nowhere in `lean`. That is Appendix B's fourth golden fixture `[S:1376]` and it is the one
that matters most.

---

## 2. `model_detail` — the backend change

### 2.1 Shape

Per side, mirroring the existing `away_*` / `home_*` pairing on the row:

```jsonc
"model_detail": {
  "away": {
    "rs": 619.0, "ra": 834.1,            // 162-game projections, from predicted
    "rs_per_game": 3.82, "ra_per_game": 5.15,
    "pythag": 0.3551,
    "obp": 0.300, "slg": 0.380, "oobp": 0.345, "oslg": 0.440
  },
  "home": { ... },
  "basis": "season",                      // the SEASON chain, always
  "runs_per_win": 9.455,
  "runs_per_win_receipt": "The fitted W~RD slope is 0.1058 wins per run — …",
  "per_game_basis": "Predicted runs are a 162-game projection from season rates; per-game figures are that projection ÷ 162, not runs scored so far."
}
```

`obp/slg/oobp/oslg` are duplicated from `away_inputs`/`home_inputs` deliberately, so
`explain()` takes **one** object and the templates cannot half-read from two. If the
reviewer prefers no duplication, `explain()` takes `(model_detail, away_inputs,
home_inputs)` instead — cheap either way, but decide once.

**`basis` is `"season"` only.** The ADJ chain is described by `adj_detail` plus the
`p_season → p_adj` move, which is exactly what Appendix B's starter template asks for
`[S:1364]`. Emitting a second full `model_detail` for the blended inputs doubles the payload
to serve a bullet that only needs two probabilities. Recommend not doing it; flagging rather
than deciding.

### 2.2 The minimal change to `feeds.py`

**(a)** Add a sibling beside `_chain_probability` and reduce the original to a delegation:

```python
def _chain_detail(
    away_inputs: dict[str, float], home_inputs: dict[str, float]
) -> dict[str, Any]:
    """Season chain, with the components the price is built from kept."""
    away_model = predict_from_inputs(**away_inputs)
    home_model = predict_from_inputs(**home_inputs)
    away_strength = pythagorean_strength(
        away_model["predicted"]["rs"], away_model["predicted"]["ra"]
    )
    home_strength = pythagorean_strength(
        home_model["predicted"]["rs"], home_model["predicted"]["ra"]
    )
    return {
        "away": away_model["predicted"],
        "home": home_model["predicted"],
        "away_strength": away_strength,
        "home_strength": home_strength,
        "prob_home": log5_probability(home_strength, away_strength),
    }


def _chain_probability(
    away_inputs: dict[str, float], home_inputs: dict[str, float]
) -> float:
    """Season chain: inputs → RS/RA models → Pythagorean → log5 (home prob)."""
    return _chain_detail(away_inputs, home_inputs)["prob_home"]
```

The operations and their order are unchanged, so `prob_home` is the **same float, bit for
bit** — not "approximately equal", identical. That matters because six existing assertions
call `_chain_probability` directly (`tests/test_price_chain_integration.py:140, 147,
154-155, 160-161, 166`), including
`test_chain_probability_matches_an_independent_derivation`, which checks it against a
longhand RS/RA → pythag → log5 computation. **Keeping the signature keeps that whole guard
intact**, which is the argument against the more obvious refactor of making
`_chain_probability` return a tuple.

**(b)** In `_price_game`, replace the season call at `feeds.py:326` with `_chain_detail`,
read `["prob_home"]` from it, and add one key to the returned dict beside `adj_detail`
(`feeds.py:383`). The ADJ call at `feeds.py:347` stays `_chain_probability` — the blended
chain's components are not published (§2.1).

### 2.3 What does not change

`predict_from_inputs`, `pythagorean_strength`, `log5_probability`, `probability_to_moneyline`,
`_team_inputs`, `_blended_side`, `blend_defense_inputs`, `starter_innings_share`,
`odds.py` entire, `POST /api/price`, `/api/matchup`, `/api/screener`, `/api/season-sim`,
`backend/verdict.py`. One production call site of `_price_game` (`feeds.py:461`), so the
blast radius is `/api/slate` and whatever consumes `reasons`.

### 2.4 The no-price-moved proof

`notes/v3-plan.md:212-214` mandates "a byte-identical `/api/slate` diff". As with the gp
change, that predicate is not satisfiable when a key is added, and stating it as satisfied
would be false. **But this item needs a strictly stronger proof than the gp one**, because
gp only *added* a read while this one *refactors the function that computes the price*.

Required, in this order:

1. **`_chain_probability` is bit-identical, not approximately.** Not `pytest.approx` — `==`
   on the raw float, over a grid of input pairs. This is the actual risk and it deserves its
   own test:
   ```python
   assert _chain_probability(WEAK_TEAM, OAK_INPUTS) == _chain_detail(WEAK_TEAM, OAK_INPUTS)["prob_home"]
   ```
   plus a before/after capture of `repr(_chain_probability(a, h))` for several pairs.
2. **The row predicate**, exactly as in `notes/gp-plumbing-design.md` §3.2/§3.3: every
   pre-existing key recursively equal, and `set(after) − set(before) == {"model_detail"}`
   (plus `{"reasons"}` if §4.2 lands in the same change). Same deterministic harness — stub
   `_team_inputs`, dump the row on both context paths, assert the predicate. `diff -u` shows
   only added lines.
3. **`python smoke_test.py` and `python -m pytest -q`** before and after, with the six
   `_chain_probability` assertions passing **unmodified**. If any of them needed an edit,
   the refactor was not signature-preserving and should be reworked, not the test.
4. `POST /api/price` unchanged — run it, and say plainly (as item 3 established) that it
   cannot detect a slate-row change and is therefore not the proof.

---

## 3. The arithmetic, verified

### 3.1 Runs per game: the derivation and its footgun

The RS regression is fit on **season totals** (`verified_stats.json:rs_model`, 1962–2001
team-seasons), so `predicted.rs` is a projected 162-game total. Appendix B's templates want
"per game" `[S:1362]`. The only available derivation is `rs / 162`.

That number is a **projected full-season rate**, not this team's runs per game so far. In
late August those differ. The template's word "projects" `[S:1362]` is carrying the honesty,
and it must survive into the shipped string.

**The footgun:** `get_standings` already puts `runs_scored` and `runs_allowed` — the team's
**actual** season-to-date runs — on every directory row (`feeds.py:722-723`), the same
directory `_price_game` will now be reading for gp. Two quantities, near-identical names,
one is a model output and one is a fact, and they will be sitting in the same function.
Recommend `model_detail` never carries a bare `runs` key, always `rs`/`rs_per_game` with the
`per_game_basis` string alongside, and that a test asserts `model_detail` values come from
`predicted`, not from the directory.

Also: `predicted.ra` is `None` when `oobp`/`oslg` are absent (`inference.py:81-85`). Slate
rows always have all four from `_team_inputs`, but `historical_slate` rows can be
`offense_only` (`feeds.py:426`). §5 refuses those.

### 3.2 Component deltas `[S:1359]`

For lean side X versus Y:

| Component | Expression | Threshold `[S:1362-1364]` |
|---|---|---|
| offense | `rs_per_game(X) − rs_per_game(Y)` | \|Δ\| ≥ 0.15 R/G |
| prevention | `ra_per_game(Y) − ra_per_game(X)` | \|Δ\| ≥ 0.15 R/G |
| starters | `(p_adj − p_season) × 100`, attributed to the blend | \|Δ\| ≥ 1 point |

Note the sign convention on prevention is **reversed** (Y minus X), so a positive delta
always means "favours X". Easy to get wrong; worth a comment and a test.

### 3.3 The win-probability proxy — accurate enough to be dangerous

Appendix B: "Each delta is converted to an approximate win-probability contribution using
the fitted runs-per-win slope so that bullets can be ranked by magnitude" `[S:1359]`.

The derivation: Δ runs/game × 162 games = Δ·162 season runs; × `wins_per_run` = wins over a
season; ÷ 162 = win-probability points per game. The 162s cancel:

> **contribution (probability) = Δ(runs per game) × `wins_per_run`**

Reproduced 2026-08-24 against the live models (`wins_per_run = 0.105766`,
`runs_per_win = 9.455`):

```
case         p_home   actual pp    off pp   prev pp    sum pp      err
lopsided     0.7302       23.02     12.35     11.24     23.59    +0.57
near-even    0.5050        0.50      1.41     -0.87      0.54    +0.03
split        0.4891       -1.09    -12.98     11.14     -1.83    -0.74

0.15 R/G threshold  ->  1.586 pp  ( = 24.3 season runs)
```

(`lopsided` = WEAK_TEAM at OAK_2002; `near-even` and `split` are desk-authored input pairs,
listed in full in the fixture table §6.)

The additive sum lands within **0.8 points** of the true log5 displacement in all three
cases, and the `split` case correctly puts offense on the away side and prevention on the
home side while still summing to the right side of 50%. As a **ranker** the proxy is sound —
which is all Appendix B claims for it.

**This is exactly why it needs a guard rail.** Pythagorean is quadratic and log5 is a
ratio; neither is additive. The agreement above is a property of these three input pairs at
these magnitudes, not a theorem, and it will degrade at extremes. So:

- The proxy orders bullets. It **must not** be printed as "worth +12.4 points."
- If a contribution figure is ever shown, it ships with `runs_per_win_receipt()` and the word
  *approximate*, and it is never summed to a total in the UI — a displayed sum invites the
  reader to check it against the model chance, and the two will not match.
- A test should assert the proxy is used only for `sorted(...)`, e.g. by checking no
  contribution value appears in any rendered string.

### 3.4 The starter delta, verified

`starter_innings_share(139.667, 22) = 0.7054` (`analytics.py:191-197`; capped to [0.4, 0.8]).
With a starter at .280/.350 against, blended at w = 0.6 into OAK's team rate
(`blend_defense_inputs`, `analytics.py:199-215`):

```
blend            -> oobp 0.2940, oslg 0.3636
p_season  0.7302  fair -270
p_adj     0.7851  fair -365      delta +5.48 pts
```

Comfortably over the 1-point trigger, and it exercises the template's
`"the price moves from {fair_season} to {fair_adj}"` clause with two real lines. Note both
fair lines come from `probability_to_moneyline`'s nearest-5 rounding (`odds.py:18`) — the
plan says leave that alone, and the template must print the **rounded** line, the same one
the card shows, not an unrounded variant.

---

## 4. API surface

### 4.1 `reasons` shape

`[A:710]` specifies `reasons {lean[], review[], context[]}`. Recommend each entry be an
object, not a pre-rendered string:

```jsonc
"reasons": {
  "lean": [
    { "kind": "offense", "side": "home", "text": "…", "delta_rpg": 1.1679, "rank": 1 },
    { "kind": "prevention", "side": "home", "text": "…", "delta_rpg": 1.0630, "rank": 2 },
    { "kind": "counterweight", "side": "away", "text": "…", "rank": 3 }
  ],
  "review":  [ { "kind": "verdict_line", "text": "…" }, { "kind": "takeaway", "text": "…" } ],
  "context": [ { "kind": "il", "text": "…", "not_in_price": true }, … ],
  "sample":  { "kind": "sample", "text": "Based on 126 and 124 games this season." },
  "limitations": [ "Home field: not priced", "Lineups: not priced",
                   "Weather: not priced", "Bullpen: approximated by team rate" ]
}
```

`text` is the rendered sentence — servers render, so "every client renders identical text"
`[A:710]`. `kind` and `delta_rpg` let the card style and re-order without re-parsing prose.
`not_in_price: true` on every context entry makes Appendix D's required qualifier
(`[S:1397]`: "Every context chip says 'not in the price'") a structural property rather than
a copy convention.

`sample` is separate from `lean` because Appendix B says it is "always last" `[S:1366]` —
if it lived in `lean` it would be subject to the max-three rule `[S:1374]` and could be
dropped by a game with three strong bullets. Pulling it out makes that impossible.

`limitations` is the standing list `[S:1372]`, constant, shown on expand.

### 4.2 Where it is served

Two surfaces `[A:710]`:

- **On slate rows.** Built inside `_price_game`, or (preferred) by `get_slate` after
  `bounded_price` returns, so `_price_game` stays a pricing function and a failure in
  explanation cannot cost a price. Recommend the latter: wrap in `try/except` and emit
  `reasons: None` on failure. **An explanation must never be able to delete a price.**
- **On `POST /api/evaluate`.** The endpoint takes probabilities, not team inputs
  (`notes/verdict-design.md` §3.2), so it has no `model_detail` and cannot build `lean`
  bullets. It *can* build `review` (the candidate/no-value line, which needs only price,
  fair, q and the verdict) and `sample`.

  **SETTLED — `/api/evaluate` does not accept `model_detail`, not even optionally, and
  returns no lean bullets.** I had floated an optional `model_detail` on the request body to
  save the card a round trip. Rejected, and the reason is better than the question:
  `verdict.py` imports `backend.odds` and the stdlib and nothing else, and a test asserts
  that against the import graph — that test is the mechanical proof that pulse and injury
  flags cannot reach a verdict. Threading team-derived components through the endpoint would
  not technically break the import assertion, which is exactly the problem: the guarantee
  would quietly weaken from *"the module cannot see context"* to *"the module does not
  import context"*, and nothing downstream would be able to tell the difference.

  So `reasons.lean[]` is built from the slate row and never round-trips through the verdict
  endpoint. Composition happens at the card, which already holds both halves — `model_detail`
  on the slate row, the verdict from `/api/evaluate`. Two single-purpose payloads, joined at
  the display layer. `/api/evaluate` stays pure and stays a 200.

### 4.3 The takeaway sentence already has a home

`[S:1368]`: "The model leans {lean} ({p}%), but the price is better on {value_side} at
{price} — marginal value." Every field is already in the verdict payload:
`game.lean_side`, `game.side`, `game.lean_differs_from_value`, the side's `price` and
`verdict` (`notes/verdict-design.md` §3.3). `verdict.py` already emits a `takeaway` for the
gated states. Two writers for one field is how the two diverge.

**SETTLED — one field, one writer. `game.takeaway` is `verdict.py`'s in every state, priced
and refused alike; `explain.py` writes no takeaway at all.** My proposal was a
state-dependent split (verdict.py owns refusals, explain.py owns priced) with the boundary
commented at both sites. Rejected, correctly: a state-dependent split still leaves one field
with two authors, and a comment is a convention rather than an enforcement — the first
person to add a verdict state gets it wrong. `verdict.py` is the only module that knows the
verdict, and the takeaway is the value statement.

If Appendix B's richer copy `[S:1368]` is wanted, it lands under **its own key** in
`reasons` and the card's choice rule between the two is written in exactly one place.

---

## 5. What the explanation must refuse

- **No `model_detail`** (context degraded, pricing error, or `mode: "historical"`) → no
  `lean` bullets at all. Not "the teams are close" — that sentence is a *finding*
  `[S:1374]`, and printing it when nothing was computed would be a fabricated finding. Emit
  `lean: []` with `reasons.unavailable: "model_detail"`.
- **All deltas under threshold** → exactly the Appendix B fallback: "The two teams are close
  on every input the model prices." This is the honest-refusal-as-result pattern.
- **`predicted.ra is None`** (offense-only, `inference.py:81-85`) → no prevention bullet and
  no proxy ranking; offense only, and say so.
- **No `p_adj`** → no starter bullet. Never phrase its absence as "the starters don't
  matter"; the truth is the probable is unannounced or unmatched in the pool
  (`feeds.py:860-867`). The card already has "starters unconfirmed" from item 3.
- **gp unknown** → no sample sentence. Appendix D requires "Every in-season number carries
  games played" `[S:1397]`, so with gp unknown the bullets themselves are on thin ice; at
  minimum the sentence must not be invented. Ties directly to the `gp_unavailable` reason
  the coordinator added to `verdict.py`.
- **No template renders without a real value** `[S:1374]` — the v2 desk-note rule. Every
  template's fields are checked non-`None` before it renders, and a missing field drops the
  bullet rather than printing "N/A" or an empty span.
- **Context items never enter `lean`** (§1.5) — enforced structurally, not by review.
- **No home field, no recent form, no weather, no lineups** `[S:33]`. They are in
  `limitations`, permanently, as the standing four.

---

## 6. Golden tests

### 6.1 Appendix B says ten and lists six

`[S:1376]`: "Ten hand-written fixtures covering: a clear favorite on all components; a split
(offense favors X, prevention favors Y); a starter that flips the lean; an injury flag on
the lean side (must not appear in the lean list); a no-value takeaway where the value side
is the underdog; and an early-season game (sample sentence with a small-sample note)."

**That is six.** The audit fills the gap `[A:710]` with a ten-item list: "clear favorite;
split components; starter flips the lean; injury flag on the lean side; value on the
underdog; early-season sample; **ADJ missing; pricing failure; historical mode; a tie in
inputs**." The audit's four extras are exactly the refusal paths in §5, and they are the
right four. Recommend adopting the audit's list, and marking in the test file which six
carry Appendix B's authority and which four are the audit's — the same convention
`notes/verdict-design.md` §2.4 established for the desk-authored verdict cases.

### 6.2 Fixture inputs I have already reproduced

Three of the ten can use verified numbers today:

| Fixture | Away inputs | Home inputs | Reproduced |
|---|---|---|---|
| clear favorite | `0.300/0.380/0.345/0.440` | `0.339/0.432/0.315/0.384` (OAK 2002) | `p_home 0.7302`, off `+12.35 pp`, prev `+11.24 pp`, fair `−270` |
| a tie in inputs | `0.325/0.410/0.320/0.400` | `0.330/0.415/0.322/0.405` | `p_home 0.5050`; both deltas under 0.15 R/G → the fallback sentence |
| split components | `0.345/0.450/0.335/0.430` | `0.310/0.385/0.305/0.375` | `p_home 0.4891`; offense favours **away** `−12.98 pp`, prevention favours **home** `+11.14 pp` → counterweight |
| starter flips / moves | clear-favorite pair + starter `.280/.350` at w = 0.6 | | `p_season 0.7302 (−270) → p_adj 0.7851 (−365)`, `+5.48 pts` |

The clear-favorite pair is the existing `WEAK_TEAM` / `OAK_INPUTS`
(`tests/test_price_chain_integration.py:43-49`), so it inherits the hand-checked 2002 A's
chain from `verified_stats.json:oak_2002_chain`. The other two pairs are **desk-authored**
and must be labelled as such.

**A starter that genuinely flips the lean** (crosses 0.5, not merely moves the price) needs
a near-even base pair plus a strong starter; I did not construct one, because CLAUDE.md
requires a new formula's hand-checked case to enter `verified_stats.json`, and inventing the
inputs is the reviewer's call, not mine. Flagged as the one fixture still to be derived.

### 6.3 Two tests Appendix B does not ask for and should have

1. **The proxy never reaches a string** (§3.3) — assert no contribution number appears in
   any `text`.
2. **The lint runs on templates, not just output** `[S:1374]`: "Prohibited words are
   impossible by construction (the lint runs on templates)." A test that greps the template
   constants for Appendix D's prohibited list is cheap and makes the claim true rather than
   aspirational. See §7.3 for the collision it will find on day one.

---

## 7. Data gaps and collisions found while tracing

### 7.1 Games played — hard dependency, already designed

Appendix B's sample sentence and Appendix D's "Every in-season number carries games played"
`[S:1397]` both require gp on the row. It is not there. `notes/gp-plumbing-design.md` is the
design; item 4 should land **after** it rather than re-deriving gp from `/api/teams-live` on
the client. Both changes touch `_price_game`'s return dict, so if they land together the
row predicate becomes `set(after) − set(before) == {"away_gp", "home_gp", "model_detail"}`.

Also note Appendix D rewrites `THRU 126 GP` → `Through 126 games` `[S:1414]`, while
Appendix B's sentence is "Based on {gp_x} and {gp_y} games this season" `[S:1366]`. Two
different sample strings for the same fact, plus the three inconsistent `THRU {n} GP`
derivations already flagged in `notes/gp-plumbing-design.md` §6. Worth settling in one place.

### 7.2 Context windows do not match the spec

- **Transactions.** Appendix B wants "transactions in the last 72 hours" `[S:1356]`.
  `get_transactions(days: int = 7)` (`feeds.py:779`) fetches a **7-day** window, and
  `get_wire` does no further date filtering. A 72-hour filter exists nowhere. Trivial to add
  at the explain layer (items carry `date`), but it must be added — silently showing a
  six-day-old transaction under a "last 72 hours" spec is a small lie in the same family as
  the rest of this document.
- **Media pulse.** Appendix B triggers the chip at `|score| ≥ 25` with an item count
  `[S:1372]`. `get_team_pulse` (`wire.py:165-190`) returns `pulse`, `items_scanned` and
  `items_matched` — the count is available, but over a **7-day** window (`wire.py:172`),
  which Appendix B does not state. Pick one and write it down; do not let the chip say
  "12 items" without saying over what window.
- **`score_pulse_items` hardcodes the window in its own receipt.** `analytics.py:272-275`
  returns `"method": "… over the last 7 days of wire items …"` — but the function does no
  windowing at all; its caller does. Change the caller's window and the published method
  string lies. Recommend the window be passed in and interpolated. **Flagged, not fixed.**

### 7.3 Appendix D's lint collides with the pulse lexicon

`[S:1399]` prohibits, among others: `hot`, `on fire`, `streak`, `fade`, `boost`.

`analytics.py:26-35` publishes:
```python
PULSE_POSITIVE = [ "walk-off", "walkoff", "streak", "sweep", "swept", … ]
PULSE_NEGATIVE = [ …, "losing streak" ]
```
and `score_pulse_items` returns the whole lexicon in its payload (`analytics.py:276-279`),
where it is rendered as the pulse's audit trail.

So a naive "lint on string resources" `[S:612]` fails the build on the desk's own evidence
vocabulary — and the wrong fix (deleting `"streak"`) breaks pulse detection and undoes part
of the `bb4d90f` lexicon work. The lint must scope to **product copy and templates**, with
the lexicon explicitly exempt as data. Worth writing into the lint's config with a comment,
because the next person to hit it will otherwise "fix" the lexicon.

### 7.4 Per-game pulse would be a performance mistake

`get_team_pulse` calls `get_wire(record, team=code, limit=250)` (`wire.py:171`), and
`get_wire` re-merges, re-dedupes and re-sorts the full item list on every call
(`wire.py:117-142`). The underlying fetches are TTL-cached, the *processing* is not. A
15-game slate × 2 teams = 30 full merge/dedupe/sort passes per slate build.

Recommend the wire be fetched and scored **once per slate**, in `_slate_context`
(`feeds.py:983-998`) alongside `pitchers_by_id` and `flags`, and passed down — the same
pattern that makes gp free. Note `_slate_context` swallows exceptions and returns `None`, so
this degrades correctly by construction.

### 7.5 Number formatting is specified and unimplemented

`[S:606-608]` is precise: whole percents in Essentials and one decimal in Full detail; signed
American odds in the monospace price face; edge in points, never a percent sign; expected
return in dollars per $100 in Essentials and percent of stake in Full detail; records as
"wins–losses" with units to one decimal.

Appendix B says "Every number is formatted by the dictionary rules" `[S:1374]`. Since
`explain.py` renders server-side, **the server must own these rules** — otherwise each client
re-implements §8.3 and they drift. Recommend one `_fmt` module of small functions
(`pct`, `price`, `points`, `rpg`) used by every template, with the Essentials/Full-detail
split handled by rendering the number at full precision in a sibling field and letting the
card choose. **Which side owns the Essentials/Full split needs sign-off** — it is the one
place where "the server renders the text" and "detail level is a client preference"
genuinely conflict.

---

## 8. Recommended order

1. Land `notes/gp-plumbing-design.md` (§7.1 dependency).
2. `_chain_detail` + `model_detail` on the row — with the bit-identical
   `_chain_probability` test **written first**, before the refactor, so it fails for the
   right reason if the refactor is wrong (§2.4).
3. The row predicate proof and the full suite, six `_chain_probability` assertions passing
   unmodified.
4. `backend/explain.py`: deltas, ranking, templates, the fallback sentence, `_fmt`.
   `reasons` on slate rows, built outside `_price_game` so it cannot cost a price.
5. The ten golden fixtures — six marked Appendix B, four marked audit-authored — plus the
   two extra tests in §6.3. The starter-flips-the-lean pair still needs deriving and a
   `verified_stats.json` entry (§6.2).
6. `reasons` on `POST /api/evaluate` — `review` and `sample` only. No `lean`, and no
   `model_detail` on the request body (§4.2, settled).
7. File separately, do not fix here: the `score_pulse_items` hardcoded-window receipt
   (§7.2), the lint/lexicon scoping (§7.3), and the per-slate wire refactor (§7.4).

## 9. Questions — settled and open

### Settled by the coordinating session, 2026-08-24

- **§4.2 — `POST /api/evaluate` does not accept `model_detail`, not even optionally, and
  returns no lean bullets.** Threading team-derived components through it would weaken the
  import-graph guarantee from "cannot see context" to "does not import context" without
  breaking the test that asserts it. `reasons.lean[]` is built from the slate row;
  composition happens at the card, which holds both halves.
- **§4.3 — one field, one writer: `game.takeaway` is `verdict.py`'s in every state.**
  `explain.py` writes no takeaway. A state-dependent split still leaves one field with two
  authors, and a boundary comment is a convention, not an enforcement. Appendix B's richer
  copy, if wanted, gets its own key.

### Endorsed as written, treat as settled for implementation

The signature-preserving `_chain_detail` sibling plus the bit-identity assertion, with the
test written first and the six existing `_chain_probability` assertions passing
**unmodified** — if any needs editing the refactor was not signature-preserving and gets
reverted, not accommodated (§2.2, §2.4). `reasons` built outside `_price_game`, wrapped,
emitting `reasons: None` on failure (§4.2). The additive proxy as a ranker only — never
printed as points, never summed in the UI, always carrying `runs_per_win_receipt()` and the
word *approximate* (§3.3). No bare `runs` key, always a `per_game_basis` string (§3.1). The
copy lint scoped to product copy with the lexicon exempt **as data**, written into the
config with a comment (§7.3). The two-function guarantee with the IL-flag test asserting the
player's name appears nowhere in `lean` (§1.5, §6.1).

### Still open

1. §2.1 — does `model_detail` duplicate the four rate inputs, or does `explain()` take three
   arguments?
2. §2.1 — `basis: "season"` only, or a second `model_detail` for the blended chain?
3. §6.2 — the inputs for the starter-flips-the-lean fixture, and its `verified_stats.json`
   entry. **Not adopted yet; escalated to Asher.** These must be hand-checked, not invented.
4. §7.2 — 72 hours per Appendix B, or 7 days per the existing feeds, for transactions and
   for pulse?
5. §7.5 — does the server render Essentials and Full detail separately, or emit full
   precision and let the card format?
