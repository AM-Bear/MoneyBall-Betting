import type { SlateGame } from "@/components/slate-rail";

export type ManualPriceCheckState = "available" | "in-progress" | "final" | "unavailable";

export function isNonPlayableGame(game: SlateGame) {
  return /postponed|suspended|ppd/i.test(game.status || "");
}

export function isFinalGame(game: SlateGame) {
  return /final|completed|cancelled|game over/i.test(game.status || "");
}

export function isInProgressGame(game: SlateGame) {
  return /live|progress|delay|warmup|inning|game time/i.test(game.status || "") && !isFinalGame(game);
}

/** The normalized status enum `POST /api/evaluate` expects.
 *  Derived from the predicates above so there is exactly one place in the app
 *  that reads `game.status`; the backend deliberately owns no second regex. */
export function evaluationStatus(game: SlateGame): "scheduled" | "live" | "final" | "postponed" {
  if (isNonPlayableGame(game)) return "postponed";
  if (isFinalGame(game)) return "final";
  if (isInProgressGame(game)) return "live";
  return "scheduled";
}

export function manualPriceCheckState(game: SlateGame): ManualPriceCheckState {
  const isHistorical = Boolean(game.team && game.year);
  const isPartial = Boolean(game.pricing_error || game.model_prob_home == null || !game.fair_lines);

  if (isHistorical || isPartial) return "unavailable";
  if (isNonPlayableGame(game)) return "unavailable";
  if (isFinalGame(game)) return "final";
  if (isInProgressGame(game)) return "in-progress";
  return "available";
}