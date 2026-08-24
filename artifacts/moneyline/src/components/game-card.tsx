import { useEffect, useId, useMemo, useState } from "react";
import {
  ArrowLeftRight,
  ChevronDown,
  CircleCheck,
  CircleDot,
  CircleHelp,
  CircleSlash,
  ExternalLink,
  Info,
  Lock,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { useLocation } from "wouter";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { formatOdds, formatProb, SlateGame } from "@/components/slate-rail";
import { DetailLevel } from "./presentation-preferences";
import { evaluationStatus, isNonPlayableGame, manualPriceCheckState } from "@/lib/game-status";
import { isMalformedMoneyline, validMoneyline } from "@/lib/moneyline";
import {
  useEvaluate,
  useTeamsLive,
  type EvaluateResponse,
  type EvaluateSide,
  type EvaluateThresholds,
  type VerdictCode,
  type VerdictFlag,
} from "@/api";

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

/** Verdict presentation. Icon + sentence-case text in every state: colour is
 *  never the only carrier of the verdict. */
const VERDICT_DISPLAY: Record<VerdictCode, { label: string; className: string; Icon: LucideIcon }> = {
  BET_CANDIDATE: { label: "Bet candidate", className: "game-card-verdict-candidate", Icon: CircleCheck },
  MARGINAL_VALUE: { label: "Marginal value", className: "game-card-verdict-marginal", Icon: CircleDot },
  NO_VALUE: { label: "No value", className: "game-card-verdict-none", Icon: CircleSlash },
  AVOID_AT_THIS_PRICE: { label: "Avoid at this price", className: "game-card-verdict-avoid", Icon: TriangleAlert },
  INSUFFICIENT_DATA: { label: "Insufficient data", className: "game-card-verdict-data", Icon: CircleHelp },
};

const FROZEN_DISPLAY = { label: "Verdict frozen", className: "game-card-verdict-frozen", Icon: Lock };

function signed(value: number | null | undefined, digits = 1) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

/** Data-status chips. These are a DATA state, not a judgment, so they live in
 *  their own row next to the existing model/starter chips — never inside the
 *  verdict pill. */
function dataStatusChips(
  evaluation: EvaluateResponse,
  labels: { home: string; away: string },
  /** null suppresses the starters chip — the card already says the same thing. */
  startersChipLabel: string | null,
): { key: string; label: string; tone: string }[] {
  const { home, away } = evaluation.sides;
  const has = (flag: VerdictFlag) => home.flags.includes(flag) || away.flags.includes(flag);
  const chips: { key: string; label: string; tone: string }[] = [];

  if (has("no_price")) {
    const missing = [
      home.flags.includes("no_price") ? labels.home : null,
      away.flags.includes("no_price") ? labels.away : null,
    ].filter((value): value is string => value != null);
    chips.push({
      key: "no_price",
      label: missing.length === 2 ? "No book price entered" : `No ${missing[0]} price entered`,
      tone: "status-label-neutral",
    });
  }
  // Two different facts, two different chips. `early_season` says the season
  // is young; `gp_unavailable` says we could not find out. The second used to
  // have no chip at all, and its intended copy sat in an unreachable branch of
  // the first — `early_season` can only fire when both counts are present.
  if (has("gp_unavailable")) {
    chips.push({
      key: "gp_unavailable",
      label: "Games played unavailable",
      tone: "status-label-warning",
    });
  }
  if (has("early_season")) {
    chips.push({
      key: "early_season",
      label: `Under ${evaluation.thresholds.gp_hard_floor} games played`,
      tone: "status-label-warning",
    });
  }
  // Under the hard floor the season chip already says so; adding "under 60"
  // beneath "under 30" is noise that reads like two separate problems.
  if (has("small_sample") && !has("early_season")) {
    chips.push({
      key: "small_sample",
      label: `Under ${evaluation.thresholds.gp_small_sample} games played`,
      tone: "status-label-warning",
    });
  }
  if (has("stale")) {
    chips.push({ key: "stale", label: "Price may be stale", tone: "status-label-warning" });
  }
  // The engine treats a null adjusted chance as unconfirmed starters, so this
  // flag also fires on games whose starters ARE named. The caller decides the
  // wording, and suppresses it entirely when the card already says the same
  // thing — one fact, two chips reads as two problems.
  if (has("starters_unconfirmed") && startersChipLabel) {
    chips.push({ key: "starters_unconfirmed", label: startersChipLabel, tone: "status-label-neutral" });
  }
  if (has("prices_disagree")) {
    chips.push({
      key: "prices_disagree",
      label: "Season and adjusted prices disagree",
      tone: "status-label-warning",
    });
  }
  return chips;
}

/** The published rubric, rendered from the payload rather than restated in the
 *  frontend, so a reader audits the numbers the verdict was actually produced
 *  under. */
function rubricRows(t: EvaluateThresholds): [string, string][] {
  return [
    ["Bet candidate", `EV ≥ ${signed(t.candidate_ev * 100)} per 100 and edge ≥ ${signed(t.candidate_edge * 100)} pts`],
    ["Marginal value", `Positive EV with edge ≥ ${signed(t.no_value_edge * 100)} pts`],
    ["No value", `EV at or below 0, or edge under ${signed(t.no_value_edge * 100)} pts`],
    ["Avoid at this price", `EV ≤ ${signed(t.avoid_ev * 100)} per 100`],
    [
      "Signal gap",
      `edge ÷ σ, σ = ${t.sigma} · Strong ≥ ${t.signal_strong_gap}, Moderate ≥ ${t.signal_moderate_gap}`,
    ],
    [
      "Sample gates",
      `Refuse under ${t.gp_hard_floor} GP · small sample under ${t.gp_small_sample} GP · moderate under ${t.gp_moderate} GP`,
    ],
    ["Price staleness", `${t.stale_seconds} s (dormant: prices here are typed by you, not fed)`],
    [
      "Volatility bands",
      `Lower at ${t.volatility_lower_price} or shorter · Higher at +${t.volatility_higher_price} or longer`,
    ],
  ];
}

function SideValueTile({ label, side }: { label: string; side: EvaluateSide }) {
  const rows: [string, string][] = [
    ["Your price", side.price == null ? "Not entered" : formatOdds(side.price)],
    ["Model chance", formatProb(side.p_eval)],
    ["Fair price", formatOdds(side.fair_line)],
    ["Breakeven", side.breakeven == null ? "Not computed — no price" : formatProb(side.breakeven)],
    ["Edge", side.edge_pts == null ? "Not computed — no price" : `${signed(side.edge_pts)} pts`],
    ["EV per 100", side.ev_per_100 == null ? "Not computed — no price" : signed(side.ev_per_100)],
    [
      "Signal",
      side.signal == null
        ? "None issued"
        : `${side.signal}${side.signal_provisional ? " · provisional, not yet graded" : ""}`,
    ],
    ["Volatility", side.volatility ?? "Not computed — no price"],
    ["Uncertainty", side.uncertainty],
    ["Evaluated on", side.p_basis === "adj" ? "Starter-adjusted chance" : "Season chance"],
  ];
  return (
    <div className="data-tile">
      <span className="eyebrow">{label}</span>
      <strong>{side.verdict ? VERDICT_DISPLAY[side.verdict].label : "No verdict"}</strong>
      <dl className="mt-1 grid gap-1 text-xs text-muted-foreground">
        {rows.map(([term, value]) => (
          <div key={term} className="flex items-baseline justify-between gap-3">
            <dt>{term}</dt>
            <dd className="tabular-nums text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      {side.verdict_reason && (
        <span className="mt-1 font-mono text-[10px] text-muted-foreground">reason: {side.verdict_reason}</span>
      )}
      {side.basis_note && <p className="mt-2 text-xs leading-5 text-warning">{side.basis_note}</p>}
    </div>
  );
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
  const [priceHome, setPriceHome] = useState("");
  const [priceAway, setPriceAway] = useState("");
  const fieldId = useId().replace(/:/g, "");
  const isHistorical = Boolean(game.team && game.year);
  const isPartial = Boolean(game.pricing_error || game.model_prob_home == null || !game.fair_lines);
  const priceCheckState = manualPriceCheckState(game);
  const hasAdjustment = game.adj_prob != null && game.adj_fair_lines != null;
  const missingStarter = isMissingStarter(game);
  const status = titleCaseStatus(game.status);
  const cardId = game.game_pk || `${game.away}-${game.home}`;
  const awayLabel = game.away_name || game.away;
  const homeLabel = game.home_name || game.home;

  // Games played is not on slate rows; it comes from /api/teams-live, keyed by
  // the same B-Ref team code the slate uses. A code we cannot resolve passes
  // null and lets the honest early-season gate fire — never a substituted guess.
  const teamsLive = useTeamsLive();
  const gamesPlayedByCode = useMemo(() => {
    const map = new Map<string, number>();
    for (const team of teamsLive.data?.teams ?? []) {
      if (typeof team.games_played === "number") map.set(team.team, team.games_played);
    }
    return map;
  }, [teamsLive.data]);

  const evaluation = useEvaluate();
  const priceHomeValue = validMoneyline(priceHome);
  const priceAwayValue = validMoneyline(priceAway);
  const priceHomeMalformed = isMalformedMoneyline(priceHome);
  const priceAwayMalformed = isMalformedMoneyline(priceAway);
  const modelProbHome = game.model_prob_home;
  const adjProbHome = game.adj_prob ?? null;
  const gpHome = gamesPlayedByCode.get(game.home) ?? null;
  const gpAway = gamesPlayedByCode.get(game.away) ?? null;
  const startersConfirmed = Boolean(game.probables?.away && game.probables?.home);
  const evalStatus = evaluationStatus(game);
  // Historical rows are excluded as well as partial ones: teams-live carries
  // this season's games played, which says nothing about a 2002 club.
  const canEvaluate = !isPartial && !isHistorical && modelProbHome != null && !teamsLive.isPending;

  useEffect(() => {
    if (!canEvaluate || modelProbHome == null) return;
    evaluation.mutate({
      p_season_home: modelProbHome,
      p_adj_home: adjProbHome,
      price_home: priceHomeValue,
      price_away: priceAwayValue,
      gp_home: gpHome,
      gp_away: gpAway,
      starters_confirmed: startersConfirmed,
      // price_age_s is deliberately omitted. Every price here is typed by the
      // user; synthesising an age would be a fabricated freshness claim.
      status: evalStatus,
    });
    // The mutation object is a fresh identity each render, so it stays out of
    // the dep list (same idiom as EdgeFinder).
  }, [
    canEvaluate,
    modelProbHome,
    adjProbHome,
    priceHomeValue,
    priceAwayValue,
    gpHome,
    gpAway,
    startersConfirmed,
    evalStatus,
  ]);

  const result = evaluation.data;
  const evaluationError = (evaluation.error as Error | null)?.message ?? null;

  // The endpoint returns a game-level NO_VALUE when neither side has a price,
  // because no side can clear the minimum edge. Printing "No value" over an
  // empty price box would be a judgment made without a price, so when BOTH
  // sides are gated the card shows the sides' own refusal instead.
  const bothSidesGated =
    result != null &&
    result.sides.home.verdict === "INSUFFICIENT_DATA" &&
    result.sides.away.verdict === "INSUFFICIENT_DATA";
  const noPriceEntered =
    bothSidesGated &&
    result!.sides.home.verdict_reason === "no_price" &&
    result!.sides.away.verdict_reason === "no_price";
  const displayVerdict: VerdictCode | null = result
    ? result.game.frozen
      ? null
      : bothSidesGated
        ? "INSUFFICIENT_DATA"
        : result.game.verdict
    : null;
  const verdictDisplay = result
    ? result.game.frozen
      ? FROZEN_DISPLAY
      : displayVerdict
        ? VERDICT_DISPLAY[displayVerdict]
        : null
    : null;
  const valueSideLabel = result?.game.side ? (result.game.side === "home" ? homeLabel : awayLabel) : null;
  const leanSideLabel = result?.game.lean_side ? (result.game.lean_side === "home" ? homeLabel : awayLabel) : null;
  const takeaway = noPriceEntered
    ? "No book price is entered yet, so there is no value call to make. The fair price above is the model's own number, not a bet signal."
    : (result?.game.takeaway ?? null);
  const startersChipLabel = missingStarter
    ? null // "Starter data incomplete" is already on the row.
    : hasAdjustment
      ? "Starters unconfirmed"
      : "No starter-adjusted chance";
  const statusChips = result
    ? dataStatusChips(result, { home: homeLabel, away: awayLabel }, startersChipLabel)
    : [];

  const showPriceRow = priceCheckState === "available";
  const priceUnavailableCopy =
    isHistorical || isPartial
      ? null
      : isNonPlayableGame(game)
        ? "This game is postponed or suspended. Manual price checks are unavailable until the schedule provides a playable game."
        : priceCheckState === "final"
          ? "This game is final. Manual price checks are unavailable after the game has ended."
          : priceCheckState === "in-progress"
            ? "This game is in progress. Manual price checks are pregame research only, so no verdict is shown."
            : null;

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
            {/* Verdict slot. Sits BELOW the lean line, never replacing it: the
                lean and the value side are different questions, and showing
                them adjacently is what makes a divergence legible. */}
            {canEvaluate && (
              <div className="mt-3" data-testid={`verdict-slot-${cardId}`}>
                {verdictDisplay && result ? (
                  <>
                    <span
                      className={cn("game-card-verdict", verdictDisplay.className)}
                      aria-label={
                        valueSideLabel
                          ? `Verdict: ${verdictDisplay.label} on ${valueSideLabel}`
                          : `Verdict: ${verdictDisplay.label} for ${awayLabel} at ${homeLabel}`
                      }
                      data-testid={`verdict-${cardId}`}
                    >
                      <verdictDisplay.Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span>
                        {verdictDisplay.label}
                        {valueSideLabel ? ` · ${valueSideLabel}` : ""}
                      </span>
                    </span>
                    {takeaway && <p className="game-card-takeaway">{takeaway}</p>}
                    {result.game.lean_differs_from_value && valueSideLabel && leanSideLabel && (
                      <p className="game-card-verdict-conflict" data-testid={`verdict-conflict-${cardId}`}>
                        <ArrowLeftRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                        <span>
                          The lean is not the value side. The model leans {leanSideLabel}; at these prices the value
                          is on {valueSideLabel}.
                        </span>
                      </p>
                    )}
                    {result.game.avoid_note && result.game.side && (
                      <p className="mt-2 flex items-start gap-2 text-xs leading-5 text-destructive">
                        <TriangleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                        <span>Avoid: {result.game.avoid_note}</span>
                      </p>
                    )}
                  </>
                ) : evaluationError ? (
                  <p className="text-sm text-warning" data-testid={`verdict-error-${cardId}`}>
                    The verdict service did not answer, so no verdict is shown ({evaluationError}).
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">Checking both sides for value…</p>
                )}
              </div>
            )}
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
          {statusChips.map((chip) => (
            <span key={chip.key} className={cn("status-label", chip.tone)} data-testid={`flag-${chip.key}-${cardId}`}>
              {chip.label}
            </span>
          ))}
        </div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {isPartial
            ? "The schedule is available, but this game does not have a complete model price yet."
            : "This is a model estimate, not a sportsbook quote. Enter the book prices you actually have and the verdict above scores both sides; with no price it stays an explicit refusal rather than a guess."}
        </p>
        {showPriceRow ? (
          <>
            <div className="game-card-price-row">
              <div className="game-card-price-field">
                <label htmlFor={`${fieldId}-away`} className="eyebrow">
                  Book price · {awayLabel}
                </label>
                <Input
                  id={`${fieldId}-away`}
                  value={priceAway}
                  onChange={(event) => setPriceAway(event.target.value)}
                  placeholder="+120"
                  className={cn("h-9 font-mono", priceAwayMalformed && "border-destructive text-destructive focus:border-destructive")}
                  data-testid={`input-price-away-${cardId}`}
                />
              </div>
              <div className="game-card-price-field">
                <label htmlFor={`${fieldId}-home`} className="eyebrow">
                  Book price · {homeLabel}
                </label>
                <Input
                  id={`${fieldId}-home`}
                  value={priceHome}
                  onChange={(event) => setPriceHome(event.target.value)}
                  placeholder="-110"
                  className={cn("h-9 font-mono", priceHomeMalformed && "border-destructive text-destructive focus:border-destructive")}
                  data-testid={`input-price-home-${cardId}`}
                />
              </div>
            </div>
            {(priceAwayMalformed || priceHomeMalformed) && (
              <p role="alert" className="mt-2 text-xs text-destructive">
                An American price must be −100 or lower, or +100 or higher.
              </p>
            )}
          </>
        ) : (
          priceUnavailableCopy && (
            <p
              className="mt-3 rounded-xl border border-border bg-muted/30 p-3 text-sm text-muted-foreground"
              data-testid={`price-check-unavailable-${cardId}`}
            >
              {priceUnavailableCopy}
            </p>
          )
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {!isHistorical && game.probables?.away && (
            <button
              type="button"
              onClick={() => navigate(`/research/players?id=${game.probables?.away?.player_id}`)}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-primary"
              data-testid={`link-starter-away-${cardId}`}
            >
              {game.probables.away.name} <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
          {!isHistorical && game.probables?.home && (
            <button
              type="button"
              onClick={() => navigate(`/research/players?id=${game.probables?.home?.player_id}`)}
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
          {result && (
            <p className="mt-4 text-xs leading-5 text-muted-foreground">
              The lean is what the model thinks and does not depend on any price. The value side is what the prices you
              entered make worth backing. They answer different questions and can point at different teams — the full
              rubric is under “Advanced numbers and receipts”.
            </p>
          )}
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
          {result && (
            <div className="mt-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="eyebrow">Value check · both sides</span>
                <span className="text-xs text-muted-foreground">{result.sample.label}</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <SideValueTile label={awayLabel} side={result.sides.away} />
                <SideValueTile label={homeLabel} side={result.sides.home} />
              </div>
              <details className="mt-4 rounded-xl border border-border bg-background/50 p-3">
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                  Published rubric · the thresholds this verdict was decided under
                </summary>
                <dl className="mt-3 grid gap-2 text-xs">
                  {rubricRows(result.thresholds).map(([term, detail]) => (
                    <div key={term} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
                      <dt className="font-medium text-foreground sm:min-w-[148px]">{term}</dt>
                      <dd className="text-muted-foreground">{detail}</dd>
                    </div>
                  ))}
                </dl>
                {result.thresholds.notes && (
                  <ul className="mt-3 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-foreground">
                    {Object.entries(result.thresholds.notes).map(([key, note]) => (
                      <li key={key}>{note}</li>
                    ))}
                  </ul>
                )}
                {result.model_version && (
                  <p className="mt-3 font-mono text-[11px] text-muted-foreground">
                    Model version: {result.model_version}
                  </p>
                )}
                {result.caveat && (
                  <p className="mt-2 border-l-2 border-muted pl-2 text-[11px] italic leading-5 text-muted-foreground">
                    {result.caveat}
                  </p>
                )}
              </details>
            </div>
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
