import { cn } from "@/lib/utils";

export function StatusStrip({
  modelLoaded,
  dbReady,
  slateMode,
  modelVersion,
  ms
}: {
  modelLoaded: boolean;
  dbReady: boolean;
  slateMode: "live" | "historical" | "error";
  modelVersion?: string;
  ms?: number;
}) {
  return (
    <footer className="border-t border-border bg-card px-4 py-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted-foreground mt-auto sticky bottom-0 z-40">
      <div className="flex flex-wrap gap-4 items-center">
        <div className="flex items-center gap-2">
          {/* The version is the API's to state, not the footer's. Until
              /api/health answers, say so rather than showing a stale literal
              that could outlive the model it names. */}
          <span>Model: {modelVersion ?? "—"}</span>
        </div>
        
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className={cn("w-1.5 h-1.5 rounded-full", slateMode === "live" ? "bg-success" : slateMode === "historical" ? "bg-warning" : "bg-destructive")} />
            Slate
          </span>
          <span className="flex items-center gap-1">
            <span className={cn("w-1.5 h-1.5 rounded-full", modelLoaded ? "bg-success" : "bg-destructive")} />
            Models
          </span>
          <span className="flex items-center gap-1">
            <span className={cn("w-1.5 h-1.5 rounded-full", dbReady ? "bg-success" : "bg-destructive")} />
            Record
          </span>
        </div>
      </div>

      <div className="flex gap-6 items-center">
        <div className="tracking-wide text-warning opacity-80 border border-warning/30 px-2 py-0.5 bg-warning/5">
          Statistical research · not wagering advice
        </div>
        {ms !== undefined && <span>{ms}ms</span>}
      </div>
    </footer>
  );
}
