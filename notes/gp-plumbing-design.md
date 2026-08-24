# Games-played plumbing — design groundwork

**Scope:** put `games_played` on a slate row so the verdict engine's `min(gp)` gates have a
real source, without moving a price. Read-only lane, written 2026-08-24 against `bb4d90f`
plus the uncommitted `backend/verdict.py`. **No code written. Nothing committed.**

`backend/main.py` is being edited live by the coordinating session — its line numbers below
were re-verified immediately before writing and will drift. `backend/feeds.py` is clean at
`bb4d90f`; its line numbers are stable.

---

## 0. Verdict up front

**The data is already in `_price_game`'s hands and is currently thrown away.**
`_slate_context` fetches the full team directory — which carries `games_played` per team —
and stuffs it into `context["directory"]` (`feeds.py:989, 994`). Nothing in the codebase
ever reads that key. `_price_game` receives that same `context` and uses only
`context["pitchers_by_id"]` and `context["flags"]`.

So the real fix is **four lines in one function, zero new I/O, zero new network calls, zero
new failure modes**, and it deletes a dead field by giving it a consumer.

Recommendation: do it, drop the teams-live frontend stopgap rather than shipping it, and
add `gp_home`/`gp_away` to the ledger at the same time. The stopgap is not merely
redundant — §4 shows it turns a lookup miss into a verdict that says `early_season` when
the truth is "we could not find the team", which is the exact species of fake-precision the
desk refuses.

---

## 1. Where games-played already exists

### 1.1 The origin — standings (`feeds.py:721`), verified

Inside `get_standings()`'s loader, per team record:

```python
                teams.append(
                    {
                        "team_id": team_id,
                        "name": name,
                        "code": _team_code(name),
                        "league_id": league_id,
                        "division_id": division_id,
                        "wins": int(team_record["wins"]),
                        "losses": int(team_record["losses"]),
                        "games_played": int(team_record["gamesPlayed"]),     # feeds.py:721
                        "runs_scored": int(team_record.get("runsScored", 0)),
                        "runs_allowed": int(team_record.get("runsAllowed", 0)),
                        "division_rank": team_record.get("divisionRank"),
                    }
                )
```

Three properties that matter:

- `name` is resolved through the `/api/v1/teams` payload first (`feeds.py:697-702`), so
  `code` is `_team_code(full_name)` — the replit.md rule is already honoured here.
- The loader hard-fails unless all 30 teams are present (`feeds.py:727-728`:
  `if len(teams) != 30: raise FeedUnavailable(...)`). There is no partial-directory state.
- It rides the ~10-minute `cache`, keyed `standings:{season}` (`feeds.py:731`).

`get_team_directory()` is a one-liner re-key of that list (`feeds.py:1003-1004`):

```python
async def get_team_directory() -> dict[int, dict[str, Any]]:
    return {team["team_id"]: team for team in await get_standings()}
```

**Keyed by MLB `team_id`, not by code.** That is the whole reason the backend fix is safe
and the frontend stopgap is not (§4).

### 1.2 The `THRU {n} GP` label (`feeds.py:949`), verified

`get_team_live()`:

```python
async def get_team_live(team_id: int) -> dict[str, Any]:
    """Live current-season inputs + record for one team, from the same cached feeds."""
    directory = await get_team_directory()
    if team_id not in directory:
        raise FeedUnavailable("Unknown MLB team id.")
    inputs, _cached = await _team_inputs(team_id, current_season())
    return {
        **directory[team_id],
        "inputs": inputs,
        "sample_label": f"THRU {directory[team_id]['games_played']} GP",   # feeds.py:949
    }
```

Note the shape: `directory[team_id]` and `_team_inputs(team_id, …)` side by side. This
function is already the pattern the fix generalises to two teams.

### 1.3 The dead carrier — `_slate_context` (`feeds.py:983-998`), verified

```python
async def _slate_context(season: int) -> dict[str, Any] | None:
    """Pools + rosters context used to enrich slate rows; None degrades."""
    try:
        pitchers, flags, directory = await asyncio.gather(
            get_player_pool("pitching", "all"),
            get_injury_flags(),
            get_team_directory(),                                          # feeds.py:989
        )
        return {
            "pitchers_by_id": {p["player_id"]: p for p in pitchers},
            "flags": flags,
            "directory": directory,                                        # feeds.py:994
        }
    except Exception:
        logger.warning("slate_context_unavailable — rows degrade gracefully")
        return None
```

```
$ grep -rn 'context\["directory"\]\|context\.get("directory")\|\["directory"\]' backend/
(no output)
```

`context["directory"]` has **no reader anywhere in `backend/`**. The directory is already
fetched on every slate build and discarded. `get_team_directory()` is additionally already
awaited by `get_injury_flags()` (`feeds.py:1014`) on the same gather, so the standings cache
is warm regardless.

### 1.4 Why `_team_inputs` is the wrong place (`feeds.py:260-274`), verified

```python
async def _team_inputs(team_id: int, season: int) -> tuple[dict[str, float], bool]:
    (hitting, hit_cached), (pitching, pitch_cached) = await asyncio.gather(
        _team_group_stats(team_id, season, "hitting"),
        _team_group_stats(team_id, season, "pitching"),
    )
    hitting_stat = _extract_stat(hitting)
    pitching_stat = _extract_stat(pitching)
    return (
        {
            "obp": float(hitting_stat["obp"]),
            "slg": float(hitting_stat["slg"]),
            "oobp": float(pitching_stat["obp"]),
            "oslg": float(pitching_stat["slg"]),
        },
        hit_cached and pitch_cached,
    )
```

Its return value is the **model input vector**. It is splatted straight into the chain —
`predict_from_inputs(**away_inputs)` (`feeds.py:306`), `_blended_side(..., away_inputs, ...)`
(`feeds.py:341`), `predict_from_inputs(**inputs)` in `_screener_live` (`main.py:738`) and
`season_sim.py:185, 253`. Adding a fifth key to that dict would be passed as a keyword
argument to the regression and raise `TypeError` in at least four call sites.

It is also the one function the price-chain tests stub
(`tests/test_price_chain_integration.py:196-202`), so changing its contract changes what the
regression suite is actually testing.

**`_team_inputs` must not change.** The model input vector stays exactly four floats.

---

## 2. The minimal change

### 2.1 What changes: `_price_game`, and only `_price_game`

Two edits inside `backend/feeds.py`, both in `_price_game` (`feeds.py:315-389`).

**(a)** After the ids are in hand and before the return — the natural spot is alongside the
existing `flags` assembly at `feeds.py:362-365`, which already reads from `context` by
`int(..._info["id"])`:

```python
    away_gp: int | None = None
    home_gp: int | None = None
    if context is not None:
        directory = context.get("directory") or {}
        away_row = directory.get(int(away_info["id"]))
        home_row = directory.get(int(home_info["id"]))
        away_gp = away_row.get("games_played") if away_row else None
        home_gp = home_row.get("games_played") if home_row else None
```

**(b)** Two keys added to the returned dict, placed next to `away_inputs`/`home_inputs`
(`feeds.py:385-386`) to match the existing `away_*`/`home_*` pairing convention:

```python
        "away_gp": away_gp,
        "home_gp": home_gp,
```

Two scalars, not a pre-computed `min`. The `min()` and the 30/60/100 bands belong to
`verdict.py` (`verdict.py:352-354`, `verdict.py:127-131`), which needs each side separately
for `sample.gp_home` / `sample.gp_away` (`verdict.py:506-507`). Baking `min` into the row
would move a threshold decision into the feed layer.

Everything is `.get()`. **Nothing on this path can raise**, so no game can be pushed into
the `pricing_error` branch (`feeds.py:462-474`) by a gp lookup — which would drop a price
off the slate and *would* be a price change.

### 2.2 What does not change

| Function | Why untouched |
|---|---|
| `_team_inputs` (`feeds.py:260`) | model input vector; see §1.4 |
| `_chain_probability` (`feeds.py:301`) | the price chain itself |
| `_blended_side` / ADJ block (`feeds.py:339-361`) | gp is not a blend input |
| `_team_code` (`feeds.py:280`) | no new code mapping is introduced (§4) |
| `get_standings` / `get_team_directory` | already emit `games_played` |
| `_slate_context` (`feeds.py:983`) | already fetches `directory`; only gains a reader |
| `historical_slate` (`feeds.py:392`) | see §2.4 |
| `backend/odds.py`, `backend/analytics.py`, `backend/inference.py` | no price math touched |
| `POST /api/price` (`main.py:531-547`) | takes `PriceInput` (obp/slg/oobp/oslg); never sees a slate row |
| `/api/matchup`, `/api/screener`, `/api/season-sim` | do not call `_price_game` |

`grep -rn "_price_game" backend/` returns exactly one production call site,
`feeds.py:461`, inside `get_slate`'s `bounded_price`. The blast radius is one endpoint.

### 2.3 The degraded path is the correct one

`_slate_context` returns `None` when standings (or pools, or rosters) fail
(`feeds.py:996-998`). Then `context is None`, both gp values are `None`, and `verdict.py`
gates:

```python
    known_gp = [gp for gp in (gp_home, gp_away) if gp is not None]      # verdict.py:352
    min_gp = min(known_gp) if len(known_gp) == 2 else None
    early_season = min_gp is None or min_gp < THRESHOLDS["gp_hard_floor"]
```

Missing gp gates rather than defaults — exactly what §3.5 of `notes/verdict-design.md`
requires. Note this also means an ADJ-less degraded slate produces no verdicts at all;
that is the honest outcome, but the frontend copy should distinguish it (§2.5).

**Do not** have `_price_game` call `get_team_directory()` itself as a fallback when
`context is None`. It is one extra await on a warm cache, but it converts a `FeedUnavailable`
into a raise inside `bounded_price`, which turns a priced game into a `pricing_error` row.
That deletes a price. Use the context or accept `None`.

### 2.4 Historical and error rows get nothing

`historical_slate` rows (`feeds.py:392-442`) are 1962–2004 full seasons against an `AVG`
baseline. They are not live games and no verdict should ever run on one. Adding a fake
`away_gp: 162` would be a fabricated sample claim. Leave them without the keys; the verdict
path must gate on `slate.mode === "live"` before it evaluates anything. Likewise
`pricing_error` rows (`feeds.py:462-474`) — already excluded everywhere.

### 2.5 One frontend line, not mine to write

The slate-row TypeScript type lives at `artifacts/moneyline/src/components/slate-rail.tsx:26`
and needs `away_gp?: number | null; home_gp?: number | null`. That file is in the
coordinator's lane; flagging, not touching.

---

## 3. The proof that no price moved

### 3.1 The `/api/price` diff is mandatory, achievable byte-for-byte, and nearly worthless here

`POST /api/price` (`main.py:531-547`) takes a `PriceInput` of `obp/slg/oobp/oslg/season`
(`main.py:110-119`) and returns `predict_from_inputs(...)` plus `data_ranges` from
`load_data()`. **It never touches `feeds.py`, `_price_game`, or a slate row.** Its output is
byte-identical after this change *by construction*, which also means it cannot detect this
change at all. Run it because the plan mandates it, but do not report it as the proof:

```bash
BASE=/tmp/claude-1000/-home-runner-workspace/<session>/scratchpad
mkdir -p "$BASE"
# BEFORE the edit, with the API server running:
curl -s -X POST localhost:80/api/price -H 'content-type: application/json' \
  -d '{"obp":0.339,"slg":0.432,"oobp":0.315,"oslg":0.384,"season":2002}' \
  | python -m json.tool --sort-keys > "$BASE/price_before.json"
# AFTER the edit and a restart, same command -> price_after.json
diff -u "$BASE/price_before.json" "$BASE/price_after.json"   # MUST be empty
```

(The payload is the hand-checked 2002 A's chain from `verified_stats.json:oak_2002_chain`,
so a non-empty diff is also a known-value regression.)

### 3.2 What "identical" actually means for the slate row

A row gains keys, so byte-identity is the wrong predicate and asserting it would be a lie.
The exact predicate:

> Let `B` be the `_price_game` return dict before the change and `A` after, for the same
> inputs. Required: **`∀k ∈ B: k ∈ A ∧ A[k] == B[k]`** (every pre-existing key present and
> equal, recursively — including `fair_lines`, `adj_prob`, `adj_fair_lines`, `adj_detail`,
> `model_prob_home`, `away_inputs`, `home_inputs`, `cache_hit`), **and
> `set(A) − set(B) == {"away_gp", "home_gp"}`** — exactly two added keys, no more.

Key *order* is not part of the contract (JSON objects are unordered and every consumer
indexes by name), but insertion order will in fact be preserved if the two keys are appended
where §2.1(b) says.

### 3.3 The strong proof: deterministic, offline, both context paths

`/api/slate` is networked and carries `updated_at`, `cache`, and `record_persisted`, so two
live calls are never identical and a live diff can only ever be corroboration. The real
proof stubs the one networked dependency exactly as
`tests/test_price_chain_integration.py:196-202` already does, and dumps the row.

Write once, run before and after the edit:

```bash
cat > "$BASE/dump_row.py" <<'PY'
"""Dump _price_game's row for a fixed game, both context paths. Deterministic."""
import asyncio, json, sys
sys.path.insert(0, "/home/runner/workspace")
from backend import feeds

WEAK = {"obp": 0.300, "slg": 0.380, "oobp": 0.345, "oslg": 0.440}
OAK  = {"obp": 0.339, "slg": 0.432, "oobp": 0.315, "oslg": 0.384}   # verified_stats.json
BY_ID = {111: WEAK, 133: OAK}

async def fake_team_inputs(team_id, season):
    return BY_ID[team_id], True
feeds._team_inputs = fake_team_inputs

GAME = {
    "gamePk": 776001,
    "gameDate": "2026-08-24T23:05:00Z",
    "status": {"detailedState": "Scheduled"},
    "teams": {
        "away": {"team": {"id": 111, "name": "Boston Red Sox"}},
        "home": {"team": {"id": 133, "name": "Athletics"}},
    },
}
CONTEXT = {
    "pitchers_by_id": {},
    "flags": {},
    "directory": {
        111: {"team_id": 111, "name": "Boston Red Sox", "code": "BOS", "games_played": 126},
        133: {"team_id": 133, "name": "Athletics",      "code": "ATH", "games_played": 124},
    },
}
out = {
    "no_context":   asyncio.run(feeds._price_game(GAME, 2026)),
    "with_context": asyncio.run(feeds._price_game(GAME, 2026, CONTEXT)),
}
print(json.dumps(out, indent=2, sort_keys=True, default=str))
PY

git stash list >/dev/null                       # BEFORE the edit:
python "$BASE/dump_row.py" > "$BASE/row_before.json"
#   ... apply the §2.1 edit ...
python "$BASE/dump_row.py" > "$BASE/row_after.json"
```

Then assert the §3.2 predicate rather than eyeballing a diff:

```bash
python - "$BASE/row_before.json" "$BASE/row_after.json" <<'PY'
import json, sys
b = json.load(open(sys.argv[1])); a = json.load(open(sys.argv[2]))
ok = True
for path in b:
    before, after = b[path], a[path]
    for k, v in before.items():
        if k not in after:
            print(f"FAIL {path}: key dropped: {k}"); ok = False
        elif after[k] != v:
            print(f"FAIL {path}: {k} moved {v!r} -> {after[k]!r}"); ok = False
    added = sorted(set(after) - set(before))
    if added != ["away_gp", "home_gp"]:
        print(f"FAIL {path}: added {added}, expected ['away_gp', 'home_gp']"); ok = False
    print(f"{path}: gp = {after.get('away_gp')}/{after.get('home_gp')}")
print("PASS — no existing key or value changed" if ok else "FAILED")
sys.exit(0 if ok else 1)
PY
```

Expected: `no_context: gp = None/None`, `with_context: gp = 126/124`, `PASS`. The
`no_context` case is what proves the degraded path (§2.3) still prices identically; the
`with_context` case is what proves the ADJ block, flags, and `cache_hit` are untouched by
the new read. `diff -u row_before.json row_after.json` should additionally show **only
added lines, never a changed or removed one** — that is the visual form of the same claim
and worth pasting into the commit message.

### 3.4 The live corroboration

Back-to-back within the ~10-minute standings/slate cache TTL so the upstream payloads are
the same cached objects, with the genuinely volatile top-level keys stripped:

```bash
STRIP='del(.updated_at, .cache, .record_persisted)'
curl -s localhost:80/api/slate | jq -S "$STRIP" > "$BASE/slate_before.json"
#   ... restart with the edit ...
curl -s localhost:80/api/slate | jq -S "$STRIP" > "$BASE/slate_after.json"
diff -u "$BASE/slate_before.json" "$BASE/slate_after.json"
```

Acceptance: every diff line is a `+` adding `away_gp`/`home_gp`. Report honestly that
`status`, `badges`, `probables`, `flags` and the `adj_*` block can legitimately move if a
game starts or a roster/injury feed refreshes between the two calls — if any of those
appear in the diff, the run is inconclusive and must be repeated, **not** explained away.

### 3.5 The rest of the gate

`python smoke_test.py` and `python -m pytest -q` before and after, per CLAUDE.md. Neither
should need editing: `tests/test_price_chain_integration.py:205-239` calls
`_price_game(_game(), 2026)` with **no context**, asserts individual keys, and never
compares whole dicts — so two new `None` keys pass untouched. Add one new test asserting
`away_gp`/`home_gp` come off `context["directory"]`, and one asserting they are `None`
when `context is None`.

---

## 4. The `/api/teams-live` frontend stopgap — assess honestly

### 4.1 Does teams-live map through TEAM_CODES? Yes.

`GET /api/teams-live` (`main.py:1197-1224`) reads `get_team_directory()`, and each row's
`team` field is the directory's `code`, which is `_team_code(full_name)` set at
`feeds.py:700`. Slate rows set `away`/`home` with `_team_code(away_name)` /
`_team_code(home_name)` at `feeds.py:371, 373`. **Both sides go through the same function**,
so for the 30 current clubs the codes agree, and `tests/test_price_chain_integration.py:214`
pins the `"Athletics" → "ATH"` case that would otherwise regress.

So the narrow question — "is the mapping consistent?" — is **yes, for live rows.** That is
not the same as the mapping being safe.

### 4.2 Where it misses

1. **The historical fallback slate — every row, always.** `historical_slate`
   (`feeds.py:392-442`) is returned whenever there are no games scheduled, the MLB API is
   down, or every game fails to price (`feeds.py:452, 478, 490`). Its rows carry
   `"away": team` from `HISTORICAL_TEAMS` (`feeds.py:74-80`) and a literal
   `"home": "AVG"`. `"AVG"` is not a team. `"OAK"` (2002 A's) is not in `TEAM_CODES`
   either — the current key is `"Athletics" → "ATH"` (`feeds.py:41`), because the bundle
   already tracks the relocation. **Both sides of every historical row miss.**
2. **`pricing_error` rows** (`feeds.py:462-474`) — codes present, no probability. Should
   never reach a verdict anyway, but the code-keyed lookup will happily "succeed" on them.
3. **A `_team_code` fallback collision.** On an unknown club name, `_team_code` derives
   initials (`feeds.py:283-295`) and logs a loud warning. Both endpoints would derive the
   *same* fallback from the *same* name, so a rename is survivable — but if the schedule
   payload and the teams payload ever disagree on a name (the exact hazard
   `feeds.py:697-699` was written to prevent, and which this stopgap re-opens on the
   client), the codes diverge and the map misses silently.
4. **A stale React Query cache.** `useTeamsLive` (`api.ts:133-134`) and the slate query are
   independent fetches with independent lifetimes. A code present in one and not yet in the
   other is a transient miss with no server-side counterpart.

The backend fix has none of these, because it joins on **MLB `team_id`** — the same integer
`_price_game` already uses for `_team_inputs` and `context["flags"]` — and never round-trips
through a string code at all.

### 4.3 What a miss does — this is the real objection

A miss yields `gp = undefined` for one side. In `verdict.py`:

```python
    known_gp = [gp for gp in (gp_home, gp_away) if gp is not None]      # verdict.py:352
    min_gp = min(known_gp) if len(known_gp) == 2 else None
    early_season = min_gp is None or min_gp < THRESHOLDS["gp_hard_floor"]
```

`early_season` becomes `True`, and the payload then carries
`verdict: "INSUFFICIENT_DATA"`, `verdict_reason: "early_season"` and flag `early_season`
(`verdict.py:221-224, 409-411`), with `sample.label` `"GP UNKNOWN"` (`verdict.py:508`).

So the desk tells the user **"too early in the season to price this"** in late August, when
the truth is **"the frontend could not find this team in a second endpoint."** The refusal
is right; the stated reason is false. That is the same failure class as
`entered_line = fair_line` — a number (here, a reason string) that reads as a measurement
and is not one. `"GP UNKNOWN"` in `sample.label` is the only honest signal in the payload
and it is contradicted by `verdict_reason` two fields away.

**Two things follow, independent of which plumbing wins:**

- `verdict.py` should distinguish `min_gp is None` from `min_gp < 30`. Suggest a separate
  reason `gp_unavailable` (flag and `verdict_reason`) for the `None` case, keeping
  `early_season` for the genuinely-early case. One extra branch at `verdict.py:354` and one
  at `verdict.py:409`. Coordinator's call — it is in their file.
- Whatever supplies gp should log a warning on a miss, the way `_team_code` does
  (`feeds.py:287-292`), so a systematic miss is visible rather than showing up as a
  season-long run of "early season" verdicts.

### 4.4 Recommendation

Ship the backend fix and **drop the stopgap without merging it.** It is not smaller than the
real fix — it costs a client-side join, a second query dependency, four miss modes, and a
false refusal reason, against four lines in `_price_game` that read an object already in
memory. If the stopgap must ship first for scheduling reasons, it should at minimum gate on
`slate.mode === "live"` and render "games played unavailable", never "early season", when
the lookup misses.

---

## 5. Should gp go in the ledger?

**Yes — `gp_home` and `gp_away` on `moneyline_record_picks`, alongside `model_version`.**

The argument is the one that just carried item 2. `model_version` was added
(`record_store.py:125-133`) so a graded pick records *which model* priced it. `gp` records
*how much season* it was priced on, and that is the second axis every honest read of the
record needs: a 4–1 stretch priced at 22 GP and a 4–1 stretch priced at 140 GP are not the
same evidence, and today the ledger cannot tell them apart. Slate snapshots are immutable
and one per date (`record_store.py:64-66`), so the information is unrecoverable after the
fact — standings for a past date are not re-derivable from the row.

It is also the natural home for the *provisional* problem: `signal_provisional` ships
hardcoded `true` until 200 graded candidates exist in a bucket
(`notes/verdict-design.md` §3.5). Bucketing by sample size is impossible without gp on the
graded row.

Shape, following the existing conventions exactly:

```sql
ALTER TABLE moneyline_record_picks
  ADD COLUMN IF NOT EXISTS gp_home integer,
  ADD COLUMN IF NOT EXISTS gp_away integer
```

- `IF NOT EXISTS`, appended to the `statements` list in `ensure_schema`
  (`record_store.py:38-140`) — the tables predate the repo and no existing row may be
  rewritten (replit.md gotcha).
- **Nullable, never backfilled.** Same reasoning as the `model_version` comment at
  `record_store.py:119-122`: rows written before gp existed stay `NULL` rather than being
  stamped with a value nobody checked against them. Reconstructing gp for a past date from
  today's standings would be exactly the fabrication that comment exists to prevent.
- Written in `store_slate_snapshot` (`record_store.py:205-231`) from `game.get("away_gp")` /
  `game.get("home_gp")` — `.get`, so a degraded row (§2.3) or a historical row (§2.4) writes
  `NULL` instead of raising.
- Mirror the two columns into `tests/conftest.py`'s `DDL` block (`conftest.py:34-59`), which
  duplicates the schema for the isolated test schema and must stay in step.

Not recommended: a `gp` column on `moneyline_slate_snapshots`. It would have to be a
league-level aggregate, and §6 is about exactly how badly those aggregate.

**Ordering:** this depends only on `away_gp`/`home_gp` existing on the row, so it lands in
the same change as §2 or immediately after. It does **not** depend on the verdict engine.

---

## 6. gp is already derived three different ways

Same `THRU {n} GP` phrasing, three different aggregations, no shared helper:

| Site | Aggregation | Renders as |
|---|---|---|
| `feeds.py:949` (`get_team_live`) | that one team's gp | `THRU 126 GP` |
| `season_sim.py:230` (team sim) | that one team's gp | `THRU 126 GP` |
| `main.py:768, 775` (`_screener_live`) | **`max`** over all 30 teams | `THRU 127 GP` |
| `season_sim.py:314` (league sim) | **`max`** over all 30 teams | `THRU 127 GP` |
| `verdict.py:508` (`_envelope`) | **`min`** of the two sides | `THRU 124 GP` |

Real MLB spread between the most- and least-played team in late August is routinely 3–5
games, so these disagree by a few games at any moment and the label never says which rule
it used. The user-visible consequence: the screener can print `THRU 127 GP` on the same
screen where a verdict prints `THRU 124 GP` for a game involving one of those same teams.

`min` is the right choice for the verdict — a two-team price is only as well-sampled as its
thinner side — and `max` is arguably right for a league-wide "how far into the season are
we" banner. But they should not share a string format that implies one meaning.

**Flagged, not fixed** (read-only lane). Two follow-ups worth a ticket, neither blocking
this change:

1. Extract one `sample_label(gp, *, basis)` helper so the label states its rule, e.g.
   `THRU 124 GP (thinner side)` vs `THRU 127 GP (league leader)`.
2. `main.py:768` — `max(team["games_played"] for team in directory.values())` raises
   `ValueError` on an empty directory. Unreachable today because `get_standings` enforces
   30 teams (`feeds.py:727`), so this is a latent coupling, not a live bug.

Also worth naming so nobody conflates them: `games` in the player pools
(`feeds.py:969, 1077`) is a *player's* games played from `stat["gamesPlayed"]`, a different
quantity that happens to come from the same MLB field name. It is unrelated to team gp and
must never feed the verdict gates.

---

## 7. Recommended order

1. §2 — four lines in `_price_game`, plus the two `feeds` tests in §3.5.
2. §3 — run the `row_before`/`row_after` predicate check and paste the result; run
   `/api/price` because the plan mandates it, while saying plainly it cannot detect this.
3. §5 — the two ledger columns, `record_store.py` + `tests/conftest.py`.
4. §4.3 — `gp_unavailable` as a reason distinct from `early_season` in `verdict.py`
   (coordinator's file, coordinator's call).
5. Drop the teams-live stopgap.
6. §6 — file the `sample_label` inconsistency; do not fix it inside this change.
