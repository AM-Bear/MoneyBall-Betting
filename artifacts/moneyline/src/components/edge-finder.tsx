import { useState, useEffect } from "react";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { formatOdds, formatProb } from "./slate-rail";
import { useMatchup, useTeamPrice, useTeams } from "@/api";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

function parseMoneyline(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed || !/^[+-]?\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

function isMalformedMoneyline(value: string): boolean {
  if (!value.trim()) return false;
  const parsed = parseMoneyline(value);
  return parsed === null || parsed === 0 || Math.abs(parsed) < 100;
}

export function EdgeFinder({
  teamAStats,
  teamALabel,
  activeSlateGame,
  overrideB,
  contextSlot,
  deferUntilBookLine = false,
}: {
  teamAStats: any;
  teamALabel: string;
  activeSlateGame?: any;
  /** H2H teams mode: fixed opponent inputs/label instead of the picker. */
  overrideB?: { inputs: any; label: string } | null;
  /** Extra context rendered above the verdict (starter context, IL flags). */
  contextSlot?: React.ReactNode;
  /** Today cards already display fair prices; only price a comparison after a manual line is entered. */
  deferUntilBookLine?: boolean;
}) {
  const [lineA, setLineA] = useState<string>("");
  const [lineB, setLineB] = useState<string>("");
  const [teamBId, setTeamBId] = useState<{team: string, year: number}>({ team: "NYY", year: 2002 });
  
  const { data: teamsData } = useTeams();
  const teamBData = useTeamPrice(overrideB ? "" : teamBId.team, teamBId.year);
  const matchup = useMatchup();

  useEffect(() => {
    // Determine inputs for A and B
    let inputsA = null;
    let inputsB = null;
    let labelA = "";
    let labelB = "";

    if (activeSlateGame) {
      if (!activeSlateGame.away_inputs || !activeSlateGame.home_inputs) return; // Wait or historical
      inputsA = activeSlateGame.away_inputs;
      inputsB = activeSlateGame.home_inputs;
      labelA = activeSlateGame.away_name || activeSlateGame.away;
      labelB = activeSlateGame.home_name || activeSlateGame.home;
    } else if (overrideB) {
      if (!teamAStats || !overrideB.inputs) return;
      inputsA = teamAStats;
      inputsB = overrideB.inputs;
    } else {
      if (!teamAStats || !teamBData.data?.inputs) return;
      inputsA = teamAStats;
      inputsB = teamBData.data.inputs;
    }

    const parsedA = parseMoneyline(lineA);
    const parsedB = parseMoneyline(lineB);
    
    // Valid American moneyline: must be <= -100 or >= +100 and not 0
    const isValidA = parsedA !== null && parsedA !== 0 && Math.abs(parsedA) >= 100;
    const isValidB = parsedB !== null && parsedB !== 0 && Math.abs(parsedB) >= 100;
    if (isMalformedMoneyline(lineA) || isMalformedMoneyline(lineB)) {
      matchup.reset();
      return;
    }
    if (deferUntilBookLine && !isValidA && !isValidB) {
      matchup.reset();
      return;
    }

    const payload = {
      team_a: inputsA,
      team_b: inputsB,
      book_line_a: isValidA ? parsedA : null,
      book_line_b: isValidB ? parsedB : null,
      // The API scores the selected side, not merely the first field.
      evaluation_side: isValidA ? "a" : "b",
    };
    
    matchup.mutate(payload);
  }, [teamAStats, teamBData.data, lineA, lineB, activeSlateGame, overrideB?.inputs, deferUntilBookLine]);

  const result = matchup.data;
  const isLoading = matchup.isPending || (teamBData.isLoading && !activeSlateGame && !overrideB);
  
  const labelA = activeSlateGame ? (activeSlateGame.away_name || activeSlateGame.away) : teamALabel;
  const labelB = activeSlateGame
    ? (activeSlateGame.home_name || activeSlateGame.home)
    : overrideB
      ? overrideB.label
      : `${teamBId.team} ${teamBId.year}`;
  const isValidLineA = !isMalformedMoneyline(lineA) && parseMoneyline(lineA) !== null;
  const isValidLineB = !isMalformedMoneyline(lineB) && parseMoneyline(lineB) !== null;
  const evaluationLabel = result?.evaluation_side === "b" || (!isValidLineA && isValidLineB)
    ? labelB
    : labelA;

  const verdictVariant = 
    result?.verdict === "VALUE" ? "value" :
    result?.verdict === "NO VALUE" ? "novalue" :
    result?.verdict === "INSIDE THE VIG — NO PLAYABLE EDGE" ? "insidevig" : "outline";

  const isLineAInvalid = isMalformedMoneyline(lineA);
  const isLineBInvalid = isMalformedMoneyline(lineB);

  return (
    <div className="moneyline-panel lg:col-span-1 min-h-[400px]">
      <div className="moneyline-section-header mb-4">EDGE FINDER</div>
      
      <div className="flex flex-col gap-4 flex-1">
        
        {/* Matchup Inputs */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-2 p-3 bg-background border border-border">
            <div className="text-xs font-mono font-bold truncate h-6">{labelA}</div>
            <div className="flex justify-between text-xs text-muted-foreground font-mono">
              <span>Fair</span>
              <span className="text-primary">{result?.fair_line_a != null ? formatOdds(result.fair_line_a) : "..."}</span>
            </div>
            <div className="mt-2">
              <label className="text-[10px] uppercase text-muted-foreground">Book Line</label>
              <Input 
                value={lineA} 
                onChange={(e) => setLineA(e.target.value)} 
                placeholder="-110" 
                className={cn("h-8 font-mono", isLineAInvalid && "border-destructive text-destructive focus:border-destructive")}
              />
            </div>
          </div>
          
          <div className="flex flex-col gap-2 p-3 bg-background border border-border">
            <div className="text-xs font-mono font-bold truncate h-6 relative group">
              {(activeSlateGame || overrideB) ? labelB : (
                <select 
                  className="w-full bg-transparent outline-none appearance-none cursor-pointer truncate pr-4 text-muted-foreground hover:text-foreground transition-colors"
                  value={`${teamBId.team} ${teamBId.year}`}
                  onChange={(e) => {
                    const match = e.target.value.match(/^([A-Za-z]+)\s+(\d{4})$/);
                    if (match) setTeamBId({ team: match[1], year: parseInt(match[2], 10) });
                  }}
                >
                  {teamsData?.teams.map(t => (
                    <option key={t.label} value={t.label}>{t.label}</option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex justify-between text-xs text-muted-foreground font-mono">
              <span>Fair</span>
              <span className="text-primary">{result?.fair_line_b != null ? formatOdds(result.fair_line_b) : "..."}</span>
            </div>
            <div className="mt-2">
              <label className="text-[10px] uppercase text-muted-foreground">Book Line</label>
              <Input 
                value={lineB} 
                onChange={(e) => setLineB(e.target.value)} 
                placeholder="+100" 
                className={cn("h-8 font-mono", isLineBInvalid && "border-destructive text-destructive focus:border-destructive")}
              />
            </div>
          </div>
        </div>
        {(isLineAInvalid || isLineBInvalid) && (
          <div role="alert" className="text-[10px] font-mono text-destructive -mt-2">
            AMERICAN LINE MUST BE ≤ −100 OR ≥ +100
          </div>
        )}

        {contextSlot}

        {/* Verdict Area */}
        <div aria-live="polite" className="flex-1 border border-border bg-background p-4 flex flex-col items-center justify-center text-center relative overflow-hidden">
          {isLoading && !result && (
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground absolute" />
          )}
          
          {result && (
            <div className="w-full flex flex-col items-center gap-4 animate-in fade-in">
              <Badge variant={verdictVariant} className="text-lg px-4 py-1 text-center whitespace-normal h-auto leading-tight">
                {result.verdict}
              </Badge>
              {result.edge_pp !== null && (
                <span className="text-xs text-muted-foreground">Your price: {evaluationLabel}</span>
              )}
              
              {result.edge_pp !== null && (
                <div className="grid grid-cols-3 w-full gap-2 text-center divide-x divide-border border-y border-border py-2">
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] text-muted-foreground uppercase">Model Edge</span>
                    <span className={cn("font-mono font-bold", result.edge_pp > 0 ? "text-success" : "text-destructive")}>
                      {result.edge_pp > 0 ? "+" : ""}{result.edge_pp.toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] text-muted-foreground uppercase">B/E Rate</span>
                    <span className="font-mono">{formatProb(result.break_even_rate)}</span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] text-muted-foreground uppercase">½ Kelly</span>
                    <span className="font-mono">{formatProb(result.kelly_fraction)}</span>
                  </div>
                </div>
              )}
              
              {result.vig_pp !== null && (
                <div className="text-xs text-muted-foreground font-mono">
                  Market Vig: {result.vig_pp.toFixed(1)}%
                </div>
              )}
            </div>
          )}
          
          {!result && !isLoading && (
            <div className="text-sm font-mono text-muted-foreground">
              Enter a book line to calculate edge.
            </div>
          )}
        </div>

        {/* Receipts */}
        {result?.receipts && (
          <div className="flex flex-col gap-1 border border-border p-2 bg-background/50 max-h-32 overflow-y-auto">
            <div className="text-[9px] text-muted-foreground uppercase mb-1 sticky top-0 bg-background/50 backdrop-blur-sm z-10">Receipts ({evaluationLabel})</div>
            {(result.evaluation_side === "b" ? result.receipts.team_b : result.receipts.team_a).map((r: any, i: number) => (
              <div key={i} className="flex justify-between text-[10px] font-mono text-muted-foreground">
                <span className="truncate mr-2">{r.feature} ({r.value.toFixed(3)}) × {r.coefficient.toFixed(1)}</span>
                <span className="text-primary shrink-0">{r.contribution > 0 ? "+" : ""}{r.contribution.toFixed(1)}</span>
              </div>
            ))}
          </div>
        )}
        
        {/* Caveat */}
        {result?.caveat && (
          <div className="text-[10px] text-muted-foreground italic border-l-2 border-muted pl-2 leading-tight">
            {result.caveat}
          </div>
        )}
      </div>
    </div>
  );
}
