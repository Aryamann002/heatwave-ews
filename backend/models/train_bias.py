"""Train and evaluate per-zone Tmax bias correction on real 2022-2025 data.

Raw forecast: Open-Meteo historical-forecast archive (the model's first forecast day, stitched).
Target: ERA5 daily Tmax from the Open-Meteo archive, the same frame as the 1991-2020 normals, so
the corrected Tmax and its departure from normal are computed against one consistent reference.

    python -m models.train_bias      # writes data/models/bias_*.txt and bias_model_card.json
"""

import json
import math
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import lightgbm as lgb

from models.bias_correction import BiasCorrector, BiasSample, evaluate_bias_correction, fit_bias_correctors
from pipeline.s1_fetch import load_districts

PERIOD = ("2022-01-01", "2025-12-31")
FEATURES = ("raw_tmax_c", "doy_sin", "doy_cos", "latitude")
MODEL_DIR = Path("data/models")
CARD_PATH = MODEL_DIR / "bias_model_card.json"
SOURCES = {
    "forecast": "https://historical-forecast-api.open-meteo.com/v1/forecast",
    "era5": "https://archive-api.open-meteo.com/v1/archive",
}


def features(raw_tmax_c: float, day: date, latitude: float) -> tuple[float, ...]:
    angle = 2 * math.pi * day.timetuple().tm_yday / 366
    return (raw_tmax_c, math.sin(angle), math.cos(angle), latitude)


def _daily_tmax(kind: str, district: dict[str, Any], cache_dir: Path) -> dict[str, float]:
    path = cache_dir / kind / f"{district['id']}.json"
    if not path.exists():
        query = urlencode({
            "latitude": district["latitude"], "longitude": district["longitude"],
            "start_date": PERIOD[0], "end_date": PERIOD[1],
            "daily": "temperature_2m_max", "timezone": "Asia/Kolkata",
        })
        for attempt in range(5):
            try:
                with urlopen(f"{SOURCES[kind]}?{query}", timeout=120) as response:
                    body = response.read()
                break
            except (HTTPError, OSError):
                if attempt == 4:
                    raise
                time.sleep(30 * (attempt + 1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    daily = json.loads(path.read_text(encoding="utf-8"))["daily"]
    return {day: value for day, value in zip(daily["time"], daily["temperature_2m_max"]) if value is not None}


def build_samples(cache_dir: Path = Path("data/raw/bias_training")) -> list[BiasSample]:
    samples = []
    for district in load_districts():
        raw = _daily_tmax("forecast", district, cache_dir)
        observed = _daily_tmax("era5", district, cache_dir)
        for day in sorted(raw.keys() & observed.keys()):
            when = date.fromisoformat(day)
            samples.append(BiasSample(
                f"{district['id']}:{day}", when.year, district["climate_zone"], 1,
                raw[day], observed[day], features(raw[day], when, district["latitude"]),
            ))
    return samples


def load_correctors(card_path: Path = CARD_PATH) -> dict[str, BiasCorrector]:
    """Return correctors only for zones where held-out MAE improved; {} if never trained."""
    if not card_path.exists():
        return {}
    card = json.loads(card_path.read_text(encoding="utf-8"))
    return {
        group["climate_zone"]: BiasCorrector(
            group["climate_zone"], tuple(card["features"]),
            lgb.Booster(model_file=str(card_path.parent / f"bias_{group['climate_zone']}.txt")),
        )
        for group in card["evaluation"]["groups"]
        if group["use_correction"]
    }


def main() -> None:
    samples = build_samples()
    evaluation = evaluate_bias_correction(samples, feature_names=FEATURES)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for zone, model in fit_bias_correctors(samples, feature_names=FEATURES).items():
        model.booster.save_model(str(MODEL_DIR / f"bias_{zone}.txt"))
    card = {
        "model": "LightGBM L1 residual regression per climate zone",
        "features": list(FEATURES),
        "raw": "Open-Meteo historical forecast, first forecast day",
        "target": "ERA5 daily Tmax (Open-Meteo archive)",
        "period": list(PERIOD),
        "samples": len(samples),
        "evaluation": evaluation,
    }
    CARD_PATH.write_text(json.dumps(card, indent=2), encoding="utf-8")
    for group in evaluation["groups"]:
        print(
            f"{group['climate_zone']}: n={group['count']} raw MAE {group['raw_mae_c']:.2f} C -> "
            f"corrected {group['corrected_mae_c']:.2f} C ({group['selected']})"
        )


if __name__ == "__main__":
    main()
