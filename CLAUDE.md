# MONEYLINE — Claude Code operating notes

Product doctrine, stack, and gotchas are shared with Replit Agent and live in:

@replit.md

Read that first. Everything below is Claude-Code-specific and does not apply to Replit Agent.

## Start here on a fresh session

Read `notes/v3-plan.md` — the current ranked plan, what is broken, and what is already
verified healthy. It supersedes the strategy docs in `attached_assets/`, which were written
~9 commits behind `main` and understate what has shipped.

Supporting detail lives in `notes/map-model.md` (price chain, doctrine audit),
`notes/map-data.md` (feeds, caches, TEAM_CODES, persistence), and `notes/map-surface.md`
(routes, frontend, v3 gap). Read the map for the area you are touching; do not re-audit
what they already cover.

## Build loop

1. **Plan before writing.** Read the relevant code, state the approach and files touched, surface open questions. Get agreement before editing. This is the cheapest place to catch a wrong turn.
2. Write it in this workspace — these files ARE the Repl, there is no sync step.
3. **Verify before reporting.** `python smoke_test.py` and `python -m pytest -q` must pass *before and after* any backend change. Add `pnpm typecheck` for TS.
4. For anything touching price math, additionally diff `/api/price` output before/after to prove the change moved no number.
5. Asher presses Run/Deploy. That step is his.

Green tests prove no regression against known values. They do NOT prove new math is right, and they do not prove a write path exists — `entered_line` was read, tested, and never written in production. New formulas need one hand-checked case added to `verified_stats.json`.

## Never invoke Replit Agent

Asher is flat-rate on Claude and metered on Replit. Do not prompt Replit Agent or Assistant, and do not use the Replit MCP `update_app_using_prompt` / `create_app_from_prompt` tools. Replit is runtime, Postgres, preview proxy, and the Deploy button — nothing else.

## Reporting to Slack

Post substantive results to Slack via the Slack MCP connector so work is visible away from the terminal. Standing convention:

- `#claude-reports` — findings, audits, completed work. Lead with the verdict, then evidence with `file:line`. Written for someone reading on a phone.
- `#claude-status` — short progress markers: work started, work finished, blocked.

Post the synthesis, not the transcript. One useful message beats a stream.

## Multi-session work

Sessions coordinate over local sockets via `ListAgents` / `SendMessage` — this never touches Slack. When several sessions run at once:

- One output file per session; never two sessions writing the same file.
- Recon and audit work is **read-only**. Report violations with `file:line`; do not silently fix them — a quiet fix hides that the bug existed.
- Message the coordinating session with a short summary when done.
