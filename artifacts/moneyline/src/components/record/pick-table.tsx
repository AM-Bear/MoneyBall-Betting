import { useState } from "react";
import { Button } from "../ui/button";
import { Download } from "lucide-react";
import {
  LEDGER_CSV_COLUMNS,
  downloadCsv,
  formatPct,
  ledgerCsv,
  type Grade,
  type RecordEntry,
} from "./record-stats";

const GRADE_WORD: Record<string, string> = {
  WIN: "Win",
  LOSS: "Loss",
  VOID: "Void",
};

function GradeCell({ grade }: { grade: Grade }) {
  if (grade === null) {
    return (
      <span className="text-muted-foreground border border-dashed border-border px-1.5 py-0.5 text-[10px]">
        Pending
      </span>
    );
  }
  const tone =
    grade === "WIN"
      ? "border-success/40 bg-success/10 text-success"
      : grade === "LOSS"
        ? "border-destructive/40 bg-destructive/10 text-destructive"
        : "border-border bg-muted/30 text-muted-foreground";
  return (
    <span className={`border px-1.5 py-0.5 text-[10px] ${tone}`}>
      {GRADE_WORD[grade]}
    </span>
  );
}

/** Every pick in the ledger, newest first, with the export.
 *
 * Pending rows are shown outlined and are already excluded from the totals
 * above by `get_record()`; VOID rows show their 0 units rather than being
 * hidden, because a pick that was logged and then voided is part of the record.
 */
export function PickTable({
  entries,
  trackingSince,
}: {
  entries: RecordEntry[];
  trackingSince: string | null;
}) {
  const [showAll, setShowAll] = useState(false);
  const ordered = [...entries].reverse();
  const visible = showAll ? ordered : ordered.slice(0, 25);

  const exportCsv = () => {
    // Export the full ledger in ledger order, not the truncated view.
    downloadCsv(
      `moneyline_record_${trackingSince ?? "all"}.csv`,
      ledgerCsv(entries),
    );
  };

  return (
    <div className="border border-border bg-background font-mono flex flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-3">
        <div className="moneyline-section-header">
          EVERY PICK
          <span className="text-[10px] normal-case tracking-normal">
            {entries.length} logged
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={exportCsv}
          disabled={entries.length === 0}
        >
          <Download className="mr-1 h-3 w-3" />
          EXPORT CSV
        </Button>
      </div>

      {entries.length === 0 ? (
        <div className="p-6 text-center text-xs text-muted-foreground font-sans">
          No picks logged yet
          {trackingSince ? ` — tracking since ${trackingSince}` : ""}.
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-xs">
              <caption className="sr-only">
                Every logged pick with its model probability, final score, grade
                and units.
              </caption>
              <thead>
                <tr className="border-b border-border bg-muted/30 text-[10px] uppercase text-muted-foreground">
                  <th scope="col" className="p-2 text-left font-semibold">Date</th>
                  <th scope="col" className="p-2 text-left font-semibold">Game</th>
                  <th scope="col" className="p-2 text-left font-semibold">Pick</th>
                  <th scope="col" className="p-2 text-right font-semibold">Model</th>
                  <th scope="col" className="p-2 text-right font-semibold">Fair</th>
                  <th scope="col" className="p-2 text-right font-semibold">Final</th>
                  <th scope="col" className="p-2 text-left font-semibold">Result</th>
                  <th scope="col" className="p-2 text-right font-semibold">Units</th>
                  <th scope="col" className="p-2 text-left font-semibold">ADJ</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((entry, i) => (
                  <tr
                    key={`${entry.game_date}-${entry.pick_team}-${i}`}
                    className="border-b border-border/50 last:border-0"
                  >
                    <td className="p-2 text-muted-foreground whitespace-nowrap">
                      {entry.game_date}
                    </td>
                    <td className="p-2 whitespace-nowrap text-muted-foreground">
                      {entry.away_team} @ {entry.home_team}
                    </td>
                    <td className="p-2 font-bold whitespace-nowrap">
                      {entry.pick_team}
                    </td>
                    <td className="p-2 text-right text-primary">
                      {formatPct(entry.model_probability)}
                    </td>
                    <td className="p-2 text-right text-muted-foreground">
                      {entry.fair_line == null
                        ? "—"
                        : entry.fair_line > 0
                          ? `+${entry.fair_line}`
                          : entry.fair_line}
                    </td>
                    <td className="p-2 text-right text-muted-foreground whitespace-nowrap">
                      {entry.final_away == null || entry.final_home == null
                        ? "—"
                        : `${entry.final_away}–${entry.final_home}`}
                    </td>
                    <td className="p-2">
                      <GradeCell grade={entry.result} />
                    </td>
                    <td className="p-2 text-right">
                      {entry.units_pnl == null
                        ? "—"
                        : `${entry.units_pnl > 0 ? "+" : ""}${entry.units_pnl.toFixed(2)}`}
                    </td>
                    <td className="p-2 whitespace-nowrap text-[10px] text-warning">
                      {entry.adj_pick_team
                        ? `${entry.adj_pick_team} ${
                            entry.adj_probability == null
                              ? ""
                              : formatPct(entry.adj_probability)
                          }${entry.adj_result ? ` · ${GRADE_WORD[entry.adj_result]}` : ""}`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border p-2 text-[10px] text-muted-foreground">
            <span className="font-sans">
              CSV columns: {LEDGER_CSV_COLUMNS.join(", ")}. `entered_line` is
              blank on every row — no odds feed is ingested, so picks grade at
              the −110 fallback.
            </span>
            {ordered.length > 25 && (
              <Button
                variant="outline"
                size="sm"
                className="h-6 shrink-0 text-[10px]"
                onClick={() => setShowAll((v) => !v)}
              >
                {showAll ? "SHOW RECENT 25" : `SHOW ALL ${ordered.length}`}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
