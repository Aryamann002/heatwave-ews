# Heatwatch India — Heatwave EWS

Extreme heatwave early warning and human thermal stress index for India (MoES, Disaster Management theme).

**What it does:** fetches a 7-day hourly forecast for 29 heat-prone districts, computes UTCI, estimated WBGT and Heat Index, compares Tmax against 1991–2020 normals, issues IMD-style and human-stress alerts, and gives district officers a GIS dashboard to draft, approve and dispatch advisories and allocate response resources to the most exposed wards.

## Quick start

```bash
cp .env.example .env               # optional: add GROQ_API_KEY for regional-language advisories
docker compose up --build          # postgres, API :8000, dashboard :5173, pipeline, 6-hourly scheduler
```

Landing page: http://localhost:5173/landing.html (links into the dashboard and its replays).

The first pipeline run downloads 30 years of daily temperatures per district (a few minutes, rate-limited) and the ward population data; later runs reuse the cache in `data/`. Open http://localhost:5173.

To precompute the historical replays so the demo works offline:

```bash
docker compose run --rm backend python -m pipeline.replay
```

## How it works

| Stage | What | Code |
|---|---|---|
| Ingest | Open-Meteo hourly T, RH, wind, pressure, shortwave + direct radiation, IST days | `backend/pipeline/s1_fetch.py` |
| Climatology | 1991–2020 ERA5 daily normals (±7-day window), p90 Tmin for hot nights | `backend/pipeline/climatology.py` |
| Bias correction | LightGBM per climate zone, ECMWF IFS Tmax → ERA5 frame, 2024–2025, leave-one-year-out; used only where held-out MAE improves (`python -m models.train_bias`) | `backend/models/train_bias.py` |
| Indices | UTCI (pythermalcomfort), WBGT est. (thermofeel Liljegren), Heat Index (Rothfusz) | `backend/indices/` |
| Track 1 | IMD heat-wave criteria: zone minimum, departure from normal, plains absolute, persistence | `backend/app/alerts.py`, `config/alert_rules.yaml` |
| Track 2 | Human thermal stress: UTCI assessment scale + consecutive hot nights | same |
| Alert | max of the two tracks; disagreement logged; blocked when data are stale or fail QC | `backend/pipeline/operational.py` |
| Exposure | WorldPop 2020 population per ward (Ahmedabad, New Delhi, Chennai) | `backend/pipeline/vulnerability.py` |
| Response | Advisory drafts (EN/HI templates + LLM regional translation), officer approval, CAP 1.2, mock SMS/email, ward resource allocation, tasks, audit log | `backend/app/main.py` |
| Replay | Real past heatwaves (ERA5 hourly) run through the same indices and rules | `backend/pipeline/replay.py`, `config/replay_scenarios.json` |

## Commands

| Command | Description |
|---|---|
| `docker compose up --build` | Run everything |
| `make test` | Backend tests, against a separate `heatwave_test` database |
| `docker compose run --rm --build backend python -m pipeline` | One pipeline cycle (`make pipeline-run`) |
| `docker compose run --rm --build frontend npm run build` | Type-check and build the dashboard |

## Safety notes

- Alert levels are computed by deterministic, versioned rules. The LLM never sets or changes an alert level or a number.
- Stale (>12 h) or QC-failed data block alerts and show a banner.
- Nothing is dispatched without officer/admin approval; every action is in the audit log.
- Not an official IMD warning. Known limitations: `docs/LIMITATIONS.md`. Demo walkthrough: `docs/DEMO_SCRIPT.md`.

## Environment (`.env`)

```
GROQ_API_KEY=               # optional
ALLOW_UNPINNED_POPULATION=0 # optional, see config/vulnerability_source.json
```
