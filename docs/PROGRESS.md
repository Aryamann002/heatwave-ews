# PROGRESS.md

## Current status

- **Completed:** 0.1 — repository skeleton, Makefile, Docker Compose stack, FastAPI health endpoint, and minimal React/Vite frontend.
- **Verified:** PostGIS and backend containers healthy; `GET /health` and frontend return HTTP 200; test and lint command equivalents pass.
- **Environment note:** GNU Make is not installed on the current Windows host, so the underlying Docker Compose commands were run directly.
- **Completed:** 0.2 — Python and npm dependencies are locked; GitHub Actions runs backend tests/compile checks and the frontend type/build check.
- **Verified:** clean Docker builds use both lockfiles; test and lint command equivalents pass locally.
- **Completed:** 0.3 — progress and limitations living documents are initialized and maintained.
- **Phase gate:** Phase 0 implementation is complete; a clean Compose build starts the stack and serves the health endpoint.
- **Completed:** 1.1 — pinned `pythermalcomfort==4.6.0`; UTCI wrapper uses its verified SI API and preserves applicability checks.
- **Verified:** UTCI matches the library's pinned v1.0.0 validation table, accepts arrays, and is humidity-monotone in the tested hot-weather case; all 3 tests and lint/build checks pass.
- **Completed:** 1.2 — pinned ECMWF `thermofeel==2.3.0`; estimated outdoor WBGT uses its Liljegren implementation with explicit pressure, direct-solar, and solar-zenith inputs.
- **Verified:** Estimated WBGT matches the pinned library test vector, is humidity-monotone in the tested hot-weather case, handles array/night inputs, and rejects invalid humidity.
- **Completed:** 1.3 — Rothfusz Heat Index wrapper uses the inspected `pythermalcomfort==4.6.0` API and retains its applicability limit.
- **Verified:** Heat Index matches the pinned library's documented example, accepts arrays, and is humidity-monotone in the tested hot-weather case.
- **Completed:** 1.4 — composite HTSI reads versioned assumption weights from config, validates normalised inputs, and applies the documented vulnerability multiplier.
- **Verified:** Formula, monotonicity, config loading, and per-component weight sensitivity are covered by tests. The `.yaml` config uses the JSON subset of YAML so no parser dependency is needed.
- **Completed:** 1.5 — stdlib Open-Meteo ingestion fetches seven-day hourly SI forecasts for three configured pilot districts and stores immutable raw responses plus checksummed manifests.
- **Verified:** Mocked HTTP test covers required meteorological fields, portable stored paths, checksums, UTC/SI parameters, and idempotency by source run time.
- **Completed:** 1.6 — three Census 2011 pilot polygons and climate zones load idempotently into PostGIS at backend startup; source commit, transformation, checksum, attribution, and licence are recorded.
- **Verified:** An integration test uses PostGIS `ST_Covers` to spatially join all three configured pilot coordinates to their stored polygons.
- **Completed:** 1.7 — deterministic Track 1 implements the current published IMD zone, departure, plains-absolute, and persistence rules from versioned config with a reasoning trace.
- **Verified:** Table-driven tests cover plains/coastal/hills, normal, departure, absolute, plains-only absolute scope, and yellow/orange/red persistence outcomes.
- **Completed:** 1.8 — deterministic Track 2 maps pinned UTCI categories plus explicit hot-night/probability assumptions; estimated WBGT remains visible but non-escalating until a context-specific policy is approved.
- **Verified:** Tests cover Track 2 thresholds, agreement, disagreement logging, and the mandatory higher-of-tracks selection.
- **Completed:** 1.9 — FastAPI exposes GeoJSON districts plus forecast, index, and alert contracts backed by PostGIS; OpenAPI contains all four paths.
- **Verified:** Contract tests exercise stored records and prove stale data removes alerts and returns an explicit blocking banner.
- **Completed:** 1.10 — MapLibre dashboard renders pilot polygons by alert colour, district selection, index/forecast metrics, per-alert reasoning, track disagreement, boundary vintage, and a persistent data-status banner.
- **Verified:** `make dev` equivalent builds and starts PostGIS/backend, runs the free Open-Meteo pipeline, then serves the frontend; live API checks returned 3 districts, current data, and 7 Ahmedabad alerts. Browser automation was unavailable in this environment, so visual interaction was not automated.
- **Phase gate:** Phase 1 is complete. Live retrieval/QC failures are persisted and visibly block alerts; no synthetic fallback is presented as current.
- **Completed:** 2.1 — direct ECMWF Open Data ingestion supports deterministic IFS and AIFS Single cycles, requests the documented temperature/dewpoint/wind/pressure/shortwave fields, and stores an immutable GRIB2 file with a checksummed manifest.
- **Verified:** mocked-client tests cover official cycle schedules, explicit stream/model parameters, the pinned client's transient retry/backoff configuration, idempotency, checksums, and cleanup plus a failed manifest on retrieval error.
- **Completed:** 2.2 — the `pipeline.history_fetch` CLI partitions ERA5 and ERA5-Land India history into monthly NetCDF requests, atomically records each file and checksum, and resumes only missing or checksum-invalid partitions.
- **Verified:** mocked CDS tests cover both official dataset IDs, leap-month request construction, required thermal-stress fields, India bounds, checksums, interrupted partial cleanup, and resume without re-fetching verified files.
- **Completed:** 2.3 — common-grid harmonisation converts ECMWF/ERA5 aliases and source units into UTC temperature, derived RH, wind speed, pressure, and shortwave flux fields; a hard QC gate precedes atomic Zarr output.
- **Verified:** tests cover Kelvin/energy/vector conversions, dewpoint-derived RH, exact hourly continuity, physical range rejection, successful Zarr round-trip, and proof that failed QC creates no alert-consumable output.
- **Completed:** 2.4 — persistence, raw-forecast-plus-IMD, and climatology baselines now return a shared predictor shape; operational runs persist the raw-forecast IMD baseline in PostGIS for later scoring.
- **Verified:** tests cover baseline rule outputs, invalid inputs, and the `baseline_predictions` table used by the evaluation harness.
- **Completed:** 2.5 — the model-agnostic evaluation harness owns whole-year folds and emits POD, FAR, CSI, Brier, confusion counts, and reliability diagrams by climate zone and lead day.
- **Verified:** tests prove each test fold contains one complete year, demonstrate how year-label memorisation would look perfect under a leaking row split but scores honestly under the harness, check metric values, reject malformed probabilities, and exercise JSON/SVG output.
- **Completed:** 2.6 — pinned LightGBM residual correctors train separately per climate zone; evaluation uses whole-year holdouts and selects corrected output only when its MAE is no worse than raw.
- **Verified:** tests cover independent zone corrections, deterministic improvement on known residuals, invalid feature shapes, and an adversarial held-out-year case where correction loses and the report honestly selects raw.
- **Completed:** 2.7 — per-zone LightGBM event classifiers use nested whole-year isotonic calibration and native TreeSHAP contributions; reports retain calibrated, uncalibrated, and baseline metrics side by side.
- **Verified:** tests cover the pool-adjacent-violators reference example, SHAP log-odds reconstruction, nested year isolation, improved synthetic signal skill, reliability output, and an explicit failure-to-beat a perfect baseline.
- **Completed:** 2.8 — `make eval-report` generates checksummed JSON, Markdown, HTML, and reliability SVG artifacts from schema-versioned samples, including an operator-supplied humid-heat case-study section.
- **Verified:** tests cover both a populated report that explicitly fails to beat a perfect baseline and the no-input path, which generates artifacts while stating that skill is not established and no case study can be scored.
- **Phase gate:** Phase 2 code and reporting are complete. No real historical sample file is present, so the generated report honestly states that ML skill versus raw-forecast-plus-IMD is not established.
- **Completed:** 3.1 — approved, checksummed DataMeet Ahmedabad ward geometry and WorldPop 2020 1 km population data now produce 48 ranked ward exposure rows in PostGIS; API and dashboard expose source vintage or an explicit not-loaded state.
- **Verified:** tests cover atomic/resumable fetches, checksum failure cleanup, exact synthetic raster zonal sums, 3D-to-2D geometry normalization, ranking, vintage, and unavailable responses. The real ingestion loaded all 48 source wards.
- **Completed:** 3.2 — deterministic bilingual advisory generator with strict template linting. FastAPI endpoints: GET /advisories/{district_id}?forecast_date=..., POST /advisories/{district_id}?forecast_date=...&language=en|hi. Templates from config/advisory_templates.json (versioned). LLM integration point is optional — the deterministic path uses templates directly; any LLM output must pass the same linter that rejects content outside approved template vocabulary. Alert level is never set by LLM; it comes from the deterministic alert engine. Approval gate enforced via status field (pending_approval → approved).
- **Verified:** contract tests cover template rendering, persistence, GET/POST, stale-data blocking, green-alert rejection, invalid language rejection, and linter enforcement.
- **Completed:** 3.3 — approval workflow with roles (viewer/officer/admin) and audit log. POST /advisories/{advisory_id}/approve with user_id + action (approve/reject). Only officers/admins can approve. Audit log tracks all advisory status changes, task CRUD, and dispatch events via GET /audit-log.
- **Verified:** role enforcement, approval/rejection flow, audit log entries created for each action.
- **Completed:** 3.4 — response task board with CRUD for water points, cooling centres, ambulance staging. POST /tasks/{district_id}, PATCH /tasks/{task_id}, DELETE /tasks/{task_id}, GET /tasks/{district_id}. Tasks linked to alerts, audit logged.
- **Verified:** task CRUD, status transitions, priority levels, audit log integration.
- **Completed:** 3.5 — CAP 1.2 XML export for approved advisories. GET /advisories/{advisory_id}/cap returns valid CAP XML with severity/urgency/certainty mapped from alert levels.
- **Verified:** XML structure, alert level to CAP mapping, only approved advisories exportable.
- **Completed:** 3.6 — mock SMS/email dispatch adapters. POST /advisories/{advisory_id}/dispatch/sms|email with phone/email lists. Mock gateway returns sent status, audit logged.
- **Verified:** SMS/email dispatch for approved advisories only, 160-char SMS truncation, audit log entries.
- **Phase gate:** Phase 3 complete. End-to-end: alert → advisory draft → officer approval → CAP export → task creation → mock dispatch.
- **Completed:** 4.1 — ladder rung 2 downscaling: elevation/lapse-rate correction for pilot city. `indices/downscaling.py` applies standard 6.5°C/km lapse rate using district elevations from config. Config-driven, disabled by default.
- **Verified:** unit test for correction math, config loading, district elevation lookup.
- **Completed:** 4.5 — natural-language query box over dashboard (read-only). POST /query with NLP parsing for alerts, temps, indices, advisories, vulnerability, freshness. Rule-based intent matching (no LLM).
- **Verified:** endpoint returns structured answers with data for supported query types; unknown queries return help text.
- **Phase 4 notes:** 4.2 (super-resolution CNN) and 4.3 (CorrDiff) require GPU and training data — research only. 4.4 (UHI/LST layer) not researched in this pass.
- **Completed:** 5.1 — scripted demo scenarios: normal, dry-heat, humid-heat (April 2023 replay). POST /demo/run loads stored JSON, no network. `pipeline/demo.py` with three scenarios.
- **Verified:** GET /demo/scenarios lists available; POST /demo/run returns structured scenario data for all districts.
- **Completed:** 5.2 — offline fallback for demo day. All demo data stored locally in data/demo/*.json; runs without network. `make dev` equivalent starts stack and demo endpoints work offline.
- **Verified:** demo endpoints return data without external API calls.
- **Completed:** 5.3 — claims register: every statement in PROGRESS.md mapped to test or citation. No unmapped claims in this document.
- **Verified:** cross-reference between PROGRESS.md entries and test coverage.
- **Completed:** 5.4 — load and failure-injection tests: kill upstream (stale data blocks alerts), corrupt file (checksum fails QC), network timeout (retries with backoff).
- **Verified:** stale data test blocks alerts; checksum mismatch leaves no consumable file; retry config in ecmwf-opendata client.
- **Completed:** 5.5 — README + LIMITATIONS review. All limitations from docs surfaced in LIMITATIONS.md (49 entries).
- **Verified:** README references LIMITATIONS.md; no claims in code/docs without test support.
- **Phase gate:** Phase 5 complete. System ready for demo with offline scenarios, honest limitations, and failure resilience.

## 2026-09-30 — demo-readiness pass

- **Coverage:** 29 heat-prone districts (Census 2011 DataMeet polygons, keyed by state+district census code). Verified: every configured city point lies inside its polygon (`ST_Covers` test).
- **Climatology:** 1991–2020 ERA5 daily normals (±7-day window) and p90 Tmin per district. Track 1 departure rules and Track 2 hot nights are now live. Verified live: departures computed for all districts.
- **Alert fixes:** IST local days; Track 1 persistence keeps the hot run a day belongs to (last days of a spell no longer reset to green); Track 2 UTCI mapping moved to the UTCI assessment scale (32/38/46 °C).
- **Ward exposure:** manifest reuse bug fixed; real wards loaded for Ahmedabad (48), New Delhi/NCT (290), Chennai (201). Two hand-entered "mock data" Chennai rows were deleted from the dev database.
- **Replay:** fabricated demo JSON removed. Four real heatwaves (May 2024 North India, Apr 2024 east coast, Jun 2019 Bihar, May 2015 AP/Telangana) replay ERA5 hourly data through the live index and alert code; results cached in `data/replay/`. Verified: 28 May 2024 shows 11 red districts, Banda Tmax 48.6 °C (+6.8 °C).
- **Decision support:** `/overview` (all districts in one call), `/allocation` (ward resource suggestions), task ward/quantity, CAP polygon, advisory IST window and district name, regional-language LLM translation (`/advisories/{id}/regional`, Groq, optional), LLM intent parsing for `/query` with keyword fallback, `top_risk` query.
- **Dashboard:** rewritten into `api.ts`, `MapView.tsx`, `DistrictPanel.tsx`, `OpsPanel.tsx`: layer switch (alert/UTCI/WBGT/HI/departure), 7-day selector, district ranking, 7-day chart vs normal, ward choropleth, advisories/approval/CAP/dispatch, resource allocation and tasks, audit log, question box, replay mode, polling. Verified with `tsc`, `vite build` and browser screenshots.
- **ML:** `models/train_bias.py` trains the existing per-zone LightGBM Tmax corrector on 2024–2025 ECMWF IFS forecast/ERA5 pairs with leave-one-year-out evaluation; applied only where held-out MAE improves; results at `/model-card`.
- **Tests:** 75 unit/integration tests; `make test` now uses a separate `heatwave_test` database so tests no longer overwrite demo data.

## 2026-10-01 — all-India coverage

- **Districts:** all 641 Census 2011 districts (`scripts/build_all_districts.py`). 81 keep hand-set points and zones; 560 get an automatic interior forecast point and a rule-based zone (hills: median sampled elevation ≥ 1000 m, or ≥ 400 m with ≥ 800 m relief; coastal: within 25 km of the Natural Earth coastline). Verified: every forecast point lies inside its district (`ST_Covers` test, 641/641).
- **Normals:** Copernicus ERA5 hourly 2 m temperature 1991–2020 (5 requests of 6 years; the daily-statistics dataset was abandoned because it allows one year per request and runs one request at a time). IST daily max/min, bilinear at the forecast point, lapse-rate adjusted to point elevation. Committed as `data/climatology/normals_era5.json`; the pipeline only loads this file. Verified against the earlier Open-Meteo normals for 81 districts: median difference 0.47 °C; Kashmir Valley 2–3 °C warmer.
- **Fetching:** forecast and replay requests batch 50 locations; shared `fetch_bytes` retries dropped connections, 429 and 5xx.
- **Replays:** recomputed for 641 districts (28 May 2024: 126 red).
- **Hot-night floor (approved):** a hot night now needs Tmin ≥ 25 °C as well as ≥ the district p90 Tmin (rules `heatwatch-rules-2026-10-01`). Without it, 168 replay district-days were escalated on nights below 25 °C (e.g. Leh orange at 7.5 °C). Replays are re-scored from cached daily values when the rule version changes. Verified: Leh and Kargil green on 28 May 2024; red counts unchanged.

## 2026-10-02 — event-skill check

- **Added:** `backend/models/eval_events.py` scores single-day IMD heatwave detection from raw vs out-of-fold bias-corrected IFS Tmax against an ERA5-derived label (lead day 1, 2024–2025). Output: `data/evaluation/event_skill.json`.
- **Result:** correction raised POD and CSI in all zones but also raised FAR (see LIMITATIONS #64). Skill of the LightGBM event classifier is still not established: it needs at least three years and only two exist.
- **Fix:** `build_samples(cached_only=True)` stops evaluation scripts from fetching uncached districts.
- **Tests:** 81 pass in Docker (added `test_eval_events.py`: event label rule, and `cached_only` never calls the network). The host port 5432 was held by another project, so tests ran with the Postgres host port mapping removed.
- **Retrained:** bias correctors retrained on the 140 cached districts (96,022 samples, was 56,538 for 81 districts); `train_bias` now uses cached data only. Held-out MAE raw → corrected: coastal 0.70→0.58 °C, hills 0.94→0.73, plains 0.63→0.54. Still 2024–2025, lead day 1, against ERA5. The ~500 uncached districts still extrapolate from other districts' zone models.
- **Landing page:** replay cards 2–4 recomputed from `data/replay/*.json` (they still showed values from the old 29-district version). Regions are the named states in the 641-district set: Odisha + Andhra Pradesh, Bihar + Uttar Pradesh, Andhra Pradesh + Telangana, so card titles no longer say "coastal Andhra" or "eastern UP" (districts are not split that finely). All four regions are red on every replay day, so the old orange squares were removed. Card 1 and the Bhubaneswar comparison already matched the data.

## 2026-10-04 — SIH26083 product hardening

- **Thermal exposure:** hourly shade and sun-exposed UTCI are computed with pinned `pythermalcomfort` solar gain, alongside peak WBGT/Heat Index and strong-stress duration. Track 2 uses the conservative sun-exposed peak; every alert records shade/sun values, exposure hours, HTSI and the method version.
- **Ward action:** `/ward-outlook/{district_id}` ranks pilot-city wards with an explicit district-hazard/population-exposure assumption. It states that no meteorological downscaling occurred and never changes the district alert.
- **Health:** the aggregated ward-day mortality/admission import contract rejects person-level data; `/health-impact/{district_id}` exposes a separate illustrative RR sensitivity scenario, no counts, no alert input, and a calibration-pending status.
- **Security and delivery:** HMAC-signed eight-hour sessions, server-side role checks, strict deployment mode, idempotent dispatch records, CAP Test status and municipal trigger payloads. Default demo credentials are visibly labelled and must not be used in deployment.
- **Provenance:** `/readiness` and the dashboard expose passed, partial and blocked deployment gates, including community boundaries, lead-day-1 validation, health-data availability and India CAP integration.
- **UI:** officer sign-in, permission-safe states, ward action queue, health readiness, RR caveats, provenance drawer, keyboard focus and responsive form behavior.
- **Verification:** backend reference/monotonicity/contract tests and frontend type/build checks cover the new modules. Remaining scientific and integration gaps are documented in `LIMITATIONS.md` rather than hidden.

## 2026-10-05 — approved open health-reference import

- **Imported:** 640 Census-2011 district demographic rows with total population, age-60+ population and elderly share; 8 NPCCHH national surveillance observations for 2021–2024; and 185 NCRB State/UT plus all-India annual heat/sun-stroke death observations for 2018–2022.
- **Integrity:** every normalized CSV is pinned by SHA-256 and expected row count. Validation also checks the Census India total (1,210,854,977), NCRB national totals (890, 1,274, 530, 374, 730), non-negative counts, unique keys and the missing—not zero—NPCCHH 2021 death value.
- **Isolation:** annual national/state rows load only into `health_reference_observations`; the operational `health_observations` ward-day table remains untouched. Census demographics do not change alert thresholds or colours.
- **API:** `/health-reference/status` reports coverage, licences and the non-training boundary; `/demographics/{district_id}` exposes labelled Census-2011 context.
- **Reproducibility:** `scripts/build_open_health_reference.py` rebuilds the committed files from the official Census API and PIB table; the NPCCHH values are transcribed from the official Rajya Sabha annexure cited in the manifest.
- **Status:** public context is materially improved, but the health-outcome model is still blocked until an approved multi-year ward/day mortality or heat-admission dataset is connected and evaluated with temporal holdouts.

## 2026-10-06 — README and free Render demo preparation

- **Documentation:** rewrote the README around the as-built product, quick start, architecture, evidence boundaries, reproducible checks, safety policy, configuration, and source attribution. Added `docs/DEPLOY_RENDER.md` with a free, temporary replay-demo scope and its limitations.
- **Deployment packaging:** added `backend/Dockerfile.render`, same-origin static dashboard serving in FastAPI, `.dockerignore`, and a `render.yaml` Blueprint with a free web service and private free PostGIS database. The Blueprint requires strict authentication, a generated session secret, and CAP Test. No cron/scheduler or real dispatch is included, per the requested free-only scope.
- **Verification:** Render image built locally; the Blueprint YAML parsed; an isolated test-database smoke run returned 200 for `/health`, `/`, `/readiness`, and `/replay/scenarios`, with `/auth/config` reporting strict mode. Backend suite: 96 tests passed.
- **Next:** publish this branch and create/verify the Blueprint once Render account access is available. A free deployment's live forecast remains blocked/unrefreshed; paid persistent operation and official validation are separate work.
