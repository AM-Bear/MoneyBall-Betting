import {
  formatPct,
  formatUnits,
  meanInterval,
  picksToDetect,
  wilsonInterval,
  type RecordEntry,
} from "./record-stats";

interface Props {
  entries: RecordEntry[];
  wins: number;
  losses: number;
  graded: number;
  breakEvenRate: number;
  sampleLabel: string | null;
  trackingSince: string | null;
}

/** "What this proves" — the honest reading of the numbers above it.
 *
 * Every claim on this card is derived from the payload in view and shows its
 * n. Where the sample cannot support a claim the card says so instead of
 * softening the wording around a number it cannot stand behind.
 */
export function ProofStatement({
  entries,
  wins,
  losses,
  graded,
  breakEvenRate,
  sampleLabel,
  trackingSince,
}: Props) {
  const decidedUnits = entries
    .filter((e) => e.result === "WIN" || e.result === "LOSS")
    .map((e) => (e.units_pnl == null ? 0 : e.units_pnl));

  const rate = wilsonInterval(wins, graded);
  const perPick = meanInterval(decidedUnits);
  // A flat-stake record swings by roughly ±1.96·sd·√n units on luck alone.
  // 1.96, not 1: every other interval in this card is 95%, and mixing a
  // one-sigma band in among them would understate the swing by a third while
  // looking like the same kind of number.
  const luckSwing = perPick ? 1.96 * perPick.sd * Math.sqrt(perPick.n) : null;
  const at5 = perPick ? picksToDetect(0.05, perPick.sd) : null;
  const at3 = perPick ? picksToDetect(0.03, perPick.sd) : null;

  return (
    <div className="border border-border bg-background p-4 font-mono flex flex-col gap-3">
      <div className="moneyline-section-header">WHAT THIS PROVES</div>

      {graded === 0 ? (
        <p className="text-xs leading-5 text-muted-foreground font-sans">
          Nothing yet — no pick has been decided.
          {trackingSince ? ` Tracking since ${trackingSince}.` : ""} A hit rate
          needs decided picks; pending and VOID picks are not one.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase text-muted-foreground">
                Hit rate, 95% interval
              </span>
              <span className="text-lg font-bold tracking-tighter">
                {rate
                  ? `${formatPct(rate.low)} – ${formatPct(rate.high)}`
                  : "—"}
              </span>
              <span className="text-[10px] text-muted-foreground leading-4">
                {rate
                  ? `${rate.method} · n = ${rate.n} decided picks (VOID excluded) · point estimate ${formatPct(rate.point)}`
                  : "no decided picks"}
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase text-muted-foreground">
                Units per pick, 95% interval
              </span>
              <span className="text-lg font-bold tracking-tighter">
                {perPick
                  ? `${formatUnits(perPick.low, 3)} – ${formatUnits(perPick.high, 3)}`
                  : "—"}
              </span>
              <span className="text-[10px] text-muted-foreground leading-4">
                {perPick
                  ? `${perPick.method} · n = ${perPick.n} · sd = ${perPick.sd.toFixed(3)}u`
                  : `n = ${decidedUnits.length} — an interval needs at least two decided picks`}
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-2 text-xs leading-5 text-muted-foreground font-sans border-t border-border pt-3">
            <p>
              {wins}–{losses} on {graded} decided picks. Break-even at the −110
              fallback is {formatPct(breakEvenRate, 1)}
              {rate && rate.low > breakEvenRate
                ? " — the whole interval clears it. That is not an edge claim: no book price is recorded against these picks, and the model only ever backs its own favourite, so a hit rate above the fallback is what that selection produces, not proof it beat a market."
                : rate && rate.high < breakEvenRate
                  ? " — the whole interval sits below it."
                  : " — the interval straddles it, so this record does not yet separate skill from noise."}
            </p>
            {luckSwing !== null && (
              <p>
                Over {perPick?.n} flat one-unit picks, luck alone moves the
                running total by about ±{luckSwing.toFixed(1)}u at 95%
                (1.96 ×&nbsp;sd ×&nbsp;√n). Any total inside that band is
                indistinguishable from break-even betting — the null here is
                the {formatPct(breakEvenRate, 1)} fallback, not a 50/50 coin.
              </p>
            )}
            {at5 !== null && at3 !== null && Number.isFinite(at5) && (
              <p>
                To show a 5% return per pick with 95% confidence would take
                roughly {at5.toLocaleString()} decided picks; a 3% return,
                roughly {at3.toLocaleString()}. Derived as n = (1.96 × sd / r)²
                using this ledger's own sd of {perPick?.sd.toFixed(3)}u — not a
                published figure.
              </p>
            )}
            <p>
              What it does not prove: this is every game at a flat one unit
              booked at −110. MONEYLINE ingests no odds feed, so no pick here
              was graded against a price anyone was actually offered, and none
              of this is closing-line value.
              {sampleLabel === "SMALL SAMPLE"
                ? " The ledger is still labelled SMALL SAMPLE (under 100 decided picks)."
                : ""}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
