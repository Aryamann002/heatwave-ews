# Heatwatch India — Heatwave EWS

Extreme heatwave early warning and human thermal stress index for India (MoES, Disaster Management theme).

**What it does:** fetches a 7-day hourly forecast for all 641 Census 2011 districts of India, computes shade and sun-exposed UTCI, estimated WBGT, Heat Index, stress duration and HTSI, compares Tmax against 1991–2020 normals, issues deterministic IMD-style and human-stress alerts, and gives authenticated district officers a GIS dashboard to approve advisories and rank actions for exposed wards. An illustrative relative heat-health risk scenario is shown separately; it predicts no deaths or admissions and never drives alerts.

**Full documentation:** [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) — architecture, data, indices, alert logic, ML, dashboard and API (Word version: [`docs/PROJECT_OVERVIEW.docx`](docs/PROJECT_OVERVIEW.docx)).

## Quick start

```bash
cp .env.example .env               # optional: add GROQ_API_KEY for regional-language advisories
docker compose up --build          # postgres, API :8543, dashboard :5173, pipeline, 6-hourly scheduler
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
| Indices | Shade + sun-exposed UTCI (pythermalcomfort/ASHRAE solar gain), hourly stress duration, WBGT est. (thermofeel Liljegren), Heat Index and HTSI | `backend/indices/` |
| Track 1 | IMD heat-wave criteria: zone minimum, departure from normal, plains absolute, persistence | `backend/app/alerts.py`, `config/alert_rules.yaml` |
| Track 2 | Human thermal stress: UTCI assessment scale + consecutive hot nights | same |
| Alert | max of the two tracks; disagreement logged; blocked when data are stale or fail QC | `backend/pipeline/operational.py` |
| Exposure | WorldPop 2020 population per ward (Ahmedabad, New Delhi, Chennai), combined with district hazard into a response queue rather than fake ward weather | `backend/pipeline/vulnerability.py`, `backend/models/ward_impact.py` |
| Health | Privacy-preserving ward-day outcome plug-in plus a labelled illustrative relative-risk sensitivity scenario; no absolute counts | `backend/models/health_data.py`, `backend/models/health_impact.py` |
| Public health context | Census 2011 district elderly share plus NPCCHH national and NCRB State/UT annual heat-health counts, checksum-validated and isolated from operational training | `backend/pipeline/open_health_data.py`, `config/open_health_sources.json` |
| Response | Signed sessions and roles, advisory approval, CAP 1.2 Test output, idempotent mock SMS/email, municipal trigger payload, tasks and audit log | `backend/app/main.py` |
| Replay | Real past heatwaves (ERA5 hourly) run through the same indices and rules | `backend/pipeline/replay.py`, `config/replay_scenarios.json` |

## Commands

| Command | Description |
|---|---|
| `docker compose up --build` | Run everything |
| `make test` | Backend tests, against a separate `heatwave_test` database |
| `docker compose run --rm --build backend python -m pipeline` | One pipeline cycle (`make pipeline-run`) |
| `docker compose run --rm --build frontend npm run build` | Type-check and build the dashboard |
| `python scripts/build_open_health_reference.py` | Rebuild the three normalized public reference files from official sources |

## Safety notes

- Alert levels are computed by deterministic, versioned rules. The LLM never sets or changes an alert level or a number.
- Stale (>12 h) or QC-failed data block alerts and show a banner.
- Nothing is dispatched without an authenticated officer/admin session and approval; repeat dispatches are idempotent and every action is in the audit log.
- Ward outputs are response priorities, not ward-resolution meteorology. Health impact is an illustrative RR scenario, not a mortality forecast.
- Public NPCCHH/NCRB counts are national or annual State/UT context. They are deliberately excluded from the ward-day training table and do not change alerts.
- Census age structure is from 2011. The required ORGI notice is: “This product uses the ORGI Census API but is not endorsed or certified by ORGI.”
- Not an official IMD warning. Known limitations: `docs/LIMITATIONS.md`. Demo walkthrough: `docs/DEMO_SCRIPT.md`.

## Environment (`.env`)

```
GROQ_API_KEY=               # optional
ALLOW_UNPINNED_POPULATION=0 # optional, see config/vulnerability_source.json
AUTH_MODE=demo              # set strict for deployment
HEATWATCH_SESSION_SECRET=   # at least 32 random characters in strict mode
HEATWATCH_USERS_JSON=       # username-to-password JSON, environment only
CAP_STATUS=Test             # use Actual only after authority/gateway approval
```
