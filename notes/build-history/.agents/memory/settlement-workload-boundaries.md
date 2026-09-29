---
name: Settlement workload boundaries
description: Operational limits for safe live-record settlement work.
---

Settlement is a privileged maintenance operation: the scheduler owns normal execution, while any manual invocation must use an explicit deployment-controlled operator allowlist. Concurrent callers must share one in-flight pass, and each pass must read a fixed batch through an index that matches the unresolved-row ordering.

**Why:** A full pending-ledger scan fans out to the database and MLB final-score feed. Repeating that work from ordinary authenticated requests can exhaust both resources even when each individual fetch is concurrency-limited.

**How to apply:** Preserve the date/window and cache bounds on public slate work. If settlement batching or its ordering changes, keep the query limit and its matching partial index aligned; do not reintroduce page-load settlement triggers.