export type BackendState = {
  current_step: number;
  time: string;
  society_net_load_kw: number;
  cap_kw: number;
  grid_price: number;
  stress: boolean;
  running_cost: number;
  policy: string | null;
  learned_model_loaded: boolean;
  learned_agents: string[];
};

export type BackendStep = {
  step: number;
  net_load_kw: number;
  grid_import_kw: number;
  grid_export_kw: number;
  cap_kw: number;
  grid_price: number;
  stress: boolean;
  temperature_c: number;
  homes: Array<{home:string; solar_kw:number; load_kw:number; net_kw:number}>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail ?? body.error ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return body as T;
}

export const backend = {
  state: () => request<BackendState>('/simulation/state'),
  start: (scenario: 'summer' | 'heatwave' = 'heatwave', policy: 'learned' | 'teacher' = 'learned') =>
    request<BackendState>('/simulation/start', { method: 'POST', body: JSON.stringify({ n_homes: 56, seed: 7, scenario, policy }) }),
  step: (n_steps = 1) => request<BackendState>('/simulation/step', { method: 'POST', body: JSON.stringify({ n_steps }) }),
  reset: () => request<{status:string}>('/simulation/reset', { method: 'POST' }),
  metrics: () => request<Record<string, any>>('/metrics'),
  timeseries: () => request<{steps:BackendStep[]}>('/timeseries'),
  homes: () => request<Array<Record<string, any>>>('/homes'),
  events: () => request<{events:Array<Record<string, any>>}>('/events'),
  gridEvent: () => request('/grid/event', { method: 'POST', body: JSON.stringify({ type:'heatwave', start:72, end:88, cap_reduction_pct:20 }) }),
};
