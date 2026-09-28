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
- **Next:** 2.4 — implement persistence, raw-forecast-plus-IMD, and climatology baselines as comparable predictors.
