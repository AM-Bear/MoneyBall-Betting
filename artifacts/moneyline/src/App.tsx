import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Route, Switch, Router as WouterRouter } from 'wouter';

import { CommandBar } from '@/components/command-bar';
import { SlateRail, SlateGame } from '@/components/slate-rail';
import { PricerPanel } from '@/components/pricer-panel';
import { EdgeFinder } from '@/components/edge-finder';
import { BaParadoxPanel } from '@/components/ba-paradox';
import { TrackRecordPanel } from '@/components/track-record';
import { BankrollPanel } from '@/components/bankroll-backtest';
import { LiveRecordPanel } from '@/components/live-record';
import { ScreenerPanel } from '@/components/screener';
import { StatusStrip } from '@/components/status-strip';
import { TerminalBoot, PanelError, PanelSkeleton } from '@/components/layout';

import { useHealth, useSlate, useTeamPrice, usePrice } from '@/api';

const queryClient = new QueryClient();

function Dashboard() {
  const health = useHealth();
  const slate = useSlate();

  const [pricerTeam, setPricerTeam] = useState({ team: "OAK", year: 2002 });
  const [customInputs, setCustomInputs] = useState<any>(null);
  const [customPrice, setCustomPrice] = useState<any>(null);
  const [activeSlateGame, setActiveSlateGame] = useState<SlateGame | null>(null);

  const teamData = useTeamPrice(pricerTeam.team, pricerTeam.year);
  const priceMutation = usePrice();

  useEffect(() => {
    if (customInputs) {
      const timer = setTimeout(() => {
        priceMutation.mutate(customInputs, {
          onSuccess: (data) => setCustomPrice(data)
        });
      }, 300);
      return () => clearTimeout(timer);
    } else {
      setCustomPrice(null);
      return undefined;
    }
  }, [customInputs]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelectTeam = (team: string, year: number) => {
    setPricerTeam({ team, year });
    setCustomInputs(null);
    setActiveSlateGame(null); // Clear slate game override if they manually pick a team
  };

  const handleSelectSlateGame = (game: SlateGame) => {
    if (game.team && game.year) {
      // Historical mode: load team into pricer
      handleSelectTeam(game.team, game.year);
    } else {
      // Live mode: set active matchup
      setActiveSlateGame(game);
    }
  };

  const loaded = !!health.data?.model_loaded;
  const dbReady = !!health.data?.database_ready;
  const slateMode = slate.error ? "error" : (slate.data?.mode || "live");

  return (
    <div className="min-h-[100dvh] flex flex-col bg-background text-foreground overflow-hidden">
      <TerminalBoot loaded={loaded} error={health.error} />

      <CommandBar
        onSelectTeam={handleSelectTeam}
        slateStatus={slateMode === "live" ? "LIVE" : slateMode === "historical" ? "HISTORICAL" : "ERROR"}
        lastUpdated={slate.data?.updated_at || slate.data?.date}
      />

      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        <SlateRail
          games={slate.data?.games || []}
          mode={slate.data?.mode}
          onSelectGame={handleSelectSlateGame}
        />

        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          <div className="max-w-7xl mx-auto flex flex-col gap-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {teamData.isLoading ? (
                <>
                  <div className="lg:col-span-2"><PanelSkeleton /></div>
                  <div className="lg:col-span-1"><PanelSkeleton /></div>
                </>
              ) : teamData.error ? (
                <div className="lg:col-span-3">
                  <PanelError message={teamData.error.message || "Failed to load team data"} />
                </div>
              ) : teamData.data ? (
                <>
                  <PricerPanel
                    team={pricerTeam.team}
                    year={pricerTeam.year}
                    data={teamData.data}
                    onInputsChange={setCustomInputs}
                    customInputs={customInputs}
                    customPrice={customPrice}
                    isDirty={!!customInputs}
                    onReset={() => setCustomInputs(null)}
                  />
                  <EdgeFinder
                    teamAStats={customInputs || teamData.data.inputs}
                    teamALabel={`${pricerTeam.team} ${pricerTeam.year}`}
                    activeSlateGame={activeSlateGame}
                  />
                </>
              ) : null}
            </div>

            <BaParadoxPanel />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <TrackRecordPanel />
              <BankrollPanel />
            </div>

            <LiveRecordPanel />
            <ScreenerPanel />
          </div>
        </main>
      </div>

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
            <Switch>
              <Route path="/" component={Dashboard} />
              <Route>
                <div className="min-h-screen flex items-center justify-center font-mono">404 NOT FOUND</div>
              </Route>
            </Switch>
          </ErrorBoundary>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
