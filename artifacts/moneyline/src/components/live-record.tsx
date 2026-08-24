import { useLiveRecord, useGradeRecord } from "@/api";
import { PanelSkeleton, PanelError } from "./layout";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Loader2 } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from "recharts";
import { formatProb } from "./slate-rail";
import { CalibrationChart, CalibrationSummary } from "./record/calibration-chart";
import { PickTable } from "./record/pick-table";
import { ProofStatement } from "./record/proof-statement";
import { formatPct, type RecordEntry } from "./record/record-stats";

export function LiveRecordPanel() {
  const { data, isLoading, error } = useLiveRecord();
  const gradeRecord = useGradeRecord();

  if (isLoading) return <PanelSkeleton />;
  if (error || !data) return <PanelError message="Failed to load live record" />;

  const { curve, database_ready } = data;
  const entries: RecordEntry[] = data.entries ?? [];

  // Which model priced THESE rows -- not which model is loaded today. A row
  // written before versioning carries NULL and is counted, not relabelled;
  // saying "MODEL v1" over it would assert something never checked against
  // it, which is the exact claim backend/record_store.py refuses to make.
  // Spelled out from the bases the rows evidence, never from an assumed
  // cutover date. `indistinguishable` is a loss: -1.0 under either basis, so
  // there is nothing to claim about how it settled.
  const bases: Record<string, number> = data.parlay_record?.settled_bases ?? {};
  const retired = bases["fair_line_retired"] ?? 0;
  const compounded = bases["standard_-110_compounded"] ?? 0;
  const indistinguishable = bases["indistinguishable"] ?? 0;
  const basisParts: string[] = [];
  if (compounded > 0) basisParts.push(`${compounded} settled at the −110 legs compounded`);
  if (retired > 0) basisParts.push(`${retired} at the retired fair-line basis`);
  if (indistinguishable > 0)
    basisParts.push(
      `${indistinguishable} ${indistinguishable === 1 ? "was a loss, which grades" : "were losses, which grade"} to −1.00u under either basis`,
    );
  const parlayBasisSentence = basisParts.length ? ` Of those, ${basisParts.join("; ")}.` : "";

  const versionsPresent: string[] = data.model_versions_present ?? [];
  const unversioned: number = data.unversioned_picks ?? 0;
  const provenance =
    versionsPresent.length === 0
      ? unversioned > 0
        ? `No pick here carries a model stamp: all ${unversioned} predate versioning, so the desk does not claim which model priced them.`
        : ""
      : unversioned > 0
        ? `Mixed provenance — ${unversioned} pick${unversioned === 1 ? "" : "s"} carry no model stamp; the rest were priced by ${versionsPresent.join(", ")}. These rows are not all comparable.`
        : versionsPresent.length === 1
          ? `Priced by ${versionsPresent[0]}.`
          : `Spans ${versionsPresent.join(" and ")} — these rows are not all comparable.`;

  if (!database_ready) {
    return <PanelError message="PERSISTENT STORE UNAVAILABLE — CANNOT VERIFY RECORD" />;
  }

  // Format data for chart
  const chartData = curve.map((c: any) => ({
    date: c.date,
    winRate: c.hit_rate,
    units: c.units
  }));

  const breakEvenRate = data.break_even_rate;

  return (
    <div className="moneyline-panel lg:col-span-3 min-h-[400px]">
      <div className="flex justify-between items-center mb-4">
        <div className="moneyline-section-header w-1/3">LIVE PUBLIC RECORD</div>
        <div className="flex gap-2">
          {data.tracking_since && (
            <span className="hidden sm:inline-flex items-center text-[10px] font-mono text-muted-foreground">
              TRACKING SINCE {data.tracking_since}
            </span>
          )}
          {data.sample_label && (
            <Badge variant="outline" className="text-warning border-warning/30 text-[10px]">
              {data.sample_label}
            </Badge>
          )}
          <Button 
            variant="outline" 
            size="sm" 
            className="h-6 text-xs" 
            onClick={() => gradeRecord.mutate()}
            disabled={gradeRecord.isPending}
          >
            {gradeRecord.isPending ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
            GRADE PENDING
          </Button>
        </div>
      </div>

      <p className="mb-3 text-xs leading-5 text-muted-foreground">
        Every game on the slate, flat one unit, booked at the −110 fallback. This is a model
        check, not a betting record — no price anyone was offered is recorded against these picks.
      </p>

      {gradeRecord.isError && (
        <div className="mb-3 px-2 py-1.5 border border-destructive/40 bg-destructive/10 text-destructive font-mono text-[11px]">
          GRADING FAILED — {gradeRecord.error instanceof Error ? gradeRecord.error.message.toUpperCase() : "UNKNOWN ERROR"}
        </div>
      )}
      {gradeRecord.isSuccess && (
        <div
          className={`mb-3 px-2 py-1.5 border font-mono text-[11px] ${
            gradeRecord.data.graded > 0
              ? "border-success/40 bg-success/10 text-success"
              : "border-border bg-muted/30 text-muted-foreground"
          }`}
        >
          {gradeRecord.data.graded > 0
            ? `GRADED ${gradeRecord.data.graded} PICK${gradeRecord.data.graded === 1 ? "" : "S"} — LEDGER UPDATED`
            : gradeRecord.data.checked > 0
              ? `CHECKED ${gradeRecord.data.checked} GAME${gradeRecord.data.checked === 1 ? "" : "S"} — NO FINALS AVAILABLE YET`
              : "NO GAMES ELIGIBLE YET — PICKS GRADE AFTER THEIR GAME DATE PASSES"}
        </div>
      )}

      <div className="flex flex-col gap-4">
        {/* Dual-price grading: SEASON and ADJ side by side */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <div className="flex flex-wrap items-end gap-6 bg-background border border-border p-4 font-mono">
            <div className="flex flex-col">
              <span className="text-[10px] text-muted-foreground uppercase">Season Record</span>
              <span className="text-3xl font-bold text-primary tracking-tighter">
                {data.wins}–{data.losses}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] text-muted-foreground uppercase">Win Rate</span>
              <span className="text-2xl font-bold tracking-tighter">
                {data.hit_rate !== null ? (data.hit_rate * 100).toFixed(1) : "0.0"}%
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] text-muted-foreground uppercase">Units (Flat -110)</span>
              <span className="text-2xl font-bold tracking-tighter text-success">
                {data.units_pnl > 0 ? "+" : ""}{data.units_pnl.toFixed(2)}u
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] text-muted-foreground uppercase">Break-even</span>
              <span className="text-2xl font-bold tracking-tighter text-warning">
                {formatPct(breakEvenRate)}
              </span>
              <span className="text-[9px] text-muted-foreground">110/210 at −110</span>
            </div>
          </div>

          <div className="flex flex-col justify-between bg-background border border-warning/30 p-4 font-mono gap-2">
            <div className="flex items-end gap-6">
              <div className="flex flex-col">
                <span className="text-[10px] text-warning uppercase">ADJ Record</span>
                <span className="text-3xl font-bold text-warning tracking-tighter">
                  {data.adj_record ? `${data.adj_record.wins}–${data.adj_record.losses}` : "—"}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] text-muted-foreground uppercase">Win Rate</span>
                <span className="text-2xl font-bold tracking-tighter">
                  {data.adj_record?.hit_rate != null ? `${(data.adj_record.hit_rate * 100).toFixed(1)}%` : "—"}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] text-muted-foreground uppercase">Units</span>
                <span className="text-2xl font-bold tracking-tighter">
                  {data.adj_record?.units_pnl != null ? `${data.adj_record.units_pnl > 0 ? "+" : ""}${data.adj_record.units_pnl.toFixed(2)}u` : "—"}
                </span>
              </div>
            </div>
            {data.adj_record?.note && (
              <span className="text-[9px] text-muted-foreground leading-tight">{data.adj_record.note}</span>
            )}
          </div>
        </div>

        {data.parlay_record && (
          <div className="bg-background border border-border px-4 py-2 font-mono text-xs flex flex-wrap items-center gap-4">
            <span className="text-[10px] text-muted-foreground uppercase">Paper Parlays</span>
            <span className="font-bold text-primary">{data.parlay_record.line}</span>
            <span className="text-muted-foreground text-[10px]">
              {data.parlay_record.slips} PERSONAL SLIP{data.parlay_record.slips === 1 ? "" : "S"} LOGGED · GRADED ALL-OR-NOTHING · ONE PER USER PER DAY
            </span>
            {/* The parlay table is the one whose grading basis changed. This
                disclosure replaces regrading the rows -- but it may only state
                what the rows actually evidence. An earlier version said these
                slips "were settled at the −110 legs compounded", which was
                false for every row graded before that became the fallback and
                unknowable for a loss. The basis now comes from each row's own
                stored payout, and a loss says so rather than being assigned to
                whichever basis is convenient. */}
            {(data.parlay_record.fallback_graded ?? 0) > 0 && (
              <span className="w-full text-muted-foreground text-[10px] leading-4 normal-case">
                {data.parlay_record.fallback_graded} of {data.parlay_record.graded} graded
                slip{data.parlay_record.graded === 1 ? "" : "s"} had no book price recorded.
                {parlayBasisSentence}{" "}
                Slips settled from now on use the −110 legs compounded, the same fallback
                picks use. No sportsbook price is recorded against any slip here, and no
                graded row has been rewritten.
              </span>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="h-64 border border-border bg-background p-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} tickMargin={5} minTickGap={30} />
                <YAxis yAxisId="left" stroke="hsl(var(--muted-foreground))" fontSize={10} tickFormatter={(v) => `${(v*100).toFixed(0)}%`} domain={[0, 1]} />
                <YAxis yAxisId="right" orientation="right" stroke="hsl(var(--primary))" fontSize={10} tickFormatter={(v) => `${v}u`} hide />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: 0, fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                  itemStyle={{ color: 'hsl(var(--foreground))' }}
                  formatter={(value: number, name: string) => [
                    name === 'winRate' ? `${(value*100).toFixed(1)}%` : `${value.toFixed(2)}u`, 
                    name === 'winRate' ? 'Win Rate' : 'Units'
                  ]}
                />
                {breakEvenRate && (
                  <ReferenceLine yAxisId="left" y={breakEvenRate} stroke="hsl(var(--warning))" strokeDasharray="3 3" label={{ position: 'insideTopLeft', value: `B/E ${formatProb(breakEvenRate)}`, fill: 'hsl(var(--warning))', fontSize: 10 }} />
                )}
                <Line yAxisId="left" type="monotone" dataKey="winRate" stroke="hsl(var(--foreground))" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line yAxisId="right" type="stepAfter" dataKey="units" stroke="hsl(var(--primary))" strokeWidth={1} dot={false} isAnimationActive={false} opacity={0.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="sr-only">
            Running hit rate and cumulative units after each decided pick, from{" "}
            {data.tracking_since ?? "the first pick"} to now. It ends at{" "}
            {data.hit_rate !== null ? formatPct(data.hit_rate) : "no rate yet"} on{" "}
            {data.graded} decided picks and {data.units_pnl.toFixed(2)} units, against a
            break-even of {formatPct(breakEvenRate)}.
          </p>

          <ProofStatement
            entries={entries}
            wins={data.wins}
            losses={data.losses}
            graded={data.graded}
            breakEvenRate={breakEvenRate}
            sampleLabel={data.sample_label ?? null}
            trackingSince={data.tracking_since ?? null}
          />
        </div>

        <CalibrationChart entries={entries} />
        <CalibrationSummary entries={entries} />

        <PickTable entries={entries} trackingSince={data.tracking_since ?? null} />

        <p className="text-[10px] leading-4 text-muted-foreground font-mono">
          METHOD · Hit-rate band is a Wilson score interval; the units-per-pick band is
          mean ± 1.96 × sd/√n. Both are computed in the browser from the {entries.length}{" "}
          rows above, and both exclude VOID and pending picks exactly as the ledger does.
          Break-even {formatPct(breakEvenRate)} is 110/210, the −110 fallback the ledger books at.
          {" "}
          {provenance}
        </p>
      </div>
    </div>
  );
}
