## Overview
HiveGrid is a simulated smart-energy coordination system for a housing society,
built for the CodeKshetra SUS-02 hackathon. Three agents (Home, Society, Grid)
coordinate energy use to reduce load and cost.

## Architecture
- **Model:** a shared policy network with three heads (Home, Society, Grid),
  trained with imitation learning on synthetic data and optionally fine-tuned
  with PPO.
- **Safety Shield:** projects model actions onto physical constraints so the
  agents never output infeasible decisions.
- **Backend:** Python, PyTorch, Gymnasium, Stable-Baselines3, FastAPI.
- **Frontend:** React + TypeScript (Vite, TailwindCSS, Recharts).

## Status
- Frontend currently runs on mock data (live API connection in progress).
- PostgreSQL persistence is planned.

## Team
- Saksham Rahate: [@sakshamrahate420-ctrl](https://github.com/sakshamrahate420-ctrl)
- Bhavam Bokare: [@CodrBhavi](https://github.com/CodrBhavi)
