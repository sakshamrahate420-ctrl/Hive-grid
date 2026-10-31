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

export type BackendRequest = {
  id:string; homeId:string; resident:string; description:string; date:string; category:string;
  priority:'Critical'|'Preferred'|'Flexible'; status:'Submitted'|'Under Review'|'Approved'|'Rejected'|'Scheduled'|'Applied'|'Cancelled';
  adminResponse:string; updated:string; constraint:Record<string,number|number[]>; unsupportedFields:string[];
  execution:{status:string;step:number;time:string;constraint:Record<string,unknown>}|null;
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

let simulationCommandQueue: Promise<unknown> = Promise.resolve();
function enqueueSimulationCommand<T>(command: () => Promise<T>): Promise<T> {
  const next = simulationCommandQueue.then(command, command);
  simulationCommandQueue = next.then(() => undefined, () => undefined);
  return next;
}

export const backend = {
  state: () => request<BackendState>('/simulation/state'),
  start: (scenario: 'summer' | 'heatwave' = 'heatwave', policy: 'learned' | 'teacher' = 'learned') =>
    enqueueSimulationCommand(() => request<BackendState>('/simulation/start', { method: 'POST', body: JSON.stringify({ n_homes: 56, seed: 7, scenario, policy, demo_date: '2023-05-14', weather_year: 2023 }) })),
  step: (n_steps = 1) => enqueueSimulationCommand(() => request<BackendState>('/simulation/step', { method: 'POST', body: JSON.stringify({ n_steps }) })),
  run: () => enqueueSimulationCommand(() => request<{state:BackendState;metrics:Record<string,any>}>('/simulation/run', { method: 'POST' })),
  reset: (restart = false) => enqueueSimulationCommand(() => request<BackendState | {status:string}>(`/simulation/reset${restart?'?restart=true':''}`, { method: 'POST' })),
  metrics: () => request<Record<string, any>>('/metrics'),
  timeseries: () => request<{steps:BackendStep[]}>('/timeseries'),
  homes: () => request<Array<Record<string, any>>>('/homes'),
  events: () => request<{events:Array<Record<string, any>>}>('/events'),
  gridEvent: () => request('/grid/event', { method: 'POST', body: JSON.stringify({ type:'heatwave', start:72, end:88, cap_reduction_pct:20 }) }),
  requests: (homeId?:string) => request<BackendRequest[]>(`/requests${homeId?`?home_id=${encodeURIComponent(homeId)}`:''}`),
  createRequest: (body:Pick<BackendRequest,'homeId'|'resident'|'description'|'category'|'priority'|'constraint'|'unsupportedFields'>) =>
    request<BackendRequest>('/requests',{method:'POST',body:JSON.stringify({home_id:body.homeId,resident:body.resident,description:body.description,category:body.category,priority:body.priority,constraint:body.constraint,unsupported_fields:body.unsupportedFields})}),
  reviewRequest: (id:string,status:string,response:string) => request<BackendRequest>(`/requests/${encodeURIComponent(id)}/review`,{method:'POST',body:JSON.stringify({status,response})}),
  cancelRequest: (id:string) => request<BackendRequest>(`/requests/${encodeURIComponent(id)}/cancel`,{method:'POST'}),
  provenance: () => request<DataProvenance>('/data/provenance'),
};

export type DataProvenance = {demo_date:string|null;weather:{status:string;source:string;database:string|null;cache:string|null;year:number;variables:string[]};solar:{status:string;source:string;derate:number|null};tariff:{status:string;config:string;currency_rates_are_assumptions:boolean;rupee_rates_configured:boolean;p2p_trading_enabled:boolean};household_loads:{status:string;source:string};runtime_internet_required:boolean};
