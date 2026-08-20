import { useState } from "react";
import { Link } from "wouter";
import { Badge } from "./ui/badge";
import { Slider } from "./ui/slider";
import { Switch } from "./ui/switch";
import { cn } from "@/lib/utils";
import { formatOdds } from "./slate-rail";
import { PulseMeter } from "./pulse-meter";
import { Loader2 } from "lucide-react";

function formatStat(val: number) {
  return val.toFixed(3).replace(/^0\./, '.');
}

function StatSlider({ 
  label, 
  value, 
  min, 
  max, 
  onChange,
  disabled
}: { 
  label: string; 
  value: number; 
  min: number; 
  max: number; 
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between items-center text-xs font-mono">
        <span className="text-muted-foreground">{label}</span>
        <span className={disabled ? "text-muted-foreground/50" : ""}>{formatStat(value)}</span>
      </div>
      <Slider
        disabled={disabled}
        min={min}
        max={max}
        step={0.001}
        value={[value]}
        onValueChange={(v) => onChange(v[0])}
        className="my-1"
      />
    </div>
  );
}

export function PricerPanel({ 
  team,
  year,
  data, 
  onInputsChange,
  isDirty,
  customInputs,
  customPrice,
  onReset,
  liveContext
}: { 
  team: string;
  year: number;
  data: any; 
  onInputsChange: (inputs: any) => void;
  isDirty: boolean;
  customInputs: any;
  customPrice: any;
  onReset: () => void;
  liveContext?: {
    season?: number;
    sampleLabel: string;
    flags: any[];
    pulse: any;
    record: { wins: number; losses: number; games_played: number; runs_scored: number; runs_allowed: number };
  } | null;
}) {
  const [frontOffice, setFrontOffice] = useState(false);

  // If front office is disabled, we always show the original data
  const currentInputs = (frontOffice && customInputs) ? customInputs : data.inputs;
  const currentData = (frontOffice && customPrice) ? customPrice : data;
  const predicted = currentData.predicted || {};
  const currentFairLine = currentData.fair_line;
  const ranges = data.data_ranges || {
    obp: { min: 0.280, max: 0.380 },
    slg: { min: 0.320, max: 0.490 },
    oobp: { min: 0.290, max: 0.370 },
    oslg: { min: 0.360, max: 0.470 }
  };

  const playoffProb = predicted.playoff_prob;
  const hasProb = typeof playoffProb === "number";
  
  // Needles range 0 to 180deg
  const gaugeRotation = hasProb ? Math.max(0, Math.min(180, (playoffProb * 180))) : 0;
  const gaugeColor = hasProb ? (playoffProb > 0.7 ? "text-success" : playoffProb > 0.4 ? "text-warning" : "text-destructive") : "text-muted";

  const winDelta = data.actual && predicted.wins ? predicted.wins - data.actual.wins : null;
  const winDeltaFmt = winDelta !== null ? (winDelta > 0 ? `▲+${winDelta.toFixed(1)}` : `▼${Math.abs(winDelta).toFixed(1)}`) : "";

  const handleSliderChange = (field: string, val: number) => {
    onInputsChange({
      ...currentInputs,
      [field]: val
    });
  };

  const handleToggle = (checked: boolean) => {
    setFrontOffice(checked);
    if (!checked) {
      onReset();
    }
  };

  return (
    <div className="moneyline-panel lg:col-span-2">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-2xl font-bold font-mono tracking-tighter uppercase">
            {team} {year}
          </h2>
          {data.offense_only && (
            <Badge variant="outline" className="text-[10px]">OFFENSE ONLY (PRE-1999)</Badge>
          )}
          {liveContext && (
            <Badge variant="outline" className="text-[10px] text-warning border-warning/30">
              {liveContext.sampleLabel}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs font-mono">
          {isDirty && frontOffice && (
            <button onClick={onReset} className="text-muted-foreground hover:text-primary underline underline-offset-2 mr-2">
              RESET
            </button>
          )}
          <span className={cn("transition-colors", !frontOffice ? "text-muted-foreground" : "text-primary font-bold")}>
            FRONT OFFICE
          </span>
          <Switch checked={frontOffice} onCheckedChange={handleToggle} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-center mb-8">
        {/* Pipeline Stage 1: Offense */}
        <div className="flex flex-col gap-2 relative">
          <div className="text-[10px] text-muted-foreground font-semibold tracking-widest uppercase">Offense</div>
          <div className="bg-background border border-border p-3 flex flex-col gap-3">
            <StatSlider disabled={!frontOffice} label="OBP" value={currentInputs.obp} min={ranges.obp.min} max={ranges.obp.max} onChange={(v) => handleSliderChange('obp', v)} />
            <StatSlider disabled={!frontOffice} label="SLG" value={currentInputs.slg} min={ranges.slg.min} max={ranges.slg.max} onChange={(v) => handleSliderChange('slg', v)} />
          </div>
          <div className="absolute -right-3 top-1/2 -translate-y-1/2 text-border hidden md:block">→</div>
        </div>

        {/* Pipeline Stage 2: Defense */}
        <div className="flex flex-col gap-2 relative">
          <div className="text-[10px] text-muted-foreground font-semibold tracking-widest uppercase">Defense</div>
          <div className="bg-background border border-border p-3 flex flex-col gap-3">
            <StatSlider disabled={!frontOffice || data.offense_only} label="OOBP" value={currentInputs.oobp || ranges.oobp.min} min={ranges.oobp.min} max={ranges.oobp.max} onChange={(v) => handleSliderChange('oobp', v)} />
            <StatSlider disabled={!frontOffice || data.offense_only} label="OSLG" value={currentInputs.oslg || ranges.oslg.min} min={ranges.oslg.min} max={ranges.oslg.max} onChange={(v) => handleSliderChange('oslg', v)} />
          </div>
          <div className="absolute -right-3 top-1/2 -translate-y-1/2 text-border hidden md:block">→</div>
        </div>

        {/* Pipeline Stage 3: Runs & Wins */}
        <div className="flex flex-col gap-2 relative h-full">
          <div className="text-[10px] text-muted-foreground font-semibold tracking-widest uppercase">Projection</div>
          <div className="bg-background border border-border p-3 flex flex-col justify-center h-full gap-2 font-mono">
            <div className="flex justify-between items-baseline">
              <span className="text-muted-foreground text-xs">RS</span>
              <span className="text-lg">{predicted.rs != null ? predicted.rs.toFixed(0) : "—"}</span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-muted-foreground text-xs">RA</span>
              <span className="text-lg">{predicted.ra != null ? predicted.ra.toFixed(0) : "—"}</span>
            </div>
            <div className="h-px bg-border my-1" />
            <div className="flex justify-between items-baseline text-primary">
              <span className="font-bold">WINS</span>
              <span className="text-2xl font-bold">{predicted.wins != null ? predicted.wins.toFixed(1) : "—"}</span>
            </div>
          </div>
          <div className="absolute -right-3 top-1/2 -translate-y-1/2 text-border hidden md:block">→</div>
        </div>

        {/* Pipeline Stage 4: Playoff Odds Gauge (historical logistic) —
            hidden in live mode: the honest playoff number is the
            Season Desk simulation, not the 1962–2001 logistic. */}
        <div className="flex flex-col gap-2 items-center justify-center h-full">
          <div className="text-[10px] text-muted-foreground font-semibold tracking-widest uppercase mb-2">Playoff Odds</div>

          {liveContext ? (
            <Link
              href="/season"
              className="border border-border bg-background p-3 text-center font-mono text-[10px] text-muted-foreground hover:border-primary hover:text-primary transition-colors leading-snug"
            >
              {liveContext.season ?? "LIVE"} PLAYOFF ODDS LIVE IN
              <br />
              <span className="font-bold">SEASON DESK →</span>
              <br />
              <span className="text-[9px]">(SIMULATED, NOT THE HISTORICAL LOGISTIC)</span>
            </Link>
          ) : (
            <div className="relative w-32 h-16 overflow-hidden mb-2">
              <div className="absolute top-0 left-0 w-32 h-32 rounded-full border-8 border-muted" />
              <div 
                className={cn("absolute top-0 left-0 w-32 h-32 rounded-full border-8 border-transparent border-t-current border-l-current transition-transform duration-700 ease-out", gaugeColor)}
                style={{ transform: `rotate(${gaugeRotation - 45}deg)` }}
              />
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 text-2xl font-bold font-mono tracking-tighter">
                {hasProb ? `${(playoffProb * 100).toFixed(1)}%` : "—"}
              </div>
            </div>
          )}

          <div className="text-xs font-mono text-muted-foreground flex gap-2 items-center">
            FAIR LINE: <span className="text-primary font-bold">{currentFairLine != null ? formatOdds(currentFairLine) : "—"}</span>
          </div>
        </div>
      </div>

      {data.actual && !isDirty && (
        <div className="bg-background border border-border p-2 text-xs font-mono flex items-center gap-4 text-muted-foreground">
          <span className="font-bold text-primary">ACTUAL</span>
          <span>RS {data.actual.rs}</span>
          <span>RA {data.actual.ra}</span>
          <span className="flex items-center gap-2">
            WINS {data.actual.wins}
            {winDelta !== null && (
              <Badge variant="outline" className={cn("text-[10px]", winDelta > 0 ? "text-success border-success/30" : "text-destructive border-destructive/30")}>
                {winDeltaFmt}
              </Badge>
            )}
          </span>
        </div>
      )}

      {liveContext && (
        <div className="flex flex-col gap-2 mt-2">
          <div className="bg-background border border-border p-2 text-xs font-mono flex items-center gap-4 text-muted-foreground flex-wrap">
            <span className="font-bold text-primary">SO FAR</span>
            <span>{liveContext.record.wins}–{liveContext.record.losses}</span>
            <span>RS {liveContext.record.runs_scored}</span>
            <span>RA {liveContext.record.runs_allowed}</span>
            <span className="text-[10px]">PROJECTION IS THE 162-GAME RATE, {liveContext.sampleLabel}</span>
          </div>

          {liveContext.flags.length > 0 && (
            <div className="border border-destructive/30 bg-destructive/5 p-2 flex flex-col gap-1 font-mono text-xs">
              <div className="text-[9px] uppercase tracking-widest text-destructive">
                IL FLAGS — CONTEXT ONLY, NEVER MOVES A PRICE
              </div>
              {liveContext.flags.map((f: any, i: number) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <span className="font-bold">{f.player}</span>
                  <span className="text-destructive">{f.status}</span>
                  <span className="text-muted-foreground text-[10px]">
                    #{f.playing_time_rank?.rank} by {f.playing_time_rank?.metric}
                  </span>
                </div>
              ))}
            </div>
          )}

          <PulseMeter pulse={liveContext.pulse} />
        </div>
      )}
    </div>
  );
}
