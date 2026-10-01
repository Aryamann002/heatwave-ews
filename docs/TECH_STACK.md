# TECH_STACK.md

> **Design-phase document.** It records the original plan. For the system as built — 641 districts, ERA5 normals, replays, bias correction, dashboard and API — see [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md).

Every choice lists the alternative rejected and why. Anything marked `[JUDGMENT]` is my engineering opinion, not something I verified. Anything marked `[VERIFIED]` I confirmed in search this session.

## Guiding constraint

Assumed: hackathon prototype, small team, free/open data, ~weeks. The stack optimises for **a working end-to-end demo with honest uncertainty**, not for production IMD-grade operations.

**The central design decision:** do NOT train a global forecast model. Consume an existing open forecast, then add value in (1) bias correction, (2) thermal-stress indexing, (3) impact-based alerting, (4) the decision dashboard. Training a weather model in a hackathon is the classic way to burn the whole timeline and end up with something worse than the free forecast.

---

## 1. Data layer

| Need | Choice | Rejected alternative | Why |
|------|--------|----------------------|-----|
| Real-time forecast | **ECMWF open data (IFS + AIFS 0.25°) via `ecmwf-opendata`**, and/or **Open-Meteo API** | Paid APIs (Tomorrow.io, Meteomatics) | [VERIFIED] ECMWF open data is CC-BY-4.0, on AWS/GCP/Azure. Open-Meteo serves IFS 9 km and AIFS 0.25° with hourly interpolation to 15 days. Free. |
| Historical training data | **ERA5-Land / ERA5 via Copernicus CDS**, or Open-Meteo Historical | Scraping IMD | [VERIFIED] ERA5 is free via CDS. Open-Meteo on AWS Open Data exposes ERA5-Land history. Note ERA5 daily updates lag 5–7 days. |
| Thermal-index ground truth | **ERA5-HEAT (UTCI, MRT)** from C3S | Computing your own labels only | [VERIFIED] Di Napoli et al. dataset. Use as a validation target for your own computed UTCI. |
| India observations | **IMD gridded Tmax** (research access) + IMD station data | Crowd-sourced weather | [VERIFIED] Multiple Indian studies use IMD gridded Tmax. **Access terms need checking; I did not verify a public API.** |
| Solar radiation | ERA5 / Open-Meteo `shortwave_radiation`, `direct_radiation` | Ignoring radiation | Needed to get mean radiant temperature; ignoring it makes UTCI/WBGT wrong outdoors. [JUDGMENT on which variable names to request; check Open-Meteo docs] |
| Vulnerability data | Census 2011 + WorldPop / GHSL population grids | Making up vulnerability scores | [JUDGMENT] Census is stale (2011); state this on the dashboard. |

## 2. Thermal stress computation

| Need | Choice | Rejected | Why |
|------|--------|----------|-----|
| UTCI, Heat Index, others | **`pythermalcomfort`** | Hand-rolling equations | [VERIFIED] MIT-licensed, published in SoftwareX, accepts numpy arrays, includes UTCI and Heat Index. Current docs require Python 3.10+. **API changed across major versions (v1.x vs 2.x vs newer). Pin the version and read its docs; do not trust snippets written for older versions.** |
| WBGT | **ECMWF `thermofeel` Liljegren implementation, pinned and reference-tested** | ISO 7243 combination without forecast globe/wet-bulb inputs | Outdoor WBGT needs globe temperature, which forecasts do not provide directly. The system derives an **estimated WBGT** from forecast temperature, humidity, pressure, wind, radiation, and solar geometry. |
| Primary index | **UTCI as primary, WBGT-est as secondary** | WBGT only | [VERIFIED] C1 (Nature Comms 2025) argues UTCI matches or beats WBGT for body temp/perception/labour loss. [VERIFIED] C6 found WBGT best for one hot-arid setting. **The literature disagrees; showing both is the defensible choice.** |
| Composite "Human Thermal Stress Index" | Your own: UTCI category + nighttime recovery + duration + exposure/vulnerability weights | A single raw index | [JUDGMENT] The problem statement asks for a "comprehensive" index. I recommend a composite, but **its weights are an assumption, not validated science. Say so in the docs and expose weights as config.** |

## 3. ML / forecasting layer

| Need | Choice | Rejected | Why |
|------|--------|----------|-----|
| Base forecast | Consume AIFS/IFS. Optionally ensemble several. | Training GraphCast/Pangu/Aurora | [VERIFIED] A8 showed a multi-model ensemble beat individual models. [JUDGMENT] Training is out of hackathon scope. |
| Bias correction | **Gradient boosting (LightGBM/XGBoost) on forecast-vs-ERA5/obs residuals**, per zone | Deep nets for correction | [JUDGMENT] Tabular residual correction is fast, interpretable, debuggable. Directly addresses the humidity bias in A7. |
| Heatwave/heat-stress event classifier | **LightGBM + calibrated probabilities**, with class-imbalance handling | LSTM/Transformer first | [VERIFIED] B2 addresses severe class imbalance; B3 used undersampling. [JUDGMENT] Start with GBM as the baseline; add a sequence model only if it beats it on held-out extreme years. Do not assume deep learning wins. |
| Probability calibration | Isotonic / Platt + reliability diagrams | Raw model scores | [JUDGMENT] An early warning system that emits uncalibrated "80%" is misleading. Calibration is the difference between a demo and a credible tool. |
| Downscaling (stretch goal) | **Start: bilinear + lapse-rate/elevation correction. Stretch: CNN/SR (D6). Stretch-stretch: CorrDiff.** | CorrDiff first | [VERIFIED] D6 is India-specific. [VERIFIED] CorrDiff needs regional training data (D1 trained on Taiwan) and GPU time. [JUDGMENT] Ladder the ambition; ship rung 1 first. |
| Explainability | **SHAP** on the classifier | None | [VERIFIED] B4 uses XAI for heat prediction. [JUDGMENT] Decision-makers ask "why is my district red?" |
| Validation | Temporal split by **year** (leave-one-heatwave-year-out), not random split | Random train/test split | [JUDGMENT] Random splits leak autocorrelated days and inflate scores. This is the most common evaluation error in this domain. |

## 4. Backend

| Need | Choice | Rejected | Why |
|------|--------|----------|-----|
| API | **FastAPI** | Flask / Django | [JUDGMENT] Async, typed, OpenAPI docs free — helpful when an agentic coder generates clients. |
| Geospatial DB | **PostgreSQL + PostGIS** | MongoDB | [JUDGMENT] District polygons, spatial joins, and zonal stats are the core workload. |
| Raster/array handling | **xarray + zarr + netCDF4 + rioxarray** | Loading everything into pandas | [JUDGMENT] Gridded forecasts are N-d arrays. |
| Scheduling | **Prefect** or plain cron/GitHub Actions for a hackathon | Airflow | [JUDGMENT] Airflow is heavy for this scope. |
| Task cache | Redis (optional) | — | Only if latency demands it. |
| Alerts delivery | **Twilio-style SMS/WhatsApp mock + email + CAP XML** | Building real SMS integration | [JUDGMENT] Real telecom integration isn't feasible in a hackathon. **Emit standards-compliant CAP (Common Alerting Protocol) messages and mock the delivery.** I did not verify India's NDMA alert-gateway integration specifics; describe as "CAP-ready, integration-pending". |

## 5. Frontend / GIS dashboard

| Need | Choice | Rejected | Why |
|------|--------|----------|-----|
| App | **React + TypeScript + Vite** | Streamlit | [JUDGMENT] Streamlit is faster to start but weaker for a multi-role civic workflow UI. If the team is Python-only and time is very short, Streamlit is the honest fallback. |
| Map | **MapLibre GL JS** (+ deck.gl for heat layers) | Google Maps / Mapbox | [JUDGMENT] MapLibre is open source, no key/billing surprises. |
| Tiles/vector | OpenStreetMap-derived tiles; district shapefiles from official/open sources | Proprietary tiles | Verify boundary-data licence, especially given India's official-map rules; **use government-sanctioned boundaries.** [JUDGMENT — check compliance] |
| Charts | Recharts / Apache ECharts | — | — |
| i18n | i18next, Hindi + English minimum | English only | [JUDGMENT] Advisories that citizens cannot read do not save lives. |

## 6. Agentic / LLM layer (optional but on-brief for "agentic AI")

The brief asks for a prompt to "vibe code in an agentic AI model." That is about **how you build**, and is separate from whether the product needs an LLM. Be clear-eyed:

- [JUDGMENT] The **alerting decision must be deterministic and auditable** (thresholds + calibrated model). Do not let an LLM decide who gets a red alert.
- An LLM is appropriate for: **drafting localized advisory text** (Hindi/regional languages) from structured alert data, and a natural-language query box over the dashboard. Both are human-reviewed.
- Recommended: Claude via API for advisory drafting, with strict templates and a human approval gate. [JUDGMENT]

## 7. DevOps

Docker + docker-compose, GitHub Actions CI (lint, type-check, unit tests on index math), `.env`-based secrets, one-command local start (`make dev`).

## Tech-stack risks

1. **`pythermalcomfort` API drift.** Pin the version.
2. **CDS/ERA5 queueing** can take hours. Prefetch training data on day 1.
3. **Open-Meteo rate limits / non-commercial terms** — I did not verify current limits. Check before demo day.
4. **GPU access** only matters if you attempt CorrDiff; plan without it.
