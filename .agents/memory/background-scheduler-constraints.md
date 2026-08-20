---
name: Background scheduler constraints
description: The pick-snapshot/grading loop assumes an always-on server process
---

The daily pick snapshot and auto-grading both run in an in-process asyncio loop started at FastAPI startup (single interval env-tunable via GRADE_INTERVAL_SECONDS).

**Why:** Simplest reliable option in dev; snapshot/grade writes are idempotent (ON CONFLICT guards), so running every cycle is safe and re-runs never duplicate picks.

**How to apply:** Any deployment must keep one server process running continuously (Reserved VM, not scale-to-zero autoscale), or the ledger silently misses days again — the exact failure this design removed. If autoscale is chosen, move snapshot/grade to a scheduled job instead.
