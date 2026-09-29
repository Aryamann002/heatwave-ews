"""Per-climate-zone LightGBM residual bias correction."""

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import lightgbm as lgb
import numpy as np


@dataclass(frozen=True)
class BiasSample:
    """One forecast/observation pair; temperatures are degrees C."""

    sample_id: str
    year: int
    climate_zone: str
    lead_day: int
    raw_temperature_c: float
    observed_temperature_c: float
    features: tuple[float, ...]


@dataclass(frozen=True)
class BiasCorrector:
    """A fitted residual model for one climate zone."""

    climate_zone: str
    feature_names: tuple[str, ...]
    booster: lgb.Booster

    def correct(self, raw_temperature_c: float, features: Sequence[float]) -> float:
        """Return raw temperature plus the predicted residual, in degrees C."""
        if len(features) != len(self.feature_names):
            raise ValueError("feature count does not match the fitted model")
        residual = float(
            self.booster.predict(np.asarray([features], dtype=float), validate_features=True)[0]
        )
        return raw_temperature_c + residual


def _validate(samples: Sequence[BiasSample], feature_names: Sequence[str]) -> None:
    if not samples:
        raise ValueError("samples must not be empty")
    if not feature_names or len(set(feature_names)) != len(feature_names):
        raise ValueError("feature_names must be non-empty and unique")
    for sample in samples:
        values = (*sample.features, sample.raw_temperature_c, sample.observed_temperature_c)
        if len(sample.features) != len(feature_names):
            raise ValueError("feature count does not match feature_names")
        if sample.lead_day < 1 or not sample.climate_zone or not all(map(isfinite, values)):
            raise ValueError("samples must contain finite values, a zone, and a positive lead")


def fit_bias_correctors(
    samples: Sequence[BiasSample], *, feature_names: Sequence[str]
) -> dict[str, BiasCorrector]:
    """Fit one deterministic LightGBM residual model per climate zone."""
    _validate(samples, feature_names)
    by_zone: dict[str, list[BiasSample]] = defaultdict(list)
    for sample in samples:
        by_zone[sample.climate_zone].append(sample)

    models: dict[str, BiasCorrector] = {}
    for zone, zone_samples in sorted(by_zone.items()):
        features = np.asarray([sample.features for sample in zone_samples], dtype=float)
        residuals = np.asarray(
            [sample.observed_temperature_c - sample.raw_temperature_c for sample in zone_samples],
            dtype=float,
        )
        dataset = lgb.Dataset(features, label=residuals, feature_name=list(feature_names))
        booster = lgb.train(
            {
                "objective": "regression_l1",
                "metric": "l1",
                "verbosity": -1,
                "seed": 17,
                "num_threads": 1,
                "deterministic": True,
                "force_col_wise": True,
                "min_data_in_leaf": 1,
                "num_leaves": 7,
                "learning_rate": 0.1,
            },
            dataset,
            num_boost_round=40,
        )
        models[zone] = BiasCorrector(zone, tuple(feature_names), booster)
    return models


def evaluate_bias_correction(
    samples: Sequence[BiasSample], *, feature_names: Sequence[str]
) -> dict[str, object]:
    """Compare raw and corrected MAE using leave-one-year-out folds."""
    _validate(samples, feature_names)
    years = sorted({sample.year for sample in samples})
    if len(years) < 2:
        raise ValueError("bias-correction evaluation requires at least two years")

    predictions: list[tuple[BiasSample, float]] = []
    folds: list[dict[str, object]] = []
    for held_out_year in years:
        train = [sample for sample in samples if sample.year != held_out_year]
        test = [sample for sample in samples if sample.year == held_out_year]
        models = fit_bias_correctors(train, feature_names=feature_names)
        for sample in test:
            model = models.get(sample.climate_zone)
            corrected = (
                model.correct(sample.raw_temperature_c, sample.features)
                if model is not None
                else sample.raw_temperature_c
            )
            predictions.append((sample, corrected))
        folds.append(
            {
                "held_out_year": held_out_year,
                "train_years": [year for year in years if year != held_out_year],
                "test_count": len(test),
            }
        )

    grouped: dict[tuple[str, int], list[tuple[BiasSample, float]]] = defaultdict(list)
    for sample, corrected in predictions:
        grouped[(sample.climate_zone, sample.lead_day)].append((sample, corrected))
    results: list[dict[str, object]] = []
    for (zone, lead_day), values in sorted(grouped.items()):
        raw_mae = sum(
            abs(sample.raw_temperature_c - sample.observed_temperature_c)
            for sample, _ in values
        ) / len(values)
        corrected_mae = sum(
            abs(corrected - sample.observed_temperature_c) for sample, corrected in values
        ) / len(values)
        use_correction = corrected_mae <= raw_mae
        results.append(
            {
                "climate_zone": zone,
                "lead_day": lead_day,
                "count": len(values),
                "raw_mae_c": raw_mae,
                "corrected_mae_c": corrected_mae,
                "use_correction": use_correction,
                "selected": "corrected" if use_correction else "raw",
                "selected_mae_c": corrected_mae if use_correction else raw_mae,
            }
        )
    return {"protocol": "leave-one-year-out", "years": years, "folds": folds, "groups": results}
