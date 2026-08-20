import { useState } from "react";
import { cn } from "@/lib/utils";

/** Media pulse chip — disclosed context that NEVER moves a price.
 *  Click opens the evidence list (every item traces to a real API response). */
export function PulseMeter({ pulse }: { pulse: any }) {
  const [open, setOpen] = useState(false);
  if (!pulse) return null;

  const value = pulse.pulse;
  const hasSignal = value != null && pulse.items_matched > 0;

  return (
    <div className="font-mono text-xs border border-warning/30 bg-warning/5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 px-2 py-1.5 text-left hover:bg-warning/10 transition-colors"
      >
        <span className="flex items-center gap-2 text-warning uppercase tracking-wider">
          MEDIA PULSE {pulse.team ? `· ${pulse.team}` : ""}
          <span className="font-bold tabular-nums">
            {hasSignal ? `${value > 0 ? "+" : ""}${value}` : "NO SIGNAL"}
          </span>
          <span className="text-[9px] text-muted-foreground normal-case">
            {pulse.window_days}d · {pulse.items_matched}/{pulse.items_scanned} matched
          </span>
        </span>
        <span className="text-muted-foreground">{open ? "▴ EVIDENCE" : "▾ EVIDENCE"}</span>
      </button>
      {open && (
        <div className="border-t border-warning/20 p-2 flex flex-col gap-2">
          <div className="text-[10px] text-muted-foreground">{pulse.method}</div>
          {(pulse.evidence || []).length === 0 ? (
            <div className="text-muted-foreground">NO MATCHED ITEMS IN WINDOW</div>
          ) : (
            (pulse.evidence || []).map((item: any) => (
              <div key={item.id} className="border border-border/60 bg-background p-2 flex flex-col gap-1">
                <div className="flex justify-between gap-2 text-[10px] text-muted-foreground uppercase">
                  <span>
                    {item.date} · {item.type} · {item.source}
                  </span>
                  <span className="flex gap-1">
                    {(item.matched_positive || []).map((t: string) => (
                      <span key={t} className="text-success">+{t}</span>
                    ))}
                    {(item.matched_negative || []).map((t: string) => (
                      <span key={t} className="text-destructive">−{t}</span>
                    ))}
                  </span>
                </div>
                <div className="text-foreground/90">{item.text}</div>
                {item.link && (
                  <a
                    href={item.link}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[10px] text-primary underline underline-offset-2 w-fit"
                  >
                    SOURCE ↗
                  </a>
                )}
              </div>
            ))
          )}
          <div className={cn("text-[10px] uppercase tracking-wider text-warning border-t border-warning/20 pt-1")}>
            {pulse.hard_rule || "The pulse never moves a price; it is disclosed context only."}
          </div>
        </div>
      )}
    </div>
  );
}
