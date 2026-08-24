# Audit — Tier 3 items 2 (MODEL_VERSION) and 5 (Track Record)

Read-only review of the uncommitted working tree, 2026-08-24. No source file was edited.

## VERDICT

**Yes, safe to commit the backend — no, not the UI as written.**

Item 2's schema work is the cleanest part of this diff and I verified it against the live
production database, not by reading: `ensure_schema` is additive-only, and its
`CREATE TABLE` column lists match production **exactly, ordinal for ordinal**. Nothing
else in the repo pushes the Drizzle schema, so removing `db push` breaks nothing. The
`record-stats.ts` arithmetic is correct — I reproduced the Wilson interval against the
textbook closed form and the mean interval by hand, and both match to 15 digits.

What must change before this goes out is the **honesty layer**, which is the one thing
this product cannot get wrong:

1. `live-record.tsx:221` stamps the record with the **current** model version while
   **all 49 production picks carry `model_version = NULL`** (verified). The payload ships
   `model_versions_present` and `unversioned_picks` precisely so the UI can say that, and
   the UI ignores both fields. This is the exact relabelling `record_store.py:407-410`'s
   own comment forbids.
2. `proof-statement.tsx:96-97` will render **"the whole interval clears it"** against a
   break-even that no book ever offered. On today's ledger that line is live.

Both are one-paragraph fixes. Neither is a math error.

---

## What I verified vs. what I inferred

| Claim | How |
| --- | --- |
| `ensure_schema` CREATE matches production | **Verified** — read-only `information_schema` query against `DATABASE_URL` |
| Wilson + mean interval arithmetic | **Verified** — recomputed against textbook closed form and by hand |
| VOID/pending exclusion matches the backend | **Verified** — line-by-line against `record_store.get_record` |
| CSV header/row alignment | **Verified** — 17 columns, 17 fields, checked pairwise |
| Nothing else pushes the Drizzle schema | **Verified** — grep over all json/ts/sh/yml/toml; no `.github`, no CI |
| Tests pass | **Verified** — `pytest -q`: 154 passed / 2 failed (both pre-existing `test_serve_spa.py`, stale `dist/`); `smoke_test.py` green |
| `pnpm typecheck` | **Verified** — one error, `game-card.tsx:312`, in another session's active work. The `record/` components typecheck clean |
| Behaviour of the UI at other sample sizes | **Inferred** — I could not run the frontend; findings below are read from the source plus the live payload shape |

---

## 1. `ensure_schema` safety — PASS

`backend/record_store.py:38-138`. Every one of the eleven statements is additive:

- 3 × `CREATE TABLE IF NOT EXISTS` (`record_store.py:56,68,105`)
- 3 × `CREATE [UNIQUE] INDEX IF NOT EXISTS` (`record_store.py:64,86,90`)
- 1 × `ALTER TABLE … ADD COLUMN IF NOT EXISTS ×6` for the ADJ columns (`record_store.py:94`)
- 3 × `ALTER TABLE … ADD COLUMN IF NOT EXISTS model_version text` (`record_store.py:123,127,131`)

No `UPDATE`, no `DROP`, no `DELETE`, no backfill, no `SET DEFAULT`. The new columns are
declared bare `text` with no default, so PostgreSQL does not rewrite the heap and cannot
touch a graded row. Statement ordering is correct: snapshots is created before picks (FK
dependency), and each table is created before it is ALTERed.

Verified against production after the fact: 49 picks, 29 WIN / 10 LOSS / 10 pending,
0 VOID — all intact, and **0 of 49 carry a `model_version`**, i.e. nothing was backfilled.

`tests/test_model_version_stamping.py:110-131` asserts idempotency by row equality
(`assert _rows(...) == before`), which is the right assertion.

**Nit (not a defect):** `CREATE INDEX IF NOT EXISTS` matches on index *name*, not
definition. I checked `pg_indexes`: production's names are `moneyline_snapshot_date_idx`,
`moneyline_record_game_idx`, `moneyline_record_grade_idx` — identical to the migration, so
these are true no-ops. Worth knowing that the guard is name-based if anyone ever renames one.

**Nit:** on a genuinely fresh database the FK gets PostgreSQL's auto-name
(`moneyline_record_picks_snapshot_id_fkey`), where production carries Drizzle's
`moneyline_record_picks_snapshot_id_moneyline_slate_snapshots_id`. Cosmetic only; the
constraint definition is identical.

### Risk — the new bootstrap test's only isolation is `search_path`

`tests/test_model_version_stamping.py:134-170` points `record_store._connection` at
`search_path=moneyline_bootstrap_tests` and then calls `ensure_schema`,
`store_slate_snapshot` and `grade_pick` against the **production `DATABASE_URL`**. If the
schema creation on line 152-153 ever fails silently, `CREATE TABLE IF NOT EXISTS` no-ops
instead of erroring — and the test would then write and grade a pick in `public`.

In practice PostgreSQL raises `no schema has been selected to create in` when the
search_path schema is absent, so the window is narrow. But note the asymmetry with
`tests/conftest.py:100-105`, whose bare `CREATE TABLE` (no `IF NOT EXISTS`) fails loudly in
the same situation. Cheap hardening: assert `current_schema() = BOOTSTRAP_SCHEMA` before
the first write.

---

## 2. CREATE vs. reality — PASS, exactly

Cross-checked three ways: the migration's `CREATE` + later `ALTER`s, `tests/conftest.py`'s
DDL, and a live `information_schema.columns` read.

`moneyline_record_picks` — CREATE declares 15 columns (`record_store.py:68-85`), the ADJ
ALTER adds 6 (`record_store.py:94-102`), the version ALTER adds 1 (`record_store.py:127`).
Total 22. Production has 22, **in the same ordinal order, with the same types and the same
nullability**. `tests/conftest.py:34-59` declares the same 22.

`moneyline_slate_snapshots` — 4 + 1 = 5; production has 5; conftest has 5.
`moneyline_parlay_slips` — 10 + 1 = 11; production has 11; conftest has 11.

**No column is present in one place and missing from another.** Specifically, the case the
task flagged as a real bug — a column nothing ever adds — does not occur. Every column the
CREATE omits (`probables`, `adj_*`, `model_version`) is added by an ALTER later in the same
function. A fresh database and production converge.

---

## 3. Removing `drizzle-kit push` — PASS

- `.replit:39` is the only caller of `scripts/post-merge.sh`. The script now runs
  `pnpm install --frozen-lockfile` and nothing else (`scripts/post-merge.sh:1-13`).
- No `.github`, no CI config of any kind. Nothing else invokes a push.
- **Nothing imports the moneyline tables.** grep for `moneylineRecordPicksTable`,
  `moneylineSlateSnapshotsTable`, `moneylineParlaySlipsTable`, `MoneylineRecordPick`,
  `@workspace/db` across all `.ts`/`.tsx` returns zero hits outside the schema file itself.
  The header comment's claim at `lib/db/src/schema/moneyline.ts:10` is accurate.
- `pnpm typecheck` still builds `lib/db` (root `tsconfig.json:7`,
  `artifacts/api-server/tsconfig.json:13`) and it compiles clean with the new `jsonb`
  import.

**Risk — the loaded gun is still on the table.** `lib/db/package.json:11-12` still ships
`"push"` and `"push-force"`, and `lib/db/src/schema/index.ts:20` still re-exports the
moneyline tables. The file header says it is "deliberately NOT pushed", but nothing
enforces that — a hand-run `pnpm --filter db push` still reaches these tables. The mirror
is now at parity so a push would no longer propose dropping `adj_*`, which is the big win;
but drizzle names a column-level `.unique()` `{table}_{column}_unique` where production
carries `moneyline_parlay_slips_slip_date_key`, so a push could still propose churning that
constraint. Suggest deleting the two scripts, or at minimum `push-force`.

**Nit:** `scripts/post-merge.sh` mode changed 100644 → 100755. Harmless, but it is an
unannounced change in a diff already carrying scope creep (see §6).

---

## 4. `record-stats.ts` arithmetic — PASS

### Wilson score interval (`record-stats.ts:61-75`) — correct

The implementation is the standard form. I recomputed it against the textbook closed form
`(p + z²/2n ± z√((p(1−p) + z²/4n)/n)) / (1 + z²/n)` at six (successes, n) pairs including
the degenerate 0/10 and 10/10 — agreement to 15 significant figures. Clamping to [0,1] at
`record-stats.ts:70-71` is belt-and-braces; Wilson cannot escape the unit interval anyway.

Worked example on the live ledger, 29 wins of 39 decided:
`p = 0.74359`, **Wilson 95% = [0.58918, 0.85431]**.

### Mean interval (`record-stats.ts:83-99`) — correct

Sample sd with the `n−1` denominator (`record-stats.ts:88`), half-width `z·sd/√n`
(`record-stats.ts:90`), and it correctly refuses at `n < 2` (`record-stats.ts:85`).

Hand-checked on the live ledger. 29 wins at `100/110 = 0.909091u`, 10 losses at `−1u`:
- mean = `(29 × 0.909091 − 10) / 39` = **0.419580** — matches the code's output exactly
- Σ(v−mean)² = `29 × 0.489511² + 10 × 1.419580²` = 6.94901 + 20.15207 = 27.10108
- var = 27.10108 / 38 = 0.713186, **sd = 0.844504**
- half = 1.959964 × 0.844504 / √39 = **0.265044**
- **CI = [0.15454, 0.68462]**

`picksToDetect` (`record-stats.ts:103-106`) inverts `z·sd/√n < r` correctly. Called with
fixed 5% and 3% targets rather than the observed ROI (`proof-statement.tsx:43-44`), which
is the honest choice — feeding it the observed 42%/pick would print "16 more picks".
Yields 1,096 and 3,045 on the live sd. **Nit:** `Math.ceil` gives equality rather than the
strict inequality the doc comment claims, at exactly one integer. Irrelevant in practice.

### VOID / pending exclusion — matches the backend exactly

`decided()` (`record-stats.ts:41-43`) filters `result === "WIN" || result === "LOSS"`.
That is character-for-character the backend's rule at `record_store.py:355`
(`if row["result"] in ("WIN", "LOSS")`) which drives both the curve and `graded`.
`get_record` counts wins/losses/voided separately (`record_store.py:344-346`), computes
`hit_rate = wins / graded` where `graded = wins + losses` (`record_store.py:347,424`), and
VOID rows carry `units_pnl = 0` from `void_pick` (`record_store.py:311`) so they cannot move
the total either way. The client and the ledger agree.

The calibration buckets also run through `decided()` (`record-stats.ts:142`) and the
proof card filters the same way (`proof-statement.tsx:36`). Consistent throughout.

### CSV export — no mislabelled column, no dropped row

`LEDGER_CSV_COLUMNS` has 17 entries (`record-stats.ts:175-193`); the row builder emits 17
fields in the same order (`record-stats.ts:198-215`). I checked them pairwise — every
header lands on its own value. The one header that is *not* a literal field name,
`snapshot_created_at` → `e.created_at`, is correctly labelled: `get_record` selects
`s.created_at` from the **snapshot**, not the pick (`record_store.py:335`). Good call
renaming it.

No rows are dropped: `ledgerCsv(entries)` is passed the full array, deliberately not the
25-row view (`pick-table.tsx:57-63`). Quoting at `record-stats.ts:167-171` is correct
RFC-4180 (doubling embedded quotes, quoting on `" , \n \r`).

**Defect (minor, real) — the export drops the provenance it was built to carry.** The CSV
omits `model_version` and `game_pk`. `model_version` is the entire point of item 2 and the
export is the "here are the receipts" artifact; `game_pk` is the only join key back to the
MLB feed. `RecordEntry` (`record-stats.ts:19-37`) does not declare either field, so they
were never available to the writer. Add both.

**Nit:** rows are joined with `\n`; RFC-4180 specifies CRLF.
**Nit:** no guard against a leading `= + - @` (Excel formula injection). Not exploitable
here — every field is a date, a B-Ref team code, or a number — but the helper is generic.

---

## 5. Honesty check — TWO REAL DEFECTS

### D1 (highest severity) — the record is stamped with a version none of its rows carry

`artifacts/moneyline/src/components/live-record.tsx:221`:

```
{health?.model_version ? ` MODEL ${health.model_version.toUpperCase()}.` : ""}
```

This closes the METHOD footnote that sits directly beneath the hit rate, units and
calibration. `health.model_version` is `/api/health`'s report of the **currently loaded**
constant (`backend/main.py:485`). It says nothing about the rows above it.

Verified against production: **all 49 picks have `model_version = NULL`.** So
`/api/record` today returns `model_versions_present: []` and `unversioned_picks: 49`, and
the page renders `MODEL CHRONOLOGICAL-1962-2001-V1` under a record where that provenance
was never recorded for a single pick.

This is precisely what the backend refuses to do, in its own words at
`backend/record_store.py:407-410`:

> Rows written before versioning carry NULL and are counted, not relabelled: stamping them
> "v1" would assert something never checked against them.

The backend declines to relabel; the UI relabels anyway, one layer up. Both new payload
fields are unread by any frontend file (grep: `model_versions_present` and
`unversioned_picks` appear only in `record_store.py` and its test). Item 2's stated
deliverable — "`get_record` reports `model_versions_present` + `unversioned_picks`" — is
half-shipped: the honest number is computed and then discarded.

**Fix:** read the two fields from the record payload. When `unversioned_picks > 0`, say so
("49 of 49 picks predate version stamping"). When `model_versions_present.length > 1`, say
the record spans a bump. Use `health.model_version` only where it belongs — the footer
(`status-strip.tsx:22-24`), where it correctly describes the running app rather than the
ledger.

### D2 (high severity) — "the whole interval clears it", against a price nobody offered

`artifacts/moneyline/src/components/proof-statement.tsx:93-101`:

```
Break-even at the −110 fallback is {formatPct(breakEvenRate, 1)}
{rate && rate.low > breakEvenRate ? " — the whole interval clears it." : …}
```

On today's ledger this branch is taken: Wilson low = 0.5892 > break-even 0.5238. The page
will assert that a 95% interval **entirely clears break-even** — the strongest possible
statement of demonstrated edge, at n = 39.

The arithmetic is right. The comparison is not meaningful, for a reason the card does not
state: the model only ever picks its own favourite, so every pick has model probability
≥ 0.5 (mean ≈ 0.56 on the live rows). A real book would price those at roughly −127 to
−180, not −110. Comparing a favourites-only hit rate against a flat −110 break-even
manufactures apparent edge out of the fallback price itself. Beating 52.4% on a book of
56%-favourites is the null result, not the positive one.

The card does disclose the underlying fact — "no pick here was graded against a price
anyone was actually offered" (`proof-statement.tsx:120-122`) — but two paragraphs below,
and in a block headed "What it does not prove". The affirmative claim lands first, in the
same sentence as the number, in a card titled **WHAT THIS PROVES**. A reader who takes one
thing away takes "the whole interval clears break-even".

Two supporting problems in the same card:

- `proof-statement.tsx:41-42,102-107` — the luck band is `sd·√n` = ±5.27u, a **one-sigma**
  band, printed beside an actual total of +16.36u, in a card where every other interval is
  95%. "Any total inside that band is indistinguishable from a coin" is technically a
  weaker claim than 95% would give, so it is safe in itself; but the mixed confidence
  levels invite the reader to conclude that +16.36u, being outside it, is significant.
- The same sentence calls the null "a coin". The relevant null for a favourites book is
  not 50%.

**Fix (small):** make the break-even sentence conditional on there being a real price, or
reword to name what it is — "clears the −110 fallback, which is not a price this desk was
offered; against real prices for 56%-favourites it clears nothing." Keep the interval; drop
the verdict verb. Consider moving the "What it does not prove" paragraph above the claim.

### Calibration buckets — disclosed, but the floor is low (risk, not a defect)

`record-stats.ts:109-111` sets `BUCKET_MIN_N = 10` and `BUCKET_READABLE_N = 30`. On the
live ledger that produces:

| bucket | n | wins | rendered |
| --- | --- | --- | --- |
| 50–55% | 13 | 10 | 77%, de-emphasized, "TOO SMALL TO READ" |
| 55–60% | 13 | 10 | 77%, de-emphasized, "TOO SMALL TO READ" |
| 60–65% | 11 | 8 | 73%, de-emphasized, "TOO SMALL TO READ" |
| 65%+ | 2 | 1 | "n = 2 — too few to report a rate" |

So the chart will draw three bars showing the model is 20+ points under-confident, on
11–13 samples each. The refusal machinery works and the warning label is explicit
(`calibration-chart.tsx:85-89`), which is why this is a risk rather than a defect. But the
module's own justification for the floor — "A bar drawn from four picks looks like
evidence" (`calibration-chart.tsx:16`) — applies nearly as well at thirteen, and a drawn
bar outweighs a 9px label. Two options: raise `BUCKET_MIN_N` toward 30 so the floor and the
readability threshold coincide, or give each bucket its own Wilson interval — the module
already has the function, and a bucket whose band spans 50%–92% argues its own case.

### `entered_line` — handled correctly, no finding

- `pick-table.tsx:167-169` states it outright: "`entered_line` is blank on every row — no
  odds feed is ingested, so picks grade at the −110 fallback."
- `live-record.tsx:74-77`: "This is a model check, not a betting record."
- `lib/db/src/schema/moneyline.ts:60-62` documents it as unimplemented manual entry.
- Verified in production: **0 of 49 rows have a non-null `entered_line`.**

This matches `notes/v3-plan.md:45-52` exactly. Nothing presents it as a book price.

---

## 6. Other observations

**Scope creep in the same working tree** (not part of items 2 or 5, and not reviewed here):
`.replit:49-50` adds an `[objectStorage]` bucket ID, and `CLAUDE.md` gained 30 lines of
Slack channel IDs and multi-session guidance. Both are unrelated to Tier 3 items 2 and 5
and should be split into their own commit rather than riding along with a schema change.

**Type safety is nominal.** `useLiveRecord` is `fetchApi<any>` (`api.ts:117`), so
`const entries: RecordEntry[] = data.entries ?? []` (`live-record.tsx:22`) is an unchecked
cast. `RecordEntry` is documentation, not a contract — which is how `model_version` and
`game_pk` went missing from it without any compiler complaint.

**Mixed sources for n in one card.** `ProofStatement` takes its Wilson n from the
backend's `data.graded` and its mean-interval n from a client-side filter over `entries`
(`proof-statement.tsx:35-40`). They agree today because `entries` is the full ledger. If
the payload is ever paginated, the card will print two different n side by side without
noticing.

**Null-coalescing a decided pick's units to 0** (`proof-statement.tsx:37`). A WIN or LOSS
always has `units_pnl` written by `grade_pick` (`record_store.py:283-296`), so this cannot
fire; but if it ever did it would quietly bias the mean rather than surface the anomaly.

**`text-success` is hardcoded on the units tile** (`live-record.tsx`, Season Record block).
A negative unit total renders in success green. Pre-existing, carried through the rewrite.

---

## Recommended order

1. **Blocking** — D1: surface `unversioned_picks` / `model_versions_present`; stop
   labelling the ledger with `health.model_version`.
2. **Blocking** — D2: reword the break-even verdict in `proof-statement.tsx:96-100`.
3. **Should fix** — add `model_version` and `game_pk` to `RecordEntry` and the CSV.
4. **Should fix** — delete `push` / `push-force` from `lib/db/package.json`.
5. **Consider** — raise `BUCKET_MIN_N`, or add per-bucket Wilson intervals.
6. **Consider** — assert `current_schema()` in the bootstrap test before it writes.
7. **Housekeeping** — split `.replit` and `CLAUDE.md` into their own commit.

Items 1–3 of §1–§3 (schema safety, CREATE-vs-reality, push removal) need no changes.
