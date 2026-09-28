# Heatwave EWS — Planning Pack

Planning documents for an Extreme Heatwave Early Warning and Human Thermal Stress Index system (MoES / Disaster Management).

## How to use this pack
1. Copy this folder into your project workspace.
2. Open your agentic coder (Claude Code, Cursor, etc.).
3. Paste the prompt from `prompts/KICKOFF_PROMPT.md`.
4. Before anything else, resolve every `VERIFY-BEFORE-CITING` and `CHECK` flag in `docs/RESEARCH_MATRIX.md` and `docs/OSS_LANDSCAPE.md`.

## Files
| File | Purpose |
|------|---------|
| AGENTS.md | Rules the coding agent reads every session |
| docs/PRD.md | Scope, users, success metrics, non-goals |
| docs/RESEARCH_MATRIX.md | Sources reviewed, with verification status |
| docs/TECH_STACK.md | Choices, rejected alternatives, reasons |
| docs/OSS_LANDSCAPE.md | Open-source projects with what is/isn't verified |
| docs/ARCHITECTURE.md | Layers, alert logic, data model, failure modes |
| docs/PIPELINE.md | Stage contracts and evaluation protocol |
| docs/IMPLEMENTATION_PLAN.md | Phased tasks with acceptance criteria |
| docs/LIMITATIONS.md | Known limitations (agent appends) |
| prompts/KICKOFF_PROMPT.md | The vibe-coding prompt + follow-ups |
