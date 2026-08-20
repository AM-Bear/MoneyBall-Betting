import {
  date,
  doublePrecision,
  index,
  integer,
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
    enteredLine: integer("entered_line"),
    finalAway: integer("final_away"),
    finalHome: integer("final_home"),
    result: text("result"),
    unitsPnl: doublePrecision("units_pnl"),
    gradedAt: timestamp("graded_at", { withTimezone: true }),
  },
  (table) => [
    uniqueIndex("moneyline_record_game_idx").on(table.gamePk),
    index("moneyline_record_grade_idx").on(table.gameDate, table.result),
  ],
);

export type MoneylineSlateSnapshot =
  typeof moneylineSlateSnapshotsTable.$inferSelect;
export type MoneylineRecordPick =
  typeof moneylineRecordPicksTable.$inferSelect;