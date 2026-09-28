# Heatwave EWS

Extreme Heatwave Early Warning & Human Thermal Stress Index system (MoES / Disaster Management).

## Quick start

```bash
make dev          # start backend + frontend
make test         # run all tests
make lint         # lint backend + frontend
make pipeline-run # run full pipeline once
```

## Structure

```
heatwave-ews/
├── AGENTS.md                 # Agent rules (read every session)
├── config/                   # Runtime config (YAML + GeoJSON)
│   ├── htsi_weights.yaml     # Composite index weights
│   ├── alert_rules.yaml      # Alert thresholds & logic
│   ├── districts.yaml        # District metadata
│   └── pilot_districts.geojson
├── backend/
│   ├── app/                  # FastAPI service
│   ├── pipeline/             # s1_fetch ... s9_publish stages
│   ├── indices/              # UTCI, WBGT-est, Heat Index, Composite
│   ├── models/               # Bias correction, classifier, calibration
│   └── tests/                # Pytest suite
├── frontend/                 # React + Vite + TS
│   └── src/
├── docs/                     # Architecture, pipeline, progress, limitations
├── docker-compose.yml
├── Makefile
└── requirements.txt / package.json
```

## Key commands

| Command | Description |
|---------|-------------|
| `make dev` | Start dev servers (backend:8000, frontend:5173) |
| `make test` | Run pytest + vitest |
| `make lint` | ruff + mypy + eslint |
| `make pipeline-run` | Execute s1→s9 once |
| `make eval-report` | Generate evaluation metrics |

## Data flow

1. **Fetch** — ERA5-Land (hist), ECMWF (fcst), Open-Meteo (obs)
2. **Harmonise** — Common grid, units, QC flags
3. **Indices** — UTCI, WBGT-est, HI per grid cell
4. **Composite (HTSI)** — Weighted blend per district
5. **Alert tracks** — IMD criteria (T1) + Human stress (T2)
6. **Publish** — API + GeoJSON + advisory draft (human approval required)

## Safety-critical notes

- Alert decision path is **deterministic** — no LLM involvement
- QC failure = block alert, show data age banner
- Track disagreement → take higher level, log conflict
- Every alert stores: model versions, rule version, run IDs, reasoning trace
- Advisory dispatch requires human approval (no auto-send)

## Documentation

| File | Purpose |
|------|---------|
| `docs/PRD.md` | Scope, users, success metrics, non-goals |
| `docs/ARCHITECTURE.md` | Layers, alert logic, data model, failure modes |
| `docs/PIPELINE.md` | Stage contracts & evaluation protocol |
| `docs/TECH_STACK.md` | Choices, rejected alternatives, reasons |
| `docs/IMPLEMENTATION_PLAN.md` | Phased tasks with acceptance criteria |
| `docs/LIMITATIONS.md` | Known limitations (appended during dev) |
| `docs/PROGRESS.md` | Running log of completed work |

## Environment

```
# Backend (.env)
OPEN_METEO_API_KEY=
ECMWF_API_KEY=
ERA5_API_KEY=
DATABASE_URL=postgresql://...
```

## License

Internal use — MoES / Disaster Management.