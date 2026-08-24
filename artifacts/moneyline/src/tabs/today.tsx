import { useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useSlate } from "@/api";
import { PanelError, PanelSkeleton } from "@/components/layout";
import { SlateGame } from "@/components/slate-rail";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { GameCard } from "@/components/game-card";
import { WelcomeGuide, usePresentationPreferences } from "@/components/presentation-preferences";
import { ResearchTag } from "@/components/research-tag";
import { isFinalGame, isInProgressGame, isNonPlayableGame } from "@/lib/game-status";

type GroupKey = "scheduled" | "attention" | "in-progress" | "final";
type FilterKey = "all" | GroupKey;

function isPartial(game: SlateGame) {
  return Boolean(game.pricing_error || game.model_prob_home == null || !game.fair_lines);
}

function isMissingStarter(game: SlateGame) {
  return !game.probables?.away || !game.probables?.home;
}

function groupFor(game: SlateGame): GroupKey {
  if (isFinalGame(game)) return "final";
  if (isNonPlayableGame(game)) return "attention";
  if (isInProgressGame(game)) return "in-progress";
  if (isPartial(game) || isMissingStarter(game)) return "attention";
  return "scheduled";
}

const GROUPS: { key: GroupKey; label: string; description: string }[] = [
  { key: "scheduled", label: "Ready to review", description: "Games with a complete season-model price." },
  { key: "attention", label: "Needs attention", description: "The schedule is present, but pricing or starter data is incomplete." },
  { key: "in-progress", label: "In progress", description: "Status comes from the live schedule. No live odds are implied." },
  { key: "final", label: "Final", description: "Completed or cancelled games stay visible for the day’s context." },
];

function formatDate(date?: string) {
  if (!date) return "Date unavailable";
  const parsed = new Date(`${date}T12:00:00`);
  return Number.isNaN(parsed.getTime())
    ? date
    : parsed.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}

function formatUpdatedAt(value?: string) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
    timeZone: "America/New_York",
  });
}

function humanSlateStatus(mode?: string, feedUp?: boolean) {
  if (mode === "historical") return { label: "Historical fallback", tone: "warning" };
  if (feedUp === false) return { label: "Feed unavailable", tone: "warning" };
  return { label: "Live schedule", tone: "success" };
}

export default function TodayTab() {
  const slate = useSlate();
  const { preferences, updatePreferences } = usePresentationPreferences();
  const [filter, setFilter] = useState<FilterKey>("all");
  const status = humanSlateStatus(slate.data?.mode, slate.data?.feed_up);
  const games: SlateGame[] = slate.data?.games || [];

  const grouped = useMemo(() => {
    return GROUPS.reduce<Record<GroupKey, SlateGame[]>>((acc, group) => {
      acc[group.key] = games.filter((game) => groupFor(game) === group.key);
      return acc;
    }, { scheduled: [], attention: [], "in-progress": [], final: [] });
  }, [games]);

  if (slate.isLoading) {
    return <main className="page-wrap"><PanelSkeleton /></main>;
  }

  if (slate.error || !slate.data) {
    return (
      <main className="page-wrap">
        <PanelError message="Today’s schedule could not be loaded. Try again in a moment." />
      </main>
    );
  }

  const updated = formatUpdatedAt(slate.data.updated_at);
  const visibleGroups = filter === "all" ? GROUPS : GROUPS.filter((group) => group.key === filter);
  const readyCount = grouped.scheduled.length;
  const attentionCount = grouped.attention.length;
  const inProgressCount = grouped["in-progress"].length;
  const finalCount = grouped.final.length;

  return (
    <main className="page-wrap today-page">
      <div className="today-hero">
        <div>
          <div className="eyebrow">Daily model view</div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl" data-testid="heading-today">Today</h1>
            <span className={`status-label status-label-${status.tone}`} data-testid="status-slate">
              <span className="status-dot" aria-hidden="true" /> {status.label}
            </span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground sm:text-base" data-testid="text-slate-date">
            {formatDate(slate.data.date)}
            {updated && <span className="ml-2 text-muted-foreground/70">· updated {updated}</span>}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => slate.refetch()} disabled={slate.isFetching} data-testid="button-refresh-slate">
          <RefreshCw className={slate.isFetching ? "animate-spin" : ""} aria-hidden="true" /> Refresh
        </Button>
      </div>

      {slate.data.mode === "historical" && (
        <div className="today-notice today-notice-warning" role="status" data-testid="status-historical">
          <Badge variant="warning">Historical fallback</Badge>
          <p>{slate.data.reason || "A live slate was not available. Historical examples are shown for research only."}</p>
        </div>
      )}

      {!preferences.guideDismissed && (
        <WelcomeGuide onDismiss={() => updatePreferences({ guideDismissed: true })} />
      )}

      <section className="today-summary" aria-label="Today summary">
        <div>
          <span className="eyebrow">A calm read on the slate</span>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            {games.length
              ? `${games.length} game${games.length === 1 ? "" : "s"} in view. Start with readiness, then open a game for its model basis and optional manual price check.`
              : "There are no games in this slate. The research surfaces remain available below."}
          </p>
        </div>
        <div className="today-metrics">
          <div><strong data-testid="metric-ready">{readyCount}</strong><span>Ready to review</span></div>
          <div><strong data-testid="metric-attention">{attentionCount}</strong><span>Needs attention</span></div>
          <div><strong data-testid="metric-live">{inProgressCount}</strong><span>In progress</span></div>
          <div><strong data-testid="metric-final">{finalCount}</strong><span>Final</span></div>
        </div>
      </section>

      <div className="today-filter-row" role="group" aria-label="Filter today’s games">
        {([{ key: "all", label: "All games", count: games.length }, ...GROUPS.map((group) => ({ key: group.key, label: group.label, count: grouped[group.key].length }))] as { key: FilterKey; label: string; count: number }[]).map((item) => (
          <button
            key={item.key}
            type="button"
            className={`filter-button ${filter === item.key ? "filter-button-active" : ""}`}
            onClick={() => setFilter(item.key)}
            aria-pressed={filter === item.key}
            data-testid={`button-filter-${item.key}`}
          >
            {item.label} <span>{item.count}</span>
          </button>
        ))}
      </div>

      {games.length === 0 ? (
        <section className="empty-state" data-testid="empty-today">
          <h2>No live slate to review</h2>
          <p>{slate.data.mode === "historical" ? "The app is showing historical examples because the current schedule is empty or unavailable." : "When today’s schedule arrives, games will appear here grouped by readiness."}</p>
        </section>
      ) : (
        <div className="today-groups">
          {visibleGroups.map((group) => grouped[group.key].length > 0 && (
            <section key={group.key} aria-labelledby={`group-${group.key}`} data-testid={`section-${group.key}`}>
              <div className="group-heading">
                <div>
                  <h2 id={`group-${group.key}`}>{group.label}</h2>
                  <p>{group.description}</p>
                </div>
                <span className="group-count">{grouped[group.key].length}</span>
              </div>
              <div className="game-grid">
                {grouped[group.key].map((game) => (
                  <GameCard key={game.game_pk || `${game.away}-${game.home}`} game={game} detailLevel={preferences.detailLevel} explainTerms={preferences.explainTerms} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <div className="today-footer-note">
        <ResearchTag />
        <p>Fair prices are model translations, not available sportsbook odds. No edge, expected return, or stake is shown until you enter a valid American price.</p>
      </div>
    </main>
  );
}