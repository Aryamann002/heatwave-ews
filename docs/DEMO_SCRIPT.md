# Demo script (about 7 minutes)

Before the demo: `docker compose up --build`, wait for the pipeline to finish, run
`docker compose run --rm backend python -m pipeline.replay` once so replays load instantly, and
set `GROQ_API_KEY` in `.env` if you want regional-language advisories.

1. **The problem (30 s).** Air temperature alone misses humid heat. The system scores what the body feels (UTCI, WBGT, Heat Index) alongside IMD's temperature criteria.
2. **National view (1 min).** Map of 81 districts, coloured by today's alert. Banner shows data freshness and counts per level. Switch the layer to UTCI, WBGT, Heat Index and *Tmax vs normal*; step through the 7 days.
3. **Why this level (1 min).** Pick the highest-ranked district. Show the four indices, the 7-day chart against the 1991–2020 normal, and the two tracks: IMD criteria vs human thermal stress. Open *Why* to show the full, versioned reasoning trace.
3b. **The ML piece (30 s).** Scroll to *AI bias correction*: a LightGBM model per climate zone corrects ECMWF IFS Tmax into the ERA5 frame used for the normals, cutting held-out error from 0.77 to 0.55 °C on the coast and 0.63 to 0.52 °C on the plains (2024–2025, leave-one-year-out). It is used only where it beats the raw forecast.
4. **Real heatwave replay (1.5 min).** Choose *Replay: North & Central India heatwave, May 2024*. The same code on ERA5 data turns Rajasthan and Delhi red. Then *East coast humid heat, April 2024*: point out coastal districts where the human-stress track fires while the temperature-only IMD track stays lower. That gap is the reason this tool exists.
5. **Ward-level response (1.5 min).** Back to live, select Ahmedabad (or Delhi/Chennai): ward population layer appears. *Resources & tasks*: suggested water points, cooling centres and ambulance staging for the most exposed wards, scaled by alert level; edit and create tasks; move one to *in progress*.
6. **Advisory dispatch (1 min).** *Advisories*: draft English and Hindi from approved templates, and a regional-language version (LLM translation). Switch *Acting as* to viewer: approval is refused. As officer: approve, export CAP 1.2, dispatch SMS (simulated). Show the audit log.
7. **Ask a question (15 s).** “Which districts are at highest risk today?” The answer comes from the database; the LLM only parses the question.
8. **Honesty slide (15 s).** Not an IMD warning; UTCI thresholds and planning ratios are assumptions; ERA5 smooths extremes; see `docs/LIMITATIONS.md`.
