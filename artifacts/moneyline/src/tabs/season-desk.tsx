import { Fragment, useState } from "react";
import { useSearchParams } from "wouter";
import { useLiveSeason, useSeasonSim, useTeamOutlook } from "@/api";
import { DistributionSparkline } from "@/components/sparkline";
import { ResearchTag } from "@/components/research-tag";
import { PanelSkeleton, PanelError } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatProb } from "@/components/slate-rail";

const SORTS: Record<string, { label: string; value: (r: any) => number }> = {
  expected_wins: { label: "EXP W", value: (r) => r.expected_wins },
  playoff_odds: { label: "PLAYOFF %", value: (r) => r.playoff_odds },
  division_odds: { label: "DIV %", value: (r) => r.division_odds },
  delta_vs_pace: { label: "Δ PACE", value: (r) => r.delta_vs_pace },
  wins: { label: "W", value: (r) => r.wins },
};

function TeamDrill({ teamId }: { teamId: number }) {
  const outlook = useTeamOutlook(teamId);
  if (outlook.isLoading)
    return <div className="p-3 font-mono text-xs text-muted-foreground animate-pulse">COMPUTING REMAINING SCHEDULE…</div>;
  if (outlook.error || !outlook.data)
    return <div className="p-3 font-mono text-xs text-destructive">REMAINING-SCHEDULE INPUTS UNAVAILABLE</div>;
  const d = outlook.data;
  const rating = d.mean_opponent_rating;
  return (
    <div className="p-3 flex flex-col gap-3 bg-background/60 border-t border-border">
      <div className="flex flex-wrap gap-4 font-mono text-xs items-baseline">
        <span className="text-[10px] uppercase text-muted-foreground">REMAINING SCHEDULE · {d.games_remaining} G</span>
        <span>
          MEAN OPP RATING{" "}
          <span className={cn("font-bold tabular-nums", rating > 0.5 ? "text-destructive" : "text-success")}>
            {rating?.toFixed(3) ?? "—"}
          </span>
          <span className="text-muted-foreground"> (.500 = LEAGUE AVG)</span>
        </span>
      </div>
      <div className="flex flex-wrap gap-1">
        {(d.next_10 || []).map((g: any, i: number) => (
          <div
            key={i}
            title={`${g.date} ${g.home ? "vs" : "@"} ${g.opponent_name} — win prob ${formatProb(g.win_prob)}`}
            className={cn(
              "border px-1.5 py-1 font-mono text-[10px] flex flex-col items-center min-w-[52px]",
              g.win_prob >= 0.5 ? "border-success/40 bg-success/5" : "border-destructive/40 bg-destructive/5",
            )}
          >
            <span className="text-muted-foreground">{g.date.slice(5)}</span>
            <span className="font-bold">{g.home ? "" : "@"}{g.opponent}</span>
            <span className={g.win_prob >= 0.5 ? "text-success" : "text-destructive"}>{formatProb(g.win_prob)}</span>
          </div>
        ))}
      </div>
      <div className="text-[9px] font-mono text-muted-foreground">{d.rating_definition}</div>
    </div>
  );
}

export default function SeasonDeskTab() {
  const sim = useSeasonSim();
  const liveSeason = useLiveSeason();
  const [params, setParams] = useSearchParams();
  const sortKey = SORTS[params.get("sort") || ""] ? params.get("sort")! : "expected_wins";
  const [drill, setDrill] = useState<number | null>(params.get("team") ? parseInt(params.get("team")!, 10) : null);

  if (sim.isLoading)
    return (
      <div className="max-w-7xl mx-auto flex flex-col gap-4">
        <h1 className="moneyline-section-header w-1/3">SEASON DESK · SIMULATING {liveSeason ?? "SEASON"}…</h1>
        <PanelSkeleton />
      </div>
    );
  if (sim.error || !sim.data)
    return (
      <div className="max-w-7xl mx-auto">
        <PanelError message="SEASON SIMULATION UNAVAILABLE — LIVE INPUTS DOWN" />
      </div>
    );

  const d = sim.data;
  const rows = [...d.rows].sort((x, y) => SORTS[sortKey].value(y) - SORTS[sortKey].value(x));
  const byDelta = [...d.rows].sort((x, y) => y.delta_vs_pace - x.delta_vs_pace);
  const risers = byDelta.slice(0, 3).filter((r) => r.delta_vs_pace > 0);
  const fallers = byDelta.slice(-3).reverse().filter((r) => r.delta_vs_pace < 0);

  const setSort = (key: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("sort", key);
      return next;
    });

  const toggleDrill = (teamId: number) => {
    const next = drill === teamId ? null : teamId;
    setDrill(next);
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      if (next == null) p.delete("team");
      else p.set("team", String(next));
      return p;
    });
  };

  const exportCsv = () => {
    const headers = ["team","name","wins","losses","gp","remaining","pace_wins","expected_wins","p5","p95","playoff_odds","division_odds","delta_vs_pace"];
    const csv = [
      headers.join(","),
      ...d.rows.map((r: any) =>
        [r.team, `"${r.name}"`, r.wins, r.losses, r.games_played, r.games_remaining, r.pace_wins, r.expected_wins, r.wins_p5, r.wins_p95, r.playoff_odds, r.division_odds, r.delta_vs_pace].join(","),
      ),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `moneyline_season_sim_${d.season}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="moneyline-section-header w-full sm:w-1/3">SEASON DESK · {d.season} SIMULATED ×{d.iterations}</h1>
        <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
          <span>SEED {d.seed}</span>
          <span>· {d.compute_ms}ms</span>
          <Badge variant="outline" className="text-warning border-warning/30 text-[10px]">{d.sample_label}</Badge>
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={exportCsv}>
            <Download className="w-3 h-3 mr-1" /> CSV
          </Button>
        </div>
      </div>

      {(risers.length > 0 || fallers.length > 0) && (
        <div className="flex flex-wrap gap-2 font-mono text-xs">
          {risers.map((r) => (
            <button key={r.team} onClick={() => toggleDrill(r.team_id)} className="border border-success/40 bg-success/10 text-success px-2 py-1">
              ▲ {r.team} +{r.delta_vs_pace.toFixed(1)} VS PACE
            </button>
          ))}
          {fallers.map((r) => (
            <button key={r.team} onClick={() => toggleDrill(r.team_id)} className="border border-destructive/40 bg-destructive/10 text-destructive px-2 py-1">
              ▼ {r.team} {r.delta_vs_pace.toFixed(1)} VS PACE
            </button>
          ))}
        </div>
      )}

      <div className="moneyline-panel overflow-x-auto p-0">
        <table className="w-full text-xs font-mono text-left whitespace-nowrap">
          <thead className="bg-muted/30 text-[10px] text-muted-foreground uppercase border-b border-border">
            <tr>
              <th className="p-2 font-semibold">Team</th>
              <th aria-sort={sortKey === "wins" ? "descending" : "none"} className="p-2 font-semibold text-right">
                <button type="button" aria-label="Sort by wins" onClick={() => setSort("wins")} className="moneyline-focus-ring hover:text-foreground">
                  W–L {sortKey === "wins" && "▾"}
                </button>
              </th>
              <th className="p-2 font-semibold text-right">PACE</th>
              <th aria-sort={sortKey === "expected_wins" ? "descending" : "none"} className="p-2 font-semibold text-right border-l border-border/50">
                <button type="button" aria-label="Sort by expected wins" onClick={() => setSort("expected_wins")} className="moneyline-focus-ring hover:text-foreground">
                  EXP W {sortKey === "expected_wins" && "▾"}
                </button>
              </th>
              <th className="p-2 font-semibold">DIST</th>
              <th className="p-2 font-semibold text-right">P5–P95</th>
              <th aria-sort={sortKey === "playoff_odds" ? "descending" : "none"} className="p-2 font-semibold text-right border-l border-border/50">
                <button type="button" aria-label="Sort by playoff odds" onClick={() => setSort("playoff_odds")} className="moneyline-focus-ring hover:text-foreground">
                  PLAYOFF {sortKey === "playoff_odds" && "▾"}
                </button>
              </th>
              <th aria-sort={sortKey === "division_odds" ? "descending" : "none"} className="p-2 font-semibold text-right">
                <button type="button" aria-label="Sort by division odds" onClick={() => setSort("division_odds")} className="moneyline-focus-ring hover:text-foreground">
                  DIV {sortKey === "division_odds" && "▾"}
                </button>
              </th>
              <th aria-sort={sortKey === "delta_vs_pace" ? "descending" : "none"} className="p-2 font-semibold text-right border-l border-border/50">
                <button type="button" aria-label="Sort by change versus pace" onClick={() => setSort("delta_vs_pace")} className="moneyline-focus-ring hover:text-foreground">
                  Δ PACE {sortKey === "delta_vs_pace" && "▾"}
                </button>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {rows.map((r: any) => (
              <Fragment key={r.team}>
                <tr className={cn("hover:bg-muted/20 transition-colors", drill === r.team_id && "bg-muted/30")}>
                  <td className="p-2 font-bold text-primary">
                    <button
                      type="button"
                      aria-label={`${drill === r.team_id ? "Hide" : "Show"} remaining schedule for ${r.name || r.team}`}
                      aria-expanded={drill === r.team_id}
                      aria-controls={`team-drill-${r.team_id}`}
                      onClick={() => toggleDrill(r.team_id)}
                      className="moneyline-focus-ring font-bold hover:underline underline-offset-2"
                    >
                      {r.team}
                    </button>
                  </td>
                  <td className="p-2 text-right tabular-nums">{r.wins}–{r.losses}</td>
                  <td className="p-2 text-right tabular-nums text-muted-foreground">{r.pace_wins.toFixed(1)}</td>
                  <td className="p-2 text-right tabular-nums font-bold border-l border-border/50">{r.expected_wins.toFixed(1)}</td>
                  <td className="p-2"><DistributionSparkline distribution={r.distribution} /></td>
                  <td className="p-2 text-right tabular-nums text-muted-foreground">{r.wins_p5}–{r.wins_p95}</td>
                  <td className="p-2 text-right tabular-nums border-l border-border/50">
                    <span className={r.playoff_odds >= 0.5 ? "text-success" : ""}>{(r.playoff_odds * 100).toFixed(1)}%</span>
                  </td>
                  <td className="p-2 text-right tabular-nums">{(r.division_odds * 100).toFixed(1)}%</td>
                  <td className="p-2 text-right tabular-nums border-l border-border/50">
                    <span className={r.delta_vs_pace > 0 ? "text-success" : r.delta_vs_pace < 0 ? "text-destructive" : "text-muted-foreground"}>
                      {r.delta_vs_pace > 0 ? "+" : ""}{r.delta_vs_pace.toFixed(1)}
                    </span>
                  </td>
                </tr>
                {drill === r.team_id && (
                  <tr id={`team-drill-${r.team_id}`}>
                    <td colSpan={9} className="p-0"><TeamDrill teamId={r.team_id} /></td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border border-border bg-background p-3 font-mono text-[10px] text-muted-foreground flex flex-col gap-1">
        <h2 className="text-[9px] uppercase tracking-widest">ASSUMPTIONS — READ BEFORE QUOTING</h2>
        {(d.assumptions || []).map((a: string, i: number) => (
          <div key={i}>· {a}</div>
        ))}
        <div>· {d.playoff_format_note}</div>
      </div>

      {d.next_season && (
        <div className="border border-warning/30 bg-warning/5 p-3 font-mono text-xs text-warning">
          {d.next_season.season}: {d.next_season.status} — {d.next_season.reason}
        </div>
      )}

      <ResearchTag />
    </div>
  );
}
