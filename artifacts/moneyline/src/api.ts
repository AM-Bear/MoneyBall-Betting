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
