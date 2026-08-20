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

export function LiveRecordPanel() {
  const { data, isLoading, error } = useLiveRecord();
  const gradeRecord = useGradeRecord();

  if (isLoading) return <PanelSkeleton />;
  if (error || !data) return <PanelError message="Failed to load live record" />;

  const { curve, entries, database_ready } = data;

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

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Stats & Chart */}
        <div className="md:col-span-2 flex flex-col gap-4">
          <div className="flex items-end gap-6 bg-background border border-border p-4 font-mono">
            <div className="flex flex-col">
              <span className="text-[10px] text-muted-foreground uppercase">Record</span>
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
          </div>

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
        </div>

        {/* Ledger Table */}
        <div className="md:col-span-1 border border-border bg-background flex flex-col h-full max-h-[350px]">
          <div className="p-2 border-b border-border bg-muted/30 text-[10px] font-mono font-bold text-muted-foreground flex justify-between uppercase">
            <span>Recent Picks</span>
            <span>Grade</span>
          </div>
          <div className="overflow-y-auto flex-1 p-2 flex flex-col gap-1 font-mono text-xs">
            {entries.length === 0 ? (
              <div className="text-center p-4 text-muted-foreground">NO GRADED PICKS YET</div>
            ) : (
              entries.map((entry: any, i: number) => (
                <div key={i} className="flex justify-between items-center p-2 border border-border/50 hover:border-border bg-card/50">
                  <div className="flex flex-col">
                    <span className="text-[9px] text-muted-foreground">{entry.game_date}</span>
                    <span className="font-bold">{entry.pick_team}</span>
                    <span className="text-[10px] text-primary">{formatProb(entry.model_probability)}</span>
                  </div>
                  <div>
                    {entry.result === "WIN" ? (
                      <Badge variant="success" className="px-1.5 py-0">W</Badge>
                    ) : entry.result === "LOSS" ? (
                      <Badge variant="destructive" className="px-1.5 py-0 text-destructive-foreground">L</Badge>
                    ) : (
                      <Badge variant="outline" className="px-1.5 py-0 text-muted-foreground border-dashed">PENDING</Badge>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
