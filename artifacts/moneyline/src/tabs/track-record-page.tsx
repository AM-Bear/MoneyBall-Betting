import { BankrollPanel } from "@/components/bankroll-backtest";
import { LiveRecordPanel } from "@/components/live-record";
import { PanelError } from "@/components/layout";
import { TrackRecordPanel } from "@/components/track-record";
import { ResearchTag } from "@/components/research-tag";

export default function TrackRecordPage() {
  return (
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
      <section className="record-grid" aria-label="Record views">
        <TrackRecordPanel />
        <BankrollPanel />
      </section>
      <LiveRecordPanel />
      <ResearchTag />
    </main>
  );
}