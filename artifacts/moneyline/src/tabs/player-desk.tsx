import { useSearchParams } from "wouter";
import { useLiveSeason, usePlayerCard, usePlayers, ApiError } from "@/api";
import { PlayerCard } from "@/components/player-card";
import { PlayerSearch } from "@/components/player-search";
import { PlayerIdentity } from "@/components/player-identity";
import { ResearchTag } from "@/components/research-tag";
import { PanelSkeleton } from "@/components/layout";

function PoolList({
  group,
  onPick,
}: {
  group: "hitting" | "pitching";
  onPick: (id: number) => void;
}) {
  const { data, isLoading } = usePlayers(group, "qualified", "");
  const players = (data?.players || []).slice(0, 10);
  return (
    <div className="flex flex-col gap-1">
      <h2 className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
        {group === "hitting" ? "QUALIFIED BATS · BY PA" : "QUALIFIED ARMS · BY IP"}
      </h2>
      {isLoading ? (
        <div className="text-xs font-mono text-muted-foreground animate-pulse p-2">LOADING POOL…</div>
      ) : (
        players.map((p: any) => (
          <button
            key={p.player_id}
            onClick={() => onPick(p.player_id)}
            className="text-left border border-border/60 bg-background hover:border-primary transition-colors px-2 py-1.5"
          >
            <PlayerIdentity size="sm" name={p.name} team={p.team_name} position={p.position} />
          </button>
        ))
      )}
    </div>
  );
}

export default function PlayerDeskTab() {
  const [params, setParams] = useSearchParams();
  const idParam = params.get("id");
  const playerId = idParam ? parseInt(idParam, 10) : null;

  const card = usePlayerCard(playerId);
  const liveSeason = useLiveSeason();
  const notInPool = card.error instanceof ApiError && card.error.status === 404;

  const select = (id: number) => setParams({ id: String(id) });

  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="moneyline-section-header w-full sm:w-1/3">PLAYER DESK · {liveSeason ?? ""} LIVE</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="moneyline-panel lg:col-span-1 flex flex-col gap-4">
          <PlayerSearch onSelect={(hit) => select(hit.player_id)} />
          <PoolList group="hitting" onPick={select} />
          <PoolList group="pitching" onPick={select} />
        </div>

        <div className="moneyline-panel lg:col-span-2 min-h-[400px]">
          {playerId == null ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center font-mono text-muted-foreground p-8">
              <div className="text-2xl">⌁</div>
              <div className="text-sm uppercase tracking-widest">PICK A PLAYER</div>
              <div className="text-xs max-w-sm">
                Any {liveSeason ?? "current-season"} hitter with ≥100 PA or pitcher with ≥30 IP. Percentiles are computed live against the
                qualified pool.
              </div>
            </div>
          ) : card.isLoading ? (
            <PanelSkeleton />
          ) : notInPool ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center font-mono p-8 border border-warning/30 bg-warning/5">
              <div className="text-warning text-sm uppercase tracking-widest">NOT IN THE {liveSeason ?? "LIVE"} POOL</div>
              <div className="text-xs text-muted-foreground max-w-sm">
                {card.error instanceof ApiError ? card.error.message : ""}
              </div>
            </div>
          ) : card.error ? (
            <div className="flex-1 flex items-center justify-center font-mono text-destructive text-sm p-8">
              {card.error instanceof ApiError ? card.error.message : "PLAYER FEED UNAVAILABLE"}
            </div>
          ) : card.data ? (
            <PlayerCard card={card.data} />
          ) : null}
        </div>
      </div>

      <ResearchTag />
    </div>
  );
}
