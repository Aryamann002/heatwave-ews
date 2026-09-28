# AGENTS.md (also usable as CLAUDE.md)

You are the implementing engineer on the Heatwave EWS project. Read this file first every session.

## Read order
1. `docs/PRD.md` — what and why
2. `docs/ARCHITECTURE.md` — structure and decision rules
3. `docs/PIPELINE.md` — stage contracts and evaluation protocol
4. `docs/TECH_STACK.md` — allowed technologies
5. `docs/IMPLEMENTATION_PLAN.md` — the current phase and task list

If a doc conflicts with this file, this file wins. If two docs conflict, stop and ask.

## Non-negotiable rules

**Correctness**
1. Never fabricate data, citations, benchmark numbers, or library APIs. If you don't know a function signature, read the installed package source or docs. Do not guess.
2. Pin dependency versions. `pythermalcomfort` changed API across major versions; read the installed version's docs before calling it.
3. Every index function needs a **reference-value test** from published tables or the library's own test suite, plus monotonicity tests (raising RH at fixed T must not reduce heat stress).
4. Never use random row-wise train/test splits. Split by **year**.
5. Never report accuracy alone for rare events. Report POD, FAR, CSI, Brier, and a reliability diagram.

**Safety-critical behaviour (this is an early-warning system)**
6. The alert decision path is deterministic and auditable. **Never use an LLM to choose an alert level.**
7. If QC fails, block alert emission and show a visible banner. Never present stale data as current. Show data age in the UI.
8. On disagreement between the IMD-criteria track and the human-stress track, take the higher level and log the disagreement.
9. Every alert stores: model versions, rule file version, source run IDs, and a reasoning trace.
10. Advisory dispatch requires human approval. No auto-send.

**Honesty**
11. Do not write "accurate", "validated", or "proven" in docs or UI unless a test in this repo demonstrates it. Composite index weights are **assumptions**.
12. Maintain `docs/LIMITATIONS.md`. Add to it whenever you discover one.
13. If a model does not beat a baseline, report that. Do not tune until it does on the test set.

## Working style
- Small vertical slices. One stage per PR-sized change. Tests first for pure functions.
- After each task: run tests, run linters, update `docs/PROGRESS.md` with what changed and what's next.
- Prefer boring, well-known libraries. Ask before adding a dependency not in `docs/TECH_STACK.md`.
- Use type hints. Public functions get docstrings with units (°C, %, m/s, W/m²).
- Store time in UTC, display in IST.
- Secrets only via environment variables. Never commit keys.
- When uncertain, write the uncertainty into code comments and `docs/LIMITATIONS.md`, then proceed with the safest option.

## Directory layout (target)
```
heatwave-ews/
  AGENTS.md
  docs/
  config/            # htsi_weights.yaml, alert_rules.yaml, districts.yaml
  backend/
    app/             # FastAPI
    pipeline/        # s1_fetch ... s9_publish
    indices/         # utci, wbgt_est, heat_index, composite
    models/          # bias_correction, classifier, calibration
    tests/
  frontend/
  data/              # git-ignored
  scripts/
  docker-compose.yml
  Makefile
```

## Commands (create these targets early)
`make dev`, `make test`, `make lint`, `make pipeline-run`, `make eval-report`

## Stop-and-ask triggers
- Any change to alert thresholds or rule semantics.
- Any new external data source or licence.
- Any place where a test fails and the "fix" would be loosening the test.
- Any claim in the UI about health outcomes.
