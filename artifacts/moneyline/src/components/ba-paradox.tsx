import { useState } from "react";
import { useBaParadox } from "@/api";
import { Switch } from "./ui/switch";
import { cn } from "@/lib/utils";
import { PanelSkeleton, PanelError } from "./layout";

export function BaParadoxPanel() {
  const { data, isLoading, error } = useBaParadox();
  const [showBa, setShowBa] = useState(false);

  if (isLoading) return <PanelSkeleton />;
  if (error || !data) return <PanelError message="Failed to load BA Paradox data" />;

  const current = showBa ? data.with_ba : data.base;
  const maxCoef = Math.max(
    ...Object.values(data.base.coefficients).map((value) => Math.abs(Number(value))),
    ...Object.values(data.with_ba.coefficients).map((value) => Math.abs(Number(value))),
  ) * 1.05;

  return (
    <div className="moneyline-panel lg:col-span-3">
      <div className="flex justify-between items-center mb-4">
        <div className="moneyline-section-header w-1/3">THE BA PARADOX</div>
        <div className="flex items-center gap-3 text-sm font-mono">
          <span className={cn("transition-colors", !showBa ? "text-primary" : "text-muted-foreground")}>OBP + SLG</span>
          <Switch checked={showBa} onCheckedChange={setShowBa} />
          <span className={cn("transition-colors", showBa ? "text-primary" : "text-muted-foreground")}>+ BA</span>
        </div>
      </div>

      <div className="bg-background border border-border p-6 flex flex-col gap-4">
        <div className="flex flex-col gap-6 font-mono text-sm max-w-2xl mx-auto w-full">
          
          <div className="flex items-center gap-4">
            <div className="w-12 text-right font-bold">OBP</div>
            <div className="flex-1 h-6 bg-muted relative">
              <div 
                className="absolute top-0 left-0 h-full bg-primary transition-all duration-500 ease-out"
                style={{ width: `${(current.coefficients.OBP / maxCoef) * 100}%` }}
              />
            </div>
            <div className="w-20 tabular-nums">+{current.coefficients.OBP.toFixed(1)}</div>
          </div>

          <div className="flex items-center gap-4">
            <div className="w-12 text-right font-bold">SLG</div>
            <div className="flex-1 h-6 bg-muted relative">
              <div 
                className="absolute top-0 left-0 h-full bg-primary transition-all duration-500 ease-out"
                style={{ width: `${(current.coefficients.SLG / maxCoef) * 100}%` }}
              />
            </div>
            <div className="w-20 tabular-nums">+{current.coefficients.SLG.toFixed(1)}</div>
          </div>

          <div className={cn("flex items-center gap-4 transition-opacity duration-500", showBa ? "opacity-100" : "opacity-30")}>
            <div className="w-12 text-right font-bold">BA</div>
            <div className="flex-1 h-6 bg-muted relative flex justify-end overflow-hidden">
               {/* Negative bar goes left from a zero line, but for simplicity we'll just color it red and anchor right */}
              <div 
                className={cn("absolute top-0 right-0 h-full transition-all duration-500 ease-out", showBa && current.coefficients.BA < 0 ? "bg-destructive" : "bg-primary")}
                style={{ 
                  width: showBa ? `${(Math.abs(current.coefficients.BA) / maxCoef) * 100}%` : '0%',
                }}
              />
            </div>
            <div className={cn("w-20 tabular-nums", showBa && current.coefficients.BA < 0 ? "text-destructive" : "")}>
              {showBa ? current.coefficients.BA.toFixed(1) : "0.0"}
            </div>
          </div>

        </div>

        <div className="mt-4 text-center text-muted-foreground font-mono text-xs italic">
          {data.caption}
        </div>
      </div>
    </div>
  );
}
