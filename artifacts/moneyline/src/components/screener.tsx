import { useState } from "react";
import { useScreener } from "@/api";
import { PanelSkeleton, PanelError } from "./layout";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Download } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

export function ScreenerPanel() {
  const [year, setYear] = useState(2002);
  const { data, isLoading, error } = useScreener(year);

  // Generate year options 1962-2012
  const years = Array.from({ length: 51 }, (_, i) => 2012 - i);

  const handleExport = () => {
    if (!data?.rows) return;
    
    const headers = ["Year", "Team", "OBP", "SLG", "OOBP", "OSLG", "Pred Wins", "Actual Wins", "Prior Wins", "Mispricing"];
    const csvContent = [
      headers.join(","),
      ...data.rows.map((r: any) => [
        r.year,
        r.team,
        r.obp,
        r.slg,
        r.oobp || "",
        r.oslg || "",
        r.predicted_wins,
        r.actual_wins,
        r.prior_wins || "",
        r.mispricing || ""
      ].join(","))
    ].join("\n");

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `moneyline_screener_${year}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="moneyline-panel lg:col-span-3">
      <div className="flex justify-between items-center mb-4">
        <div className="moneyline-section-header w-1/3">UNDERVALUED ASSET SCREENER</div>
        
        <div className="flex items-center gap-4">
          <Select value={year.toString()} onValueChange={(v) => setYear(parseInt(v, 10))}>
            <SelectTrigger className="w-[100px] h-8 text-xs font-mono rounded-none">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="rounded-none">
              {years.map(y => (
                <SelectItem key={y} value={y.toString()} className="font-mono text-xs rounded-none">
                  {y}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={handleExport} disabled={!data}>
            <Download className="w-3 h-3 mr-2" />
            CSV
          </Button>
        </div>
      </div>

      {isLoading ? (
        <PanelSkeleton />
      ) : error || !data ? (
        <PanelError message="Failed to load screener data" />
      ) : (
        <div className="flex flex-col gap-2">
          {data.offense_only && (
            <div className="bg-warning/10 border border-warning/30 p-2 text-[10px] font-mono text-warning">
              {data.method}
            </div>
          )}
          
          <div className="border border-border bg-background overflow-x-auto">
            <table className="w-full text-sm font-mono text-left whitespace-nowrap">
              <thead className="bg-muted/30 text-xs text-muted-foreground uppercase border-b border-border">
                <tr>
                  <th className="p-3 font-semibold">Team</th>
                  <th className="p-3 font-semibold">OBP</th>
                  <th className="p-3 font-semibold">SLG</th>
                  {!data.offense_only && (
                    <>
                      <th className="p-3 font-semibold">OOBP</th>
                      <th className="p-3 font-semibold">OSLG</th>
                    </>
                  )}
                  <th className="p-3 font-semibold text-right border-l border-border/50">Proj W</th>
                  <th className="p-3 font-semibold text-right">Actual W</th>
                  <th className="p-3 font-semibold text-right">Prior W</th>
                  <th className="p-3 font-semibold text-right border-l border-border/50">Delta</th>
                  <th className="p-3 font-semibold text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {data.rows.map((row: any, i: number) => (
                  <tr key={`${row.team}-${i}`} className="hover:bg-muted/20 transition-colors">
                    <td className="p-3 font-bold text-primary">{row.team}</td>
                    <td className="p-3 tabular-nums">{row.obp.toFixed(3)}</td>
                    <td className="p-3 tabular-nums">{row.slg.toFixed(3)}</td>
                    {!data.offense_only && (
                      <>
                        <td className="p-3 tabular-nums">{row.oobp?.toFixed(3)}</td>
                        <td className="p-3 tabular-nums">{row.oslg?.toFixed(3)}</td>
                      </>
                    )}
                    <td className="p-3 tabular-nums text-right font-bold border-l border-border/50">{row.predicted_wins.toFixed(1)}</td>
                    <td className="p-3 tabular-nums text-right">{row.actual_wins}</td>
                    <td className="p-3 tabular-nums text-right text-muted-foreground">{row.prior_wins || '-'}</td>
                    <td className="p-3 tabular-nums text-right border-l border-border/50">
                      <span className={row.mispricing > 0 ? "text-success" : row.mispricing < 0 ? "text-destructive" : ""}>
                        {row.mispricing > 0 ? "+" : ""}{row.mispricing?.toFixed(1) || '-'}
                      </span>
                    </td>
                    <td className="p-3 text-center">
                      {row.badge && (
                        <Badge variant={row.mispricing > 0 ? "value" : "novalue"} className="text-[9px] px-1.5 py-0">
                          {row.badge}
                        </Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
