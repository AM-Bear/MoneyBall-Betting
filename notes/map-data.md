# MONEYLINE — Data Layer Map (Recon Lane 2)

Scope: `backend/feeds.py`, `backend/record_store.py`, `backend/precompute.py`,
`backend/wire.py`, `backend/players.py`. Read-only recon; nothing was changed.
Boundary call sites in `backend/main.py` / `backend/season_sim.py` are cited
where an identifier crosses into or out of the data layer.

---

## 0. Headline findings

| # | Severity | Finding |
|---|----------|---------|
| A | **HIGH — live bug** | `get_news()` references three names that do not exist anywhere in the repo: `RSS_URL`, `ESPN_NEWS_URL`, `_espn_dead` (`backend/feeds.py:488`, `:506-507`, `:509`). Every call raises `NameError`. The MLB.com RSS source has never worked in v2. |
| B | MEDIUM | `get_transactions()` never filters to MLB (`backend/feeds.py:679-682` sends no `sportId`), so minor-league team names reach `_team_code()` and are silently coined into phantom 3-letter codes (`backend/feeds.py:698`). |
| C | MEDIUM | `_team_code()` has a **silent** initials fallback (`backend/feeds.py:208`). A single MLB rename produces a new code with no log and no exception — the one way stored record codes and freshly-derived grading codes could diverge. |
| D | LOW-MED | `ensure_schema()` cannot bootstrap a fresh database: `moneyline_slate_snapshots` is never created by the app, and `ALTER TABLE moneyline_record_picks` (`record_store.py:38`) throws if that table is absent, rolling back the parlay-table creation in the same transaction. |
| E | LOW | `entered_line` is read at grading (`record_store.py:182,194`) but written by nothing in the codebase — every graded pick uses the `-110` default payout. |

**TEAM_CODES verdict: the graded-record path is clean.** Every identifier that
reaches or leaves Postgres passes through `_team_code()`. Details in §2.

---

## 1. External fetches

All MLB traffic goes through one shared `httpx.AsyncClient`
(`feeds.py:114-122`), `FEED_TIMEOUT_SECONDS` default **10s**, UA
`MONEYLINE/1.0`. `_fetch_json` (`feeds.py:132-151`) retries **once** after a
0.25s sleep, so worst case per logical call is ~20.25s. A `404` short-circuits
the retry and raises `GameNotFound` (subclass of `FeedUnavailable`); anything
else exhausts the retry and raises `FeedUnavailable`.

### Cache tiers (`feeds.py:108-110`) — CLAUDE.md's claims verified

| Tier | Env var | Default | CLAUDE.md claim | Verdict |
|------|---------|---------|-----------------|---------|
| `cache` | `CACHE_TTL_SECONDS` | 600s = **10m** | "slate/standings ~10m" | ✅ correct |
| `pool_cache` | `POOL_CACHE_TTL_SECONDS` | 21600s = **6h** | "pools/rosters ~6h" | ✅ correct |
| `wire_source_cache` | `WIRE_CACHE_TTL_SECONDS` | 1800s = **30m** | "transactions/news ~30m" | ✅ correct |

`AsyncTTLCache` (`feeds.py:86-105`) is a double-checked per-key `asyncio.Lock`
around an in-process dict. Two consequences worth knowing: **(a)** no negative
caching — a raising loader caches nothing and every subsequent request retries
the network; **(b)** the lock is held for the whole loader, so a slow upstream
serializes all concurrent callers of that key behind one request (see §4).

### The calls

| Endpoint | Returns | Cache | Key | On failure |
|---|---|---|---|---|
| `/api/v1/schedule` (`:158`, hydrate `probablePitcher,linescore`) | today's games + probables | `cache` 10m | `schedule:{date}` | `FeedUnavailable` → `get_slate` returns `historical_slate()` (`:402-403`) |
| `/api/v1/teams/{id}/stats` (`:176`) | team season OBP/SLG (+ against) | `cache` 10m | `team:{id}:{season}:{group}` | raises; caught per-game in `bounded_price` (`:374-386`) → row gets `pricing_error` + `FEED PARTIAL` badge |
| `/api/v1.1/game/{pk}/feed/live` (`:414`) | final score / cancellation | **none** | — | `GameNotFound` → void-after-grace; other → pick stays pending (`main.py:180-195`) |
| `/api/v1/stats` (`:448`, paged ×5 @2000) | league player pools | `pool_cache` 6h | `pool:{season}:{group}:{pool}` | `FeedUnavailable` if empty (`:474`) |
| `https://www.mlb.com/feeds/news/rss.xml` (`:488`) | headlines | `wire_source_cache` 30m | `news` | **never reached — `NameError`**, see §0-A |
| ESPN news (`:509`) | headlines | same loader | — | `try/except` + sticky `_espn_dead` — see §0-A |
| `/api/v1/teams/{id}/roster` (`:545`, 40Man, sem 5) | 40-man + IL status | `pool_cache` 6h | `rosters:{season}` | raises → `get_injury_flags` fails → `_slate_context` returns `None` (`:885-887`) |
| `/api/v1/seasons` (`:567`) | regular-season start/end | `pool_cache` 6h | `season_dates:{season}` | `FeedUnavailable` if empty (`:572`) |
| `/api/v1/standings` + `/api/v1/teams` (`:596-606`, gathered) | W/L, RS/RA, division, **full names** | `cache` 10m | `standings:{season}` | `FeedUnavailable` unless exactly 30 teams (`:638-639`) |
| `/api/v1/standings` (prior season, `:654`) | final wins by team_id | `pool_cache` 6h | `standings:final:{season-1}` | `FeedUnavailable` if <30 (`:666-667`) |
| `/api/v1/transactions` (`:679`) | 7-day transaction log | `wire_source_cache` 30m | `transactions:{days}` | raises → `wire.safe()` marks source down |
| `/api/v1/schedule` (rest-of-season, `:715`) | remaining games | `pool_cache` 6h | `remaining_schedule:{season}` | raises → sim 503 |
| `/api/v1/teams/stats` (`:981`) | all-30 team aggregates | **none** (wrapped by `pool:context` 6h) | — | `FeedUnavailable` if <30 splits (`:987-988`) |

`precompute.py` makes **no** network calls — it fits the 1962–2001 regressions
from the bundled `baseball.csv` via `model_setup.paths` and writes joblib/JSON
artifacts. It is entirely offline.

### ESPN "optional, silent skip" — only half true

The `try/except Exception: _espn_dead = True` at `feeds.py:528-530` *is* a
silent skip and *is* correctly scoped so ESPN can never fail the MLB RSS parse.
But two caveats:

1. It is **unreachable today.** `RSS_URL` at `:488` blows up before the ESPN
   block runs, so the documented "silent skip" behavior has never executed.
2. `_espn_dead` is **sticky for the life of the process** with no reset and no
   TTL. Once ESPN fails once, ESPN is dead until restart. That is arguably the
   intent ("never a dependency"), but it is not a TTL-bounded skip.
3. Even with `RSS_URL` fixed, `:507` *reads* `_espn_dead` before any assignment
   — since it is never initialized at module scope, that read is a second
   `NameError`. **Both** the constant and the flag need a definition.

Verified: `python -c "import backend.feeds as f; [hasattr(f,n) for n in
('RSS_URL','ESPN_NEWS_URL','_espn_dead')]"` → `False, False, False`.
`git log -S RSS_URL` shows the names arrived undefined in the v2 commit
`a2780cd`; this is not a later regression. The intended URL is recorded in
`notes/mlb_api_transcripts.md:127`.

**Blast radius is contained.** `wire.get_wire()` wraps each source in `safe()`
(`wire.py:102-114`), so the `NameError` is swallowed and surfaces only as
`sources_up["news"] = False`. The Wire silently ships transactions + desk notes
and no headlines. Nothing crashes; the feature is just permanently absent.

---

## 2. TEAM_CODES audit — **the graded path is clean**

`TEAM_CODES` (`feeds.py:34-65`) maps 30 **full** MLB names → B-Ref codes
(`TBR`, `SDP`, `KCR`, `SFG`, `WSN`, `CHW`, `ATH`). The single conversion
function is:

```python
# feeds.py:207-208
def _team_code(name: str) -> str:
    return TEAM_CODES.get(name, "".join(word[0] for word in name.split()).upper()[:3])
```

Every boundary, traced:

| # | Boundary | Site | Source of the identifier | Converted? |
|---|---|---|---|---|
| 1 | Slate row codes | `feeds.py:284,286` | `schedule.teams.{side}.team.name` (full name) | ✅ `_team_code` |
| 2 | Slate degraded row | `feeds.py:381-382` | same | ✅ `_team_code` — the error path converts too |
| 3 | Historical fallback slate | `feeds.py:305-346` | `HISTORICAL_TEAMS` literals (already B-Ref) | ✅ n/a — never persisted (`store_slate_snapshot` returns early on `mode != "live"`, `record_store.py:69`) |
| 4 | Standings / directory | `feeds.py:611-614, 622, 627` | **full name resolved from `/api/v1/teams`**, not the standings short name | ✅ `_team_code`, and the short-name landmine is explicitly handled with a comment at `:608-610` |
| 5 | Injury flags | `feeds.py:923` | `directory[team_id]["code"]` | ✅ inherits #4 (falls back to `"???"`) |
| 6 | Transactions wire | `feeds.py:690-698` | `toTeam.name` / `fromTeam.name` | ⚠️ calls `_team_code`, but the input is not guaranteed to be an MLB club — see finding B |
| 7 | Season sim / outlook | `season_sim.py:207, 217` | `directory[id]["code"]` | ✅ inherits #4; the sim itself keys on integer `team_id` throughout |
| 8 | `/api/teams-live` | `main.py:1090-1097` | `directory[...]["code"]` | ✅ inherits #4 |
| 9 | **Record write (picks)** | `record_store.py:101, 118, 140-141` | `game["away"] / game["home"] / pick_team` from #1 | ✅ |
| 10 | **Grading read (finals)** | `feeds.py:427-428` | `feed/live gameData.teams.{side}.name` (full name — confirmed `notes/mlb_api_transcripts.md:154-160`) | ✅ `_team_code` |
| 11 | **Grade comparison** | `record_store.py:192-193, 200` | stored `pick_team` vs `_team_code`-derived winner | ✅ both sides mapped through the same function |
| 12 | Parlay leg team | `main.py:1033-1034` | slate row codes from #1 | ✅ |
| 13 | Parlay grade comparison | `main.py:278-282` → `record_store.py:404-407` | `_team_code`-derived winner vs stored leg `team` | ✅ |
| 14 | Wire team filter | `wire.py:130-138` | user query code vs `directory[...]["code"]` | ✅ |
| 15 | Player card "team" | `feeds.py:856, 964` → `players.py:83` | `split.team.name` — **raw MLB full name, no code** | ⚠️ display-only; see below |
| 16 | Historical team pricer | `main.py:462-486` | user-supplied code → `predict_team` against `baseball.csv` | ✅ separate namespace, hard-bounded 1962–2012 |
| 17 | Historical franchise bridges | `precompute.py:56-64` | CSV codes (`ANA→LAA`, `FLA→MIA`, `TBD→TBR`, `MON→WSN`) | ✅ offline only, never touches a live feed |

**Conclusion: no unconverted identifier reaches the graded record.** The
store→grade round trip (#9 → #10 → #11, and #12 → #13) is symmetric: both ends
call `_team_code` on a full MLB club name. The specific hazard CLAUDE.md warns
about — the standings endpoint's short name `"Mets"` bypassing `TEAM_CODES` — is
already defused at `feeds.py:611-614`, which resolves full names from
`/api/v1/teams` before mapping, with a comment saying exactly why.

### The two soft spots (neither breaks grading today)

**B — MiLB names get phantom codes.** `get_transactions` (`feeds.py:679-682`)
sends only `startDate`/`endDate`, no `sportId=1`. The transcript
(`notes/mlb_api_transcripts.md:115-116`) records **1105 transactions in 7 days**,
which is far more than MLB-only volume — the response includes affiliates.
`_classify_transaction` (`feeds.py:775-791`) filters on type and description
text, not on level. So a Triple-A move survives, `team_name` is e.g.
`"Las Vegas Aviators"`, and `_team_code` silently coins `"LVA"`
(`feeds.py:698`). Effect: wire items tagged with codes that match no team, and
the `?team=` filter at `wire.py:130-138` can never match them. Cosmetic, not a
record correctness issue — the wire never touches a price or a pick.

**C — the fallback is silent.** `feeds.py:208` never logs and never raises on a
miss. If MLB renames a club (the `Athletics` → `ATH` entry shows renames do
happen here), the app keeps running and starts emitting a different code —
`"Cleveland Guardians"` would become `"CG"`. Picks stored before the rename hold
the old code; the grader derives the new one; `row["pick_team"] == winner`
(`record_store.py:193`) goes false and **every affected pick grades as a LOSS**.
This is the only route to a corrupted record, and it is a latent one, not an
active bug. A `logger.warning` on the fallback would turn a silent
mis-grade into an alert. *(Not fixed — read-only lane.)*

**#15 — inconsistent player-card team identity.** Player pool rows carry
`team_name` (`feeds.py:856, 964`) and `players.py:83` surfaces it as
`card["team"]` — a full name where the rest of the API returns a code. The
frontend renders it verbatim (`player-search.tsx:119`, `player-desk.tsx:32`),
so it is a display inconsistency only; nothing joins on it.

---

## 3. Persistence

### Tables

Four tables, all created **externally** (pre-date the repo):

- `moneyline_slate_snapshots` — `id`, `snapshot_date` (UNIQUE), `mode`,
  `created_at`. **Never created by application code.**
- `moneyline_record_picks` — `id`, `snapshot_id` FK, `game_pk` (UNIQUE),
  `game_date`, `away_team`, `home_team`, `pick_team`, `model_probability`,
  `fair_line`, `entered_line`, `final_away`, `final_home`, `result`,
  `units_pnl`, `graded_at`, plus the six v2 columns added by the migration.
- `moneyline_parlay_slips` — created by the migration (`record_store.py:47-59`).

### `ensure_schema()` (`record_store.py:30-66`) — migration safety

Two statements, one connection, one commit:

1. `ALTER TABLE moneyline_record_picks ADD COLUMN **IF NOT EXISTS**` ×6 —
   `probables jsonb`, `adj_probability`, `adj_pick_team`, `adj_fair_line`,
   `adj_result`, `adj_units_pnl` (`:38-45`).
2. `CREATE TABLE **IF NOT EXISTS** moneyline_parlay_slips` (`:47-59`).

**Verdict: strictly additive. Nothing rewrites an existing row.** No `UPDATE`,
no `ALTER COLUMN`, no `DROP`, no `DEFAULT` backfill — the six new columns
materialize as NULL on existing rows, which every reader tolerates
(`record_store.py:199, 298-307, 312-320`). Safe to run on every boot, as the
docstring claims.

**But it cannot bootstrap (finding D).** Statement 1 is `ALTER TABLE`, not
`CREATE TABLE IF NOT EXISTS`. On a database where `moneyline_record_picks`
does not exist it raises, and because both statements share one transaction
(`:61-65`), the parlay table is rolled back too. `moneyline_slate_snapshots` is
never created by any code path in the repo. Boot survives it —
`main.py:355-359` catches, logs `schema_migration_skipped`, sets
`schema_ready = False` — but every later `store_slate_snapshot` then fails
inside the scheduler's `except` (`main.py:328-333`) and the record silently
never accumulates. Given "tables predate the repo" this is by design, but it
means the app is **not** self-hosting on a fresh Postgres.

### All four write paths are guarded against rewrites

| Function | Statement | Guard |
|---|---|---|
| `store_slate_snapshot` `:77-85` | INSERT snapshot | `ON CONFLICT (snapshot_date) DO NOTHING`, then re-SELECT the existing id |
| `store_slate_snapshot` `:126-135` | INSERT pick | `ON CONFLICT (game_pk) DO NOTHING` |
| `grade_pick` `:203-210` | UPDATE pick | `WHERE game_pk = %s AND result IS NULL` + `SELECT … FOR UPDATE` at `:180-188` |
| `void_pick` `:233-240` | UPDATE pick | `WHERE game_pk = %s AND result IS NULL` |
| `store_parlay_slip` `:355-363` | INSERT slip | `ON CONFLICT (slip_date) DO NOTHING` |
| `grade_parlay` `:413-419` | UPDATE slip | `WHERE id = %s AND result IS NULL` + `FOR UPDATE` at `:389-395` |
| `void_parlay` `:490-496` | UPDATE slip | `WHERE id = %s AND result IS NULL` |

Every mutation is append-or-first-resolution-wins. A graded pick is terminal:
no code path in the repo can flip a `WIN` to a `LOSS` or re-grade a resolved
row. The `FOR UPDATE` + `result IS NULL` pairing also makes concurrent graders
(the scheduler at `main.py:313-347` plus any manual trigger) safe.

### Dual SEASON / ADJ grading

**Write** (`record_store.py:100-151`) — for each non-errored live game:

- SEASON: pick the side with `model_prob_home >= 0.5`; store `pick_team`,
  `model_probability` (the *chosen side's* probability), `fair_line`.
- ADJ: only when `game["adj_prob"] is not None` — i.e. only when at least one
  probable starter blended successfully (`feeds.py:259-274`). Independently
  picks `adj_pick_team` at the 0.5 threshold and stores `adj_probability`,
  `adj_fair_line`. When no starter blended, all four ADJ columns stay NULL and
  the pick is SEASON-only.

**Resolve** (`record_store.py:171-222`): one `winner` code, compared twice.

```python
winner    = final_away_team if final_away > final_home else final_home_team  # :192
won       = row["pick_team"] == winner                                       # :193
adj_won   = row["adj_pick_team"] == winner   # only if not NULL              # :200
```

- A tie (`final_away == final_home`) returns `False` at `:190` — the pick stays
  pending forever. Correct for MLB, which has no regular-season ties, but note
  a suspended-game 0–0 would wedge here rather than void.
- Both ledgers share **one payout** derived from `entered_line` (default
  `-110`), so ADJ inherits SEASON's price even when `adj_fair_line` differs.
  That is defensible — it isolates the pick-side experiment from a price
  experiment — but it means `adj_units_pnl` is not "what ADJ would have paid".
- When SEASON and ADJ pick the same side (the common case), the two ledgers are
  identical by construction; ADJ only diverges on games where the starter blend
  crossed the 0.5 line.

**Read** (`record_store.py:246-343`): `adj_record` (`:312-326`) counts only rows
with `adj_result IN ('WIN','LOSS')`, so SEASON-only picks never dilute the ADJ
denominator — the two records are honestly non-comparable in sample size, and
the payload says so at `:322-325`. `VOID` is terminal at 0 units and is excluded
from both the hit rate and the equity curve (`:276-286`) — the comment at
`:274-275` states the intent and the code matches it.

`get_record()` `JOIN`s `moneyline_slate_snapshots` (`:257-258`), so an orphaned
pick (snapshot deleted) silently vanishes from the record rather than erroring.

**Finding E:** `entered_line` is `SELECT`ed at `:182` and used at `:194` but
never written anywhere in the repo (`grep -rn entered_line backend/` returns
only those two lines plus the read in `get_record`). Every pick therefore grades
at the hardcoded `-110` fallback. Either the column is filled out-of-band or the
"entered line" feature is unbuilt; the payout math is honest either way, but
`fair_line` — which the model actually produced — is never what the record pays.

---

## 4. Failure modes

### Degrades gracefully ✅

- **MLB fully down.** `get_slate` catches `FeedUnavailable` (`:402`) and returns
  `historical_slate()` — the 2002 A's / 1998 Yankees set, `feed_up: False`, with
  a reason string. The single best-behaved path in the codebase.
- **One team's stats missing.** `bounded_price` (`:370-386`) catches per game and
  emits a `pricing_error` row with `FEED PARTIAL`; the rest of the slate prices.
  If *every* game fails, `:390-391` falls back to historical.
- **Pools / rosters down.** `_slate_context` catches everything (`:885-887`),
  logs `slate_context_unavailable`, returns `None` → slate rows lose ADJ prices
  and injury flags but keep SEASON prices. Doctrine-safe: the disclosed-context
  layer failing never affects a price.
- **Wire sources down.** `wire.safe()` (`:102-109`) per-source; the Wire always
  returns 200 with `sources_up` telling the truth.
- **DB down.** `database_available()` (`record_store.py:21-28`) gates the
  scheduler; `ensure_schema` failure is caught at boot. Pick endpoints 503 with
  the standard error envelope.
- **Grading feed errors.** Per-pick try/except (`main.py:193-195, 215-217`)
  returns `"pending"`; a bad pick never blocks the others. Parlays mirror this
  per-slip (`main.py:291-292`).
- **Vanished `game_pk`.** `GameNotFound` → grace period `VOID_AFTER_DAYS` before
  voiding (`main.py:180-192`), so a reschedule under a new pk isn't punished.
- **Cancelled game.** Checked *before* the `Final` check (`feeds.py:418-421`),
  with a docstring explaining that a cancelled game reports `Final` at 0–0 —
  a genuinely subtle bug that was correctly anticipated.

### Throws or hangs ⚠️

- **Worst failure mode: a slow — not dead — MLB Stats API stalls the slate with
  no ceiling.** There is no request-level deadline anywhere. `_fetch_json`
  budgets ~20.25s per logical call (10s timeout ×2 attempts + 0.25s backoff).
  `get_rosters` (`feeds.py:539-560`) fans out 30 roster calls at concurrency 5 →
  6 sequential waves → **~120s**. `get_player_pool` pages up to 5× sequentially →
  **~100s**. Both sit inside `_slate_context`, and `AsyncTTLCache.get_or_set`
  holds its per-key `asyncio.Lock` for the entire loader (`feeds.py:98-105`) —
  so every concurrent `/api/slate` request queues behind the first one. Result:
  a degraded upstream produces multi-minute hangs across the whole app rather
  than the clean historical fallback that a *dead* upstream produces. Ironically
  the total-outage path is the well-handled one.
- **Response-shape changes are only partly contained.** `get_slate` catches
  `FeedUnavailable`, not `TypeError`/`KeyError`/`IndexError`. `dates[0]` at
  `feeds.py:363` and `game["gameDate"][:10]` / `game["teams"]` at `:378-382`
  (inside the *error* handler) would raise uncaught → 500. Inside `_price_game`
  the same risk is contained by `bounded_price`.
- **Strict count assertions.** `get_standings` requires exactly 30 teams
  (`:638`), `_league_team_stats` ≥30 splits (`:987`), `get_prior_season_wins`
  ≥30 (`:666`). Correct and honest — but an expansion team, a mid-migration
  response, or a partial standings payload takes down standings, the directory,
  the sim, and the player-card baseline together, since `get_team_directory`
  (`:892-893`) is a thin wrapper over `get_standings`.
- **`/api/wire?team=X` has no guard.** `wire.py:132` calls `get_team_directory()`
  outside any try/except, so a standings failure 500s a filtered wire request
  while the unfiltered one succeeds.
- **No negative caching.** A failing loader caches nothing, so a persistently
  broken upstream is re-hit at full rate on every request. `_espn_dead` is the
  only circuit breaker in the file, and it is permanent rather than TTL'd.
- **`get_final_score` is uncached** (`feeds.py:414`) — correct for grading
  freshness, but it means a scheduler tick with N pending picks issues N live
  calls at concurrency 3 with no backoff between cycles.
