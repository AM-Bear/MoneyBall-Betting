---
name: PostgreSQL partial uniqueness
description: Constraint behavior needed when ownership and nullable legacy rows share a table
---

When a uniqueness rule is implemented as a partial unique index, PostgreSQL requires the matching predicate in the `ON CONFLICT` target.

**Why:** A partial index is not inferred from only its indexed columns; omitting its predicate raises an invalid-column-reference error at runtime.

**How to apply:** Keep the `WHERE` predicate identical in the unique index and the insert conflict target, and test both the first insert and duplicate-owner insert.