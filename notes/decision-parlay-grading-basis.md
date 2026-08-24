# The parlay grading basis: verification and what remains

*Not a decision memo — the decision was already made in code. This verifies that and states
the remainder.*

**Verdict: the asymmetry is fixed, correctly and completely, forward-only — in `0ea4cc0`, not
`bb4d90f`. The only thing left open is that the published parlay line silently mixes two
grading bases: two of the three graded slips were struck at the retired `fair_line` basis,
nothing in the payload or the UI says so, and `parlay_record()` is the one ledger reader that
never got the era-reporting the picks side has.**

Everything below is read-only: DB access was `SELECT` only, no regrade was run, no file
outside this one was edited.

---

## Answers to the five questions

**1. Confirmed, not refuted.** `STANDARD_LEG_LINE = -110` at `backend/record_store.py:19`
(the coordinator said :20 — it is :19 in the current working tree, with the explanatory
comment on :16-18). The NULL-`book_line` branch is `backend/record_store.py:508-518`, grading
at `parlay_book_decimal([STANDARD_LEG_LINE] * len(legs)) - 1`. Symmetric with `grade_pick`'s
−110 at `:273`. Covered by `tests/test_parlay_grading_basis.py`. And confirmed independently:
`git show --stat bb4d90f` touches only `backend/feeds.py` and
`tests/test_transaction_attribution.py`; the `record_store.py` change and the test file are
both in `0ea4cc0`. Detail worth having: `0ea4cc0` is authored by **Replit Agent**, `bb4d90f`
by Claude — the work and the message describing it were committed by two different authors,
which is how they came apart.

**2. The fix is complete. No other path can reach a `fair_line` fallback.** I read every
occurrence of `fair_line` and `book_line` in `backend/record_store.py`. Only three functions
read them off a parlay row:
- `grade_parlay` `:490` — the only payout-computing path, already fixed.
- `parlay_record` `:536` — display only; it passes `fair_line` and `book_line` through to
  `entries` via the `**row` spread at `:552` and computes no payout. Units come from the
  stored `units_pnl` column (`:545`), never recomputed on read. So yes — the reported line is
  struck at whatever basis each row was *graded* at, which is precisely the mixing problem in
  (3), not a second bug.
- `pending_parlays` `:580` — `SELECT`s `book_line, fair_line` but its only consumer,
  `_grade_pending_parlays` at `backend/main.py:276-320`, uses only `slip["legs"]`,
  `slip["slip_date"]` and `slip["id"]`; `grade_parlay` re-reads the price itself under
  `FOR UPDATE`.

Two **vestigial reads** are left over from the fix, both harmless but both misleading to a
future reader: `grade_parlay`'s `SELECT` at `:490` still fetches `fair_line` though nothing in
the function body uses `row["fair_line"]` any more, and `pending_parlays` at `:580` fetches
two columns nobody consumes. Reporting, not fixing — `record_store.py` is another worker's
file this session.

**3. Yes — and nothing marks them. This is the live defect.** Two graded slips (ids 3 and 5)
have NULL `book_line` and `graded_at` before the fix, so both were struck at `fair_line`.
Full row-level detail in §3 below. Nothing in the schema, the payload, or the UI distinguishes
them from a slip graded at compounded −110. The coordinator's framing is right: the same
defect, now invisible instead of visible. One correction to the framing — the retired basis
was not "optimistic"; on this data it is *pessimistic*, see §4.

**4. No.** `artifacts/moneyline/src/components/live-record.tsx:158-165` renders the parlay
block as the line plus `N SLIPS LOGGED · GRADED ALL-OR-NOTHING · ONE PUBLIC PAPER SLIP PER
DAY`. No mention of −110, of a fallback, or of a basis. A reader cannot tell what price a unit
was struck at. (Read only — that file belongs to another worker.)

**5. Something is still genuinely open, but it is smaller than the original brief and it is
not a grading question.** The math decision is closed. What is open is a disclosure decision,
and it carries one judgement call only Asher should make: the retired basis *understated* the
record by 0.89u, so correcting it would move the published number in the product's own favour
— which is exactly why the recommendation is to disclose the gap rather than close it. See
§7.

---

## 1. Where the fix actually landed

`bb4d90f`'s commit message describes the parlay grading basis fix at length, but its diff
touches only `backend/feeds.py` and `tests/test_transaction_attribution.py`. The
`record_store.py` change is in the commit immediately before it, `0ea4cc0` (authored by
Replit Agent), together with `tests/test_parlay_grading_basis.py`. The message and the code
were split across two commits.

Practical consequence: anyone auditing by reading `bb4d90f`'s diff will conclude the fix is
missing. It is not. This is very likely why `notes/v3-plan.md` still carried the item as an
open decision — the coordinator has since corrected that file.

## 2. Exact current behaviour, both paths

**Picks — `backend/record_store.py:273`**

```python
line = int(row["entered_line"]) if row["entered_line"] is not None else -110
payout = 100 / abs(line) if line < 0 else line / 100
```

A pick with `entered_line` NULL grades at a flat −110, i.e. payout 0.9091 on a win, −1.0 on
a loss.

**Parlays — `backend/record_store.py:508-518`**

```python
if row["book_line"] is not None:
    line = int(row["book_line"])
    payout = 100 / abs(line) if line < 0 else line / 100
else:
    # No book price was recorded. This used to fall back to the
    # slip's own fair_line -- grading the parlay as if you had been
    # offered the model's price, which no book offers. ...
    payout = parlay_book_decimal([STANDARD_LEG_LINE] * len(legs)) - 1
```

with `STANDARD_LEG_LINE = -110` at `backend/record_store.py:19`. A slip with `book_line`
NULL now grades at the same −110 legs compounded. **The two paths are symmetric as of
`0ea4cc0`.**

**Forward-only by construction.** The settlement `UPDATE` at
`backend/record_store.py:522-527` carries `WHERE id = %s AND result IS NULL`, and the
`SELECT ... FOR UPDATE` at `:490-495` carries the same guard. A graded slip is terminal.
`void_parlay` (`:599`) and both pick writers (`:284`, `:314`) carry the identical guard.
There is **no regrade path anywhere in the codebase** — `grep -rn "regrade\|UPDATE moneyline"`
returns only these four guarded UPDATEs and three test names.

## 3. Rows affected — queried, not inferred

`SELECT` against the live `DATABASE_URL`:

| id | slip_date | legs | fair_line | book_line | result | units_pnl | graded_at (UTC) | model_version |
|----|-----------|------|-----------|-----------|--------|-----------|-----------------|---------------|
| 1 | 2026-08-20 | 3 | +320 | **596** | LOSS | −1.0 | 2026-08-21 01:46 | NULL |
| 3 | 2026-08-21 | 3 | +320 | NULL | LOSS | −1.0 | 2026-08-23 18:09 | NULL |
| 5 | 2026-08-23 | 2 | +175 | NULL | WIN | **+1.75** | 2026-08-23 22:37 | NULL |

- Total slips: **3**. Graded: **3** (zero pending). NULL `book_line`: **2**. NULL `book_line`
  *and* graded: **2**.
- Picks, for contrast: **49** rows, **39** graded, **49** with NULL `entered_line` — i.e.
  every pick that has ever been graded was graded at the −110 fallback. The manual-entry
  feature has never been used, on either table.
- All three slips carry `model_version = NULL` (they predate the Tier 3 item 2 stamping).
- **Only one row is actually basis-sensitive.** A loss is −1.0 unit under every basis; only
  a win's payout depends on the price. So of the two old-basis rows, only slip 5 differs.
- Every graded slip has `graded_at` earlier than `0ea4cc0` (2026-08-24 04:25 UTC). The
  old-basis set is therefore exactly `book_line IS NULL AND graded_at < '2026-08-24 04:25Z'`
  — a clean, checkable partition requiring no new column.

## 4. Numeric impact

Composed from `backend/odds.py` `parlay_book_decimal` / `decimal_odds`, not re-derived:

- 2-leg −110 parlay: decimal `3.644628`, payout `2.644628` (implied 27.44%)
- 3-leg −110 parlay: decimal `6.957926`, payout `5.957926`

Slip 5 is the only row that moves: stored `+1.75` (its own `fair_line` of +175, implied
36.36%, matching its `combined_probability` of 0.3632 — that identity is the defect) versus
`+2.6446` under compounded −110.

| | units | published line |
|---|---|---|
| **Current (as stored)** | −0.2500 | `PARLAYS 1–2, -0.2u` |
| **Symmetric −110 basis** | +0.6446 | `PARLAYS 1–2, +0.6u` |
| **Delta** | **+0.8946u** | sign flip |

The current line was read live from `parlay_record()`, not reconstructed.

### The plan's framing has the sign backwards

`notes/v3-plan.md` describes the parlay side as "the optimistic one." **On the actual data it
is the pessimistic one.** Grading at your own `fair_line` is exactly zero-EV by construction:
`P·(1/P − 1) − (1 − P) = 0`. It is not a thumb on the scale in either direction — it is a
basis that cannot measure anything, because the payout is defined to cancel the probability.

Which way it errs depends on whether the model claims edge. Here the model priced a 2-leg
parlay at 36.32% that a −110-legged book prices at 27.44%; the model claims a large edge, so
being paid the book price rewards it *more* than being paid its own price. Fixing the
asymmetry therefore **improves** the published record by +0.89u and flips it from negative to
positive. That matters for how this gets communicated: it is not a correction that costs the
product anything, which removes the main reason to be suspicious of the person proposing it —
but it also means shipping it silently would look like exactly the kind of favourable
retroactive adjustment the doctrine exists to prevent.

## 5. Options

Note the size of the prize before weighing these: **one row, +0.89u.** The exposure is
trivial today and grows one slip per day.

**(a) Leave the rows, disclose the split.**
Change: `parlay_record()` at `backend/record_store.py:531-570` gains a basis aggregate
alongside the existing counts; `artifacts/moneyline/src/components/live-record.tsx:158-165`
(currently `N SLIPS LOGGED · GRADED ALL-OR-NOTHING · ONE PUBLIC PAPER SLIP PER DAY`) gains the
basis note. No row is rewritten; nothing in the DB changes. Published line stays `-0.2u` and
carries a footnote that 2 of 3 slips were graded on a retired basis.

**(b) Regrade history to compounded −110.**
Change: a one-off script `UPDATE`ing slips 3 and 5. This **violates `replit.md`** — "DB tables
predate the repo… migrations must be `IF NOT EXISTS` style and never rewrite existing rows" —
and it would require deliberately defeating the `AND result IS NULL` guard that makes
settlement terminal, a guard that `tests/test_parlay_grading_basis.py:123`
(`test_an_already_graded_slip_is_never_regraded`) and `tests/test_grade_pick.py:69` both
exist to protect. A regrade *is* a rewrite. And the rewrite happens to move the number in the
product's favour. Buys +0.89u on one row at the cost of the guarantee that a settled number
never moves.

**(c) Cutover marking — old rows flagged as a different era, never rewritten.**
Change: same disclosure surfaces as (a), but the era is stated per-row rather than as a
footnote, using the `graded_at < 2026-08-24 04:25Z AND book_line IS NULL` partition
established above. No new column needed; no row touched. The published line stays `-0.2u` and
the reader can see which rows are not comparable.

**(d) Recommended — (c), reusing the `model_version` pattern already in the tree.**
See below.

## 6. The honesty question, and the `model_version` precedent

Tier 3 item 2 (uncommitted, `backend/record_store.py`) established exactly the pattern this
decision needs, and its own comment states the principle:

```
# Stamp every ledger table with the model identity that produced the
# row. Nullable on purpose: rows written before versioning stay NULL
# rather than being backfilled with a version that was never checked
# against them. get_record reports the distinct set it actually finds.
```

and at `:407-411`:

```
# Which model priced this record. Rows written before versioning carry
# NULL and are counted, not relabelled: stamping them "v1" would assert
# something never checked against them. A record spanning a bump shows
# more than one version here, which is the point -- it is the reader's
# signal that the rows are not all comparable.
```

That is the same problem — a ledger spanning a methodology change — and it was answered by
*reporting the split*, not by rewriting rows. `get_record()` now returns
`model_versions_present` and `unversioned_picks` (`backend/record_store.py:429-430`). **The
precedent applies directly, and it rules out (b).**

**There is a concrete gap to close.** `parlay_record()` now `SELECT`s `model_version`
(`:537`) and it reaches the caller per-entry via the `**row` spread at `:552`, but the
function returns **no aggregate** — its keys are exactly
`slips, graded, wins, losses, voided, units_pnl, line, entries` (verified against the live
function). The picks side got `model_versions_present` / `unversioned_picks`; the parlay side
did not. So the table whose *grading basis* actually changed is the one with no era reporting
at all.

Which option lets a reader trust the parlay line most? **(d).** A reader can trust `1–2,
-0.2u` only if they can tell what price each unit was struck at. (b) makes the number more
internally consistent but destroys the property that makes any of it credible — that a
settled result is final. (a) is honest but buries the split in prose. (d) states it in the
payload, in the same shape the picks side already uses, and costs nothing already recorded.

## 7. Recommendation

Adopt **(d)**: leave every graded row exactly as written, and extend the existing era-reporting
pattern to the parlay table.

1. Add `grading_basis` to each `parlay_record()` entry, derived at read time, not stored:
   `"book"` when `book_line IS NOT NULL`, `"standard_-110_compounded"` when NULL and
   `graded_at` is at/after cutover, `"fair_line_retired"` when NULL and before it. Purely
   derived — no migration, no column, no write.
2. Add the aggregate `parlay_record()` is missing, mirroring `get_record`'s
   `model_versions_present` / `unversioned_picks`: a count per basis, plus
   `model_versions_present` / `unversioned_slips` for consistency with the picks side.
3. Surface it at `live-record.tsx:158-165`, which today says only `GRADED ALL-OR-NOTHING`.
   Something like `2 OF 3 SLIPS GRADED ON A RETIRED BASIS` — the ADJ block two elements up
   already has a `note` slot for exactly this kind of caveat.
4. Publish the +0.89u delta as disclosure rather than applying it. State that the retired
   basis *understated* the record and that the rows were left alone anyway. A correction
   declined in your own favour is the strongest version of the honesty claim this product
   makes.
5. `notes/v3-plan.md` Tier 1 item 1 has already been corrected by the coordinator. The one
   thing still worth carrying across: the sign of the original framing was wrong — the
   retired basis understated, it did not flatter.
6. Optional tidy-up for whoever next owns `record_store.py`: drop the two vestigial column
   reads noted in Q2 (`fair_line` in `grade_parlay`'s `SELECT` at `:490`, and
   `book_line, fair_line` in `pending_parlays` at `:580`). Neither affects behaviour; both
   imply a dependency that no longer exists.

The whole thing is read-path only. `smoke_test.py` and `pytest` should be unmoved, and no
`/api/price` number can shift.

**Do not do (b).** It is worth +0.89u on a single row, it rewrites settled history, it moves
the number in the product's own favour, and it contradicts both `replit.md` and the pattern
Tier 3 item 2 just set.

## 8. What I could not verify

- **Deploy state.** The fix is on `main`, but Asher presses Deploy. I could not confirm the
  running production process has `0ea4cc0`. If it has not been deployed, slips graded between
  now and deploy will *also* land on the retired basis, and the cutover timestamp in §3 will
  need to be the deploy time, not the commit time. Worth checking before implementing (d).
- **Exact cutover instant.** I used the `0ea4cc0` commit timestamp. It is correct for
  partitioning the three rows that exist today (all graded before it), but it is the commit
  time, not the deploy time.
- **Whether slips 2 and 4 ever existed.** The ids present are 1, 3, 5. `slip_date` is UNIQUE,
  so the gaps are most likely `ON CONFLICT DO NOTHING` burning sequence values on duplicate
  same-day attempts, which is benign — but I did not confirm that, and I did not query
  anything that would show deleted rows.
- **Whether `book_line` will ever be populated.** Same unimplemented manual-entry feature as
  `entered_line`: 49/49 picks and 2/3 slips are NULL. The one non-NULL `book_line` (596 on
  slip 1) has no recorded provenance I could trace. If manual entry is never built, the
  fallback *is* the grading basis permanently, which raises the stakes on disclosing it.
- **Frontend rendering.** I read `live-record.tsx` but did not run the app; I am describing
  the disclosure string from source, not from a screenshot.
