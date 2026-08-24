import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_BASE = '/api';

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  const data = await res.json();
  if (!res.ok) {
    throw new ApiError(data.error?.message || 'API Error', data.error?.code || 'unknown', res.status);
  }
  return data;
}

// Hooks

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => fetchApi<{ model_loaded: boolean; startup_ms: number; database_ready: boolean; model_version: string }>('/health'),
    refetchInterval: (query) => (query.state.data?.model_loaded ? false : 1000),
  });
}

export function useTeams() {
  return useQuery({
    queryKey: ['teams'],
    queryFn: () => fetchApi<{ teams: { team: string; year: number; label: string }[] }>('/teams'),
    staleTime: Infinity,
  });
}

export function useTeamPrice(team: string, year: number) {
  return useQuery({
    queryKey: ['team', team, year],
    queryFn: () => fetchApi<any>(`/team/${team}/${year}`),
    enabled: !!team && !!year,
    retry: false,
  });
}

export function useMatchup() {
  return useMutation({
    mutationFn: (payload: any) => fetchApi<any>('/matchup', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  });
}

export function usePrice() {
  return useMutation({
    mutationFn: (payload: any) => fetchApi<any>('/price', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  });
}

export function useSlate(date?: string) {
  return useQuery({
    queryKey: ['slate', date],
    queryFn: () => fetchApi<any>(`/slate${date ? `?date=${date}` : ''}`),
    refetchInterval: 5 * 60 * 1000, // 5 min
  });
}

export function useScreener(year: number) {
  return useQuery({
    queryKey: ['screener', year],
    queryFn: () => fetchApi<any>(`/screener?year=${year}`),
  });
}

export function useTrackRecord() {
  return useQuery({
    queryKey: ['track-record'],
    queryFn: () => fetchApi<any>('/track-record'),
    staleTime: Infinity,
  });
}

export function useBacktest() {
  return useQuery({
    queryKey: ['backtest'],
    queryFn: () => fetchApi<any>('/backtest'),
    staleTime: Infinity,
  });
}

export function useBaParadox() {
  return useQuery({
    queryKey: ['ba-paradox'],
    queryFn: () => fetchApi<any>('/ba-paradox'),
    staleTime: Infinity,
  });
}

export function useLiveRecord() {
  return useQuery({
    queryKey: ['record'],
    queryFn: () => fetchApi<any>('/record'),
    refetchInterval: 60 * 60 * 1000,
  });
}

// ---- v2: live research floor ----

/** The live season is a backend contract (server clock), never a hardcoded
 *  year — every label and live-mode check derives from this. */
export function useLiveSeason(): number | undefined {
  const { data } = useTeamsLive();
  return data?.season;
}

export function useTeamsLive() {
  return useQuery({
    queryKey: ['teams-live'],
    queryFn: () => fetchApi<{ season: number; teams: { team_id: number; team: string; name: string; label: string; wins: number; losses: number; games_played: number }[] }>('/teams-live'),
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

export function usePlayers(group: 'hitting' | 'pitching', pool: 'qualified' | 'all', q: string, enabled = true) {
  return useQuery({
    queryKey: ['players', group, pool, q],
    queryFn: () => fetchApi<any>(`/players?group=${group}&pool=${pool}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function usePlayerCard(playerId: number | null) {
  return useQuery({
    queryKey: ['player', playerId],
    queryFn: () => fetchApi<any>(`/player/${playerId}`),
    enabled: playerId != null,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useComparePlayers(a: number | null, b: number | null) {
  return useQuery({
    queryKey: ['compare', a, b],
    queryFn: () => fetchApi<any>(`/compare/players?a=${a}&b=${b}`),
    enabled: a != null && b != null && a !== b,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useTeamLive(teamId: number | null) {
  return useQuery({
    queryKey: ['team-live', teamId],
    queryFn: () => fetchApi<any>(`/team-live/${teamId}`),
    enabled: teamId != null,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

/** Query-flavored /api/price for the live Team Pricer (deterministic on inputs). */
export function usePriceInputs(inputs: { obp: number; slg: number; oobp?: number | null; oslg?: number | null } | null) {
  return useQuery({
    queryKey: ['price-inputs', inputs],
    queryFn: () => fetchApi<any>('/price', { method: 'POST', body: JSON.stringify(inputs) }),
    enabled: inputs != null,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

export function useParlayPrice() {
  return useMutation({
    mutationFn: (payload: { legs: { gamePk: string; side: 'home' | 'away' }[]; book_odds: number | null }) =>
      fetchApi<any>('/parlay/price', { method: 'POST', body: JSON.stringify(payload) }),
  });
}

export function useParlayLog() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { legs: { gamePk: string; side: 'home' | 'away' }[]; book_odds: number | null }) =>
      fetchApi<any>('/parlay/log', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['record'] });
    },
  });
}

export function useSeasonSim(enabled = true) {
  return useQuery({
    queryKey: ['season-sim'],
    queryFn: () => fetchApi<any>('/season-sim'),
    enabled,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

export function useTeamOutlook(teamId: number | null) {
  return useQuery({
    queryKey: ['team-outlook', teamId],
    queryFn: () => fetchApi<any>(`/season-sim/team/${teamId}`),
    enabled: teamId != null,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

export function useWire(team: string | null, types: string[], limit = 120) {
  const typeParam = types.length ? `&types=${types.join(',')}` : '';
  const teamParam = team ? `&team=${team}` : '';
  return useQuery({
    queryKey: ['wire', team, types.join(','), limit],
    queryFn: () => fetchApi<any>(`/wire?limit=${limit}${teamParam}${typeParam}`),
    refetchInterval: 10 * 60 * 1000,
    retry: 1,
  });
}

// ---- v3: game-level verdict ----

export type EvaluateStatus = 'scheduled' | 'live' | 'final' | 'postponed';

export type VerdictCode =
  | 'BET_CANDIDATE'
  | 'MARGINAL_VALUE'
  | 'NO_VALUE'
  | 'AVOID_AT_THIS_PRICE'
  | 'INSUFFICIENT_DATA';

export type VerdictFlag =
  | 'no_price'
  | 'early_season'
  | 'stale'
  | 'starters_unconfirmed'
  | 'small_sample'
  | 'prices_disagree'
  /** Games played could not be resolved. Distinct from `early_season`, which
   *  is a claim about the season; this is a claim about our own data. */
  | 'gp_unavailable';

export interface EvaluatePayload {
  /** Required, 0 < p < 1. Away is derived as 1 - p by the API. */
  p_season_home: number;
  p_adj_home?: number | null;
  price_home?: number | null;
  price_away?: number | null;
  /** null gates the verdict to INSUFFICIENT_DATA (gp_unavailable) — never guess. */
  gp_home?: number | null;
  gp_away?: number | null;
  starters_confirmed?: boolean;
  /** Omitted for user-typed prices: there is no feed, so there is no age to claim. */
  price_age_s?: number | null;
  status?: EvaluateStatus;
  book?: string | null;
}

export interface EvaluateSide {
  p_eval: number;
  p_basis: 'adj' | 'season';
  p_season: number;
  p_adj: number | null;
  price: number | null;
  chance_lose: number;
  fair_line: number | null;
  implied: number | null;
  breakeven: number | null;
  edge_pts: number | null;
  ev_per_100: number | null;
  verdict: VerdictCode | null;
  verdict_reason: string | null;
  signal: 'Strong' | 'Moderate' | 'Weak' | null;
  signal_provisional: boolean | null;
  gap: number | null;
  volatility: 'Lower' | 'Typical' | 'Higher' | null;
  /** 'Unknown' is a real runtime state, not a placeholder: the engine returns
   *  it when games played is missing, because "Low" would be a claim with
   *  nothing behind it. See backend/verdict.py::_uncertainty. */
  uncertainty: 'Low' | 'Moderate' | 'High' | 'Unknown';
  agree: boolean | null;
  flags: VerdictFlag[];
  basis_note: string | null;
  raw?: { edge: number; ev: number; implied: number; gap: number };
}

export interface EvaluateThresholds {
  avoid_ev: number;
  no_value_edge: number;
  candidate_ev: number;
  candidate_edge: number;
  sigma: number;
  stale_seconds: number;
  gp_hard_floor: number;
  gp_small_sample: number;
  gp_moderate: number;
  signal_provisional_n: number;
  signal_strong_gap: number;
  signal_moderate_gap: number;
  volatility_lower_price: number;
  volatility_higher_price: number;
  uncertainty_high_basis_spread: number;
  uncertainty_moderate_basis_spread: number;
  sigma_is_provisional: boolean;
  notes: Record<string, string>;
}

export interface EvaluateResponse {
  sides: { home: EvaluateSide; away: EvaluateSide };
  game: {
    side: 'home' | 'away' | null;
    verdict: VerdictCode | null;
    verdict_reason: string | null;
    lean_side: 'home' | 'away' | null;
    lean_differs_from_value: boolean;
    avoid_note: string | null;
    frozen: boolean;
    status: EvaluateStatus;
    book: string | null;
    takeaway: string | null;
  };
  sample: { gp_home: number | null; gp_away: number | null; label: string };
  thresholds: EvaluateThresholds;
  model_version?: string;
  caveat?: string;
}

export function useEvaluate() {
  return useMutation({
    mutationFn: (payload: EvaluatePayload) =>
      fetchApi<EvaluateResponse>('/evaluate', { method: 'POST', body: JSON.stringify(payload) }),
  });
}

export function useGradeRecord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => fetchApi<any>('/record/grade', { method: 'POST' }),
    onSuccess: (data) => {
      queryClient.setQueryData(['record'], data.record);
      queryClient.invalidateQueries({ queryKey: ['record'] });
    }
  });
}
