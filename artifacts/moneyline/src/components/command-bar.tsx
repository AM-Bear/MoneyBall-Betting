import { useState, useEffect, useMemo, useRef } from "react";
import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import { useTeams, useTeamsLive } from "@/api";
import { usePlayerHits } from "./player-search";

export const TABS = [
  { label: "Today", path: "/" },
  { label: "Research", path: "/research" },
  { label: "Track record", path: "/track-record" },
  { label: "Desk", path: "/desk" },
  { label: "Parlay check", path: "/research/parlay" },
  { label: "Settings", path: "/settings" },
] as const;

/** Original 1–6 Desk shortcuts remain stable during the shell migration. */
export const LEGACY_SHORTCUTS = [
  { path: "/desk" },
  { path: "/research/players" },
  { path: "/research/matchups" },
  { path: "/research/parlay" },
  { path: "/research/season" },
  { path: "/research/wire" },
] as const;

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

interface OmniHit {
  kind: "live-team" | "hist-team" | "player";
  label: string;
  sub: string;
  rank: number;
  go: () => void;
}

/** Global omnisearch: live-season teams, historical seasons, and players
 *  in one ranked dropdown. `/` focuses it from anywhere. The live year is
 *  whatever /api/teams-live reports — never hardcoded. */
function OmniSearch() {
  const [raw, setRaw] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [, navigate] = useLocation();

  const { data: teamsData } = useTeams();
  const teamsLive = useTeamsLive();

  useEffect(() => {
    const t = setTimeout(() => setQuery(raw), 200);
    return () => clearTimeout(t);
  }, [raw]);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const playerHits = usePlayerHits(query);

  const hits: OmniHit[] = useMemo(() => {
    const needle = query.trim().toUpperCase();
    if (needle.length < 2) return [];
    const out: OmniHit[] = [];

    const pick = (fn: () => void) => () => {
      fn();
      setRaw("");
      setQuery("");
      setOpen(false);
      inputRef.current?.blur();
    };

    const liveSeason = teamsLive.data?.season;
    for (const t of teamsLive.data?.teams || []) {
      const hay = `${t.team} ${liveSeason ?? ""} ${t.name}`.toUpperCase();
      if (hay.includes(needle)) {
        out.push({
          kind: "live-team",
          label: t.label,
          sub: `${t.name} · ${t.wins}–${t.losses} · LIVE`,
          rank: (hay.startsWith(needle) ? 200 : 100) + 50,
          go: pick(() => navigate(`/?team=${t.team}&year=${liveSeason}`)),
        });
      }
    }

    for (const t of teamsData?.teams || []) {
      if (t.label.toUpperCase().includes(needle)) {
        out.push({
          kind: "hist-team",
          label: t.label,
          sub: "HISTORICAL SEASON",
          rank: t.label.toUpperCase().startsWith(needle) ? 150 : 60,
          go: pick(() => navigate(`/?team=${t.team}&year=${t.year}`)),
        });
      }
    }

    for (const p of playerHits.hits.slice(0, 6)) {
      out.push({
        kind: "player",
        label: p.name.toUpperCase(),
        sub: `${p.team_name || ""} · ${p.group === "hitting" ? "BAT" : "ARM"}`,
        rank: (p.name.toUpperCase().startsWith(needle) ? 180 : 90) + Math.min(p.volume / 100, 40),
        go: pick(() => navigate(`/research/players?id=${p.player_id}`)),
      });
    }

    return out.sort((a, b) => b.rank - a.rank).slice(0, 12);
  }, [query, teamsData, teamsLive.data, playerHits.hits, navigate]);

  const groups: { title: string; items: OmniHit[] }[] = useMemo(() => {
    const liveSeason = teamsLive.data?.season;
    const order: { kind: OmniHit["kind"]; title: string }[] = [
      { kind: "live-team", title: liveSeason ? `${liveSeason} LIVE` : "LIVE" },
      { kind: "player", title: "PLAYERS" },
      { kind: "hist-team", title: "HISTORICAL" },
    ];
    return order
      .map(({ kind, title }) => ({ title, items: hits.filter((h) => h.kind === kind) }))
      .filter((g) => g.items.length > 0);
  }, [hits, teamsLive.data?.season]);

  return (
    <div ref={wrapRef} className="relative">
      <input
        ref={inputRef}
        type="text"
        value={raw}
        onChange={(e) => { setRaw(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && hits[0]) {
            e.preventDefault();
            hits[0].go();
          }
          if (e.key === "Escape") {
            setOpen(false);
            inputRef.current?.blur();
          }
        }}
        placeholder="Teams · players · seasons [/]"
        aria-label="Search teams, players, and historical seasons"
        className="bg-background border border-border px-3 py-1 text-sm font-mono focus:outline-none focus:border-primary w-44 md:w-64 transition-colors placeholder:text-muted-foreground"
      />
      {open && query.trim().length >= 2 && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-popover border border-border shadow-lg z-50 max-h-80 overflow-auto">
          {groups.length === 0 ? (
            <div className="p-3 text-xs font-mono text-muted-foreground">
              {playerHits.isLoading ? "SEARCHING…" : "NO MATCH — TEAMS, PLAYERS, OR 'OAK 2002'"}
            </div>
          ) : (
            groups.map((g) => (
              <div key={g.title}>
                <div className="px-3 py-1 text-[9px] font-mono text-muted-foreground uppercase tracking-widest bg-muted/30 sticky top-0">
                  {g.title}
                </div>
                {g.items.map((h, i) => (
                  <button
                    key={`${g.title}-${i}`}
                    type="button"
                    onClick={h.go}
                    className="moneyline-focus-ring w-full text-left px-3 py-2 text-sm font-mono hover:bg-accent flex justify-between items-baseline gap-2"
                  >
                    <span className="font-bold truncate">{h.label}</span>
                    <span className="text-[9px] text-muted-foreground uppercase shrink-0">{h.sub}</span>
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export function CommandBar({
  slateStatus = "LIVE",
  lastUpdated
}: {
  slateStatus?: "LIVE" | "HISTORICAL" | "ERROR";
  lastUpdated?: string;
}) {
  const [location] = useLocation();
  const updatedTime = formatUpdatedAt(lastUpdated);

  return (
    <header className="border-b border-border bg-card px-4 py-2 flex items-center justify-between gap-4 sticky top-0 z-40 flex-wrap">
      <div className="flex items-center gap-4 flex-wrap">
         <div className="font-bold tracking-tight flex items-center gap-2 shrink-0">
          <span>MONEYLINE</span>
           <span className="text-success text-xs" aria-label="MONEYLINE is available">●</span>
        </div>

         <nav className="flex items-center gap-1 overflow-x-auto" aria-label="Primary navigation">
          {TABS.map((tab, i) => {
            const active = tab.path === "/" ? location === "/" : location.startsWith(tab.path);
            return (
              <Link
                key={tab.path}
                href={tab.path}
                 className={cn(
                   "px-2.5 py-1.5 text-xs border-b-2 transition-colors whitespace-nowrap",
                  active
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
                aria-current={active ? "page" : undefined}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        <OmniSearch />
      </div>

       <div className="flex items-center gap-3 text-xs text-muted-foreground shrink-0">
        {updatedTime && <span className="hidden sm:inline">{updatedTime}</span>}
        <div className="flex items-center gap-2 border border-border px-2 py-1 bg-background">
          <span className={cn(
            "w-2 h-2 rounded-full",
            slateStatus === "LIVE" ? "bg-success animate-pulse" :
            slateStatus === "HISTORICAL" ? "bg-warning" : "bg-destructive"
          )} />
           <span className={cn(
             "tracking-wide",
            slateStatus === "LIVE" ? "text-success" :
            slateStatus === "HISTORICAL" ? "text-warning" : "text-destructive"
           )}>{slateStatus === "LIVE" ? "Live" : slateStatus === "HISTORICAL" ? "Historical" : "Unavailable"}</span>
        </div>
      </div>
    </header>
  );
}
