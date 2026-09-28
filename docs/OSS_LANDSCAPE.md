# OSS_LANDSCAPE.md

**Honesty note.** I confirmed the existence of the projects in the first table via search this session. For most I did **not** verify current maintenance status, latest release date, or stars. Licence is only listed where I saw it stated. Anything else says `CHECK`. Before you adopt any dependency: open its repo, check last commit date, open issues, and licence file. A dead dependency in the critical path is a demo-day risk.

## Tier 1 — Core, adopt

| Project | What it gives you | Verified facts | CHECK before use |
|---------|-------------------|----------------|------------------|
| **pythermalcomfort** (CenterForTheBuiltEnvironment) | UTCI, Heat Index, Humidex, WBGT, PMV/PPD; numpy-array input | MIT licence (stated on docs site); published SoftwareX 2020; docs say Python 3.10+; Numba-optimised UTCI per changelog | Current version and API (it changed across v1/v2/later); confirm WBGT function signature and whether it needs a globe temperature |
| **ecmwf-opendata** | Python client for ECMWF open IFS/AIFS data | ECMWF data is CC-BY-4.0; package uses MARS-style requests (per AWS registry page) | Field names available for AIFS vs IFS; download size per run |
| **Open-Meteo** (API + open-data on AWS + Docker image) | Free forecast/historical API incl. ECMWF IFS/AIFS; ERA5-Land archive | Serves IFS 9 km and AIFS 0.25°, hourly interpolation to 15 days (per its docs page); ERA5 daily updates lag 5–7 days | **Current free-tier rate limits and non-commercial terms — not verified.** Self-hosting via Docker exists per repo README |
| **xarray / zarr / netCDF4** | Gridded data handling | — | Standard; low risk |
| **PostGIS / PostgreSQL** | Spatial queries | — | Standard; low risk |
| **FastAPI** | API layer | — | Standard; low risk |
| **MapLibre GL JS** | Open-source web maps | — | Check current major version |
| **LightGBM / XGBoost / scikit-learn / SHAP** | Classifier, calibration, explainability | — | Standard; low risk |

## Tier 2 — Stretch, adopt only if Tier 1 is done

| Project | Use | Verified facts | Risk |
|---------|-----|----------------|------|
| **earthkit / Anemoi** (ECMWF) | AI-weather data pipeline tooling | ECMWF publication describes earthkit and Anemoi as shared foundations for AI weather development | Heavy; steep learning curve for a hackathon. `CHECK` maturity/docs |
| **NVIDIA Earth-2 / PhysicsNeMo (CorrDiff implementation)** | Reference CorrDiff downscaling | CorrDiff paper is real (D1). A reference implementation is widely associated with NVIDIA's stack | **I did not verify the repo, its licence, or install path this session. CHECK.** Needs GPU |
| **Microsoft Aurora (open weights / fine-tuning code)** | Fine-tunable Earth-system foundation model | Aurora paper is real (A1); paper states low-cost fine-tuning | **I did not verify weight licence or code availability. CHECK.** GPU required |
| **GraphCast (google-deepmind/graphcast)** | Baseline global AI model | Repo URL appears in a survey's tool list (arXiv 2312.03014) | Licence and weights terms CHECK; JAX stack |
| **FourCastNet (NVlabs/FourCastNet)** | Baseline; open | Repo URL appears in the same survey | Licence CHECK |
| **Pangu-Weather (198808xc/Pangu-Weather)** | Baseline | Repo URL appears in the same survey | Licence historically restrictive for some uses — **CHECK before any use** |
| **ClimaX (microsoft/ClimaX)** | Forecast + downscaling foundation model | In the same survey's list | Maintenance CHECK |
| **Prithvi WxC (IBM)** | Forecast/downscaling foundation model | Listed in a foundation-model table (arXiv 2605.12542) | Weights availability CHECK |

## Tier 3 — Frontend, ops, quality

| Project | Use | Note |
|---------|-----|------|
| deck.gl | GPU heat layers over MapLibre | CHECK version compatibility with MapLibre |
| Recharts / Apache ECharts | Time-series and bar charts | Standard |
| i18next | Hindi/English UI | Standard |
| Prefect | Pipeline scheduling | Lighter than Airflow |
| Great Expectations or Pandera | Data validation in the pipeline | Catches broken upstream data before it becomes a false alert |
| MLflow (or plain JSON logs) | Experiment tracking | Optional |
| Docker / docker-compose | Reproducible run | Standard |
| Playwright | E2E dashboard test | Optional |

## Data/standards to build to (not "projects" but they raise credibility)

| Standard | Why | Status |
|----------|-----|--------|
| **CAP (Common Alerting Protocol)** | Machine-readable alert format used by disaster agencies | Concept is standard; **I did not verify which CAP profile India's NDMA/IMD uses. CHECK.** |
| **IMD colour-code system** (green/yellow/orange/red) | Verified in press coverage: green = no action, yellow = watch, orange = be prepared, red = take action | Reuse this vocabulary so outputs are legible to officials |
| **IMD heat wave criteria** | See RESEARCH_MATRIX E4 | May be under revision per May 2026 press. Re-check |

## Repos worth reading, not necessarily depending on

- Any GitHub heatwave-prediction repos accompanying B1/B2 papers (`CHECK` whether code is released).
- Open-Meteo's `open-data` repo for a self-hostable weather archive (verified to exist).

## What I would deliberately NOT adopt

- **Training-from-scratch weather models.** Wrong cost/benefit for the timeline.
- **Unvetted "heatwave prediction" GitHub notebooks** with random train/test splits. They give great-looking, invalid scores.
- **Proprietary map SDKs** that require billing keys during a live demo.
