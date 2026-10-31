# HiveGrid

HiveGrid is a multi-agent energy system simulation for a housing society. Home agents schedule household loads around resident preferences and available energy. A Society agent coordinates prices and fairness, while a Grid agent sends tariff, stress, and response-cap signals. Homes can trade surplus rooftop solar peer to peer. The goal is to reduce energy waste and peak demand while respecting resident constraints.

## How it works

- **Home agents** schedule AC, EV charging, geysers, laundry, and home batteries for 50–100 synthetic flats.
- **The Society agent** receives society loads and comfort deficits, then adjusts price multipliers and fairness weights.
- **The Grid agent** supplies time-of-use prices, capacity limits, and stress signals. In learned mode, its model head proposes these signals within programmed bounds.
- **The peer-to-peer market** matches home solar offers with household bids using a midpoint price.
- The simulation runs for 96 steps, each representing 15 minutes. It uses deterministic synthetic Nagpur-like weather and tariffs.

The profiles and weather are synthetic; this project does not use real household meter data. The demo generates profiles automatically. Residents can submit structured preference requests in the portal; supported constraints take effect only after a society administrator approves and applies them.

## Run the demo on Windows

Use Python 3.12 or later and Node.js 18 or later. In PowerShell, from the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn api.main:app --reload
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) for the React dashboard. Start the learned-agent simulation from the overview or Simulation Studio; the dashboard advances the actual Python simulator and reads its homes, metrics, time series, and agent events. API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

For frontend-only development, start the backend on port 8000, then run `npm --prefix frontend run dev`. Vite proxies simulator API requests to `http://127.0.0.1:8000`; override this with `HIVEGRID_API_TARGET` if needed.

The integrated dashboard shows current society demand, solar generation, grid import, learned-agent status, simulation time series, and backend-emitted agent events. The Home Agents page reads profiles and schedules from the active simulation. These are simulated values, not live energy readings. Admin and resident request pages use backend records; login, invitations, and other portal views remain demo-only.

## Resident request approval

Requests are stored in SQLite at `data/hivegrid_requests.sqlite3` and persist across backend restarts. Approval applies supported constraints to the selected home in the active simulation: temperature setpoint/window, EV deadline/charge target, and minimum battery reserve. The home's safety checks reject infeasible constraints. A successful approval is recorded as **Applied** and queued for the next simulation interval. Requests can still contain unsupported flexible-appliance or free-text preferences; the review page identifies those so an approval does not imply they were enforced. Applying a request requires a running simulation. Resetting the simulation clears active overrides and returns applied requests to review.

This portal is a local prototype without real authentication or access control. Do not expose its request endpoints to the public internet or use it to control physical equipment.

## Learned agents

`HivePolicy` is a shared four-layer, 144-wide transformer with separate HOME, SOCIETY, and GRID output heads. In learned mode, all three heads are active:

- The HOME head proposes household schedules. Actions pass through the feasibility shield, and the teacher schedule supplies EV charging protection and fallback.
- The SOCIETY head proposes a price multiplier and household fairness weights. Programmed bounds limit its proposals.
- The GRID head proposes price, stress, and response-cap signals. Grid safety rules bound the price and cap, and real grid stress signals cannot be suppressed.

The heads are trained by imitation: a rule-based teacher generates input/action examples, and the neural network learns to reproduce those actions. This is not training on real utility or household data.

The committed checkpoint at [`artifacts/hive_policy.pt`](artifacts/hive_policy.pt) was initialized from random weights and trained for four epochs on 5,000 seeded examples. On a separate 512-example synthetic seed, held-out mean squared error was:

| Head | MSE |
| --- | ---: |
| HOME | 0.00793 |
| SOCIETY | 0.00249 |
| GRID | 0.00973 |

A [readable preview of three complete training examples](teacher_dataset_preview.json) includes each example's 48-step observation sequence and role-specific target action. Regenerate the exact training dataset with:

```powershell
python collect.py --samples 5000 --seed 11 --output data/teacher.pt
```

To collect a larger dataset and train a new checkpoint from scratch:

```powershell
python collect.py --samples 100000 --seed 11 --output data/teacher.pt
python train.py --data data/teacher.pt --epochs 12 --output artifacts/hive_policy.pt
python eval.py --model artifacts/hive_policy.pt
```

The collection and training commands support `--smoke` for a small pipeline check. Training data and generated artifacts are ignored by Git except for the committed demo checkpoint and the small preview file.

## Verification and limits

In a seeded 50-home heatwave run, the three learned agents completed all 96 intervals with zero EV deadline, temperature comfort, or energy-balance violations. Peak reduction was 8.84% and the Jain comfort index was 0.962 for that run. This is a single deterministic synthetic scenario, not evidence of real-world performance or broad generalization.

To run the simulator's checks and terminal smoke demo:

```powershell
pytest
python demo_run.py --smoke
```

Battery, EV, and thermal dynamics are simplified. The learned heads imitate the synthetic teacher and have not been validated against real homes or grid operations. Society and Grid retain programmed bounds and fallbacks for safety.

## API examples

```powershell
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/simulation/start -H 'Content-Type: application/json' -d '{"n_homes":60,"seed":7,"policy":"learned","scenario":"heatwave"}'
curl -X POST http://127.0.0.1:8000/simulation/step -H 'Content-Type: application/json' -d '{"n_steps":4}'
curl -X POST http://127.0.0.1:8000/simulation/run
curl http://127.0.0.1:8000/simulation/state
curl http://127.0.0.1:8000/metrics
curl http://127.0.0.1:8000/timeseries
curl http://127.0.0.1:8000/events
curl -X POST http://127.0.0.1:8000/homes/H002/override -H 'Content-Type: application/json' -d '{"constraint":{"ev_deadline_step":80}}'
```
