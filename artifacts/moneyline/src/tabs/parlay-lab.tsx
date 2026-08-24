import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "wouter";
import { useParlayLog, useParlayPrice, useSlate, ApiError } from "@/api";
import { formatOdds, formatProb } from "@/components/slate-rail";
import { ResearchTag } from "@/components/research-tag";
import { PanelSkeleton } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Side = "home" | "away";
interface Leg {
  gamePk: string;
  side: Side;
}

const STANDARD_LEG_DECIMAL = 1 + 100 / 110; // −110

function standardBookLine(n: number): number {
  const dec = Math.pow(STANDARD_LEG_DECIMAL, n);
  return Math.round((dec - 1) * 100);
}

function parseLegs(raw: string | null): Leg[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((part) => {
      const [gamePk, side] = part.split(":");
      return gamePk && (side === "home" || side === "away") ? { gamePk, side } : null;
    })
    .filter((l): l is Leg => l !== null)
    .slice(0, 6);
}

function sideProb(game: any, side: Side): number | null {
  if (game.model_prob_home == null) return null;
  return side === "home" ? game.model_prob_home : 1 - game.model_prob_home;
}

export default function ParlayLabTab() {
  const slate = useSlate();
  const [params, setParams] = useSearchParams();
  const legs = useMemo(() => parseLegs(params.get("legs")), [params]);
  const [bookRaw, setBookRaw] = useState(params.get("book") || "");
  const [tooMany, setTooMany] = useState(false);

  const price = useParlayPrice();
  const logSlip = useParlayLog();

  const games: any[] = slate.data?.mode === "live" ? slate.data.games : [];
  const bookOdds = /^[+-]?\d+$/.test(bookRaw.trim()) ? parseInt(bookRaw.trim(), 10) : null;
  const bookInvalid = bookRaw.trim() !== "" && (bookOdds === null || bookOdds === 0 || Math.abs(bookOdds) < 100);

  const setLegs = (next: Leg[]) => {
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      if (next.length) p.set("legs", next.map((l) => `${l.gamePk}:${l.side}`).join(","));
      else p.delete("legs");
      if (bookRaw.trim()) p.set("book", bookRaw.trim());
      return p;
    });
  };

  const toggleLeg = (gamePk: string, side: Side) => {
    setTooMany(false);
    const existing = legs.find((l) => l.gamePk === gamePk);
    if (existing?.side === side) {
      setLegs(legs.filter((l) => l.gamePk !== gamePk));
    } else if (existing) {
      setLegs(legs.map((l) => (l.gamePk === gamePk ? { gamePk, side } : l)));
    } else if (legs.length >= 6) {
      setTooMany(true);
    } else {
      setLegs([...legs, { gamePk, side }]);
    }
  };

  useEffect(() => {
    if (legs.length < 2 || bookInvalid) {
      price.reset();
      return;
    }
    const t = setTimeout(() => {
      price.mutate({ legs, book_odds: bookOdds });
    }, 300);
    return () => clearTimeout(t);
  }, [JSON.stringify(legs), bookOdds, bookInvalid]); // eslint-disable-line react-hooks/exhaustive-deps

  const result = price.data;
  const priceError = price.error instanceof ApiError ? price.error : null;
  const correlated = priceError?.code === "correlated_legs";

  if (slate.isLoading)
    return (
      <div className="max-w-7xl mx-auto"><PanelSkeleton /></div>
    );

  if (slate.data?.mode !== "live")
    return (
      <div className="max-w-7xl mx-auto flex flex-col gap-4">
        <h1 className="moneyline-section-header w-1/3">PARLAY CHECK</h1>
        <div className="moneyline-panel items-center justify-center text-center p-10 font-mono">
          <div className="text-warning text-sm uppercase tracking-widest mb-2">NO LIVE SLATE</div>
          <div className="text-xs text-muted-foreground max-w-sm">
            Parlays are built from today's priced games. The slate feed is in historical mode — nothing to combine.
          </div>
        </div>
        <ResearchTag />
      </div>
    );

  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="moneyline-section-header w-full sm:w-1/3">PARLAY CHECK · 2–6 LEGS FROM TODAY'S SLATE</h1>
        <div className="font-mono text-[10px] text-muted-foreground">{result?.price_basis || "SEASON MODEL PROBABILITIES (NOT ADJ)."}</div>
      </div>
      <div className="border border-border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
        Build a paper combination only when you have a specific research question. This check reports combined probability and fair odds under an independence assumption; it does not recommend a slip or provide sportsbook prices.
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Leg picker */}
        <div className="moneyline-panel lg:col-span-1 flex flex-col gap-2">
          <h2 className="moneyline-section-header mb-1">TODAY'S GAMES — PICK A SIDE</h2>
          {tooMany && (
            <div className="border border-destructive/40 bg-destructive/10 px-2 py-1 font-mono text-[10px] text-destructive">
              SIX LEGS MAX — THE VIG COMPOUNDS FAST ENOUGH ALREADY
            </div>
          )}
          <div className="flex flex-col gap-2 overflow-y-auto">
            {games.map((g) => {
              const sel = legs.find((l) => l.gamePk === String(g.game_pk));
              return (
                <div key={g.game_pk} className="border border-border bg-background p-2 flex flex-col gap-1 font-mono text-xs">
                  <div className="flex justify-between text-[9px] text-muted-foreground uppercase">
                    <span>{g.time_et}</span>
                    <span>{g.status}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1">
                    {(["away", "home"] as Side[]).map((side) => {
                      const prob = sideProb(g, side);
                      const active = sel?.side === side;
                      return (
                        <button
                          key={side}
                          disabled={prob == null}
                          onClick={() => toggleLeg(String(g.game_pk), side)}
                          aria-pressed={active}
                          className={cn(
                            "border px-2 py-1.5 flex justify-between items-center transition-colors tabular-nums",
                            active
                              ? "border-primary bg-primary/15 text-primary"
                              : "border-border hover:border-primary/50",
                            prob == null && "opacity-40 cursor-not-allowed",
                          )}
                        >
                          <span className="font-bold">{side === "away" ? g.away : `@${g.home}`}</span>
                          <span>{formatProb(prob)}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Slip + verdict */}
        <div className="moneyline-panel lg:col-span-2 flex flex-col gap-3">
          <h2 className="moneyline-section-header">THE SLIP</h2>

          {legs.length === 0 ? (
            <div className="flex-1 flex items-center justify-center font-mono text-sm text-muted-foreground p-8">
              PICK 2–6 SIDES FROM TODAY'S SLATE
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-1 font-mono text-xs">
                {legs.map((l) => {
                  const g = games.find((x) => String(x.game_pk) === l.gamePk);
                  const leg = result?.legs?.find((rl: any) => rl.game_pk === l.gamePk);
                  const team = l.side === "home" ? g?.home : g?.away;
                  const opp = l.side === "home" ? g?.away : g?.home;
                  return (
                    <div key={l.gamePk} className="flex items-center justify-between border border-border bg-background px-2 py-1.5">
                      <span>
                        <span className="font-bold">{team}</span>
                        <span className="text-muted-foreground"> over {opp}</span>
                      </span>
                      <span className="flex items-center gap-3 tabular-nums">
                        <span>{formatProb(leg?.probability ?? sideProb(g, l.side))}</span>
                        <span className="text-primary">{leg ? formatOdds(leg.fair_line) : ""}</span>
                        <button
                          onClick={() => toggleLeg(l.gamePk, l.side)}
                          aria-label={`Remove ${team} over ${opp} from parlay`}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          ✕
                        </button>
                      </span>
                    </div>
                  );
                })}
              </div>

              {legs.length < 2 && (
                <div className="font-mono text-[10px] text-muted-foreground">ADD AT LEAST ONE MORE LEG — A PARLAY NEEDS TWO.</div>
              )}

              <div className="flex items-center gap-2 font-mono text-xs">
                <label htmlFor="book-odds" className="text-[10px] uppercase text-muted-foreground">Book parlay odds</label>
                <Input
                  id="book-odds"
                  value={bookRaw}
                  onChange={(e) => setBookRaw(e.target.value)}
                  placeholder={`+${standardBookLine(Math.max(legs.length, 2))}`}
                  className={cn("h-8 w-28 font-mono", bookInvalid && "border-destructive text-destructive")}
                />
                {bookInvalid && <span className="text-[10px] text-destructive">AMERICAN LINE ≤ −100 OR ≥ +100</span>}
              </div>

              {correlated && (
                <div role="alert" className="border border-destructive/50 bg-destructive/10 p-3 font-mono text-xs text-destructive">
                  {priceError?.message}
                </div>
              )}
              {priceError && !correlated && (
                <div role="alert" className="border border-destructive/40 bg-destructive/5 p-3 font-mono text-xs text-destructive">
                  {priceError.message}
                </div>
              )}

              {price.isPending && !result && (
                <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
                  <Loader2 className="w-3 h-3 animate-spin" /> PRICING…
                </div>
              )}

              {result && !correlated && (
                <div className="flex flex-col gap-3" aria-live="polite">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-center font-mono border-y border-border py-3">
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] text-muted-foreground uppercase">Combined Prob</span>
                      <span className="text-xl font-bold tabular-nums">{formatProb(result.combined_prob)}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] text-muted-foreground uppercase">Fair Odds</span>
                      <span className="text-xl font-bold tabular-nums text-primary">{formatOdds(result.fair_odds)}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] text-muted-foreground uppercase">Edge vs Book</span>
                      <span className={cn("text-xl font-bold tabular-nums", result.book?.edge_pp > 0 ? "text-success" : "text-destructive")}>
                        {result.book?.edge_pp != null ? `${result.book.edge_pp > 0 ? "+" : ""}${result.book.edge_pp.toFixed(1)}pp` : "—"}
                      </span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] text-muted-foreground uppercase">½-Kelly Stake</span>
                      <span className={cn("text-xl font-bold tabular-nums", result.book?.stake_label?.includes("NO EDGE") ? "text-destructive" : "text-success")}>
                        {result.book?.stake_label ?? "—"}
                      </span>
                    </div>
                  </div>

                  {result.book && (
                    <div className="font-mono text-[10px] text-muted-foreground">
                      BOOK {formatOdds(result.book.book_odds)} IMPLIES {formatProb(result.book.implied_prob)} · EV{" "}
                      {result.book.ev_per_unit > 0 ? "+" : ""}
                      {result.book.ev_per_unit?.toFixed(4)}u PER 1u STAKE
                    </div>
                  )}

                  {result.vig_comparison && (
                    <div className="border border-warning/30 bg-warning/5 p-3 font-mono text-xs flex flex-col gap-1">
                      <div className="text-[10px] uppercase tracking-widest text-warning">VIG COMPOUNDS — THE HOUSE TAKE, SIDE BY SIDE</div>
                      <div className="flex flex-wrap gap-4 tabular-nums">
                        <span>
                          {result.vig_comparison.legs} SINGLES AT {formatOdds(result.vig_comparison.leg_reference_line)}:{" "}
                          <span className="text-destructive">{result.vig_comparison.singles_house_take_pct}%</span> HOUSE TAKE
                        </span>
                        <span>
                          STANDARD PARLAY {formatOdds(result.vig_comparison.standard_book_parlay_line)} VS FAIR{" "}
                          {formatOdds(result.vig_comparison.fair_parlay_line)}:{" "}
                          <span className="text-destructive">{result.vig_comparison.parlay_house_take_pct}%</span> HOUSE TAKE
                        </span>
                      </div>
                    </div>
                  )}

                  <div className="font-mono text-[9px] text-muted-foreground">{result.independence_note}</div>

                  <div className="flex items-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs w-fit"
                      onClick={() => logSlip.mutate({ legs, book_odds: bookOdds })}
                      disabled={logSlip.isPending}
                    >
                      {logSlip.isPending && <Loader2 className="w-3 h-3 animate-spin mr-1" />}
                      LOG PAPER SLIP → LIVE RECORD
                    </Button>
                    {logSlip.isSuccess && (
                      <span className="font-mono text-[10px] text-success">
                        {logSlip.data?.already_logged ? "ALREADY LOGGED TODAY — ONE COPY KEPT" : "LOGGED — GRADES WITH FINALS IN THE LIVE RECORD"}
                      </span>
                    )}
                    {logSlip.isError && (
                      <span className="font-mono text-[10px] text-destructive">
                        {logSlip.error instanceof ApiError ? logSlip.error.message : "LOGGING FAILED"}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <ResearchTag />
    </div>
  );
}
