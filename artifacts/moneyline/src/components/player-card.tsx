import { useState } from "react";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { PercentileBar } from "./percentile-bars";
import { PlayerIdentity } from "./player-identity";
import { cn } from "@/lib/utils";

function fmt3(v: number | null | undefined) {
  if (v == null) return "—";
  return v.toFixed(3).replace(/^0\./, ".");
}

const HITTING_BARS: [string, string, (s: any) => string][] = [
  ["BA", "ba", (s) => fmt3(s.ba)],
  ["OBP", "obp", (s) => fmt3(s.obp)],
  ["SLG", "slg", (s) => fmt3(s.slg)],
  ["HR", "hr", (s) => `${s.hr}`],
  ["BB%", "bb_rate", (s) => `${(s.bb_rate * 100).toFixed(1)}%`],
  ["K% (INV)", "k_rate", (s) => `${(s.k_rate * 100).toFixed(1)}%`],
];

const PITCHING_BARS: [string, string, (s: any) => string][] = [
  ["ERA", "era", (s) => s.era.toFixed(2)],
  ["WHIP", "whip", (s) => s.whip.toFixed(2)],
  ["OBP-A", "obp_against", (s) => fmt3(s.obp_against)],
  ["SLG-A", "slg_against", (s) => fmt3(s.slg_against)],
  ["SO", "so", (s) => `${s.so}`],
];

function ModelSection({ model, framing }: { model: any; framing: string }) {
  return (
    <div className="flex flex-col gap-2 border border-border bg-background p-3">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 font-mono">
        <div className="flex flex-col">
          <span className="text-[10px] text-muted-foreground uppercase">ΔRS</span>
          <span className={cn("text-lg font-bold tabular-nums", (model.delta_rs ?? 0) > 0 ? "text-success" : "")}>
            {model.delta_rs != null ? `${model.delta_rs > 0 ? "+" : ""}${model.delta_rs.toFixed(1)}` : "—"}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-muted-foreground uppercase">ΔRA</span>
          <span className={cn("text-lg font-bold tabular-nums", (model.delta_ra ?? 0) < 0 ? "text-success" : "")}>
            {model.delta_ra != null ? `${model.delta_ra > 0 ? "+" : ""}${model.delta_ra.toFixed(1)}` : "—"}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-muted-foreground uppercase">ΔRD</span>
          <span className="text-lg font-bold tabular-nums">
            {model.delta_rd != null ? `${model.delta_rd > 0 ? "+" : ""}${model.delta_rd.toFixed(1)}` : "—"}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-muted-foreground uppercase">mWAA</span>
          <span className="text-2xl font-bold tabular-nums text-primary">
            {model.mwaa != null ? `${model.mwaa > 0 ? "+" : ""}${model.mwaa.toFixed(2)}` : "—"}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-muted-foreground uppercase">SHARE</span>
          <span className="text-lg tabular-nums">{model.share != null ? `${(model.share * 100).toFixed(1)}%` : "—"}</span>
        </div>
      </div>

      <div className="flex flex-col gap-1 border-t border-border pt-2">
        <div className="text-[9px] text-muted-foreground uppercase tracking-wider">Receipts</div>
        {(model.receipts || []).map((r: any, i: number) => (
          <div key={i} className="flex justify-between text-[10px] font-mono text-muted-foreground gap-2">
            <span className="truncate">
              {r.feature}: {r.formula} = {r.share} × {r.coefficient} × ({r.player} − {r.league})
            </span>
            <span className="text-primary shrink-0 tabular-nums">
              {r.runs > 0 ? "+" : ""}
              {r.runs?.toFixed(1)} runs
            </span>
          </div>
        ))}
        <div className="text-[10px] font-mono text-foreground/80">{model.wins_formula}</div>
        <div className="text-[10px] font-mono text-muted-foreground italic">{model.runs_per_win_receipt}</div>
      </div>

      <div className="text-[10px] font-mono text-primary/90 border-t border-border pt-2">{framing}</div>
    </div>
  );
}

function SalaryTool({ mwaa, note }: { mwaa: number | null; note: string }) {
  const [raw, setRaw] = useState("");
  const salary = parseFloat(raw);
  const valid = Number.isFinite(salary) && salary > 0;
  const perWin = valid && mwaa != null && mwaa > 0 ? salary / mwaa : null;

  return (
    <div className="flex flex-col gap-2 border border-border bg-background p-3 font-mono">
      <div className="flex items-center gap-2">
        <Badge variant="insidevig" className="text-[9px]">USER-SUPPLIED</Badge>
        <span className="text-[10px] text-muted-foreground uppercase">$/mWAA — your number, not ours</span>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <label htmlFor="salary-input" className="text-muted-foreground uppercase text-[10px]">
          Salary ($M)
        </label>
        <Input
          id="salary-input"
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder="e.g. 12.5"
          inputMode="decimal"
          className="h-7 w-24 font-mono"
        />
        <span className="tabular-nums">
          {valid ? (
            perWin != null ? (
              <>
                = <span className="text-primary font-bold">${perWin.toFixed(1)}M / mWAA win</span>
              </>
            ) : (
              <span className="text-muted-foreground">mWAA ≤ 0 — $/mWAA undefined</span>
            )
          ) : raw ? (
            <span className="text-destructive">ENTER A POSITIVE NUMBER</span>
          ) : null}
        </span>
      </div>
      <div className="text-[9px] text-muted-foreground leading-tight">{note}</div>
    </div>
  );
}

function KindSection({
  kind,
  section,
  card,
  compact,
}: {
  kind: "hitting" | "pitching";
  section: any;
  card: any;
  compact?: boolean;
}) {
  const bars = kind === "hitting" ? HITTING_BARS : PITCHING_BARS;
  const s = section.stat_line;
  const statLine =
    kind === "hitting"
      ? `${s.games} G · ${s.pa} PA · ${fmt3(s.ba)}/${fmt3(s.obp)}/${fmt3(s.slg)} · ${s.hr} HR · ${s.bb} BB · ${s.so} SO`
      : `${s.games} G · ${s.games_started} GS · ${s.ip_display} IP · ${s.era.toFixed(2)} ERA · ${s.whip.toFixed(2)} WHIP · ${s.so} SO`;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
          {kind === "hitting" ? "AT THE PLATE" : "ON THE MOUND"}
        </span>
        {!section.qualified && (
          <Badge variant="outline" className="text-[9px] text-warning border-warning/30">
            BELOW QUALIFIED THRESHOLD — PERCENTILES VS QUALIFIED POOL
          </Badge>
        )}
        {kind === "hitting" && section.would_beane_buy && (
          <Badge variant="value" className="text-[10px]">WOULD-BEANE-BUY ✓</Badge>
        )}
      </div>

      <div className="font-mono text-sm tabular-nums bg-background border border-border p-2">{statLine}</div>

      <div className="flex flex-col gap-2">
        {bars.map(([label, key, statFn]) => (
          <PercentileBar key={key} label={label} stat={statFn(s)} pctl={section.percentiles?.[key]} />
        ))}
        <div className="text-[9px] font-mono text-muted-foreground">{section.percentile_note}</div>
      </div>

      {kind === "hitting" && section.badge_caption && (
        <div className="text-[10px] font-mono text-success/90 border-l-2 border-success/40 pl-2">
          {section.badge_caption}
        </div>
      )}

      {!compact && <ModelSection model={section.model} framing={section.fair_odds_framing} />}
      {compact && (
        <div className="font-mono text-xs flex items-baseline gap-2">
          <span className="text-[10px] text-muted-foreground uppercase">mWAA</span>
          <span className="text-lg font-bold text-primary tabular-nums">
            {section.model?.mwaa != null ? `${section.model.mwaa > 0 ? "+" : ""}${section.model.mwaa.toFixed(2)}` : "—"}
          </span>
          <span className="text-[9px] text-muted-foreground">{card.metric_label ? "SEE FULL CARD FOR RECEIPTS" : ""}</span>
        </div>
      )}
    </div>
  );
}

/** Full player card: stat line, live percentiles, run-value model with
 *  receipts, WOULD-BEANE-BUY badge, and the USER-SUPPLIED salary tool. */
export function PlayerCard({ card, compact }: { card: any; compact?: boolean }) {
  const kinds = (["hitting", "pitching"] as const).filter((k) => card[k]);
  const primary = kinds.length === 2
    ? (card.hitting.model.share >= card.pitching.model.share ? "hitting" : "pitching")
    : kinds[0];
  const primaryModel = primary ? card[primary].model : null;

  return (
    <div className="flex flex-col gap-4">
      <PlayerIdentity size={compact ? "md" : "lg"} name={card.name} team={card.team} position={card.position} />
      {kinds.map((kind) => (
        <KindSection key={kind} kind={kind} section={card[kind]} card={card} compact={compact} />
      ))}
      {!compact && (
        <>
          <div className="text-[9px] font-mono text-muted-foreground leading-tight border border-border bg-background p-2">
            {card.metric_label}
            {card.pool_context ? ` · ${card.pool_context.mean_definition}` : ""}
          </div>
          <SalaryTool mwaa={primaryModel?.mwaa ?? null} note={card.salary?.note || ""} />
        </>
      )}
    </div>
  );
}
