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
