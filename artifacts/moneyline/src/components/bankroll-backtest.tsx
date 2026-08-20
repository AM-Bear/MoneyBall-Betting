import { useBacktest } from "@/api";
import { PanelSkeleton, PanelError } from "./layout";
import { Badge } from "./ui/badge";
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

export function BankrollPanel() {
  const { data, isLoading, error } = useBacktest();

  if (isLoading) return <PanelSkeleton />;
  if (error || !data) return <PanelError message="Failed to load backtest data" />;

  const { model, baseline, assumptions } = data;

  // Merge curves for charting
  const chartData = model.curve.map((mc: any, i: number) => ({
    year: mc.year,
    model: mc.bankroll,
    baseline: baseline.curve[i]?.bankroll || 1000
  }));

  return (
    <div className="moneyline-panel flex-1">
      <div className="flex items-center justify-between mb-4">
        <div className="moneyline-section-header">PAPER BANKROLL BACKTEST</div>
        <Badge variant="outline" className="text-[9px] text-warning border-warning/30">
          SIMULATION
        </Badge>
      </div>
      
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="bg-background border border-primary/30 p-3 font-mono flex flex-col items-center text-center">
          <div className="text-[10px] text-primary uppercase mb-1">Model Picks PNL</div>
          <div className="text-xl font-bold text-primary">{model.units > 0 ? "+" : ""}{model.units}u</div>
          <div className="text-xs text-muted-foreground mt-1">{(model.hit_rate * 100).toFixed(1)}% ({model.wins}/{model.bets})</div>
        </div>
        
        <div className="bg-background border border-border p-3 font-mono flex flex-col items-center text-center opacity-70">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Baseline PNL</div>
          <div className="text-xl font-bold">{baseline.units > 0 ? "+" : ""}{baseline.units}u</div>
          <div className="text-xs text-muted-foreground mt-1">{(baseline.hit_rate * 100).toFixed(1)}% ({baseline.wins}/{baseline.bets})</div>
        </div>
      </div>

      <div className="h-48 w-full border border-border bg-background p-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis dataKey="year" stroke="hsl(var(--muted-foreground))" fontSize={10} tickMargin={5} />
            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} domain={['auto', 'auto']} tickFormatter={(v) => `$${v}`} />
            <Tooltip 
              contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: 0, fontFamily: 'var(--font-mono)', fontSize: '12px' }}
              itemStyle={{ color: 'hsl(var(--foreground))' }}
            />
            <ReferenceLine y={1000} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />
            <Line type="stepAfter" dataKey="model" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line type="stepAfter" dataKey="baseline" stroke="hsl(var(--muted-foreground))" strokeWidth={1} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 text-[9px] text-muted-foreground font-mono space-y-1">
        <div>* {assumptions.vig}</div>
        <div>* Prior: {assumptions.market_prior}</div>
      </div>
    </div>
  );
}
