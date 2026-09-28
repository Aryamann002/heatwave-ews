# RESEARCH_MATRIX.md

## Read this first: what this matrix is and is not

The brief asked for 45 recent papers. **This file contains only papers whose existence and venue I confirmed via live search during planning.** Count of confirmed rows: **see Section A–E totals below**. I did not pad to 45. Padding a citation list from memory is the single most likely way to put fabricated references in front of a Ministry jury.

**Status column meaning**
- `VERIFIED` — title, venue and year seen in search results this session.
- `VERIFY-BEFORE-CITING` — I recognize the work but did NOT see it confirmed in search this session. Do not cite until checked against the publisher page or DOI.

**Filter I applied:** peer-reviewed venue (Nature family, Science-family, AGU, Springer, Elsevier, Frontiers, PLOS, PNAS, Copernicus) OR a widely-used preprint from an established lab, with the type marked per row. If you want journals only, drop rows marked `preprint`.

**Known gap:** authors' h-index / "credible track record" was NOT checked. I only checked venue. Do not claim author-credibility filtering in the submission unless you do that step.

---

## A. AI weather foundation models (the forecasting engine)

| # | Work | Venue / Year | Type | Status | Why it matters for THIS project |
|---|------|--------------|------|--------|---------------------------------|
| A1 | Aurora: "A foundation model for the Earth system" | Nature, 2025 | journal | VERIFIED | Fine-tunable to new variables at modest cost; outperforms IFS HRES at 0.1° on >92% of targets per the paper. Candidate backbone for regional heat fine-tuning. |
| A2 | AIFS (ECMWF Artificial Intelligence Forecasting System) | ECMWF operational system, v2 running per ECMWF data pages | operational system | VERIFIED (system exists and is open-data; the specific AIFS paper citation is VERIFY-BEFORE-CITING) | Free open forecast stream (CC-BY-4.0). This is your zero-cost, no-GPU forecast source. |
| A3 | GenCast (DeepMind) probabilistic ensemble forecasting | Nature 637, 84–90 (2025) per a reference list seen in search | journal | VERIFIED (via citing reference) | Ensemble = calibrated probabilities. Directly relevant to "probability of heatwave" output. |
| A4 | GraphCast (Lam et al.) | Title "GraphCast: Learning skillful medium-range global weather forecasting" seen in a reference list; venue/year NOT confirmed | journal | VERIFIED (title); venue/year VERIFY-BEFORE-CITING | Baseline global AI model. |
| A5 | Pangu-Weather (Bi et al.) | Cited as "Bi23" in search results; venue NOT confirmed | journal | VERIFIED (existence); exact venue VERIFY-BEFORE-CITING | Baseline. |
| A6 | FourCastNet (Pathak et al.) | arXiv 2022 | preprint | VERIFIED | Baseline; open weights, GPU-light. |
| A7 | "An Observations-focused assessment of Global AI Weather Prediction Models During the South Asian Monsoon" | arXiv 2509.01879, Sep 2025 | preprint | VERIFIED | **Most decision-relevant paper in the set for India.** Evaluates 7 AI models over South Asia; reports that all except GenCast underestimate near-surface humidity. Humidity bias directly corrupts WBGT/UTCI. |
| A8 | "Evaluation of five global AI models for predicting weather in Eastern Asia and Western Pacific" | npj Clim. Atmos. Sci., 2024 | journal | VERIFIED | FengWu/FuXi/GraphCast ranking; multi-model ensemble mean beat individuals. Supports ensembling design. |
| A9 | "Validating Deep Learning Weather Forecast Models on Recent High-Impact Extreme Events" | arXiv 2404.17652 | preprint | VERIFIED | Includes the April 2023 South Asian humid heatwave. Reports a limitation on ML utility for humid heat. **This is your honest-limitations citation.** |
| A10 | "Weather Emulators at the Frontier of Heat Extremes Predictability" | arXiv 2607.28220 | preprint | VERIFIED (existence) | Heat-extreme predictability with emulators. Read fully before relying on its claims. |
| A11 | "Foundation Models for Weather and Climate Data Understanding: A Comprehensive Survey" | arXiv 2312.03014 | preprint/survey | VERIFIED | Tool/model catalogue; useful for OSS section. |
| A12 | "Deep Learning Techniques in Extreme Weather Events: A Review" | arXiv 2308.10995 | preprint/survey | VERIFIED | Includes heatwave LSTM work for northern India up to 5–6 days ahead. |

## B. Heatwave prediction with ML/DL (the EWS classifier layer)

| # | Work | Venue / Year | Type | Status | Why it matters |
|---|------|--------------|------|--------|----------------|
| B1 | Johnvictor AC, "Comparative analysis of machine learning approaches for heatwave event prediction in India" | Scientific Reports 15, 2025 | journal | VERIFIED | Nine ML models incl. GNNs, Tamil Nadu. Direct India benchmark. |
| B2 | "Deep learning prediction of rare heatwave and coldwave events under severe class imbalance" | Stoch. Environ. Res. Risk Assess. (Springer), 2026 | journal | VERIFIED | **Class imbalance is a core design problem for your classifier.** Nine architectures across horizons. |
| B3 | Jacques-Dumas, Ragone, Borgnat, Abry, Bouchet, "Deep Learning-Based Extreme Heatwave Forecast" | Frontiers in Climate, 2022 | journal | VERIFIED | Undersampling for rare-event training; the authors note DL still trails physics models for prediction. |
| B4 | Shafiq et al., "Extreme heat prediction through deep learning and explainable AI" | PLOS ONE, 2025 | journal | VERIFIED | ANN/CNN/LSTM + XAI on Pakistan Met Dept data. Neighbouring climate; XAI pattern reusable. |
| B5 | "Forecasting temperature and rainfall using deep learning for the challenging climates of Northern India" | PeerJ Computer Science, 2025 | journal | VERIFIED | Jammu/Kashmir/Ladakh; RNN/LSTM. Regional; limited relevance to the plains. |
| B6 | Chattopadhyay et al. (2020), CapsNet for heatwave/coldwave prediction | cited within B3 and A12 | journal | VERIFY-BEFORE-CITING (seen only as a citation) | Early DL heatwave classification. |

## C. Human thermal stress indices — India-specific (the "Human Thermal Stress Index" pillar)

| # | Work | Venue / Year | Type | Status | Why it matters |
|---|------|--------------|------|--------|----------------|
| C1 | "Spatiotemporal changes in heat stress exposure in India, 1981–2023" | Nature Communications, Oct 2025 | journal | VERIFIED | **Anchor paper.** District-level UTCI across India; argues UTCI performs as well as or better than WBGT for body temperature, perception, labour loss. Also reports caste-based inequality in outdoor occupational exposure. |
| C2 | "Excess Mortality Risk Due to Heat Stress in Different Climatic Zones of India" (PDF hosted on an IIT Delhi faculty page; filename "EST2023b" suggests Environ. Sci. Technol. 2023 but this is an inference) | Venue/year NOT confirmed | journal | VERIFIED (existence via author PDF); exact citation VERIFY-BEFORE-CITING | Mortality-risk lags of 3–6 days in Varanasi, Delhi, Chennai. **The 3–6 day lag is a design input:** alerts must be forward-looking and lag-aware. Heterogeneity across climate zones argues against one national threshold. |
| C3 | "Emerging heat stress patterns across India under future climate scenarios" | PMC12891482 (journal name NOT confirmed in search) | journal article (per PMC) | VERIFIED (title + PMC ID only); JOURNAL AND YEAR VERIFY-BEFORE-CITING | Future scenarios; persistence of heat-stress events. |
| C4 | "Comprehensive analysis of thermal stress over northwest India: Climatology, trends and extremes" | ScienceDirect (pii S2212095522001067), page dated May 2022; journal name NOT confirmed | journal article (per ScienceDirect) | VERIFIED (title + ScienceDirect listing); JOURNAL VERIFY-BEFORE-CITING | UTCI from ERA5-HEAT 1981–2019. Baseline for NW India. |
| C5 | "Comparative analysis of heatwaves and heat stress in six climatic zones of India based on observed data" | Elsevier (Weather & Climate Extremes / Urban Climate family), 2025 | journal | VERIFIED (existence); journal name VERIFY-BEFORE-CITING | Six climate zones, 1990–2020, UTCI + humidity index. Supports zone-specific calibration. |
| C6 | "Assessing the monthly heat stress risk to society using thermal comfort indices in the hot semi-arid climate of India" | ScienceDirect, 2021 | journal | VERIFIED | WBGT/PET/UTCI compared; found WBGT best-suited for hot arid outdoor comfort in that study. **Note this conflicts with C1's UTCI preference. Do not hide the disagreement.** |
| C7 | "Thermal stress across the Indus-Ganges-Brahmaputra basins: UTCI-based trends analysis" | Theor. Appl. Climatol. (Springer), 2026 | journal | VERIFIED | IGB basin trends. |
| C8 | Di Napoli et al., "Thermal comfort indices derived from ERA5 reanalysis" (ERA5-HEAT) | Copernicus C3S CDS dataset, 2020 | dataset | VERIFIED | This is your ground-truth-ish UTCI training target, not a paper per se. |
| C9 | Tartarini & Schiavon, "pythermalcomfort: A Python package for thermal comfort research" | SoftwareX 12, 100578, 2020 | journal | VERIFIED | The calculation library you will actually call. |

## D. Downscaling (the city-scale resolution layer)

| # | Work | Venue / Year | Type | Status | Why it matters |
|---|------|--------------|------|--------|----------------|
| D1 | Mardani et al., "Residual corrective diffusion modeling for km-scale atmospheric downscaling" (CorrDiff) | Communications Earth & Environment, Feb 2025 | journal | VERIFIED | 25 km → 2 km, trained on Taiwan. **Shows it works for one region trained from scratch; it has NOT been shown for India in what I found.** |
| D2 | "Dynamical-generative downscaling of climate model ensembles" | PNAS, Apr 2025 | journal | VERIFIED | Hybrid RCM + diffusion. |
| D3 | "Diffusion model-based probabilistic downscaling for 180-year East Asian climate reconstruction" | npj Clim. Atmos. Sci., 2024 | journal | VERIFIED | 1° → 0.1° probabilistic. |
| D4 | "Can AI be enabled to perform dynamical downscaling? A latent diffusion model to mimic km-scale COSMO5.0_CLM9 simulations" | Geoscientific Model Development, Apr 2025 | journal | VERIFIED | Notes inter-variable and temporal consistency as unresolved limits. **Relevant: WBGT/UTCI need consistent T, RH, wind, radiation jointly.** |
| D5 | "Diffusion Models for Climate Data Surpass alternative Statistical Downscaling Techniques" | ESS Open Archive, Feb 2025 | preprint | VERIFIED | Diffusion beats GARD/CNN/GAN on extremes (US basin). |
| D6 | "Deep learning super-resolution for temperature data downscaling: a comprehensive study using residual networks" | Frontiers in Climate, Apr 2025 | journal | VERIFIED | Explicitly India 2-m temperature, SRCNN/VDSR/EDSR. **Most directly transferable downscaling paper.** |
| D7 | "Deep Learning Based Statistical Downscaling for Enhanced Representation of Indian Monsoon Rainfall…" (Ghosh group) | JGR Atmospheres 130(19), 2025 | journal | VERIFIED (seen as a citation) | India-specific downscaling with extremes. |
| D8 | "China Regional 3km Downscaling Based on Residual Corrective Diffusion Model" | arXiv 2512.05377 | preprint | VERIFIED | CorrDiff transfer to a large new region with an AI global forecast as input. Closest analogue to the plan for India. |
| D9 | Apeliotes: "A Diffusion-Based Modeling Framework for km-scale Multi-Level Atmospheric Fields" | arXiv 2607.17037 | preprint | VERIFIED | Aurora + CorrDiff pipeline. Shows the exact composition proposed in ARCHITECTURE.md exists in the literature. |

## E. Public health effectiveness and operations (the decision-support pillar)

| # | Work | Venue / Year | Type | Status | Why it matters |
|---|------|--------------|------|--------|----------------|
| E1 | "Development and Implementation of South Asia's First Heat-Health Action Plan in Ahmedabad (Gujarat, India)" | PMC4024996 (authors, journal, year NOT confirmed in search) | journal article (per PMC) | VERIFIED (title + PMC ID only); AUTHORS/JOURNAL/YEAR VERIFY-BEFORE-CITING | Origin of the 7-day probabilistic forecast + colour-coded alert model. |
| E2 | "Building Resilience to Climate Change: Pilot Evaluation of the Impact of India's First Heat Action Plan on All-Cause Mortality" | PMC6236972 (authors, journal, year NOT confirmed in search) | journal article (per PMC) | VERIFIED (title + PMC ID only); AUTHORS/JOURNAL/YEAR VERIFY-BEFORE-CITING | Reports >1,100 deaths avoided per year (per NRDC/PreventionWeb summary). **Caveat: pre/post design with a 2007–2010 baseline. Causal attribution is not airtight. Do not present it as proof of causation.** |
| E3 | Upreti et al., "Heat Adaptation Through Policy and Planning: A Case Study of Ahmedabad's Heat Action Plan" | Springer chapter, 2026 | book chapter | VERIFIED | Policy evolution; documentary-analysis method, not causal. |
| E4 | IMD heat wave criteria (40°C plains / 37°C coastal / 30°C hills; departure 4.5–6.4°C; severe >6.4°C or ≥45/47°C absolute) | IMD FAQ (internal.imd.gov.in) | official source | VERIFIED | Your alert logic must reproduce IMD's criteria as the baseline. Coverage in May 2026 press indicates IMD may revise these; **re-check before build.** |

---

## Confirmed count (restated after a self-audit)

I audited this file against the raw search results and removed authors/journals/years that I had inferred rather than seen. The counts below reflect that.

- **Rows listed:** 40 (Section A 12, B 6, C 9, D 9, E 4). Several are datasets, systems, or official sources rather than papers (A2, C8, C9's library, E4).
- **Rows where title, venue and year were all seen in search:** the Nature/Nature-family, Communications Earth & Environment, PNAS, npj, Frontiers, PLOS ONE, PeerJ, GMD, Springer and Scientific Reports items in Sections A-D. Even these are best re-checked against the publisher page before you cite.
- **Rows where only the title and a hosting ID were seen** (venue/authors/year unconfirmed): A4, A5, C2, C3, C4, E1, E2. These carry explicit flags.
- **Rows seen only as a citation inside another paper:** A3 (venue via a reference list), B6, D7.

**Do not tell the jury "40 verified sources."** The accurate statement is: "40 sources identified across 5 categories; bibliographic details confirmed for the majority; remaining entries flagged for verification." Resolve the flags first, then report the final number.

## What is NOT covered (open gaps you should close)

1. **Author credibility filter** was not run.
2. **UTCI/WBGT operational forecasting from AI models** (i.e., computing indices from forecast fields rather than reanalysis). I found evaluations of AI model humidity bias (A7, A9) but no paper validating end-to-end AI-forecast → UTCI for India. **This may be the real novelty gap your project can address.**
3. **Nowcasting** (0–6h) with satellite/radar was not researched.
4. **Urban heat island / LST-based** downscaling for intra-city risk (Landsat/MODIS) was not searched.
5. **Vulnerability mapping** literature (slums, outdoor workers, elderly) beyond C1's caste finding was not searched.

## Strongest counter-arguments to the plan these papers imply

- B3 itself says DL "remains far from challenging" physics-based prediction. If your EWS claims to beat IMD's NWP-based products, that is a claim the literature does not support. Position the ML layer as **calibration and impact translation**, not as a better forecaster.
- A7/A9 indicate AI models underestimate humidity, and humid heat is exactly what the 2023 event was. A humidity-dependent index built on an AI forecast inherits that bias. **This must be a documented limitation and, ideally, a bias-correction step.**
- D1 is trained on Taiwan. India's terrain, monsoon and irrigation effects differ. Transfer is unproven in what I found.
