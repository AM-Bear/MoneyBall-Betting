import { useState } from "react";
import { useSearchParams } from "wouter";
import {
  useComparePlayers,
  usePlayerCard,
  useSlate,
  useTeamLive,
  useTeamPrice,
  useTeams,
  useTeamsLive,
  ApiError,
} from "@/api";
import { PlayerCard } from "@/components/player-card";
import { PlayerSearch } from "@/components/player-search";
import { PlayerIdentity } from "@/components/player-identity";
import { PercentileBarPair } from "@/components/percentile-bars";
import { ResearchTag } from "@/components/research-tag";
import { EdgeFinder } from "@/components/edge-finder";
import { PanelSkeleton, PanelError } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { formatOdds } from "@/components/slate-rail";
import { cn } from "@/lib/utils";

function ShareButton() {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(window.location.href).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="text-[10px] font-mono uppercase border border-border px-2 py-1 hover:border-primary transition-colors"
    >
      {copied ? "LINK COPIED ✓" : "SHARE VIEW ⧉"}
    </button>
  );
}

function PlayerSlot({
  id,
  onPick,
  label,
}: {
  id: number | null;
  onPick: (id: number | null) => void;
  label: string;
}) {
  const card = usePlayerCard(id);
  return (
    <div className="flex flex-col gap-2 border border-border bg-background p-3">
      <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{label}</div>
      {id != null && card.data ? (
        <div className="flex items-center justify-between gap-2">
          <PlayerIdentity name={card.data.name} team={card.data.team} position={card.data.position} />
          <button
            onClick={() => onPick(null)}
            className="text-[10px] font-mono text-muted-foreground hover:text-destructive"
          >
            CLEAR ✕
          </button>
        </div>
      ) : (
        <PlayerSearch onSelect={(hit) => onPick(hit.player_id)} />
      )}
    </div>
  );
}

const DELTA_LABELS: Record<string, string> = {
  games: "G", pa: "PA", ba: "BA", obp: "OBP", slg: "SLG", hr: "HR", bb: "BB", so: "SO",
  bb_rate: "BB%", k_rate: "K%", games_started: "GS", era: "ERA", whip: "WHIP",
  obp_against: "OBP-A", slg_against: "SLG-A",
};

function PlayersMode() {
  const [params, setParams] = useSearchParams();
  const a = params.get("a") ? parseInt(params.get("a")!, 10) : null;
  const b = params.get("b") ? parseInt(params.get("b")!, 10) : null;

  const setSlot = (slot: "a" | "b", id: number | null) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (id == null) next.delete(slot);
      else next.set(slot, String(id));
      next.set("mode", "players");
      return next;
    });
  };

  const compare = useComparePlayers(a, b);
  const data = compare.data;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <PlayerSlot id={a} onPick={(id) => setSlot("a", id)} label="PLAYER A" />
        <PlayerSlot id={b} onPick={(id) => setSlot("b", id)} label="PLAYER B" />
      </div>

      {a != null && b != null && a === b && (
        <div className="border border-warning/30 bg-warning/5 p-3 font-mono text-xs text-warning">
          SAME PLAYER TWICE — PICK TWO DIFFERENT PLAYERS
        </div>
      )}

      {compare.isLoading && <PanelSkeleton />}
      {compare.error && (
        <PanelError
          message={compare.error instanceof ApiError ? compare.error.message : "COMPARISON UNAVAILABLE"}
        />
      )}

      {data?.mode === "boundary" && (
        <div className="flex flex-col gap-4">
          <div className="border border-warning/40 bg-warning/10 p-4 font-mono text-sm text-warning" role="status">
            {data.boundary}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="moneyline-panel"><PlayerCard card={data.a} compact /></div>
            <div className="moneyline-panel"><PlayerCard card={data.b} compact /></div>
          </div>
        </div>
      )}

      {data && data.mode !== "boundary" && (
        <div className="flex flex-col gap-4">
          <div
            aria-live="polite"
            className="border border-primary/40 bg-primary/5 p-4 font-mono flex flex-wrap items-center gap-3"
          >
            <Badge variant="value" className="text-sm px-3 py-1">
              {data.verdict?.leader?.toUpperCase()} +{data.verdict?.margin_mwaa} mWAA
            </Badge>
            <span className="text-xs text-muted-foreground">{data.verdict?.line}</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="moneyline-panel lg:col-span-2 flex flex-col gap-3">
              <div className="moneyline-section-header">PERCENTILES · A (BLUE) VS B (AMBER)</div>
              {Object.entries(data.percentile_pairs || {}).map(([key, pair]: [string, any]) => (
                <PercentileBarPair key={key} label={DELTA_LABELS[key] || key.toUpperCase()} a={pair[0]} b={pair[1]} />
              ))}
              <div className="text-[9px] font-mono text-muted-foreground">
                Percentiles vs the current-season qualified pool; rate stats oriented so higher is better.
              </div>
            </div>

            <div className="moneyline-panel lg:col-span-1">
              <div className="moneyline-section-header mb-3">DELTA (A − B)</div>
              <div className="flex flex-col gap-1 font-mono text-xs">
                {Object.entries(data.deltas || {}).map(([key, d]: [string, any]) => (
                  <div key={key} className="flex justify-between border-b border-border/40 py-1">
                    <span className="text-muted-foreground uppercase">{DELTA_LABELS[key] || key}</span>
                    <span className={cn("tabular-nums", d > 0 ? "text-success" : d < 0 ? "text-destructive" : "text-muted-foreground")}>
                      {d > 0 ? "+" : ""}{d}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="moneyline-panel"><PlayerCard card={data.a} compact /></div>
            <div className="moneyline-panel"><PlayerCard card={data.b} compact /></div>
          </div>
        </div>
      )}
    </div>
  );
}

interface TeamSel {
  kind: "live" | "hist";
  team: string;
  year: number;
  teamId?: number;
}

function parseTeamParam(
  value: string | null,
  liveTeams: any[],
  liveSeason: number | undefined,
): TeamSel | null {
  if (!value) return null;
  const match = value.match(/^([A-Z]{2,3})-(\d{4})$/);
  if (!match) return null;
  const [, team, yearStr] = match;
  const year = parseInt(yearStr, 10);
  // The live year is whatever the backend reports — never hardcoded.
  if (liveSeason != null && year === liveSeason) {
    const live = liveTeams.find((t) => t.team === team);
    return live ? { kind: "live", team, year, teamId: live.team_id } : null;
  }
  return { kind: "hist", team, year };
}

function TeamSelect({
  value,
  onChange,
  label,
  liveTeams,
  histTeams,
  liveSeason,
}: {
  value: string | null;
  onChange: (v: string) => void;
  label: string;
  liveTeams: any[];
  histTeams: any[];
  liveSeason: number | undefined;
}) {
  return (
    <div className="flex flex-col gap-1 font-mono text-xs">
      <label className="text-[10px] uppercase text-muted-foreground">{label}</label>
      <select
        className="bg-background border border-border px-2 py-1.5 focus:outline-none focus:border-primary"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="" disabled>SELECT TEAM…</option>
        <optgroup label={liveSeason ? `${liveSeason} LIVE` : "LIVE"}>
          {liveTeams.map((t) => (
            <option key={t.team} value={`${t.team}-${liveSeason}`}>{t.label}</option>
          ))}
        </optgroup>
        <optgroup label="HISTORICAL 1962–2012">
          {histTeams.map((t: any) => (
            <option key={t.label} value={`${t.team}-${t.year}`}>{t.label}</option>
          ))}
        </optgroup>
      </select>
    </div>
  );
}

function useTeamInputs(sel: TeamSel | null) {
  const live = useTeamLive(sel?.kind === "live" ? sel.teamId! : null);
  const hist = useTeamPrice(sel?.kind === "hist" ? sel.team : "", sel?.kind === "hist" ? sel.year : 0);
  if (!sel) return { inputs: null, label: "", isLoading: false, extra: null as any };
  if (sel.kind === "live") {
    return {
      inputs: live.data?.inputs || null,
      label: `${sel.team} ${sel.year} (${live.data?.sample_label || "LIVE"})`,
      isLoading: live.isLoading,
      extra: live.data,
    };
  }
  return {
    inputs: hist.data?.inputs || null,
    label: `${sel.team} ${sel.year}`,
    isLoading: hist.isLoading,
    extra: null,
  };
}

function TeamsMode() {
  const [params, setParams] = useSearchParams();
  const teamsLive = useTeamsLive();
  const teamsHist = useTeams();
  const slate = useSlate();

  const liveTeams = teamsLive.data?.teams || [];
  const histTeams = teamsHist.data?.teams || [];

  const liveSeason = teamsLive.data?.season;
  const selA = parseTeamParam(params.get("a"), liveTeams, liveSeason);
  const selB = parseTeamParam(params.get("b"), liveTeams, liveSeason);

  const setTeam = (slot: "a" | "b", value: string) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set(slot, value);
      next.set("mode", "teams");
      return next;
    });
  };

  const a = useTeamInputs(selA);
  const b = useTeamInputs(selB);

  // If both teams are live and they meet on today's slate, surface
  // the game's starter context, IL flags, and dual SEASON/ADJ prices.
  const slateGame =
    selA?.kind === "live" && selB?.kind === "live"
      ? (slate.data?.games || []).find(
          (g: any) =>
            (g.away === selA.team && g.home === selB.team) ||
            (g.away === selB.team && g.home === selA.team),
        )
      : null;

  const flags = [...(a.extra?.flags || []), ...(b.extra?.flags || [])];

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <TeamSelect label="TEAM A" value={selA ? `${selA.team}-${selA.year}` : params.get("a")} onChange={(v) => setTeam("a", v)} liveTeams={liveTeams} histTeams={histTeams} liveSeason={liveSeason} />
        <TeamSelect label="TEAM B" value={selB ? `${selB.team}-${selB.year}` : params.get("b")} onChange={(v) => setTeam("b", v)} liveTeams={liveTeams} histTeams={histTeams} liveSeason={liveSeason} />
      </div>

      {(a.isLoading || b.isLoading) && <PanelSkeleton />}

      {selA && selB && a.inputs && b.inputs && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 flex flex-col gap-4">
            {slateGame && (
              <div className="moneyline-panel flex flex-col gap-3">
                <div className="moneyline-section-header">TONIGHT ON THE SLATE · {slateGame.away} @ {slateGame.home} · {slateGame.time_et}</div>
                {slateGame.probables && (
                  <div className="font-mono text-xs flex flex-wrap gap-4">
                    <span>
                      <span className="text-muted-foreground">{slateGame.away} STARTER:</span>{" "}
                      {slateGame.probables.away?.name || "TBD"}
                    </span>
                    <span>
                      <span className="text-muted-foreground">{slateGame.home} STARTER:</span>{" "}
                      {slateGame.probables.home?.name || "TBD"}
                    </span>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                  <div className="border border-border bg-background p-2">
                    <div className="text-[9px] text-muted-foreground uppercase mb-1">SEASON PRICE</div>
                    <div className="tabular-nums">
                      {slateGame.away} {formatOdds(slateGame.fair_lines?.away)} / {slateGame.home} {formatOdds(slateGame.fair_lines?.home)}
                    </div>
                  </div>
                  <div className="border border-warning/30 bg-warning/5 p-2">
                    <div className="text-[9px] text-warning uppercase mb-1">ADJ (STARTER-BLENDED)</div>
                    <div className="tabular-nums">
                      {slateGame.adj_fair_lines
                        ? `${slateGame.away} ${formatOdds(slateGame.adj_fair_lines.away)} / ${slateGame.home} ${formatOdds(slateGame.adj_fair_lines.home)}`
                        : "NO ADJ — STARTER DATA MISSING"}
                    </div>
                  </div>
                </div>
                {slateGame.adj_detail && (
                  <div className="text-[9px] font-mono text-muted-foreground">
                    ADJ blends each starter's OBP/SLG-against over his innings share; team rate is the bullpen proxy.
                  </div>
                )}
              </div>
            )}

            {flags.length > 0 && (
              <div className="border border-destructive/30 bg-destructive/5 p-3 flex flex-col gap-2 font-mono text-xs">
                <div className="text-[10px] uppercase tracking-widest text-destructive">IL FLAGS — CONTEXT ONLY, NEVER MOVES A PRICE</div>
                {flags.map((f: any, i: number) => (
                  <div key={i} className="flex flex-wrap items-center gap-2">
                    <Badge variant="novalue" className="text-[9px]">{f.team} · {f.status}</Badge>
                    <span>{f.player}</span>
                    <span className="text-muted-foreground text-[10px]">
                      #{f.playing_time_rank?.rank} by {f.playing_time_rank?.metric}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {!slateGame && selA.kind === "live" && selB.kind === "live" && (
              <div className="border border-border bg-background p-2 font-mono text-[10px] text-muted-foreground">
                NOT ON TODAY'S SLATE — SEASON-RATE PRICE ONLY; NO STARTER CONTEXT TO BLEND.
              </div>
            )}
          </div>

          <EdgeFinder
            teamAStats={a.inputs}
            teamALabel={a.label}
            overrideB={{ inputs: b.inputs, label: b.label }}
          />
        </div>
      )}
    </div>
  );
}

export default function H2HTab() {
  const [params, setParams] = useSearchParams();
  const mode = params.get("mode") === "teams" ? "teams" : "players";

  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="moneyline-section-header w-full sm:w-1/3">HEAD-TO-HEAD</div>
        <div className="flex items-center gap-2">
          {(["players", "teams"] as const).map((m) => (
            <button
              key={m}
              onClick={() =>
                setParams((prev) => {
                  const next = new URLSearchParams(prev);
                  next.set("mode", m);
                  next.delete("a");
                  next.delete("b");
                  return next;
                })
              }
              className={cn(
                "text-xs font-mono uppercase px-3 py-1 border transition-colors",
                mode === m ? "border-primary text-primary bg-primary/10" : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {m}
            </button>
          ))}
          <ShareButton />
        </div>
      </div>

      {mode === "players" ? <PlayersMode /> : <TeamsMode />}
      <ResearchTag />
    </div>
  );
}
