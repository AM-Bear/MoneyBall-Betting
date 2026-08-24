// DOCUMENTATION ONLY -- the Python migration is authoritative.
//
// The Postgres schema is owned by backend/record_store.py::ensure_schema, an
// additive IF NOT EXISTS migration run at FastAPI boot. This file is a
// TypeScript-readable mirror of it and is deliberately NOT pushed: scripts/
// post-merge.sh no longer runs `pnpm --filter db push`, because an un-forced
// drizzle-kit push against a stale mirror can propose dropping the columns the
// graded record depends on.
//
// Nothing imports these tables today. If that changes, mirror ensure_schema --
// never the reverse.

import {
  date,
  doublePrecision,
  index,
  integer,
  jsonb,
  pgTable,
  serial,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

export const moneylineSlateSnapshotsTable = pgTable(
  "moneyline_slate_snapshots",
  {
    id: serial("id").primaryKey(),
    snapshotDate: date("snapshot_date", { mode: "string" }).notNull(),
    mode: text("mode").notNull(),
    // The MODEL_VERSION that priced this slate. NULL on rows written before
    // versioning; see backend/precompute.py::MODEL_VERSION.
    modelVersion: text("model_version"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    uniqueIndex("moneyline_snapshot_date_idx").on(table.snapshotDate),
  ],
);

export const moneylineRecordPicksTable = pgTable(
  "moneyline_record_picks",
  {
    id: serial("id").primaryKey(),
    snapshotId: integer("snapshot_id")
      .notNull()
      .references(() => moneylineSlateSnapshotsTable.id, {
        onDelete: "restrict",
      }),
    gamePk: text("game_pk").notNull(),
    gameDate: date("game_date", { mode: "string" }).notNull(),
    awayTeam: text("away_team").notNull(),
    homeTeam: text("home_team").notNull(),
    pickTeam: text("pick_team").notNull(),
    modelProbability: doublePrecision("model_probability").notNull(),
    fairLine: integer("fair_line").notNull(),
    // Manual book-price entry, unimplemented. Never written by application
    // code, so picks grade at the -110 fallback in grade_pick. MONEYLINE
    // ingests no odds provider; there is no market line to record.
    enteredLine: integer("entered_line"),
    finalAway: integer("final_away"),
    finalHome: integer("final_home"),
    result: text("result"),
    unitsPnl: doublePrecision("units_pnl"),
    gradedAt: timestamp("graded_at", { withTimezone: true }),
    // v2 dual-price (ADJ) columns. ADJ is the starter-blended experiment,
    // graded alongside SEASON; the desk never claims it is better.
    probables: jsonb("probables"),
    adjProbability: doublePrecision("adj_probability"),
    adjPickTeam: text("adj_pick_team"),
    adjFairLine: integer("adj_fair_line"),
    adjResult: text("adj_result"),
    adjUnitsPnl: doublePrecision("adj_units_pnl"),
    modelVersion: text("model_version"),
  },
  (table) => [
    uniqueIndex("moneyline_record_game_idx").on(table.gamePk),
    index("moneyline_record_grade_idx").on(table.gameDate, table.result),
  ],
);

export const moneylineParlaySlipsTable = pgTable("moneyline_parlay_slips", {
  id: serial("id").primaryKey(),
  slipDate: date("slip_date", { mode: "string" }).notNull().unique(),
  legs: jsonb("legs").notNull(),
  combinedProbability: doublePrecision("combined_probability").notNull(),
  fairLine: integer("fair_line").notNull(),
  // Manual book price, same story as enteredLine. When NULL the slip grades
  // at the compounded -110 legs, matching how picks fall back.
  bookLine: integer("book_line"),
  result: text("result"),
  unitsPnl: doublePrecision("units_pnl"),
  gradedAt: timestamp("graded_at", { withTimezone: true }),
  modelVersion: text("model_version"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export type MoneylineSlateSnapshot =
  typeof moneylineSlateSnapshotsTable.$inferSelect;
export type MoneylineRecordPick =
  typeof moneylineRecordPicksTable.$inferSelect;
export type MoneylineParlaySlip =
  typeof moneylineParlaySlipsTable.$inferSelect;
