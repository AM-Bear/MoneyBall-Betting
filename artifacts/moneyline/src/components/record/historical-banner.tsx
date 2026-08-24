/** Persistent banner over the historical section.
 *
 * It is sticky, not a one-line header, so the qualifier stays on screen for as
 * long as any historical figure is: a backtested number that scrolls away from
 * its "not bettable" label reads as live performance, which it is not.
 */
export function HistoricalBanner() {
  return (
    <div className="sticky top-0 z-20 -mx-1 mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm backdrop-blur">
      <span className="status-label status-label-warning shrink-0">
        <span className="status-dot" />
        Historical
      </span>
      <span className="text-muted-foreground">
        Season-level, fitted on 1962–2001 and tested on 2002–2012. These are
        simulations on finished seasons, not live performance, and not bettable.
        Live grading is above.
      </span>
    </div>
  );
}
