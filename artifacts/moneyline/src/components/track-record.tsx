import { useTrackRecord } from "@/api";
import { PanelSkeleton, PanelError } from "./layout";
import { Badge } from "./ui/badge";

export function TrackRecordPanel() {
  const { data, isLoading, error } = useTrackRecord();

  if (isLoading) return <PanelSkeleton />;
  if (error || !data) return <PanelError message="Failed to load track record" />;

  const { dataset, runs, wins, playoffs } = data;

  return (
    <div className="moneyline-panel flex-1">
      <div className="moneyline-section-header mb-4">MODEL TRACK RECORD</div>
      
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-background border border-border p-3 font-mono">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Dataset Split</div>
          <div className="text-sm font-bold text-primary">{dataset.split}</div>
          <div className="text-xs text-muted-foreground mt-1">{dataset.test_rows} test rows</div>
        </div>
        
        <div className="bg-background border border-border p-3 font-mono">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Win Projection Error</div>
          <div className="text-sm font-bold text-primary">±{wins.mae_test_wins} Wins (MAE)</div>
          <div className="text-xs text-muted-foreground mt-1">Test R² {wins.r2_test.toFixed(3)}</div>
        </div>
      </div>

      <div className="border border-border bg-background p-4 mb-4">
        <div className="text-[10px] text-muted-foreground uppercase mb-4 tracking-widest font-semibold">Playoff Odds Calibration</div>
        
        <div className="space-y-4">
          <div className="flex justify-between items-end font-mono text-sm border-b border-border/50 pb-2">
            <div>
              <span className="font-bold text-primary">{(playoffs.accuracy_test * 100).toFixed(1)}%</span>
              <span className="text-muted-foreground ml-2">Accuracy</span>
            </div>
            <div className="text-xs text-muted-foreground">
              vs <span className="text-primary">{(playoffs.majority_baseline * 100).toFixed(1)}%</span> baseline
            </div>
          </div>

          <div className="space-y-2">
            {playoffs.calibration.map((bucket: any) => (
              <div key={bucket.bucket} className="flex items-center gap-3 font-mono text-xs">
                <div className="w-16 text-muted-foreground">{bucket.bucket}</div>
                <div className="flex-1 h-2 bg-muted relative">
                  <div 
                    className="absolute top-0 left-0 h-full bg-primary"
                    style={{ width: `${bucket.actual_rate * 100}%` }}
                  />
                </div>
                <div className="w-24 text-right">
                  <span className="font-bold">{(bucket.actual_rate * 100).toFixed(0)}%</span>
                  <span className="text-muted-foreground text-[10px] ml-1">(n={bucket.n})</span>
                </div>
              </div>
            ))}
          </div>
          <div className="text-[10px] text-warning italic border-l border-warning pl-2 mt-2">
            {playoffs.note}
          </div>
        </div>
      </div>
    </div>
  );
}
