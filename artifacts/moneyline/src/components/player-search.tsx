import { useEffect, useRef, useState } from "react";
import { useLiveSeason, usePlayers } from "@/api";
import { PlayerIdentity } from "./player-identity";
import { cn } from "@/lib/utils";

export interface PlayerHit {
  player_id: number;
  name: string;
  team_name: string | null;
  position: string | null;
  group: "hitting" | "pitching";
  volume: number; // pa or ip — used for ranking
}

export function usePlayerHits(query: string) {
  const enabled = query.trim().length >= 2;
  const hitters = usePlayers("hitting", "all", query.trim(), enabled);
  const pitchers = usePlayers("pitching", "all", query.trim(), enabled);

  const hits: PlayerHit[] = [];
  for (const p of hitters.data?.players || []) {
    hits.push({ ...p, group: "hitting", volume: p.pa || 0 });
  }
  for (const p of pitchers.data?.players || []) {
    hits.push({ ...p, group: "pitching", volume: (p.ip || 0) * 4 });
  }
  const needle = query.trim().toLowerCase();
  hits.sort((a, b) => {
    const aStarts = a.name.toLowerCase().startsWith(needle) ? 1 : 0;
    const bStarts = b.name.toLowerCase().startsWith(needle) ? 1 : 0;
    if (aStarts !== bStarts) return bStarts - aStarts;
    return b.volume - a.volume;
  });
  return { hits, isLoading: enabled && (hitters.isLoading || pitchers.isLoading), enabled };
}

/** Autocomplete over the live-season player pool (hitters + pitchers). */
export function PlayerSearch({
  onSelect,
  placeholder,
  autoFocus,
  className,
}: {
  onSelect: (hit: PlayerHit) => void;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
}) {
  const [raw, setRaw] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  // Live year comes from the backend contract, never a hardcoded season.
  const liveSeason = useLiveSeason();
  const effectivePlaceholder =
    placeholder ?? (liveSeason ? `SEARCH ${liveSeason} PLAYERS…` : "SEARCH LIVE PLAYERS…");

  useEffect(() => {
    const t = setTimeout(() => setQuery(raw), 250);
    return () => clearTimeout(t);
  }, [raw]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const { hits, isLoading, enabled } = usePlayerHits(query);
  const shown = hits.slice(0, 8);

  const pick = (hit: PlayerHit) => {
    onSelect(hit);
    setRaw("");
    setQuery("");
    setOpen(false);
  };

  return (
    <div ref={wrapRef} className={cn("relative", className)}>
      <input
        type="text"
        value={raw}
        autoFocus={autoFocus}
        onChange={(e) => {
          setRaw(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && shown[0]) {
            e.preventDefault();
            pick(shown[0]);
          }
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder={effectivePlaceholder}
        aria-label="Search live-season players"
        className="w-full bg-background border border-border px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-primary placeholder:text-muted-foreground"
      />
      {open && enabled && (
        <div className="absolute top-full left-0 mt-1 w-full bg-popover border border-border shadow-lg z-50 max-h-72 overflow-auto">
          {isLoading ? (
            <div className="p-3 text-xs font-mono text-muted-foreground">SEARCHING POOL…</div>
          ) : shown.length === 0 ? (
            <div className="p-3 text-xs font-mono text-muted-foreground">
              NO MATCH IN THE {liveSeason ?? "LIVE"} POOL (≥100 PA OR ≥30 IP)
            </div>
          ) : (
            shown.map((hit) => (
              <button
                key={`${hit.group}-${hit.player_id}`}
                type="button"
                onClick={() => pick(hit)}
                className="moneyline-focus-ring w-full text-left px-3 py-2 hover:bg-accent flex items-center justify-between gap-2"
              >
                <PlayerIdentity size="sm" name={hit.name} team={hit.team_name} position={hit.position} />
                <span className="text-[9px] font-mono text-muted-foreground uppercase">
                  {hit.group === "hitting" ? "BAT" : "ARM"}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
