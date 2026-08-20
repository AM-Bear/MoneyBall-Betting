import { cn } from "@/lib/utils";

export function StatusStrip({
  modelLoaded,
  dbReady,
  slateMode,
  ms
}: {
  modelLoaded: boolean;
  dbReady: boolean;
  slateMode: "live" | "historical" | "error";
  ms?: number;
}) {
  return (
    <footer className="border-t border-border bg-card px-4 py-2 flex items-center justify-between text-[10px] font-mono text-muted-foreground mt-auto sticky bottom-0 z-40">
      <div className="flex gap-6 items-center">
        <div className="flex items-center gap-2">
          <span>MODEL: 1962–2001-v1</span>
        </div>
        
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className={cn("w-1.5 h-1.5 rounded-full", slateMode === "live" ? "bg-success" : slateMode === "historical" ? "bg-warning" : "bg-destructive")} />
            SLATE
          </span>
          <span className="flex items-center gap-1">
            <span className={cn("w-1.5 h-1.5 rounded-full", modelLoaded ? "bg-success" : "bg-destructive")} />
            MODELS
          </span>
          <span className="flex items-center gap-1">
            <span className={cn("w-1.5 h-1.5 rounded-full", dbReady ? "bg-success" : "bg-destructive")} />
            RECORD
          </span>
        </div>
      </div>

      <div className="flex gap-6 items-center">
        <div className="tracking-widest uppercase text-warning opacity-80 border border-warning/30 px-2 py-0.5 bg-warning/5">
          STATISTICAL RESEARCH · NOT WAGERING ADVICE
        </div>
        {ms !== undefined && <span>{ms}ms</span>}
      </div>
    </footer>
  );
}
