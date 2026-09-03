import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

export function formatOdds(odds: number | null | undefined): string {
  if (odds == null) return "—";
  if (odds > 0) return `+${odds}`;
  return odds.toString();
}

export function formatProb(prob: number | null | undefined): string {
  if (prob == null) return "—";
  return `${(prob * 100).toFixed(1)}%`;
}

export interface SlateGame {
  game_pk?: string;
  game_date?: string;
  team?: string;
  year?: number;
  away: string;
  home: string;
  away_name?: string;
  home_name?: string;
  away_inputs?: any;
  home_inputs?: any;
  model_prob_home: number | null;
  fair_lines: {
    away: number | null;
    home: number | null;
  };
  probables?: {
    away: { player_id: number; name: string } | null;
    home: { player_id: number; name: string } | null;
  };
  adj_prob?: number | null;
  adj_fair_lines?: { away: number | null; home: number | null } | null;
  adj_detail?: any;
  flags?: {
    team: string;
    player_id: number;
    player: string;
    status: string;
    playing_time_rank?: { metric: string; value: number; rank: number };
    source?: string;
    tooltip?: string;
  }[];
  time_et?: string;
  badges?: string[];
  status?: string;
  pricing_error?: boolean;
}

function ProbableLine({
  side,
  game,
  onSelectProbable,
}: {
  side: "away" | "home";
  game: SlateGame;
  onSelectProbable?: (playerId: number) => void;
}) {
  const probable = game.probables?.[side];
  if (!probable) return null;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onSelectProbable?.(probable.player_id);
      }}
      title={`${probable.name} — open in Player Desk`}
      className="text-[9px] font-mono text-muted-foreground hover:text-primary hover:underline underline-offset-2 truncate max-w-full text-left transition-colors"
    >
      P: {probable.name}
    </button>
  );
}

export function SlateRail({
  games,
  onSelectGame,
  onSelectProbable,
  mode = "live"
}: {
  games: SlateGame[];
  onSelectGame: (game: SlateGame) => void;
  onSelectProbable?: (playerId: number) => void;
  mode?: "live" | "historical";
}) {
  return (
    <div className="w-full lg:w-72 border-r border-border bg-card flex flex-col h-full overflow-hidden shrink-0">
      <div className="p-3 border-b border-border shrink-0 flex items-center justify-between">
        <span className="moneyline-section-header w-full">SLATE</span>
      </div>

      {mode === "historical" && (
        <div className="bg-warning/10 border-b border-warning/30 p-2 text-xs font-mono text-warning text-center">
          HISTORICAL MODE
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
        {games.map((game, i) => (
          <div
            key={`${game.away}-${game.home}-${i}`}
            className="text-left bg-background border border-border hover:border-primary transition-colors group flex flex-col gap-1.5 relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-1 h-full bg-muted group-hover:bg-primary/50 transition-colors" />
            <button
              type="button"
              onClick={() => onSelectGame(game)}
              className="text-left p-2 pb-1 focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary"
              aria-label={`Open ${game.away} at ${game.home} in the Desk`}
              data-testid={`button-open-slate-game-${game.game_pk || i}`}
            >
              {mode === "historical" && game.status && (
                <div className="text-[9px] text-muted-foreground uppercase">{game.status}</div>
              )}
              {mode === "live" && (game.time_et || game.status) && (
                <div className="flex justify-between text-[9px] text-muted-foreground uppercase">
                  <span>{game.time_et}</span>
                  <span>{game.status}</span>
                </div>
              )}

              <div className="flex flex-col mt-1.5">
                <div className="flex justify-between items-center text-sm font-mono tabular-nums">
                  <span className="font-bold">{game.away}</span>
                  <span className="text-muted-foreground">{formatOdds(game.fair_lines?.away)}</span>
                </div>
              </div>

              <div className="flex flex-col mt-1">
                <div className="flex justify-between items-center text-sm font-mono tabular-nums">
                  <span className="font-bold flex items-center gap-1">
                    <span className="text-[10px] text-muted-foreground">@</span>
                    {game.home}
                  </span>
                  <span className="text-muted-foreground">{formatOdds(game.fair_lines?.home)}</span>
                </div>
              </div>
            </button>

            <div className="px-2 pb-1 flex flex-col gap-1">
              <ProbableLine side="away" game={game} onSelectProbable={onSelectProbable} />
              <ProbableLine side="home" game={game} onSelectProbable={onSelectProbable} />
            </div>

            {game.adj_fair_lines && (
              <div className="mx-2 flex justify-between items-center text-[10px] font-mono tabular-nums text-warning border-t border-warning/20 pt-1">
                <span className="uppercase tracking-wide">ADJ</span>
                <span>
                  {formatOdds(game.adj_fair_lines.away)} / {formatOdds(game.adj_fair_lines.home)}
                </span>
              </div>
            )}

            {(game.flags?.length || 0) > 0 && (
              <div className="px-2 flex flex-wrap gap-1">
                {game.flags!.map((flag, fi) => (
                  <Tooltip key={fi}>
                    <TooltipTrigger asChild>
                      <span
                        className="inline-flex items-center border border-destructive/40 bg-destructive/10 text-destructive text-[8px] font-mono px-1 py-0 uppercase cursor-help"
                      >
                        {flag.team} IL: {flag.player}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className="font-mono text-xs max-w-64 rounded-none">
                      {flag.tooltip ||
                        `${flag.player} — ${flag.status}. #${flag.playing_time_rank?.rank} on the club by ${flag.playing_time_rank?.metric}. Context only — never moves a price.`}
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            )}

            <div className="mx-2 flex justify-between items-end mt-0.5 pt-1.5 border-t border-border/50">
              <div className="flex gap-1">
                {game.badges?.map(b => (
                  <Badge key={b} variant="value" className="text-[9px] px-1 py-0 h-4 whitespace-nowrap">
                    {b}
                  </Badge>
                ))}
              </div>
              <span className="text-xs text-primary font-mono flex items-center gap-2">
                {game.adj_prob != null && (
                  <span className="text-warning" title="Starter-blended (ADJ) home probability">
                    {formatProb(game.adj_prob)} A
                  </span>
                )}
                {game.model_prob_home != null && <span>{formatProb(game.model_prob_home)} H</span>}
              </span>
            </div>
          </div>
        ))}
        {games.length === 0 && (
          <div className="text-center p-4 text-muted-foreground font-mono text-sm">
            NO GAMES
          </div>
        )}
      </div>
    </div>
  );
}
