import { useState, useEffect, useMemo } from 'react';
import { useLocation, useSearchParams } from 'wouter';

import { SlateRail, SlateGame } from '@/components/slate-rail';
import { PricerPanel } from '@/components/pricer-panel';
import { EdgeFinder } from '@/components/edge-finder';
import { BaParadoxPanel } from '@/components/ba-paradox';
import { TrackRecordPanel } from '@/components/track-record';
import { BankrollPanel } from '@/components/bankroll-backtest';
import { LiveRecordPanel } from '@/components/live-record';
import { ScreenerPanel } from '@/components/screener';
import { PanelError, PanelSkeleton } from '@/components/layout';

import { useSlate, useTeamPrice, usePrice, useTeamsLive, useTeamLive, usePriceInputs } from '@/api';

export default function DeskTab() {
  const slate = useSlate();
  const [, navigate] = useLocation();
  const [params, setParams] = useSearchParams();

  const pricerTeam = useMemo(() => {
    const team = (params.get('team') || 'OAK').toUpperCase();
    const yearRaw = parseInt(params.get('year') || '2002', 10);
    const year = Number.isFinite(yearRaw) ? yearRaw : 2002;
    return { team, year };
  }, [params]);
  // The live season comes from the backend clock (/api/teams-live), never a
  // hardcoded year. While it loads, treat any post-dataset year (>2012) as a
  // live candidate so the historical path doesn't fire a doomed request.
  const teamsLive = useTeamsLive();
  const liveSeason = teamsLive.data?.season;
  const isLive =
    pricerTeam.year > 2012 &&
    (liveSeason === undefined || pricerTeam.year === liveSeason);

  const [customInputs, setCustomInputs] = useState<any>(null);
  const [customPrice, setCustomPrice] = useState<any>(null);
  const [activeSlateGame, setActiveSlateGame] = useState<SlateGame | null>(null);

  // Historical pricer path (v1, untouched).
  const teamData = useTeamPrice(isLive ? '' : pricerTeam.team, pricerTeam.year);

  // Live pricer path: resolve code → team_id, pull live inputs, price them.
  const liveEntry = isLive
    ? (teamsLive.data?.teams || []).find((t) => t.team === pricerTeam.team) || null
    : null;
  const liveTeam = useTeamLive(liveEntry?.team_id ?? null);
  const livePrice = usePriceInputs(isLive ? liveTeam.data?.inputs || null : null);
  const liveData = isLive && livePrice.data && liveTeam.data ? livePrice.data : null;

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
    setParams({ team, year: String(year) });
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

  const pricerLoading = isLive
    ? teamsLive.isLoading || liveTeam.isLoading || livePrice.isLoading
    : teamData.isLoading;
  const pricerError = isLive
    ? (teamsLive.data && !liveEntry
        ? new Error(`${pricerTeam.team} ${liveSeason ?? pricerTeam.year} — NOT A LIVE TEAM CODE`)
        : teamsLive.error || liveTeam.error || livePrice.error)
    : teamData.error;
  const pricerData = isLive ? liveData : teamData.data;

  const liveContext = isLive && liveTeam.data
    ? {
        season: liveSeason,
        sampleLabel: liveTeam.data.sample_label,
        flags: liveTeam.data.flags || [],
        pulse: liveTeam.data.pulse,
        record: {
          wins: liveTeam.data.wins,
          losses: liveTeam.data.losses,
          games_played: liveTeam.data.games_played,
          runs_scored: liveTeam.data.runs_scored,
          runs_allowed: liveTeam.data.runs_allowed,
        },
      }
    : null;

  return (
    <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
      <SlateRail
        games={slate.data?.games || []}
        mode={slate.data?.mode}
        onSelectGame={handleSelectSlateGame}
        onSelectProbable={(playerId) => navigate(`/players?id=${playerId}`)}
      />

      <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
        <div className="max-w-7xl mx-auto flex flex-col gap-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {pricerLoading ? (
              <>
                <div className="lg:col-span-2"><PanelSkeleton /></div>
                <div className="lg:col-span-1"><PanelSkeleton /></div>
              </>
            ) : pricerError ? (
              <div className="lg:col-span-3">
                <PanelError message={pricerError.message || "Failed to load team data"} />
              </div>
            ) : pricerData ? (
              <>
                <PricerPanel
                  team={pricerTeam.team}
                  year={pricerTeam.year}
                  data={pricerData}
                  onInputsChange={setCustomInputs}
                  customInputs={customInputs}
                  customPrice={customPrice}
                  isDirty={!!customInputs}
                  onReset={() => setCustomInputs(null)}
                  liveContext={liveContext}
                />
                <EdgeFinder
                  teamAStats={customInputs || pricerData.inputs}
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
  );
}
