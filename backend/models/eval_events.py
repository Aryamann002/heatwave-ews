"""Event skill of raw vs bias-corrected IFS Tmax, scored with the IMD Track 1 single-day rule.

Event = ERA5 Tmax meets the IMD heat-wave criteria for that day (zone minimum Tmax and departure
from the 1991-2020 normal). Prediction = the same rule applied to the forecast Tmax. Both are
deterministic, so probabilities are 0/1 and Brier equals the misclassification rate. Corrected
forecasts are out-of-fold (leave-one-year-out), so no year is scored by a model that saw it.
Single-day condition only: the IMD persistence rule (consecutive days) is not applied here.
Lead day 1 only; two years (2024-2025) of data.

    python -m models.eval_events    # writes data/evaluation/event_skill.json
"""

import json
from datetime import date
from pathlib import Path

from app.alerts import classify_track1_day
from models.bias_correction import fit_bias_correctors
from models.evaluate import EvaluationSample, score_predictions
from models.train_bias import FEATURES, build_samples
NORMALS_FILE = Path("data/climatology/normals_era5.json")

OUTPUT = Path("data/evaluation/event_skill.json")
MIN_EVENTS = 30  # below this, POD/FAR are too noisy to read


def _is_event(zone: str, tmax_c: float, normal_c: float) -> bool:
    return classify_track1_day(zone, tmax_c, normal_c).condition != "normal"


def run() -> dict[str, object]:
    normals = json.loads(NORMALS_FILE.read_text(encoding="utf-8"))["districts"]
    samples = build_samples(cached_only=True)
    years = sorted({s.year for s in samples})
    pairs: dict[str, list[tuple[EvaluationSample, float]]] = {"raw": [], "corrected": []}
    for held_out in years:
        models = fit_bias_correctors(
            [s for s in samples if s.year != held_out], feature_names=FEATURES
        )
        for s in samples:
            if s.year != held_out:
                continue
            district_id, day = s.sample_id.split(":")
            if district_id not in normals:
                continue
            doy = date.fromisoformat(day).timetuple().tm_yday
            normal = normals[district_id]["normals"][doy - 1][0]
            model = models.get(s.climate_zone)
            corrected = model.correct(s.raw_temperature_c, s.features) if model else s.raw_temperature_c
            row = EvaluationSample(s.sample_id, s.year, s.climate_zone, s.lead_day,
                                   _is_event(s.climate_zone, s.observed_temperature_c, normal))
            pairs["raw"].append((row, float(_is_event(s.climate_zone, s.raw_temperature_c, normal))))
            pairs["corrected"].append((row, float(_is_event(s.climate_zone, corrected, normal))))
    report = {
        "protocol": "leave-one-year-out (bias corrector only); single-day IMD rule; lead day 1",
        "years": years,
        "min_events_for_reading": MIN_EVENTS,
        **{name: score_predictions(p, 10, 0.5) for name, p in pairs.items()},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = run()
    for name in ("raw", "corrected"):
        for g in report[name]:  # type: ignore[union-attr]
            c = g["confusion"]
            pod, far, csi = (f"{g[k]:.3f}" if g[k] is not None else "n/a" for k in ("pod", "far", "csi"))
            print(f"{name:9} {g['climate_zone']:8} n={g['count']:6} events={c['tp'] + c['fn']:4} "
                  f"POD={pod} FAR={far} CSI={csi}")


if __name__ == "__main__":
    main()
