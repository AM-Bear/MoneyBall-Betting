# MONEYLINE — Model Lane Map (Recon Lane 1)

Read-only audit of the price chain, spec conformance, doctrine, and test coverage.
Scope: `backend/analytics.py`, `backend/odds.py`, `backend/season_sim.py`,
`backend/inference.py`, `backend/precompute.py`, `model_config.json`,
`verified_stats.json`, `smoke_test.py`, plus the price-carrying call sites in
`backend/feeds.py`, `backend/main.py`, `backend/players.py`.

Spec = `attached_assets/moneyline_v2_expansion_replit_prompt_1787245184521.md`
(cited as `spec:NN`).

All coefficient values below were read out of the live fit, not from the spec's
illustrative literals:

```
rs.intercept_  = -804.62706106224      rs.coef_  = [2737.76802227, 1584.90860546]   # OBP, SLG
ra.intercept_  = -837.3778886133358    ra.coef_  = [2913.59948582, 1514.28595842]   # OOBP, OSLG
wins.intercept_=   80.88137472283813   wins.coef_= [0.10576562]                     # RD
playoffs.intercept_ = -32.14482698     playoffs.coef_ = [[0.34582944]]              # W (logistic)
1 / wins.coef_[0] = 9.4548680076  runs per win
```

---

## 1. PRICE CHAIN — formula by formula

### 1.0 Where the coefficients come from

`backend/precompute.py:135-186` `build_artifacts()` fits five estimators on
`baseball.csv` (1232×15, chronological split train ≤ 2001 / test ≥ 2002,
asserted at `precompute.py:146-152`):

| Model | Fit at | Features → target | Train set |
|---|---|---|---|
| `rs` | `precompute.py:154` | OBP, SLG → RS | `Year ≤ 2001` (902 rows) |
| `ba` | `precompute.py:155` | OBP, SLG, BA → RS | same (BA-paradox panel only) |
| `ra` | `precompute.py:158` | OOBP, OSLG → RA | `Year ≤ 2001` **dropna(OOBP,OSLG)** = 1999–2001, 90 rows |
| `wins` | `precompute.py:162` | RD → W | `Year ≤ 2001` |
| `playoffs` | `precompute.py:163` | W → Playoffs (logistic) | `Year ≤ 2001` |

They are pickled to `backend/static_data/moneyline_models.joblib`
(`precompute.py:186`) and read exactly once through
`backend/inference.py:18-22` `load_models()` (`@lru_cache(maxsize=1)`).
`model_config.json` is inert — `hub_repo_id: null`, and a non-null value is a
hard error (`precompute.py:139-140`); the app only ever uses the local bundle.

### 1.1 OBP/SLG → RS, OOBP/OSLG → RA

`backend/inference.py:34-94` `predict_from_inputs(obp, slg, oobp, oslg)`.

```
RS = rs.intercept_ + β_OBP·OBP + β_SLG·SLG                    # inference.py:42
RA = ra.intercept_ + β_OOBP·OOBP + β_OSLG·OSLG                # inference.py:45   (None if either input is None)
RD = RS − RA                                                   # inference.py:49
```

Receipts (`inference.py:64-81`) emit `(feature, value, coefficient,
contribution = value × coefficient)`, coefficients pulled live off
`models["rs"].coef_` / `models["ra"].coef_` — no literals.

### 1.2 RD → wins, wins → historical playoff odds

```
W          = wins.intercept_ + slope·RD                        # inference.py:51
P(playoff) = σ(playoffs.intercept_ + playoffs.coef_·W)         # inference.py:56
```

The playoff logistic is a **historical panel** number (fit 1962–2001,
tested through 2012). See §2 and §3 for the live-season leak.

### 1.3 RS/RA → Pythagorean strength

`backend/odds.py:131-135`:

```
strength = max(RS,1)² / (max(RS,1)² + max(RA,1)²)
```

Exponent is fixed at 2 (not 1.83, not a fitted Pythagenpat) — the spec
says only "Pythagorean expectation" (spec:66, spec:79), so this is in spec.

### 1.4 Two strengths → log5 → win probability

`backend/odds.py:138-146`:

```
den  = S_a + S_b − 2·S_a·S_b
p_a  = (S_a − S_a·S_b) / den          (0.5 when den == 0)
```

Slate call site: `backend/feeds.py:215-227` `_chain_probability(away_inputs,
home_inputs)` returns **home** probability = `log5(S_home, S_away)`.
Matchup call site: `backend/main.py:508-535`.

### 1.5 Probability → American moneyline

`backend/odds.py:8-18`:

```
p ≥ 0.5 :  line = −100·p/(1−p)
p <  0.5 :  line = +100·(1−p)/p
line = round(line / 5) × 5              # snapped to the nearest 5
```

Inverse at `odds.py:21-25`; edge at `odds.py:28-30`
(`edge = p_model − implied(line)`); two-sided overround at `odds.py:33-39`.

### 1.6 Worked example — hand-computable end to end

2002 OAK, inputs OBP .339 / SLG .432 / OOBP .315 / OSLG .384
(`verified_stats.json:65-84`, reproduced by `predict_team("OAK", 2002)`):

```
RS = −804.62706 + 2737.76802×0.339 + 1584.90861×0.432
   = −804.62706 + 928.10336 + 684.68052            = 808.157   → displayed 808.2
RA = −837.37789 + 2913.59949×0.315 + 1514.28596×0.384
   = −837.37789 + 917.78384 + 581.48580            = 661.892   → displayed 661.9
RD = 808.157 − 661.892                             = 146.265   → displayed 146.3
W  = 80.88137 + 0.10576562 × 146.265               =  96.350   → displayed 96.4
logit = −32.14483 + 0.34582944 × 96.350 = 1.17577;  σ = 0.7643
S  = 808.157² / (808.157² + 661.892²)              = 0.598521
fair line = −100 × 0.598521 / 0.401479 = −149.08   → −150
```

Verified live: `predict_team("OAK",2002)` → `rs 808.2, ra 661.9, rd 146.3,
wins 96.4, playoff_prob 0.7643, fair_line −150`.

A game price then takes two of these strengths into log5 (§1.4) and
`probability_to_moneyline` (§1.5). Sanity identity used by the test suite:
`log5(S, 0.5) == S` (`smoke_test.py:105-111`).

### 1.7 mWAA run values (`backend/analytics.py`)

Coefficients: `analytics.py:38-46` `_coefficients()` — every β read off
`load_models()` per call. Runs/win: `analytics.py:49-51`
`runs_per_win() = 1 / wins.coef_[0]` = **9.4549**, and the receipt string is
built from the live slope at `analytics.py:54-60`.

Hitter (`analytics.py:63-116`):

```
s        = PA_player / league_team_PA                       # :74
ΔRS      = s·β_OBP·(OBP_p − OBP_lg) + s·β_SLG·(SLG_p − SLG_lg)   # :77-79
ΔRD      = ΔRS                                              # :86
mWAA     = ΔRS × wins.coef_[0]                              # :80
```

Pitcher (`analytics.py:119-174`), sign flipped so prevention is positive:

```
s        = IP_player / league_team_IP                       # :130
ΔRA      = s·β_OOBP·(OBPa_p − OBPa_lg) + s·β_OSLG·(SLGa_p − SLGa_lg)  # :133-135
ΔRD      = −ΔRA                                             # :136
mWAA     = ΔRD × wins.coef_[0]                              # :137
```

League baselines come from `backend/feeds.py:793-827`
`get_league_pool_context()`: `league_obp/slg` and `league_obp_against/
slg_against` are **unweighted means over the qualified pool**
(`feeds.py:812-815`); `league_team_pa/ip` are means over all 30 teams
(`feeds.py:816-817`). Matches spec:55-57. The honest-label string is built
per call at `analytics.py:17-22` and attached to every payload
(`analytics.py:115`, `:173`).

Card assembly: `backend/players.py:110-118` (hitter), `:178-186` (pitcher).

### 1.8 ADJ (starter-blended) price

```
w        = IP_starter / (GS × 9), clamped to [0.4, 0.8]     # analytics.py:191-196
OBPa_adj = w·OBPa_starter + (1−w)·OBPa_team                 # analytics.py:207-210
SLGa_adj = w·SLGa_starter + (1−w)·SLGa_team                 # analytics.py:211-213
```

Wiring: `feeds.py:743-773` `_blended_side()` (returns the team inputs
unchanged when there is no probable, no starter row, or no usable share),
then `feeds.py:250-274` reruns the *same* chain (§1.1→§1.5) on the blended
inputs to produce `adj_prob` / `adj_fair_lines`. SEASON price
(`feeds.py:239`, `:288-292`) is never touched. Both are persisted and graded
side by side (`backend/record_store.py:40-44`, `:112-150`, `:197-207`).

### 1.9 Parlay math

Resolution & correlation refusal: `main.py:998-1041`
(`_resolve_parlay_legs`) — duplicate `gamePk` → `MoneylineError(
"correlated_legs", …, 400)` at `main.py:1001-1007`, raised **before** any
fetch. Leg probability is the SEASON `model_prob_home` (or its complement),
`main.py:1023-1027`.

Pricing: `main.py:849-877` `_price_parlay_payload`.

```
P        = Π p_i                                            # odds.py:68-81   (2 ≤ n ≤ 6 enforced :74)
fair     = probability_to_moneyline(P)                      # odds.py:8-18
D_book   = decimal(book_odds)  or  Π decimal(leg_i)         # odds.py:42-46, :84-89
implied  = |L|/(|L|+100)  or  100/(L+100)                   # odds.py:21-25
edge_pp  = (P − implied) × 100                              # main.py:855, :872
EV/unit  = P·(D_book − 1) − (1 − P)                         # odds.py:92-96
½-Kelly  = max(0, ((p(D)−1)/(D−1)) / 2), applied only if EV > 0
           else the stake string is "0.00 — NO EDGE"        # odds.py:49-56, main.py:869-874
```

Vig-compounding strip: `odds.py:99-128` `parlay_vig_comparison()` —
`standard_book_parlay_line` = compounded −110 legs, `fair_parlay_line` =
`probability_to_moneyline(P)`, and two "take" percentages (see §2.2 for the
semantics problem).

Hand-check: two 55% legs → `P = 0.3025`, fair `+230`; two −110 legs compound
to `+264` while a fair 25% parlay is `+300` (`smoke_test.py:217-231`).

### 1.10 Rest-of-season simulation

`backend/season_sim.py:80-157` `simulate_season()`. Seed `20261962`, N = 2000
(`season_sim.py:30-31`). Per remaining game, `log5(S_home, S_away)`
(`:94-102`) with strengths built from the same §1.1→§1.3 chain
(`:251-256`). Each iteration adds wins, then jitters by `rng.random()*1e-6`
for random tie-breaks (`:118-121`), takes the max of each division as a
division winner (`:125-131`) and the top 3 of the remaining league pool as
wild cards (`:132-133`) — i.e. top 6 per league in real MLB shape.
Playoff odds = `playoff_counts / iterations` (`:154`). The historical
`Playoffs~W` logistic is deliberately not used here; the footnote says so at
`:318-322`. 2027 refusal payload: `season_sim.py:46-55`. Cache signature
(season-scoped) at `:61-77`, `:260-266`.

---

## 2. SPEC DRIFT

### 2.1 MODEL SLIP OF THE DAY does not exist  — *spec is right*
spec:101 and the done-checklist spec:157 require the Parlay Lab to surface a
"MODEL SLIP OF THE DAY" (best 2–3 leg combination by model-fair
probability-weighted EV at standard −110). `grep -rn "SLIP OF THE DAY|
slip_of|slipOfThe" backend/ artifacts/moneyline/src` returns **nothing**.
No endpoint, no component, no test. This is the largest outright spec gap in
the model lane.

### 2.2 `parlay_vig_comparison` reports model EV, not book margin — *spec is right*
`backend/odds.py:116-128`. Spec:75 asks for "the book's total margin vs the
same legs bet singly". The code computes
`parlay_take = −(P_model·D_book − 1)` and
`singles_take = mean(−(p_i·D(−110) − 1))` — expected loss **at the model's
probabilities**, which is an EV, not an overround. The docstring
(`odds.py:116`) is honest about it, but the keys are named
`parlay_house_take_pct` / `singles_house_take_pct` and the UI reads them as
house margin. With a model edge these can go negative, i.e. a "house take"
that is actually the bettor's edge.

### 2.3 `/api/price` serves the 1962–2012 playoff logistic for live-season inputs — *spec is right*
`backend/inference.py:55-59` always computes `playoff_prob`, and
`backend/main.py:490-504` (`POST /api/price`) returns it for arbitrary
inputs. `artifacts/moneyline/src/tabs/desk.tsx:48` feeds **live 2026 team
inputs** into that endpoint. Spec:79 says the historical logistic "would be
miscalibrated here; keep that logistic where it belongs, in the historical
panels".

Mitigation that exists: the UI suppresses it —
`artifacts/moneyline/src/components/pricer-panel.tsx:188-205` renders a link
to the Season Desk ("SIMULATED, NOT THE HISTORICAL LOGISTIC") instead of the
gauge whenever `liveContext` is set. So this is a **latent backend leak**, not
a visible violation: the API hands out a miscalibrated number with no
`historical_only` marker, and only the frontend's discipline hides it.

### 2.4 Same-game refusal keys on `gamePk`, not on teams — *spec is right*
`backend/main.py:1001-1007`. Spec:72 refuses legs "from the same game"
because they are correlated. A doubleheader is two distinct `gamePk`s with
the same two teams on the same day; both legs pass the check and get
multiplied under the stated independence assumption. Same-team-both-games and
opposite-sides-of-a-doubleheader slips are priced as if independent.

### 2.5 Pythagorean is re-implemented inline in `players.py` — *spec is neutral, reuse is wrong*
`backend/players.py:119-121` and `:187-189` inline
`x²/(x²+y²)` instead of calling `backend/odds.py:131-135`
`pythagorean_strength()`, bypassing its `max(·,1)` guard. Two copies of the
same audited formula is exactly the drift risk the doctrine exists to
prevent. Also undocumented: the "average team" baseline for that reprice is
the mean of team **runs scored** (`players.py:49-51`), used as both RS and RA.

### 2.6 Chain precision is inconsistent between call sites — *minor*
`inference.py:60-62` computes `generic_strength` from the **unrounded** RS/RA
floats, but `feeds.py:221-226`, `season_sim.py:186-188`, `season_sim.py:254-256`
and `main.py:531-535` all read `model["predicted"]["rs"|"ra"]`, which
`inference.py:85-86` has already rounded to one decimal. The two paths can
differ in the last digit before the round-to-5 snap.

### 2.7 Pulse lexicon terms overlap and match without a trailing boundary — *spec is right*
`backend/analytics.py:26-35` contains both `"streak"` (positive) and
`"losing streak"` (negative), so "…in a losing streak" scores +1 **and** −1.
`analytics.py:282-285` `_matches()` uses `(?<![a-z])` with **no trailing
boundary**, so `"torn"` matches "tornado", `"sweep"` matches "sweeping",
`"streak"` matches "streaking". Spec:90 demands "a scoring rule a reader can
audit in ten seconds" — overlapping terms and prefix matches break that.
(Disclosed-only data, so not a price violation — see §3.)

### 2.8 In spec, verified
Checked and **conforming**, no drift: mWAA share and delta formulas
(spec:55-57 vs `analytics.py:74-80`, `:130-137`); qualified-pool means
(spec:56 vs `feeds.py:812-815`); starter share cap `[0.4,0.8]` (spec:64 vs
`analytics.py:15-16`, `:191-196`); bullpen-proxy blend (spec:65 vs
`analytics.py:199-214`); dual SEASON/ADJ grading (spec:68 vs
`record_store.py:40-44,112-150,197-207`); parlay leg bounds 2–6 (spec:71 vs
`odds.py:74` + `main.py:118`); independence note stated out loud
(spec:72 vs `main.py:130-134`); ½-Kelly gated on EV>0 with the
`0.00 — NO EDGE` string (spec:74 vs `main.py:869-874`); seeded N=2000 sim
under the top-6 format from simulated standings, not the logistic (spec:79 vs
`season_sim.py:30-31,125-135,318-322`); 2027 refusal (spec:81 vs
`season_sim.py:46-55`); hitter-vs-pitcher refusal (spec:81 vs
`players.py:239-250`); no salary served (spec:45 vs `players.py:28-34,85`).

---

## 3. DOCTRINE AUDIT

Contract: (a) coefficients always from `load_models()`, never literals;
(b) media pulse and injury flags are disclosed context and NEVER move a price;
(c) honest refusals instead of fake precision.

### (a) Hardcoded coefficients — **NONE FOUND**

`grep -rn "2737|1584.9|2913|1514.3|804.6|837.4|0.1058|80.88"` over
`backend/`, `artifacts/`, `lib/`, `scripts/` returns hits in exactly three
places, all legitimate:

- `backend/static_data/track_record.json` and `ba_paradox.json` — **generated**
  by `precompute.py:251-252` from the live fit, not authored.
- `verified_stats.json:13-42` — the hand-checked ground-truth reference the
  smoke test asserts *against*; it is the oracle, not an input to pricing.

Every consumer goes through `load_models()`:
`analytics.py:38-46` (`_coefficients()`), `analytics.py:49-51`
(`runs_per_win`), `inference.py:65-71` (receipts),
`inference.py:42,45,51,56` (predictions). `analytics.py:17-22`,
`season_sim.py:34-55` and `players.py:28-34` even rebuild their *label copy*
per call so the season is never a literal. The spec's illustrative literals
(spec:53 `−804.6 + 2737.8·OBP + 1584.9·SLG`, spec:58 `0.1058`) appear
nowhere in code.

Softer, non-coefficient literals worth naming (none are model parameters):

- `backend/main.py:557` — `vig_threshold = max((vig or 0.0476)/2, 0)`. The
  `0.0476` is a hardcoded fallback two-sided −110 overround used to decide
  the `VALUE` vs `INSIDE THE VIG` verdict when the caller supplies only one
  book line. It is derivable as `market_vig(-110,-110)` (`odds.py:33-39`) but
  is written out instead.
- `backend/odds.py:102` — `leg_book_line: int|float = -110` default. Stated in
  the docstring and returned as `leg_reference_line`, so it is disclosed; it is
  a market convention, not a model coefficient.
- `backend/odds.py:133-134`, `players.py:119-121,187-189` — Pythagorean
  exponent `2`, three separate copies (see §2.5).
- `backend/analytics.py:15-16` — `INNINGS_SHARE_FLOOR/CAP = 0.4/0.8`. These
  are the spec's own values (spec:64), correctly named constants.

### (b) Pulse / injury flags reaching a price — **NONE FOUND**

Traced every path:

- `backend/feeds.py:228-302` `_price_game`: `model_prob_home` is computed at
  `:239` from `_team_inputs` alone. `context["flags"]` is read at `:275-278`
  and only attached to the response dict at `:297`. `adj_prob` at `:260`
  derives solely from `_blended_side` (probable-starter stat lines), which per
  spec:62-66 is a sanctioned experiment, not media data. Injury flags are
  fetched in the *same* `asyncio.gather` (`feeds.py:875-879`) but are never
  threaded into `_blended_side`.
- `backend/main.py:947-972` `/api/team-live`: `flags` and `pulse` are fetched
  in `try/except` blocks *after* the team payload is built, merged in at
  `:967-971`, and shipped with an explicit
  `"hard_rule": "Flags and pulse are disclosed context; they never move a price."`
- `backend/wire.py:165-183` `get_team_pulse`: pure read of wire items →
  `score_pulse_items`, returns its own `hard_rule` string at `:182`. It has no
  caller in any pricing path.
- `backend/analytics.py:234-279` `score_pulse_items` imports nothing from
  `odds` or `inference` and returns no price field.
- `backend/season_sim.py:38` states "No trade, injury, fatigue, or
  pitching-matchup modeling" as an assumption, and the sim's only inputs are
  standings, team rates and schedule (`:239-256`).
- Frontend: `pulse` appears only in `components/pulse-meter.tsx` (display),
  `pricer-panel.tsx:267` (renders the meter), `tabs/desk.tsx:98` (passes it
  through as `liveContext`). No arithmetic anywhere.

The doctrine holds. Note only that `analytics.py:26-35`'s lexicon is
double-counting (§2.7), which corrupts a *disclosed* number, not a price.

### (c) Computed numbers where the spec wants a refusal — **ONE, and it is guarded at the surface**

- **`/api/price` playoff_prob on live inputs** — §2.3. `inference.py:55-59` →
  `main.py:490-504`, reached with live 2026 inputs via `desk.tsx:48`. The spec
  wants the historical logistic confined to historical panels. The response
  carries no flag distinguishing "historical, calibrated" from "live,
  miscalibrated"; the refusal exists only in
  `pricer-panel.tsx:188-205`. Any other consumer of `/api/price` gets a
  precise-looking number the spec says shouldn't be quoted for 2026.

Refusal boundaries that **are** correctly implemented:

- Hitter vs pitcher → `players.py:239-250`, `mode: "boundary"`,
  `verdict: None`, both cards shown side by side. Matches spec:81/spec:100.
- 2027 → `season_sim.py:46-55` `next_season_refusal()`, attached at
  `season_sim.py:323`. Verbatim spec:81 language.
- Same-game parlay legs → `main.py:1001-1007`, 400 + `correlated_legs`.
- Player below the pool floor → `main.py:891-895`, `:990-995`, 404 with the
  `NOT IN THE {season} POOL` message rather than an extrapolated line.
- No salary served → `players.py:28-34`, card carries
  `"salary": {"available": False, …}` (`players.py:85`).
- Offense-only pricing when OOBP/OSLG are absent → `inference.py:44-48`
  returns `ra/rd/wins/playoff_prob = None` and `fair_line = None` rather than
  guessing (`inference.py:91-92`).

---

## 4. TEST COVERAGE

### What `smoke_test.py` actually verifies

**v1 chain (`main()`, `smoke_test.py:47-112`)**
- Bundle shape and year range (`:53-54`).
- 2002 OAK chain vs `verified_stats.json`: RS ±2, RA ±2, W ±1, playoff prob ±0.02 (`:56-66`).
- `rs` model intercept ±1 and both coefficients ±2 (`:68-71`).
- `probability_to_moneyline(0.6) == −150`; `moneyline_to_probability(−150)`, `(+130)` ±0.001 (`:73-85`).
- `half_kelly_fraction(0.6, +150) == 1/6`; `(0.6, −150) == 0` (`:86-91`, `:104`).
- `edge_probability(0.6, 150) == 0.2` (`:92-97`).
- `market_vig(−110,−110) == 0.047619` (`:98-103`).
- `log5(pythag(800,650), 0.5) == pythag(800,650)` (`:105-111`).

**Production boot (`:118-165`)** — `python -m backend.main` binds `$PORT` and answers `/api/health` with `model_loaded: true`.

**v2 math (`v2_tests`, `:168-313`)**
- `runs_per_win()` equals `1/slope` exactly, and ≈ 9.5 ± 0.2 (`:175-176`).
- Hitter mWAA: +.050 OBP at a 10% PA share → ΔRS and mWAA against hand arithmetic; receipts sum to ΔRS (`:178-200`).
- Pitcher: ΔRA against hand arithmetic and `mwaa > 0` (sign flip) (`:202-215`).
- Parlay: `0.55×0.55 = 0.3025` → `+230`; `−110×−110 → +264` vs fair `+300`; `parlay_take > singles_take`; `60/60 @ +250` EV `0.26` and half-Kelly `0.052` (`:217-240`).
- Same-game rejection through the real app: `POST /api/parlay/price` → 400 `correlated_legs` (`:242-254`).
- `parse_innings("139.2") == 139⅔`; innings share `90/(15×9)`, cap 0.8, floor 0.4, `None` on 0 GS; blend arithmetic both fields (`:256-264`).
- Percentile at 100.0 and 50.0; `beane_badge(80,55)` true, `(70,55)` false (`:266-270`).
- Pulse: one 3-item fixture → `+2/−3`, score `−20`, 2 evidence rows (`:272-282`).
- Sim determinism: same seed+inputs identical, different seed differs, odds in `[0,1]`, playoff spots sum to 10 on a 12-team/2-division-per-league fixture (`:284-311`).

### Math with **no coverage at all**

**Model constants never asserted.** Only `rs.intercept_` and `rs.coef_` are
checked (`:68-71`). `verified_stats.json:26-42` also pins
`ra.intercept_ −837.4`, `coef_OOBP 2913.6`, `coef_OSLG 1514.3`,
`wins.intercept_ 80.88`, `coef_RD 0.1058` — **none are asserted**. The W~RD
slope, which is the entire runs-per-win receipt and the mWAA multiplier, is
only checked through the loose `9.5 ± 0.2` band, which a 5% slope drift would
pass. `verified_stats.json:19-24` (`ba_paradox`) and `:90-98` (`prior_join`)
are likewise never compared to a fit.

**Odds primitives, branch coverage**
- `pythagorean_strength` — never called directly with a meaningful assertion;
  only used as a fixture input at `:105`. The `max(·,1)` clamp is untested.
- `log5_probability` — only the degenerate `S_b = 0.5` identity. No asymmetric
  case, no `den == 0` branch (`odds.py:143-144`).
- `probability_to_moneyline` — three points, none at the round-to-5 boundary,
  and the `ValueError` guard (`odds.py:11-12`) is untested.
- `moneyline_to_probability` / `decimal_odds` — zero / non-finite guards
  untested (`odds.py:23-24`, `:45`).
- `decimal_to_american` — the `decimal <= 1` guard untested (`odds.py:61-62`).
- `parlay_probability` — the 2–6 leg guard and the per-leg range guard
  (`odds.py:74-79`) are never exercised at the function level; only Pydantic's
  `min_length/max_length` is (`main.py:118`).
- `parlay_vig_comparison` — called only with `parlay_book_line=None`
  (`:226`). The `book_odds is not None` branch (`odds.py:113-115`) is untested,
  and so is the whole `result["book"]` block in `main.py:866-876`
  (edge_pp, ev_per_unit, the `0.00 — NO EDGE` stake string).

**Chain integration** — nothing tests a *price*, only its pieces.
- `feeds.py:215-227` `_chain_probability` — no test.
- `feeds.py:743-773` `_blended_side` — no test. `blend_defense_inputs` is
  tested in isolation, but the SEASON→ADJ end-to-end (probable resolution,
  missing-starter fallbacks, `adj_fair_lines`) is not.
- `feeds.py:228-302` `_price_game` — no test; the fixture-free path means the
  dual-price payload shape is unverified.
- `main.py:508-597` `/api/matchup` — the four-way verdict ladder
  (`VALUE` / `INSIDE THE VIG` / `NO VALUE` / `NO LINE`, `main.py:558-566`) and
  the `0.0476` fallback threshold are entirely untested.
- `players.py` — `build_player_card`, `_reprice_line`, the inline Pythagorean
  reprice (`:119-121`, `:187-189`), `_primary_kind` two-way tiebreak
  (`:219-229`) and, critically, the **hitter-vs-pitcher boundary payload**
  (`:239-250`) have no test, though spec:156 lists it as a done-check.
- `season_sim.py` — `get_season_sim` (cache signature, season scoping,
  pace/delta rows) and `get_team_outlook` are untested; only the pure
  `simulate_season` is. `next_season_refusal` is untested.
- `record_store.py` — dual SEASON/ADJ grading (`:112-150`, `:197-207`) and
  parlay-slip grading have no test, despite spec:160 requiring the record to
  survive a restart and grade both.

**Analytics edge cases**
- `percentile` — the empty-pool `0.0` return (`analytics.py:179-180`) and the
  `equal` midpoint term (`:182-183`) are untested; the fixture has no ties.
- `parse_innings` — only `"139.2"`. The `.1 → ⅓` case, integer strings,
  `None`, and both `ValueError` fallbacks (`:225-226`, `:230-231`) are untested.
- `score_pulse_items` — one fixture. The overlap bug (§2.7, "streak" vs
  "losing streak") and `_matches`'s missing trailing boundary (`:282-285`)
  are not covered, and the fixture happens to avoid both.
- `starter_innings_share` — the `innings_pitched <= 0` branch (`:193`) is
  untested (only `games_started == 0` is).

**Missing feature, so missing test** — MODEL SLIP OF THE DAY (§2.1).
