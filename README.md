# Heatwatch India

### Extreme heat early warning, explained as human thermal stress

Heatwatch India is a decision-support prototype for [SIH26083](https://sih.gov.in/): **Extreme Heatwave Early Warning and Human Thermal Stress Index**. It turns an open seven-day weather forecast into district-level thermal-stress indicators, transparent alerts, and a human-reviewed heat-action workflow.

> **Prototype, not an official warning.** Heatwatch does not issue IMD bulletins, predict a number of deaths or hospital admissions, or send real public SMS/WhatsApp alerts. Use official IMD and local-authority guidance for operational decisions.

## What you can explore

- A seven-day GIS view of **641 Census 2011 district areas** with alert, sun-exposed UTCI, estimated WBGT, Heat Index, and temperature-anomaly layers.
- Two explainable alert tracks: **temperature/IMD-style criteria** and **human thermal stress**. The higher valid level is shown; stale or failed-quality data block operational alerts.
- A district panel with the forecast, 1991-2020 ERA5 normal, thermal indices, and a versioned reason trace.
- Ward **population-exposure priorities** for Ahmedabad, New Delhi, and Chennai (539 wards). These are response priorities, **not ward-level weather forecasts**.
- Draft and approve advisories, export **CAP 1.2 Test** messages, simulate SMS/email delivery, and assign response tasks. Mutations require a signed officer/admin session.
- Replay four historical heat events through the same index and alert rules. Replay uses ERA5 reanalysis and does **not** measure how a past issued forecast performed.
- View health-data readiness and sourced demographic/heat-health context. The illustrative relative-risk scenario produces no mortality or admission counts and never changes alerts.

## At a glance

```text
ECMWF IFS forecast via Open-Meteo     ERA5 normals / historical replay
                  \                    /
                  ingestion + QC + provenance
                            |
                  Tmax bias correction
                            |
          UTCI / estimated WBGT / Heat Index / HTSI
                            |
            two-track deterministic alert engine
                            |
                    PostgreSQL + PostGIS
                            |
           FastAPI  <-->  React / MapLibre dashboard
                            |
          officer approval -> CAP Test / mock dispatch / tasks
```

The backend and pipeline are Python. The browser app is React, TypeScript, Vite, and MapLibre. Local orchestration uses Docker Compose. See [the as-built overview](docs/PROJECT_OVERVIEW.md) and [architecture design](docs/ARCHITECTURE.md).

## Run locally

**Requirements:** Docker Desktop with Compose, enough free disk space for the forecast/reanalysis cache, and internet access for the initial data fetch. No API key is needed for the core demo.

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

On macOS/Linux:

```bash
cp .env.example .env
docker compose up --build
```

Open the [dashboard](http://localhost:5173/) or [landing page](http://localhost:5173/landing.html). The API health endpoint is [localhost:8543/health](http://localhost:8543/health); interactive API documentation is at [localhost:8543/docs](http://localhost:8543/docs). Wait for the initial pipeline to finish before expecting live map data. It downloads/cache-builds normals and exposure inputs; the first run can take several minutes or longer depending on upstream services. Later runs reuse `data/`.

The local walkthrough starts in **demo authentication** mode. The interface shows the demo account; `officer / officer-demo` permits the simulated officer flow. Never expose this mode publicly.

For an offline-friendly historical replay after the first setup:

```bash
docker compose run --rm backend python -m pipeline.replay
```

To stop the application without deleting its database volume:

```bash
docker compose down
```

## Reproduce checks

| Check | Command | Meaning |
| --- | --- | --- |
| Backend tests | `make test` | Uses a separate `heatwave_test` database |
| Syntax and frontend build | `make lint` | Python compile check plus TypeScript/Vite build |
| One forecast cycle | `make pipeline-run` | Refreshes persisted forecast and alert snapshots |
| Evaluation report | `make eval-report` | Reports “not established” if labelled evaluation inputs are absent |
| Frontend build alone | `docker compose run --rm --build frontend npm run build` | Type-check and build |

`make` is optional on Windows: the corresponding Docker Compose commands are in [Makefile](Makefile). The CI workflow runs backend tests and the frontend build on pushes and pull requests.

## Forecast, model, and evidence

The current forecast is **ECMWF IFS 0.25-degree data via Open-Meteo**, sampled at a representative point per district. The 1991-2020 normals and historical replay are ERA5-derived. Neither is an official IMD station feed. Adjacent small districts may share a grid cell.

A zone-specific LightGBM model corrects **daily maximum temperature only**. Its model card reports 97,022 2024-2025 first-lead forecast/ERA5 pairs with leave-one-year-out evaluation. Corrected MAE was lower than raw MAE in the coastal (0.701 to 0.583 deg C), hills (0.944 to 0.733 deg C), and plains (0.631 to 0.542 deg C) groups. These are **gridded ERA5 comparisons, not station-observation validation**, and do not establish day-2 through day-7 alert skill. The model card is at [data/models/bias_model_card.json](data/models/bias_model_card.json).

The thermal calculations include shade and fixed-geometry sun-exposed UTCI scenarios, **estimated** outdoor WBGT, Heat Index, strong-stress-hour count, and an experimental composite HTSI. The two alert tracks are deterministic and versioned. An optional LLM may assist with wording or query parsing, but **never chooses an alert level**.

Public health references are kept separate from operational outcome observations: Census 2011 demographics, four NPCCHH national-seasonal rows (2021-2024), and NCRB annual State/UT records (2018-2022). Their geography/time grains cannot support supervised ward-day mortality training. No approved ward-day outcome dataset is connected, so the system intentionally has **no calibrated 3-5 day mortality or hospitalization forecast**.

## Safety and governance

1. **Freshness and QC:** an operational alert is blocked when essential inputs fail quality checks or the forecast is older than the 12-hour prototype threshold. The interface must display the data age.
2. **Disagreement:** the higher of the temperature and human-stress tracks is issued, and the disagreement is recorded.
3. **Human approval:** CAP Test export, simulated dispatch, and municipal trigger preparation follow role checks and approval; no automatic public delivery occurs.
4. **Clear source scale:** district weather is not ward weather. Ward ranking combines district hazard with population exposure, not a local weather estimate.
5. **Separate health evidence:** relative-risk sensitivity is illustrative and does not yield death/admission counts or drive the operational alert.

**Not production-ready:** the default local database uses trust authentication; demo credentials are public; the audit table is not tamper-evident; government SSO/MFA, real delivery gateways, consent/opt-out, data-governance approvals, and independent IMD/station validation remain outstanding. Production-style deployments must use strict authentication, environment-held secrets, a secured database, CAP `Test` status, and an explicit authority/operational review. The complete [limitations register](docs/LIMITATIONS.md) is part of this README's scope; do not detach the demo from it.

## Configuration

Copy [.env.example](.env.example) to an untracked `.env`. Do not commit secrets.

| Variable | Local default / purpose |
| --- | --- |
| `AUTH_MODE` | `demo`; use `strict` for any network-facing deployment |
| `HEATWATCH_SESSION_SECRET` | Required in strict mode, at least 32 random characters |
| `HEATWATCH_USERS_JSON` | Strict-mode username/password map supplied privately; use provisioned `viewer`, `officer`, or `admin` names |
| `CAP_STATUS` | Keep `Test` until authorized profile and gateway approval |
| `GROQ_API_KEY` | Optional translation/query assistance; templates and keyword parsing work without it |
| `ALLOW_UNPINNED_POPULATION` | Leave `0` unless deliberately accepting a different raster checksum |
| `CDSAPI_URL`, `CDSAPI_KEY` | Only for rebuilding Copernicus normals after accepting the dataset terms |

The current Docker Compose file is a **local development/demo** topology. It should not be published unchanged. Render deployment preparation and its remaining manual connection/secrets steps are documented in [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md).

## Documentation and attribution

- [Project overview](docs/PROJECT_OVERVIEW.md): as-built architecture, pipeline, APIs, and UI.
- [High-level architecture](docs/ARCHITECTURE.md), [pipeline contracts](docs/PIPELINE.md), and [technical stack](docs/TECH_STACK.md): original design; follow the overview and current code when these differ.
- [Demo script](docs/DEMO_SCRIPT.md), [progress log](docs/PROGRESS.md), [research matrix](docs/RESEARCH_MATRIX.md), and [known limitations](docs/LIMITATIONS.md).
- Source and licence manifests live in `config/` for weather, boundaries, population, and public-health data. Basemap attribution is shown in the map.

This product uses the ORGI Census API but is **not endorsed or certified by ORGI**. It is not endorsed by IMD, MoES, NDMA, or any public authority.
