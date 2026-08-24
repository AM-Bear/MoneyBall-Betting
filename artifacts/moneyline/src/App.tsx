import { lazy, Suspense, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Redirect, Route, Switch, Router as WouterRouter, useLocation, useSearch, useSearchParams } from 'wouter';

import { CommandBar, LEGACY_SHORTCUTS } from '@/components/command-bar';
import { StatusStrip } from '@/components/status-strip';
import { TerminalBoot, PanelSkeleton } from '@/components/layout';
import DeskTab from '@/tabs/desk';
import TodayTab from '@/tabs/today';
import ResearchHub from '@/tabs/research-hub';
import TrackRecordPage from '@/tabs/track-record-page';
import SettingsPage from '@/tabs/settings';

import { useHealth, useSlate } from '@/api';

const queryClient = new QueryClient();

// New tabs lazy-mount so the v1 desk cold start stays exactly as fast.
const PlayerDeskTab = lazy(() => import('@/tabs/player-desk'));
const H2HTab = lazy(() => import('@/tabs/h2h'));
const ParlayLabTab = lazy(() => import('@/tabs/parlay-lab'));
const SeasonDeskTab = lazy(() => import('@/tabs/season-desk'));
const WireTab = lazy(() => import('@/tabs/wire'));

function LazyPane({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
      <Suspense fallback={<div className="max-w-7xl mx-auto"><PanelSkeleton /></div>}>
        {children}
      </Suspense>
    </main>
  );
}

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<main className="page-wrap"><PanelSkeleton /></main>}>
      {children}
    </Suspense>
  );
}

function RootExperience() {
  const [params] = useSearchParams();
  // Existing shared links such as /?team=OAK&year=2002 remain Desk links.
  // A clean root URL is the new Today experience.
  if (params.get("team") || params.get("year")) return <DeskTab />;
  return <TodayTab />;
}

function ResearchRedirect({ to }: { to: string }) {
  const search = useSearch();

  return <Redirect to={`${to}${search}`} replace />;
}

function Shell() {
  const health = useHealth();
  const slate = useSlate();
  const [, navigate] = useLocation();

  // Keyboard 1–6 switches tabs anywhere outside a text input.
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = document.activeElement;
      const tag = el?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (el as HTMLElement)?.isContentEditable) return;
      const idx = parseInt(e.key, 10) - 1;
       if (idx >= 0 && idx < LEGACY_SHORTCUTS.length) {
        e.preventDefault();
         navigate(LEGACY_SHORTCUTS[idx].path);
      }
    };
    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, [navigate]);

  const loaded = !!health.data?.model_loaded;
  const dbReady = !!health.data?.database_ready;
  const slateMode = slate.error ? "error" : (slate.data?.mode || "live");

  return (
    <div className="min-h-[100dvh] flex flex-col bg-background text-foreground overflow-hidden">
      <TerminalBoot loaded={loaded} error={health.error} />

      <CommandBar
        slateStatus={slateMode === "live" ? "LIVE" : slateMode === "historical" ? "HISTORICAL" : "ERROR"}
        lastUpdated={slate.data?.updated_at || slate.data?.date}
      />

      <Switch>
        <Route path="/" component={RootExperience} />
        <Route path="/desk"><LazyPane><DeskTab /></LazyPane></Route>
        <Route path="/research"><LazyPage><ResearchHub /></LazyPage></Route>
        <Route path="/track-record"><LazyPage><TrackRecordPage /></LazyPage></Route>
        <Route path="/settings"><LazyPage><SettingsPage /></LazyPage></Route>
        <Route path="/players"><ResearchRedirect to="/research/players" /></Route>
        <Route path="/research/players"><LazyPane><PlayerDeskTab /></LazyPane></Route>
        <Route path="/h2h"><ResearchRedirect to="/research/matchups" /></Route>
        <Route path="/research/matchups"><LazyPane><H2HTab /></LazyPane></Route>
        <Route path="/parlay"><ResearchRedirect to="/research/parlay" /></Route>
        <Route path="/research/parlay"><LazyPane><ParlayLabTab /></LazyPane></Route>
        <Route path="/season"><ResearchRedirect to="/research/season" /></Route>
        <Route path="/research/season"><LazyPane><SeasonDeskTab /></LazyPane></Route>
        <Route path="/wire"><ResearchRedirect to="/research/wire" /></Route>
        <Route path="/research/wire"><LazyPane><WireTab /></LazyPane></Route>
        <Route>
          <div className="flex-1 flex items-center justify-center font-mono">404 NOT FOUND</div>
        </Route>
      </Switch>

      <StatusStrip
        modelLoaded={loaded}
        dbReady={dbReady}
        slateMode={slateMode}
        ms={health.data?.startup_ms}
      />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <ErrorBoundary>
            <Shell />
          </ErrorBoundary>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
