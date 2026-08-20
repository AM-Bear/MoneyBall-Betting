import { cn } from "@/lib/utils";

function fillColor(pctl: number) {
  if (pctl >= 70) return "bg-success";
  if (pctl >= 45) return "bg-primary";
  if (pctl >= 25) return "bg-warning";
  return "bg-destructive";
}

/** 4px percentile track (#1f2530 = --border) with the pool median ticked at 50. */
export function PercentileBar({
  label,
  stat,
  pctl,
}: {
  label: string;
  stat?: string;
  pctl: number | null | undefined;
}) {
  return (
    <div className="flex items-center gap-2 font-mono text-xs">
      <span className="w-16 text-muted-foreground uppercase shrink-0">{label}</span>
      {stat !== undefined && <span className="w-12 tabular-nums shrink-0">{stat}</span>}
      <div
        className="moneyline-percentile-track flex-1"
        role="img"
        aria-label={`${label}: ${pctl != null ? `${Math.round(pctl)}th percentile vs the qualified pool` : "no percentile"}`}
      >
        {pctl != null && (
          <div
            className={cn("absolute left-0 top-0 h-full transition-[width] duration-500", fillColor(pctl))}
            style={{ width: `${Math.max(0, Math.min(100, pctl))}%` }}
          />
        )}
        <div
          className="absolute -top-0.5 h-2 w-px bg-muted-foreground/70"
          style={{ left: "50%" }}
          title="Pool median"
        />
      </div>
      <span className="w-8 text-right tabular-nums shrink-0">
        {pctl != null ? Math.round(pctl) : "—"}
      </span>
    </div>
  );
}

/** Two stacked 4px tracks sharing one label row — the H2H paired view. */
export function PercentileBarPair({
  label,
  a,
  b,
}: {
  label: string;
  a: number | null | undefined;
  b: number | null | undefined;
}) {
  return (
    <div className="flex items-center gap-2 font-mono text-xs">
      <span className="w-16 text-muted-foreground uppercase shrink-0">{label}</span>
      <div className="flex-1 flex flex-col gap-1">
        {[a, b].map((pctl, i) => (
          <div
            key={i}
            className="moneyline-percentile-track"
            role="img"
            aria-label={`${label} ${i === 0 ? "A" : "B"}: ${pctl != null ? `${Math.round(pctl)}th percentile` : "no percentile"}`}
          >
            {pctl != null && (
              <div
                className={cn(
                  "absolute left-0 top-0 h-full transition-[width] duration-500",
                  i === 0 ? "bg-primary" : "bg-warning",
                )}
                style={{ width: `${Math.max(0, Math.min(100, pctl))}%` }}
              />
            )}
            <div className="absolute -top-0.5 h-2 w-px bg-muted-foreground/70" style={{ left: "50%" }} />
          </div>
        ))}
      </div>
      <span className="w-16 text-right tabular-nums shrink-0">
        {a != null ? Math.round(a) : "—"} / {b != null ? Math.round(b) : "—"}
      </span>
    </div>
  );
}
