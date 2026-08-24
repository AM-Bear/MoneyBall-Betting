import {
  BUCKET_MIN_N,
  BUCKET_READABLE_N,
  calibrationBuckets,
  decided,
  formatPct,
  type RecordEntry,
} from "./record-stats";

/** Live calibration: what the model said, against what happened.
 *
 * The bar is the realised hit rate; the tick is the mean model probability for
 * the same bucket. A calibrated bucket puts the tick inside the bar's end.
 *
 * Refusal rules, in order of strictness:
 *   n < 10  — no rate at all. A bar drawn from four picks looks like evidence.
 *   n < 30  — rate shown, de-emphasized, labelled "too small to read".
 *   n >= 30 — shown plainly.
 */
export function CalibrationChart({ entries }: { entries: RecordEntry[] }) {
  const buckets = calibrationBuckets(entries);
  const total = decided(entries).length;

  return (
    <div className="border border-border bg-background p-4 font-mono flex flex-col gap-3">
      <div className="moneyline-section-header">
        LIVE CALIBRATION
        <span className="text-[10px] normal-case tracking-normal">
          n = {total} decided
        </span>
      </div>

      {total === 0 ? (
        <p className="text-xs text-muted-foreground font-sans leading-5">
          No decided picks yet — there is nothing to calibrate against.
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-2" role="list">
            {buckets.map((bucket) => (
              <div
                key={bucket.label}
                role="listitem"
                className="flex items-center gap-3 text-xs"
              >
                <div className="w-20 shrink-0 text-muted-foreground">
                  {bucket.label}
                </div>
                <div className="relative h-2 flex-1 bg-muted">
                  {bucket.actualRate !== null && (
                    <div
                      className={`absolute left-0 top-0 h-full ${
                        bucket.readable ? "bg-primary" : "bg-primary/30"
                      }`}
                      style={{ width: `${bucket.actualRate * 100}%` }}
                    />
                  )}
                  {bucket.meanModelProbability !== null && (
                    <div
                      className="absolute top-[-2px] h-3 w-px bg-warning"
                      style={{ left: `${bucket.meanModelProbability * 100}%` }}
                      title={`model said ${formatPct(bucket.meanModelProbability)}`}
                    />
                  )}
                </div>
                <div className="w-40 shrink-0 text-right">
                  {bucket.actualRate === null ? (
                    <span className="text-muted-foreground text-[10px]">
                      n = {bucket.n} — too few to report a rate
                    </span>
                  ) : (
                    <>
                      <span
                        className={
                          bucket.readable
                            ? "font-bold"
                            : "font-bold text-muted-foreground"
                        }
                      >
                        {formatPct(bucket.actualRate, 0)}
                      </span>
                      <span className="ml-1 text-[10px] text-muted-foreground">
                        won {bucket.wins}/{bucket.n}
                      </span>
                      {!bucket.readable && (
                        <div className="text-[9px] uppercase text-warning">
                          too small to read
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>

          <p className="border-t border-border pt-3 text-[10px] leading-4 text-muted-foreground font-sans">
            Bar = share of that bucket's picks that won. Tick = the mean
            probability the model quoted in that bucket. Buckets under{" "}
            {BUCKET_READABLE_N} decided picks are de-emphasized; under{" "}
            {BUCKET_MIN_N} no rate is drawn at all. VOID and pending picks are
            excluded, as they are from the hit rate.
          </p>
        </>
      )}
    </div>
  );
}

/** Screen-reader and no-chart summary of the same buckets. */
export function CalibrationSummary({ entries }: { entries: RecordEntry[] }) {
  const buckets = calibrationBuckets(entries);
  const readable = buckets.filter((b) => b.actualRate !== null);
  if (readable.length === 0) {
    return (
      <p className="sr-only">
        Calibration: no bucket has enough decided picks to report a rate.
      </p>
    );
  }
  return (
    <p className="sr-only">
      Calibration by model probability.{" "}
      {readable
        .map(
          (b) =>
            `${b.label}: won ${b.wins} of ${b.n}, ${formatPct(b.actualRate as number, 0)}${
              b.readable ? "" : ", sample too small to read"
            }.`,
        )
        .join(" ")}
    </p>
  );
}
