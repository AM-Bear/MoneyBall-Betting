import { BankrollPanel } from "@/components/bankroll-backtest";
import { LiveRecordPanel } from "@/components/live-record";
import { TrackRecordPanel } from "@/components/track-record";
import { HistoricalBanner } from "@/components/record/historical-banner";
import { ResearchTag } from "@/components/research-tag";
import {
  StructuredData,
  trackRecordStructuredData,
} from "@/lib/structured-data";

export default function TrackRecordPage() {
  return (
    <>
      <StructuredData data={trackRecordStructuredData} />
      <main className="page-wrap">
        <div className="page-heading">
          <div>
            <div className="eyebrow">Evidence, separated by purpose</div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Track record</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Live grading, starter-adjusted grading, paper parlays, and historical simulation are different views.
              Keeping them separate makes the record easier to interpret.
            </p>
          </div>
        </div>
        <div className="record-callout">
          <span className="status-label status-label-neutral">Public record</span>
          <span>Live picks are graded from the existing ledger. Historical backtests are simulations, not live performance.</span>
        </div>

        {/* Live first: it is the only section that grades picks the desk made
            without knowing the answer. Historical follows, under its banner. */}
        <section className="mt-6" aria-label="Live graded record">
          <LiveRecordPanel />
        </section>

        <section className="mt-8" aria-label="Historical tests">
          <HistoricalBanner />
          <div className="grid gap-6 xl:grid-cols-2">
            <TrackRecordPanel />
            <BankrollPanel />
          </div>
        </section>

        <ResearchTag />
      </main>
    </>
  );
}
