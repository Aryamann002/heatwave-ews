# IMPLEMENTATION_PLAN.md

Each task is sized for one agent session, has acceptance criteria, and lists the doc sections it depends on. Build in order; do not skip ahead. **Phase 1 delivers a demo-able product by itself.** Later phases add depth.

Time estimates are deliberately omitted; I have no basis for your team's speed. Use the phase gates instead.

---

## Phase 0 — Scaffold

| ID | Task | Acceptance |
|----|------|------------|
| 0.1 | Repo skeleton per AGENTS.md layout; Makefile; docker-compose (postgres+postgis, backend, frontend) | `make dev` starts all services; health endpoint returns 200 |
| 0.2 | Pin deps; CI running lint + tests | CI green on empty tests |
| 0.3 | `docs/LIMITATIONS.md` and `docs/PROGRESS.md` created | Files exist with headers |

**Gate 0:** clean clone → `make dev` works.

## Phase 1 — Vertical slice (indices → alert → map)

| ID | Task | Acceptance |
|----|------|------------|
| 1.1 | `indices/utci.py` wrapping `pythermalcomfort` (pinned) | Reference-value tests pass; array input works; monotonicity test passes |
| 1.2 | `indices/wbgt_est.py` (estimated WBGT from T, RH, wind, radiation) | Documented as an estimate; tests vs library reference; edge cases |
| 1.3 | `indices/heat_index.py` | Matches library / published table |
| 1.4 | `indices/composite.py` + `config/htsi_weights.yaml` | Weights read from config; sensitivity-analysis function exists |
| 1.5 | Fetch one forecast source (Open-Meteo first — simplest) for N pilot districts | Manifest stored; idempotent; mocked-HTTP tests |
| 1.6 | District polygons + climate-zone table in PostGIS | Spatial join test passes; source + licence recorded |
| 1.7 | Alert engine Track 1 (IMD criteria) from `config/alert_rules.yaml` | Table-driven tests incl. plains/coastal/hills, departure and absolute cases |
| 1.8 | Alert engine Track 2 (human-stress) + max-of-tracks + disagreement log | Tests cover agreement and disagreement |
| 1.9 | FastAPI endpoints: districts, forecast, indices, alerts | OpenAPI generated; contract tests |
| 1.10 | Minimal dashboard: MapLibre district choropleth, colour-coded alert, data-age banner | Loads seed data; banner shows on stale |

**Gate 1 (demo #1):** map of pilot districts coloured by alert level, with a reasoning panel and visible data age.

## Phase 2 — Real data + evaluation

| ID | Task | Acceptance |
|----|------|------------|
| 2.1 | ECMWF open-data fetcher (IFS/AIFS) | Fields listed in `PIPELINE.md`; retry/backoff; checksum |
| 2.2 | ERA5 / ERA5-Land history fetch (prefetch script) | Cached; resumable |
| 2.3 | Harmonise/QC stage on zarr | Range/gap/unit tests; QC failure blocks alerts |
| 2.4 | Baselines: persistence, raw-forecast+IMD, climatology | Implemented as comparable predictors |
| 2.5 | Leave-one-year-out evaluation harness | Produces POD/FAR/CSI/Brier + reliability plots per zone and lead day |
| 2.6 | Bias-correction model per climate zone (LightGBM) | Corrected error ≤ raw error on held-out years, or reported honestly if not |
| 2.7 | Event classifier + isotonic calibration + SHAP | Calibration report; comparison against baselines |
| 2.8 | `make eval-report` → generated Markdown/HTML report | No manual edits; includes humid-heat case study |

**Gate 2:** an evaluation report exists and states honestly whether the ML layer beats the raw-forecast+IMD baseline.

## Phase 3 — Decision-support workflow

| ID | Task | Acceptance |
|----|------|------------|
| 3.1 | Vulnerability layer (census/WorldPop) with vintage label | Ranked wards; data vintage visible |
| 3.2 | Advisory generator: templates + Hindi/English; optional LLM fill | Template lint; LLM output never sets alert level; approval gate enforced |
| 3.3 | Approval workflow + roles (viewer/officer/admin) | Officer approval required; audit log |
| 3.4 | Response task board (water points, cooling centres, ambulance staging) | CRUD; linked to alerts |
| 3.5 | CAP message export | Validates against CAP schema (verify which profile applies) |
| 3.6 | Mock SMS/email adapters | Clearly labelled mock |

**Gate 3 (demo #2):** alert → approve advisory → dispatch tasks, end-to-end.

## Phase 4 — Stretch (only if Gates 1–3 pass)

| ID | Task | Note |
|----|------|------|
| 4.1 | Ladder rung 2 downscaling: elevation/lapse-rate correction for pilot city | Cheap and honest |
| 4.2 | Rung 3: super-resolution CNN (RESEARCH_MATRIX D6) for pilot city | Needs training data prep |
| 4.3 | Rung 4: CorrDiff-style (D1, D8, D9) | GPU required; treat as research, not demo-critical |
| 4.4 | Urban heat island layer (LST) for intra-city | Not researched in this pass — research first |
| 4.5 | Natural-language query box over the dashboard | Read-only |

## Phase 5 — Hardening and demo

| ID | Task | Acceptance |
|----|------|------------|
| 5.1 | Scripted demo scenarios: normal, dry-heat, humid-heat (e.g. replay April 2023) | Replay mode runs from stored data, no network |
| 5.2 | Offline fallback for demo day | Works with wifi off |
| 5.3 | Claims register: every statement in slides mapped to a test or citation | No unmapped claims |
| 5.4 | Load and failure-injection tests (kill upstream, corrupt file) | System degrades as designed |
| 5.5 | README + LIMITATIONS review | All limitations from docs surfaced |

## Cut line

If time runs short: ship Phases 0–1 fully, Phase 2 through 2.5, and Phase 3 through 3.3. A smaller system with an honest evaluation beats a larger one with none.
