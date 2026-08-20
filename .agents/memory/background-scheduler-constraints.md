---
name: Background scheduler constraints
description: The pick-snapshot/grading loop assumes an always-on server process
---

The daily pick snapshot and auto-grading run in an in-process loop inside the API server; all writes are idempotent, so repeated cycles are safe.

**Why:** Simplest reliable option in development, but the loop only runs while a server process is alive.

**How to apply:** A published deployment must either keep one process always on or move snapshot/grade to a scheduled job — a scale-to-zero deployment silently misses ledger days, the exact failure this design removed.
