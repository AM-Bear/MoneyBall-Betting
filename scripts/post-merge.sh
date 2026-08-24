#!/bin/bash
set -e
pnpm install --frozen-lockfile

# The drizzle-kit push step is gone, deliberately. The Postgres schema has
# exactly one authority:
# backend/record_store.py::ensure_schema, an additive IF NOT EXISTS migration
# run at FastAPI boot. drizzle-kit push read lib/db/src/schema/moneyline.ts,
# which is not the authority and does not know about the probables, adj_*, or
# model_version columns, nor about moneyline_parlay_slips -- so pushing it could
# propose dropping the columns the graded record depends on. The ledger is the
# product's honesty claim; it does not get a second, stale schema owner.
