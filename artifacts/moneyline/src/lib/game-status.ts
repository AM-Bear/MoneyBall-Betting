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

export function manualPriceCheckState(game: SlateGame): ManualPriceCheckState {
  const isHistorical = Boolean(game.team && game.year);
  const isPartial = Boolean(game.pricing_error || game.model_prob_home == null || !game.fair_lines);

  if (isHistorical || isPartial) return "unavailable";
  if (isNonPlayableGame(game)) return "unavailable";
  if (isFinalGame(game)) return "final";
  if (isInProgressGame(game)) return "in-progress";
  return "available";
}