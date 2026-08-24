/** Client-side arithmetic over the `/api/record` payload.
 *
 * Nothing here recomputes a number the ledger already ships. Hit rate, units,
 * `break_even_rate` (110/210, the -110 fallback) and `sample_label` all come
 * from `record_store.get_record()` and are displayed as returned. These helpers
 * only add the intervals and buckets the ledger does not carry — and each one
 * reports its method and its n alongside its number, because an interval
 * without its method is the fake precision the doctrine forbids.
 *
 * VOID picks carry 0 units and are excluded from every statistic here, exactly
 * as `get_record()` excludes them from the hit rate and the curve.
 */

/** Two-sided 95% normal quantile. */
export const Z_95 = 1.959964;

export type Grade = "WIN" | "LOSS" | "VOID" | null;

export interface RecordEntry {
  game_pk: string;
  game_date: string;
  away_team: string;
  home_team: string;
  pick_team: string;
  model_probability: number;
  fair_line: number | null;
  entered_line: number | null;
  final_away: number | null;
  final_home: number | null;
  result: Grade;
  units_pnl: number | null;
  adj_pick_team: string | null;
  adj_probability: number | null;
  adj_fair_line: number | null;
  adj_result: Grade;
  adj_units_pnl: number | null;
  /** The model that priced this row. NULL on picks graded before versioning;
   *  exported as empty rather than backfilled with a version never checked
   *  against them. */
  model_version: string | null;
  created_at: string;
}

/** Decided picks only — WIN or LOSS. PENDING has no outcome; VOID is terminal
 *  but carries 0 units and must never dilute a rate. */
export function decided(entries: RecordEntry[]): RecordEntry[] {
  return entries.filter((e) => e.result === "WIN" || e.result === "LOSS");
}

export interface Interval {
  point: number;
  low: number;
  high: number;
  n: number;
  /** Named on screen next to the number. */
  method: string;
}

/** 95% Wilson score interval for a proportion.
 *
 * Wilson rather than the normal approximation: with n in the dozens and a rate
 * near .5 the normal interval is already too narrow, and near 0 or 1 it runs
 * off the end of [0, 1] entirely. Wilson stays inside the unit interval at
 * every n, which is the only reason this page can show a band at all.
 */
export function wilsonInterval(successes: number, n: number): Interval | null {
  if (n <= 0) return null;
  const p = successes / n;
  const z2 = Z_95 * Z_95;
  const denom = 1 + z2 / n;
  const center = (p + z2 / (2 * n)) / denom;
  const half = (Z_95 / denom) * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n));
  return {
    point: p,
    low: Math.max(0, center - half),
    high: Math.min(1, center + half),
    n,
    method: "Wilson score, 95%",
  };
}

export interface MeanInterval extends Interval {
  sd: number;
}

/** 95% interval on a mean: mean ± 1.96 × sd/√n, sample sd (n−1 denominator).
 *  Needs at least two observations to have an sd at all. */
export function meanInterval(values: number[]): MeanInterval | null {
  const n = values.length;
  if (n < 2) return null;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  const variance =
    values.reduce((acc, v) => acc + (v - mean) * (v - mean), 0) / (n - 1);
  const sd = Math.sqrt(variance);
  const half = (Z_95 * sd) / Math.sqrt(n);
  return {
    point: mean,
    low: mean - half,
    high: mean + half,
    sd,
    n,
    method: "normal approximation, mean ± 1.96 × sd/√n",
  };
}

/** Picks needed before a return of `roi` units per pick would clear its own
 *  95% interval: n such that 1.96 × sd/√n < roi. Reported with the sd it used. */
export function picksToDetect(roi: number, sd: number): number {
  if (roi <= 0 || sd <= 0) return Number.POSITIVE_INFINITY;
  return Math.ceil(Math.pow((Z_95 * sd) / roi, 2));
}

/** Below this a bucket's rate is shown but de-emphasized — too small to read. */
export const BUCKET_READABLE_N = 30;
/** Below this no rate is rendered at all; only the count. */
export const BUCKET_MIN_N = 10;

export interface CalibrationBucket {
  label: string;
  lower: number;
  upper: number;
  n: number;
  wins: number;
  /** null when n < BUCKET_MIN_N — refused rather than drawn. */
  actualRate: number | null;
  /** Mean model probability in the bucket: what calibration compares against. */
  meanModelProbability: number | null;
  /** n >= BUCKET_READABLE_N. */
  readable: boolean;
}

const BUCKET_EDGES: { label: string; lower: number; upper: number }[] = [
  { label: "under 50%", lower: 0, upper: 0.5 },
  { label: "50–55%", lower: 0.5, upper: 0.55 },
  { label: "55–60%", lower: 0.55, upper: 0.6 },
  { label: "60–65%", lower: 0.6, upper: 0.65 },
  { label: "65%+", lower: 0.65, upper: 1.0001 },
];

/** Model probability vs. realised hit rate, over decided picks only.
 *
 * The "under 50%" bucket is dropped when empty: the pick is the model's own
 * side, so its probability is >= .5 by construction. It exists so that a row
 * which somehow lands below .5 is surfaced rather than silently discarded.
 */
export function calibrationBuckets(entries: RecordEntry[]): CalibrationBucket[] {
  const rows = decided(entries);
  const buckets = BUCKET_EDGES.map((edge) => {
    const inBucket = rows.filter(
      (e) => e.model_probability >= edge.lower && e.model_probability < edge.upper,
    );
    const n = inBucket.length;
    const wins = inBucket.filter((e) => e.result === "WIN").length;
    return {
      label: edge.label,
      lower: edge.lower,
      upper: edge.upper,
      n,
      wins,
      actualRate: n >= BUCKET_MIN_N ? wins / n : null,
      meanModelProbability:
        n > 0
          ? inBucket.reduce((acc, e) => acc + e.model_probability, 0) / n
          : null,
      readable: n >= BUCKET_READABLE_N,
    };
  });
  return buckets.filter((b) => b.label !== "under 50%" || b.n > 0);
}

/** One RFC-4180 field. */
function csvField(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Documented column order for the per-pick export. Kept in this module so the
 *  header and the row builder can never drift apart. */
export const LEDGER_CSV_COLUMNS = [
  "game_pk",
  "game_date",
  "away_team",
  "home_team",
  "pick_team",
  "model_probability",
  "fair_line",
  "entered_line",
  "final_away",
  "final_home",
  "result",
  "units_pnl",
  "adj_pick_team",
  "adj_probability",
  "adj_fair_line",
  "adj_result",
  "adj_units_pnl",
  "model_version",
  "snapshot_created_at",
] as const;

export function ledgerCsv(entries: RecordEntry[]): string {
  const rows = entries.map((e) =>
    [
      e.game_pk,
      e.game_date,
      e.away_team,
      e.home_team,
      e.pick_team,
      e.model_probability,
      e.fair_line,
      e.entered_line,
      e.final_away,
      e.final_home,
      e.result,
      e.units_pnl,
      e.adj_pick_team,
      e.adj_probability,
      e.adj_fair_line,
      e.adj_result,
      e.adj_units_pnl,
      e.model_version,
      e.created_at,
    ]
      .map(csvField)
      .join(","),
  );
  return [LEDGER_CSV_COLUMNS.join(","), ...rows].join("\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  // Revoked on the next tick, not synchronously: Chromium tolerates an
  // immediate revoke but Firefox can abort the download mid-flight.
  const href = link.href;
  setTimeout(() => URL.revokeObjectURL(href), 0);
}

export function formatUnits(units: number, digits = 2): string {
  return `${units > 0 ? "+" : ""}${units.toFixed(digits)}u`;
}

export function formatPct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}
