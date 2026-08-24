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

import { useHealth, useSession, useSlate } from '@/api';
import { applySeoMetadata } from '@/seo';
import { AuthScreen } from '@/components/auth';
import BillingPage from '@/tabs/billing';
import seoConfig from '../seo-config.json';

const queryClient = new QueryClient();
// The session gate must recognize the same public paths that the server can
// render before authentication. Keep this allowlist derived from the shared
// route source, including legacy aliases that redirect client-side.
const publicRouteMetadata = seoConfig.routes as Record<string, { public: boolean }>;
export const PUBLIC_RESEARCH_ROUTES = [
  ...Object.entries(publicRouteMetadata)
    .filter(([, metadata]) => metadata.public)
    .map(([path]) => path),
  ...Object.keys(seoConfig.aliases),
] as readonly string[];

const PUBLIC_RESEARCH_ROUTE_SET = new Set<string>(PUBLIC_RESEARCH_ROUTES);

function isPublicResearchRoute(location: string) {
  const path = location.split(/[?#]/, 1)[0].replace(/\/+$/, '') || '/';
  return PUBLIC_RESEARCH_ROUTE_SET.has(path);
}

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
  const [location, navigate] = useLocation();
  const session = useSession();

  useEffect(() => {
    applySeoMetadata(location);
  }, [location]);

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
        user={session.data?.user}
      />

      <Switch>
        <Route path="/" component={RootExperience} />
        <Route path="/desk"><LazyPane><DeskTab /></LazyPane></Route>
        <Route path="/research"><LazyPage><ResearchHub /></LazyPage></Route>
        <Route path="/track-record"><LazyPage><TrackRecordPage /></LazyPage></Route>
        <Route path="/settings"><LazyPage><SettingsPage /></LazyPage></Route>
        <Route path="/billing"><LazyPage><BillingPage /></LazyPage></Route>
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
        modelVersion={health.data?.model_version}
        ms={health.data?.startup_ms}
      />
    </div>
  );
}

function SessionGate() {
  const session = useSession();
  const [location] = useLocation();
  const path = location || '/';
  // The server serves useful, public research HTML for these paths. Keep the
  // hydrated client on the same public route instead of replacing it with the
  // auth screen while session state is loading or absent.
  if (isPublicResearchRoute(path)) return <Shell />;
  if (session.isLoading) {
    return <main className="auth-page min-h-[100dvh] flex items-center justify-center bg-background"><div className="font-mono text-xs uppercase tracking-widest text-muted-foreground" role="status">Checking session…</div></main>;
  }
  if (session.data?.authenticated && session.data.user) return <Shell />;
  return <AuthScreen returnTo={safeReturnPath(path)} serverError={!!session.error && !(session.error instanceof Error && 'status' in session.error && (session.error as { status?: number }).status === 401)} />;
}

function safeReturnPath(path: string) {
  return path.startsWith('/') && !path.startsWith('//') && !path.startsWith('/auth') ? path : '/';
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <ErrorBoundary>
            <SessionGate />
          </ErrorBoundary>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
