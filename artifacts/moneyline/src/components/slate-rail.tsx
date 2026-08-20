import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";

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
  badges?: string[];
  status?: string;
}

export function SlateRail({ 
  games, 
  onSelectGame,
  mode = "live"
}: { 
  games: SlateGame[];
  onSelectGame: (game: SlateGame) => void;
  mode?: "live" | "historical";
}) {
  return (
    <div className="w-full lg:w-64 border-r border-border bg-card flex flex-col h-full overflow-hidden shrink-0">
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
          <button
            key={`${game.away}-${game.home}-${i}`}
            onClick={() => onSelectGame(game)}
            className="text-left bg-background border border-border p-2 hover:border-primary transition-colors group flex flex-col gap-2 relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-1 h-full bg-muted group-hover:bg-primary/50 transition-colors" />
            
            {mode === "historical" && game.status && (
              <div className="text-[9px] text-muted-foreground uppercase">{game.status}</div>
            )}

            <div className="flex justify-between items-center text-sm font-mono tabular-nums">
              <span className="font-bold">{game.away}</span>
              <span className="text-muted-foreground">{formatOdds(game.fair_lines.away)}</span>
            </div>
            
            <div className="flex justify-between items-center text-sm font-mono tabular-nums">
              <span className="font-bold flex items-center gap-1">
                <span className="text-[10px] text-muted-foreground">@</span>
                {game.home}
              </span>
              <span className="text-muted-foreground">{formatOdds(game.fair_lines.home)}</span>
            </div>

            <div className="flex justify-between items-end mt-1 pt-2 border-t border-border/50">
              <div className="flex gap-1">
                {game.badges?.map(b => (
                  <Badge key={b} variant="value" className="text-[9px] px-1 py-0 h-4 whitespace-nowrap">
                    {b}
                  </Badge>
                ))}
              </div>
              {game.model_prob_home != null && (
                <span className="text-xs text-primary font-mono">
                  {formatProb(game.model_prob_home)} H
                </span>
              )}
            </div>
          </button>
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
