import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { useTeams } from "@/api";

function formatUpdatedAt(isoString?: string) {
  if (!isoString) return null;
  // Make sure it displays as Eastern time without just appending ET naively to a date.
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  } catch {
    return isoString;
  }
}

export function CommandBar({ 
  onSelectTeam, 
  slateStatus = "LIVE",
  lastUpdated
}: { 
  onSelectTeam: (team: string, year: number) => void;
  slateStatus?: "LIVE" | "HISTORICAL" | "ERROR";
  lastUpdated?: string;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const { data: teamsData } = useTeams();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "/" && !open && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value) return;
    
    // Parse "OAK 2002"
    const match = value.match(/^([A-Za-z]+)\s+(\d{4})$/);
    if (match) {
      onSelectTeam(match[1].toUpperCase(), parseInt(match[2], 10));
      setValue("");
      inputRef.current?.blur();
    } else if (teamsData?.teams) {
      // Try to find exact match if they didn't type it perfectly
      const vUpper = value.toUpperCase();
      const exact = teamsData.teams.find(t => t.label === vUpper);
      if (exact) {
        onSelectTeam(exact.team, exact.year);
        setValue("");
        inputRef.current?.blur();
      }
    }
  };

  const updatedTime = formatUpdatedAt(lastUpdated);

  return (
    <header className="border-b border-border bg-card px-4 py-2 flex items-center justify-between sticky top-0 z-40">
      <div className="flex items-center gap-4">
        <div className="font-bold tracking-widest uppercase flex items-center gap-2">
          <span>MONEYLINE</span>
          <span className="text-success text-xs">◆</span>
        </div>
        
        <form onSubmit={handleSubmit} className="relative group">
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Search team (e.g. OAK 2002) [/]"
            className="bg-background border border-border px-3 py-1 text-sm font-mono focus:outline-none focus:border-primary w-64 transition-colors placeholder:text-muted-foreground"
          />
          {teamsData?.teams && value && (
            <div className="absolute top-full left-0 mt-1 w-full bg-popover border border-border shadow-lg z-50 max-h-60 overflow-auto hidden group-focus-within:block hover:block">
              {teamsData.teams
                .filter(t => t.label.includes(value.toUpperCase()))
                .slice(0, 10)
                .map(t => (
                  <button
                    key={t.label}
                    type="button"
                    className="w-full text-left px-3 py-2 text-sm font-mono hover:bg-accent focus:bg-accent outline-none"
                    onClick={() => {
                      onSelectTeam(t.team, t.year);
                      setValue("");
                      inputRef.current?.blur();
                    }}
                  >
                    {t.label}
                  </button>
                ))}
            </div>
          )}
        </form>
      </div>

      <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground">
        {updatedTime && <span>{updatedTime}</span>}
        <div className="flex items-center gap-2 border border-border px-2 py-1 bg-background">
          <span className={cn(
            "w-2 h-2 rounded-full",
            slateStatus === "LIVE" ? "bg-success animate-pulse" : 
            slateStatus === "HISTORICAL" ? "bg-warning" : "bg-destructive"
          )} />
          <span className={cn(
            "tracking-wider",
            slateStatus === "LIVE" ? "text-success" : 
            slateStatus === "HISTORICAL" ? "text-warning" : "text-destructive"
          )}>{slateStatus}</span>
        </div>
      </div>
    </header>
  );
}
