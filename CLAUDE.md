# MONEYLINE — Claude Code operating notes

Product doctrine, stack, and gotchas are shared with Replit Agent and live in:

@notes/build-history/replit.md

Read that first. Everything below is Claude-Code-specific and does not apply to Replit Agent.

**Doctrine status (rewritten 2026-09-02):** the original *keyless data / no market prices /
context never moves a price* doctrine was scratched on 2026-08-24. `notes/build-history/replit.md` states the
revised position — what survives (calibration, the graded record, refusals, receipts, no
hardcoded coefficients) and what is scratched (data purity: odds feeds, third-party
sources, context signals moving prices). Do not enforce the old rules against
`notes/v4-plan.md`. Older notes in `notes/` and everything in `attached_assets/` still quote
the old doctrine; where they disagree with `notes/build-history/replit.md`, `notes/build-history/replit.md` wins.

## Start here on a fresh session

Read `notes/v4-plan.md` — the current build order (Task 0, six phases, standing rules) and
the gates between them. Then `notes/v3-plan.md`, which v4 supersedes for *sequencing* but
which remains authoritative for what is broken and what is verified healthy in the tree.
Both supersede the strategy docs in `attached_assets/`, which were written ~9 commits behind
`main` and understate what has shipped.

Supporting detail lives in `notes/map-model.md` (price chain, doctrine audit),
`notes/map-data.md` (feeds, caches, TEAM_CODES, persistence), and `notes/map-surface.md`
(routes, frontend, v3 gap). Read the map for the area you are touching; do not re-audit
what they already cover.

## Build loop

1. **Plan before writing.** Read the relevant code, state the approach and files touched, surface open questions. Get agreement before editing. This is the cheapest place to catch a wrong turn.
2. Write it in this workspace — these files ARE the Repl, there is no sync step.
3. **Verify before reporting.** `python smoke_test.py` and `python -m pytest -q` must pass *before and after* any backend change. Add `pnpm typecheck` for TS.
4. **For anything touching price math, diff `/api/price` before and after against a declaration you wrote first.** State up front which prices should move and why, then prove the diff matches the declaration and nothing else moved.
   - A change that should move nothing (refactor, additive route, feed fix) proves it with a byte-identical diff.
   - A change that is *meant* to move prices — v4 Phase 3 does this deliberately — proves the number moved *only* where intended, and lands as a graded challenger under the champion–challenger registry (v4 2.4) before it touches the headline price. Promotion to the headline needs the Phase 2 backtest showing improvement on held-out seasons — log loss and Brier, never hit rate.
   - Until 2.4 exists, no price-moving change lands at all. That is the gate, not an inconvenience.
5. Deploy when the work is done and green — see "Deploying" below.

Green tests prove no regression against known values. They do NOT prove new math is right, and they do not prove a write path exists — `entered_line` was read, tested, and never written in production (v4 1.1 closes this). New formulas need one hand-checked case added to `verified_stats.json`.

Ledger migrations stay `IF NOT EXISTS`; never rewrite existing rows. Rows graded under an older basis are marked as a distinct era via `model_version`, not regraded.

## Never invoke Replit Agent

Asher is flat-rate on Claude and metered on Replit. Do not prompt Replit Agent or Assistant, and do not use the Replit MCP `update_app_using_prompt` / `create_app_from_prompt` tools. Replit is runtime, Postgres, preview proxy, and the Deploy button — nothing else.

## Deploying

**Updated 2026-08-24: Claude may deploy.** This supersedes the older "Asher presses
Run/Deploy, that step is his" rule. Committing and shipping through Replit's Deploy
(the Replit MCP `publish_app`, with `get_publish_status` to follow it) is now yours.

This does NOT loosen the rule above it. `publish_app` is the Deploy button and is not
metered; Replit Agent and Assistant remain off-limits.

Deploy is outward-facing and awkward to reverse, so it has preconditions. All of them,
every time:

- `python smoke_test.py` green, `python -m pytest -q` with no new failures, and
  `pnpm typecheck` green if any TS changed.
- The working tree is committed. Never deploy uncommitted work — a deploy you cannot
  point at a commit is a deploy you cannot roll back.
- No background worker or peer session is still editing the tree. Mid-flight files are
  how a half-finished component reaches production.
- For anything touching price math, the `/api/price` diff-against-declaration proof (build
  loop step 4) is done first, and anything that moves a price is deployed as a graded
  challenger, not as the headline price.

If a precondition fails, say so and stop rather than shipping past it.

## Reporting to Slack

Post substantive results to Slack via the Slack MCP connector so work is visible away from
the terminal. This is standing instruction, not something to be asked about each session —
post a marker when you start substantive work and when you finish it.

Workspace `amworkspacecorp.slack.com`. Channel IDs are resolved here so you can skip the
`slack_search_channels` round trip:

- `#claude-reports` — `C0BLJ5FNTB6` — findings, audits, completed work. Lead with the
  verdict, then evidence with `file:line`. Written for someone reading on a phone.
- `#claude-status` — `C0BLB6GJHPF` — short progress markers: work started, work finished,
  blocked.

Post the synthesis, not the transcript. One useful message beats a stream.

## Multi-session work

Sessions coordinate over local sockets via `ListAgents` / `SendMessage` — this never touches
Slack. `ListAgents` will usually show several idle peer sessions; they are addressable by
name.

**Only 1–2 sessions actually run at a time.** A server-side Claude Code issue means extra
sessions stall rather than run, and `SendMessage` still returns `success: true` for them —
so work handed to a third or fourth session can silently go nowhere. Dispatch at most two
peers, keep the critical path in the coordinating session, and treat a peer's silence as
"probably never started" rather than "still working". For parallelism that has to be
reliable, prefer in-process subagents (the Agent tool); those are unaffected.

When several sessions do run at once:

- One output file per session; never two sessions writing the same file.
- Tell each session explicitly which paths another session is actively editing.
- Recon and audit work is **read-only**. Report violations with `file:line`; do not silently
  fix them — a quiet fix hides that the bug existed.
- Message the coordinating session with a short summary when done.

## Vault (memory, not documentation)

This repo is the truth for code and commands. Session memory lives in the Obsidian vault at
`/Users/ashermills/Obsidian/M-Brain-Vault`: read its root `CLAUDE.md` before writing there,
then `_state.md`, then `02 Projects/Moneyline/CLAUDE.md`. After a work session, add 3–4 lines
to the top of `## Log` in `02 Projects/Moneyline/Moneyline.md` and a row in that folder's
`Sessions.md`, as the vault contract says. If a vault note and this repo disagree, this repo
wins — fix the note.
