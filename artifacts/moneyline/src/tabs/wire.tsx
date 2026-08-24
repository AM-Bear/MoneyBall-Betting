import { useSearchParams } from "wouter";
import { useTeamsLive, useWire } from "@/api";
import { ResearchTag } from "@/components/research-tag";
import { PanelSkeleton, PanelError } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TYPE_STYLES: Record<string, string> = {
  TRADE: "border-primary/40 text-primary",
  SIGNING: "border-success/40 text-success",
  IL: "border-destructive/40 text-destructive",
  ACTIVATED: "border-success/40 text-success",
  RESULT: "border-border text-foreground",
  NEWS: "border-muted-foreground/40 text-muted-foreground",
};

function formatAsOf(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-US", {
      timeZone: "America/New_York",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return iso;
  }
}

export default function WireTab() {
  const [params, setParams] = useSearchParams();
  const team = params.get("team");
  const types = params.get("types")?.split(",").filter(Boolean) || [];

  const wire = useWire(team, types);
  const teamsLive = useTeamsLive();

  const allTypes: string[] = wire.data?.types || ["TRADE", "SIGNING", "IL", "ACTIVATED", "RESULT", "NEWS"];

  const toggleType = (t: string) => {
    const next = types.includes(t) ? types.filter((x) => x !== t) : [...types, t];
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      if (next.length) p.set("types", next.join(","));
      else p.delete("types");
      return p;
    });
  };

  const setTeam = (code: string) => {
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      if (code) p.set("team", code);
      else p.delete("team");
      return p;
    });
  };

  const sourcesUp = wire.data?.sources_up || {};
  const downSources = Object.entries(sourcesUp).filter(([, up]) => !up).map(([name]) => name);

  return (
    <div className="max-w-5xl mx-auto flex flex-col gap-4 min-h-full">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="moneyline-section-header w-full sm:w-1/3">THE WIRE · MERGED FEED</h1>
        <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
          {wire.data?.updated_at && <span>UPDATED {formatAsOf(wire.data.updated_at)}</span>}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          className="bg-background border border-border px-2 py-1 font-mono text-xs focus:outline-none focus:border-primary"
          value={team || ""}
          onChange={(e) => setTeam(e.target.value)}
          aria-label="Filter by team"
        >
          <option value="">ALL TEAMS</option>
          {(teamsLive.data?.teams || []).map((t) => (
            <option key={t.team} value={t.team}>{t.team}</option>
          ))}
        </select>
        {allTypes.map((t) => (
          <button
            key={t}
            onClick={() => toggleType(t)}
            aria-pressed={types.includes(t)}
            className={cn(
              "text-[10px] font-mono uppercase px-2 py-1 border transition-colors",
              types.includes(t)
                ? "border-primary text-primary bg-primary/10"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {t}
          </button>
        ))}
        {types.length > 0 && (
          <button onClick={() => setParams((prev) => { const p = new URLSearchParams(prev); p.delete("types"); return p; })} className="text-[10px] font-mono text-muted-foreground underline underline-offset-2">
            CLEAR
          </button>
        )}
      </div>

      {downSources.length > 0 && (
        <div className="border border-warning/40 bg-warning/10 px-3 py-2 font-mono text-[11px] text-warning flex flex-wrap gap-2 items-center">
          <span className="uppercase tracking-widest font-bold">AS OF {formatAsOf(wire.data?.updated_at)}</span>
          <span>
            {downSources.map((s) => s.toUpperCase()).join(" + ")} FEED{downSources.length > 1 ? "S" : ""} DOWN — SHOWING CACHED / REMAINING SOURCES ONLY
          </span>
        </div>
      )}

      {wire.isLoading ? (
        <PanelSkeleton />
      ) : wire.error || !wire.data ? (
        <PanelError message="THE WIRE IS DOWN — ALL SOURCES UNAVAILABLE" />
      ) : (
        <div className="moneyline-panel p-0 flex-1 flex flex-col divide-y divide-border/50">
          {wire.data.items.length === 0 ? (
            <div className="p-8 text-center font-mono text-sm text-muted-foreground">
              NOTHING ON THE WIRE FOR THIS FILTER
            </div>
          ) : (
            wire.data.items.map((item: any) => (
              <div
                key={item.id}
                className={cn(
                  "px-3 py-2 flex flex-col gap-1 hover:bg-muted/10 transition-colors",
                  item.result === "WIN" && "border-l-2 border-l-success",
                  item.result === "LOSS" && "border-l-2 border-l-destructive",
                )}
              >
                <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] text-muted-foreground">
                  <span className="tabular-nums">{item.date}</span>
                  <Badge variant="outline" className={cn("text-[9px] px-1 py-0", TYPE_STYLES[item.type] || "")}>
                    {item.type}
                  </Badge>
                  {item.team && <span className="font-bold text-foreground/70">{item.team}</span>}
                  <span className="uppercase">· {item.source}</span>
                </div>
                <div className="font-mono text-xs text-foreground/90 leading-snug">{item.text}</div>
                {item.link && (
                  <a
                    href={item.link}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[10px] font-mono text-primary underline underline-offset-2 w-fit"
                  >
                    SOURCE ↗
                  </a>
                )}
              </div>
            ))
          )}
        </div>
      )}

      <div className="font-mono text-[9px] text-muted-foreground">{wire.data?.note}</div>
      <ResearchTag />
    </div>
  );
}
