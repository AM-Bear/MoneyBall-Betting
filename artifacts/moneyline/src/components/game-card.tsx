import { useState } from "react";
import { ChevronDown, CircleHelp, ExternalLink, Info } from "lucide-react";
import { useLocation } from "wouter";
import { EdgeFinder } from "@/components/edge-finder";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatOdds, formatProb, SlateGame } from "@/components/slate-rail";
import { DetailLevel } from "./presentation-preferences";
import { isNonPlayableGame, manualPriceCheckState } from "@/lib/game-status";

function titleCaseStatus(status?: string) {
  if (!status) return "Status unavailable";
  return status
    .toLowerCase()
    .split(/[\s-]+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function isMissingStarter(game: SlateGame) {
  return !game.probables?.away || !game.probables?.home;
}

function modelLean(game: SlateGame) {
  if (game.model_prob_home == null) return "Model probability unavailable";
  if (Math.abs(game.model_prob_home - 0.5) < 0.015) return "Model is close to even";
  return game.model_prob_home > 0.5 ? `${game.home} has the model lean` : `${game.away} has the model lean`;
}

function inputValue(value: unknown) {
  return typeof value === "number" ? value.toFixed(3) : "—";
}

export function GameCard({
  game,
  detailLevel = "standard",
  explainTerms = true,
}: {
  game: SlateGame;
  detailLevel?: DetailLevel;
  explainTerms?: boolean;
}) {
  const [, navigate] = useLocation();
  const [contextOpen, setContextOpen] = useState(detailLevel === "expanded");
  const [advancedOpen, setAdvancedOpen] = useState(detailLevel === "expanded");
  const isHistorical = Boolean(game.team && game.year);
  const isPartial = Boolean(game.pricing_error || game.model_prob_home == null || !game.fair_lines);
  const priceCheckState = manualPriceCheckState(game);
  const hasAdjustment = game.adj_prob != null && game.adj_fair_lines != null;
  const missingStarter = isMissingStarter(game);
  const status = titleCaseStatus(game.status);
  const cardId = game.game_pk || `${game.away}-${game.home}`;

  return (
    <article
      className={cn("game-card", isPartial && "game-card-partial", isHistorical && "game-card-historical")}
      data-testid={`card-game-${cardId}`}
    >
      <div className="game-card-answer">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="game-card-status-dot" aria-hidden="true" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span data-testid={`text-game-time-${cardId}`}>{game.time_et || "Time unavailable"}</span>
              <span aria-hidden="true">·</span>
              <span data-testid={`status-game-${cardId}`}>{status}</span>
              {isHistorical && <Badge variant="warning">Historical</Badge>}
              {game.badges?.filter((badge) => badge !== "LIVE").map((badge) => (
                <Badge key={badge} variant={badge === "FEED PARTIAL" ? "warning" : "outline"}>{badge}</Badge>
              ))}
            </div>
            <h3 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">
              {game.away_name || game.away}
              <span className="mx-2 text-muted-foreground/50">@</span>
              {game.home_name || game.home}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground" data-testid={`text-lean-${cardId}`}>
              {modelLean(game)}
              {game.model_prob_home != null && !isPartial && (
                <span className="ml-2 font-medium text-foreground">{formatProb(game.model_prob_home)} home</span>
              )}
            </p>
          </div>
        </div>
        <div className="game-card-price-block" aria-label="Model prices">
          <span className="eyebrow">Fair price</span>
          {isPartial ? (
            <strong className="text-base text-warning">Unavailable</strong>
          ) : (
            <strong className="tabular-nums text-lg">{formatOdds(game.fair_lines.home)} / {formatOdds(game.fair_lines.away)}</strong>
          )}
          <span className="text-[11px] text-muted-foreground">Home / away</span>
        </div>
      </div>

      <div className="game-card-summary">
        <div className="flex flex-wrap items-center gap-2">
          <span className="status-label status-label-neutral">Model only</span>
          {hasAdjustment && <span className="status-label status-label-adjusted">Starter-adjusted available</span>}
          {missingStarter && !isHistorical && <span className="status-label status-label-warning">Starter data incomplete</span>}
        </div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {isPartial
            ? "The schedule is available, but this game does not have a complete model price yet."
            : "This is a model estimate, not a sportsbook quote. A value comparison appears only after you enter a valid book price."}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {!isHistorical && game.probables?.away && (
            <button
              type="button"
              onClick={() => navigate(`/players?id=${game.probables?.away?.player_id}`)}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-primary"
              data-testid={`link-starter-away-${cardId}`}
            >
              {game.probables.away.name} <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
          {!isHistorical && game.probables?.home && (
            <button
              type="button"
              onClick={() => navigate(`/players?id=${game.probables?.home?.player_id}`)}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-primary"
              data-testid={`link-starter-home-${cardId}`}
            >
              {game.probables.home.name} <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
          {explainTerms && (
            <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground">
              <CircleHelp className="h-3.5 w-3.5" aria-hidden="true" /> Model values are estimates
            </span>
          )}
        </div>
      </div>

      {detailLevel !== "compact" && (
      <details open={contextOpen} onToggle={(event) => setContextOpen(event.currentTarget.open)} className="game-card-disclosure">
        <summary className="disclosure-summary" data-testid={`button-toggle-context-${cardId}`}>
          <span className="inline-flex items-center gap-2"><Info className="h-4 w-4" aria-hidden="true" /> Explanation and context</span>
          <ChevronDown className="h-4 w-4 disclosure-chevron" aria-hidden="true" />
        </summary>
        <div className="disclosure-content">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="data-tile">
              <span className="eyebrow">Probability basis</span>
              <strong>{game.model_prob_home == null ? "Unavailable" : `${formatProb(1 - game.model_prob_home)} away · ${formatProb(game.model_prob_home)} home`}</strong>
              <span className="text-xs text-muted-foreground">Season team inputs through the current feed.</span>
            </div>
            <div className="data-tile">
              <span className="eyebrow">Starter adjustment</span>
              <strong>{hasAdjustment ? `${formatProb(1 - game.adj_prob!)} away · ${formatProb(game.adj_prob)} home` : "Not available"}</strong>
              <span className="text-xs text-muted-foreground">
                {hasAdjustment ? "A separate view blends probable-starter inputs." : "No probable-starter adjustment was returned."}
              </span>
            </div>
          </div>
          {(game.flags?.length || 0) > 0 && (
            <div className="mt-4 rounded-xl border border-warning/25 bg-warning/5 p-3">
              <div className="eyebrow text-warning">Context only · does not move a price</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {game.flags?.map((flag, index) => (
                  <span key={`${flag.player_id}-${index}`} className="context-chip">
                    {flag.team}: {flag.player} · {flag.status}
                  </span>
                ))}
              </div>
            </div>
          )}
          {game.adj_detail?.method && (
            <p className="mt-3 text-xs leading-5 text-muted-foreground">{game.adj_detail.method}</p>
          )}
        </div>
      </details>
      )}

      {detailLevel !== "compact" && (
      <details open={advancedOpen} onToggle={(event) => setAdvancedOpen(event.currentTarget.open)} className="game-card-disclosure game-card-advanced">
        <summary className="disclosure-summary" data-testid={`button-toggle-advanced-${cardId}`}>
          <span className="inline-flex items-center gap-2"><span className="receipt-mark" aria-hidden="true">∑</span> Advanced numbers and receipts</span>
          <ChevronDown className="h-4 w-4 disclosure-chevron" aria-hidden="true" />
        </summary>
        <div className="disclosure-content">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="data-tile"><span className="eyebrow">Season fair · away</span><strong>{isPartial ? "Unavailable" : formatOdds(game.fair_lines.away)}</strong></div>
            <div className="data-tile"><span className="eyebrow">Season fair · home</span><strong>{isPartial ? "Unavailable" : formatOdds(game.fair_lines.home)}</strong></div>
            <div className="data-tile"><span className="eyebrow">Adjusted fair · away</span><strong>{formatOdds(game.adj_fair_lines?.away)}</strong></div>
            <div className="data-tile"><span className="eyebrow">Adjusted fair · home</span><strong>{formatOdds(game.adj_fair_lines?.home)}</strong></div>
          </div>
          {game.away_inputs && game.home_inputs ? (
            <div className="mt-4 rounded-xl border border-border bg-background/60 p-3">
              <div className="eyebrow">Verified model inputs</div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground sm:grid-cols-4">
                <span>A OBP <b className="text-foreground">{inputValue(game.away_inputs.obp)}</b></span>
                <span>A SLG <b className="text-foreground">{inputValue(game.away_inputs.slg)}</b></span>
                <span>H OBP <b className="text-foreground">{inputValue(game.home_inputs.obp)}</b></span>
                <span>H SLG <b className="text-foreground">{inputValue(game.home_inputs.slg)}</b></span>
              </div>
            </div>
          ) : (
            <div className="mt-4 rounded-xl border border-warning/25 bg-warning/5 p-3 text-sm text-warning">
              Advanced model inputs are not available for this game.
            </div>
          )}
          {advancedOpen && priceCheckState === "available" && (
            <div className="mt-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="eyebrow">Manual price check</span>
                <span className="text-xs text-muted-foreground">Enter the book price you actually have.</span>
              </div>
              <EdgeFinder
                teamAStats={game.away_inputs}
                teamALabel={game.away_name || game.away}
                activeSlateGame={game}
                deferUntilBookLine
              />
            </div>
          )}
          {priceCheckState === "in-progress" && (
            <p className="mt-4 rounded-xl border border-border bg-muted/30 p-3 text-sm text-muted-foreground" data-testid={`price-check-unavailable-${cardId}`}>
              This game is in progress. Manual price checks are pregame research only, so no verdict is shown.
            </p>
          )}
          {priceCheckState === "final" && (
            <p className="mt-4 rounded-xl border border-border bg-muted/30 p-3 text-sm text-muted-foreground" data-testid={`price-check-unavailable-${cardId}`}>
              This game is final. Manual price checks are unavailable after the game has ended.
            </p>
          )}
          {isNonPlayableGame(game) && (
            <p className="mt-4 rounded-xl border border-warning/25 bg-warning/5 p-3 text-sm text-warning" data-testid={`price-check-unavailable-${cardId}`}>
              This game is postponed or suspended. Manual price checks are unavailable until the schedule provides a playable game.
            </p>
          )}
          {isPartial && (
            <p className="mt-4 text-sm text-muted-foreground">Receipts will appear here when the complete pricing inputs are available.</p>
          )}
        </div>
      </details>
      )}
    </article>
  );
}