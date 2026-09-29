# LIMITATIONS.md

Living document. Seeded with limitations already known from the planning research. The implementing agent must append to this whenever it finds a new one. The README must surface all of these.

## From the literature (planning stage)

1. **AI weather models can under-predict humidity.** An evaluation over the South Asian monsoon found all evaluated models except GenCast underestimated near-surface specific humidity (arXiv 2509.01879). WBGT/UTCI depend on humidity. → Bias-correction stage; humid-heat skill reported separately.
2. **ML utility for humid heatwaves is limited in one validation study** of the April 2023 South Asian event (arXiv 2404.17652). → Humid-heat case study in evaluation; no claim of superiority.
3. **Deep learning has not been shown to beat physics-based forecasting for heatwave prediction** (noted in Frontiers in Climate 2022 work). → ML layer positioned as calibration and impact translation, not a better forecaster.
4. **CorrDiff-type downscaling was demonstrated on Taiwan** (and separately explored for China/other regions). Transfer to India's terrain and monsoon is unproven in the material reviewed. → Downscaling is a stretch goal on a ladder.
5. **Downscaling models can struggle with inter-variable and temporal consistency** (GMD 2025 paper). Heat indices need T, RH, wind and radiation to be jointly consistent. → Treat downscaled index values with extra suspicion.
6. **Literature disagrees on WBGT vs UTCI.** Nature Communications 2025 favours UTCI; a 2021 semi-arid India study found WBGT best for that setting. → Both shown; UTCI primary.
7. **Mortality effects lag heat by ~3–6 days** in the cities studied (ES&T 2023). → Trailing-exposure features. Also means a same-day-only alert is structurally late.
8. **Ahmedabad HAP evaluation is pre/post.** The "avoided deaths" figures come from a before/after comparison against a 2007–2010 baseline; causal attribution is not airtight. → Never claim causation.

## Data

9. **Outdoor WBGT needs globe temperature, which forecasts do not provide.** WBGT here is an estimate.
10. **Census 2011 vulnerability is stale.** Label the vintage.
11. **ERA5 has a 5–7 day delay** for daily updates, and is a reanalysis, not observation. It is a proxy for truth, not truth.
12. **IMD access terms unverified.** Gridded Tmax availability and licence were not confirmed.
13. **Boundary data must comply with Indian official-map requirements.** Source and licence must be logged.

## Method

14. **Composite HTSI weights are unvalidated assumptions.** Sensitivity analysis provided in lieu of validation.
15. **IMD criteria can change.** Track 1 was rechecked against IMD's current morning heat bulletin on 2026-09-28 and rules remain versioned in config. Recheck before operational deployment and after any IMD revision.
16. **Research matrix is 40 sources, not 45, and author-credibility filtering was not performed.** Several entries carry VERIFY-BEFORE-CITING flags.
17. **No end-to-end validation of AI-forecast → thermal-index for India was found** in the material reviewed. This is a gap and a potential contribution, but also means there's no published benchmark to compare against.

## Scope

18. Not a replacement for IMD's official warnings.
19. No mortality or health-outcome model.
20. Alert delivery is mocked; CAP profile compatibility with Indian agencies not verified.
21. Nowcasting (0–6 h) and urban-heat-island / land-surface-temperature layers were not researched.

## Added during implementation

22. **Estimated WBGT requires more than T/RH/wind/radiation.** The adopted `thermofeel` Liljegren implementation also needs surface pressure, direct-beam fraction, and solar zenith. These forecast-derived inputs add uncertainty; the result is always labelled "estimated WBGT".
23. **Phase 1 Open-Meteo ingestion samples one configured coordinate per pilot district.** It is a point proxy, not a district-wide zonal statistic. Polygon aggregation replaces this in the later harmonise/aggregate pipeline.
24. **Pilot boundaries are community-maintained Census 2011 geometry, not current Survey of India ABDB.** The DataMeet source and CC BY 2.5 India attribution are recorded and pinned, but administrative changes since 2011 are absent. Replace with sanctioned current boundaries before operational use.
25. **The IMD bulletin explicitly limits absolute 45/47°C criteria to plains.** Coastal and hill classifications therefore use their zone eligibility temperature plus departure-from-normal criteria; this interpretation should be reviewed with IMD before operational use.
26. **Track 2 alert mappings are unvalidated policy assumptions.** UTCI categories come from the pinned library, but their mapping to IMD-style colours, probability cut-offs, and hot-night persistence have not been calibrated for Indian outcomes. Estimated WBGT is shown in the reasoning trace but does not escalate alerts until a population/workload-specific rule is approved.
27. **The Phase 1 freshness gate uses 12 hours.** This allows two expected six-hour forecast cycles before declaring data stale. It is an operational assumption, not an IMD standard, and must be tuned to the production source schedule.
28. **The live Phase 1 UTCI is a shade estimate.** Mean radiant temperature is set equal to air temperature because Open-Meteo does not provide the full shortwave/longwave flux set required by the adopted MRT method. Estimated WBGT does use forecast shortwave/direct radiation and NOAA solar geometry.
29. **The live Phase 1 Track 1 feed has no climatological normal yet.** It therefore applies only the published plains absolute-temperature branch; departure-based rules become active after the Phase 2 historical climatology stage.
30. **Direct ECMWF open data are global GRIB2 fields.** The fetcher selects only required parameters and forecast steps, but spatial subsetting happens in the harmonisation stage; raw cycle downloads can therefore be large.
31. **ECMWF `ssrd` is accumulated energy in J/m².** It must be differenced over its accumulation interval before conversion to W/m² in the harmonisation stage; the raw fetcher intentionally preserves the source encoding.
32. **Copernicus history retrieval is free but not anonymous.** An operator must create a CDS account, accept each dataset's terms once, and supply the personal CDS token outside the repository. No historical data are fabricated when credentials or queued retrievals are unavailable.
33. **Harmonisation QC bounds are conservative engineering assumptions, not alert thresholds.** Values outside −90–65°C, 0–100% RH, 0–100 m/s wind, 50–110 kPa pressure, or 0–1600 W/m² shortwave are blocked for review rather than silently clipped.
34. **Accumulated radiation needs explicit interval metadata.** The harmoniser refuses J/m² fields unless `accumulation_seconds` is supplied; source-specific decoding must derive that interval correctly before QC.
35. **Climatology and persistence baselines are implemented before real labels/normals are populated.** The functions are comparable for evaluation, but operational persistence needs observed prior alerts and climatology needs historical district normals from the Phase 2 aggregation stage.
36. **Probability-to-event evaluation defaults to 0.5.** This is a reporting convention, not an operational alert threshold. Operational colours remain controlled by the versioned deterministic alert rules; any calibrated-model policy needs separate review.
37. **Bias-correction performance is not yet established on Indian observations.** The code and year-isolation behavior are tested with constructed residuals, but real ERA5/forecast pairs still need to be fetched and evaluated. A zone/lead combination automatically retains the raw forecast when held-out MAE is worse.
38. **Classifier skill and calibration are not established on historical Indian events yet.** Nested year splitting, calibration, and native TreeSHAP behavior are tested on constructed samples only. Operational model probabilities must remain disabled until a real-data evaluation report compares them with the raw-forecast-plus-IMD baseline.
39. **The checked-out repository contains no labelled historical evaluation sample file.** `make eval-report` therefore produces an explicit “not established” report rather than benchmark numbers. Populate the documented versioned input from licensed ERA5/forecast/label data before presenting model skill or the April 2023 humid-heat case study.
40. **The vulnerability layer currently measures population exposure only and covers Ahmedabad only.** WorldPop population is a modelled 2020 estimate, not a complete vulnerability measure or a current census count. New Delhi and Chennai intentionally show “not loaded.”
41. **The DataMeet Ahmedabad ward source does not state its boundary date.** The exact repository commit and retrieval date are shown, but administrative currency is unknown; replace it with an official dated ward release before operational use.
42. **Advisory templates are static and versioned in config.** Any wording change requires a new template version and human review. The optional LLM fill path is not implemented; if added, it must pass the strict linter that enforces exact template vocabulary.
43. **Advisory time window is fixed at 06:00–12:00 IST** for the forecast date. This is a simplification; real advisories may need dynamic windows based on event timing.
44. **Approval workflow (officer sign-off) is not yet implemented.** Drafts are stored with status `pending_approval`; the role-based approval gate is task 3.3.
45. **CAP export uses a simplified profile.** The CAP 1.2 XML omits <resource>, <geocode>, and detailed <area> polygons. The <polygon> element is empty; real CAP messages need coordinate lists. Profile compatibility with Indian agencies (NDMA/SDMA) not verified.
46. **Mock SMS/email adapters have no retry, queue, or delivery confirmation.** They return "sent" immediately. No integration with actual telecom providers (e.g., BSNL, Airtel) or email services. Rate limits, opt-out, and template registry not implemented.
47. **User authentication is not implemented.** The `user_id` is passed as a query/header parameter. No JWT, OAuth, or session management. Roles are checked but identity is not verified.
48. **Task board has no spatial visualization.** Tasks store optional lat/lon but the dashboard does not render them on the map. No clustering or heatmap for task locations.
49. **Audit log is append-only with no tamper-evidence.** No hash chaining, Merkle tree, or WORM storage. An operator with DB access can modify history.
