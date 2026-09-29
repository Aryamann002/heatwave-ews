"""LightGBM heat-event classifier with year-isolated isotonic calibration."""

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import lightgbm as lgb
import numpy as np

from models.evaluate import EvaluationSample, score_predictions


@dataclass(frozen=True)
class EventSample:
    """One labelled heat-event sample and its baseline probability."""

    sample_id: str
    year: int
    climate_zone: str
    lead_day: int
    observed: bool
    features: tuple[float, ...]
    baseline_probability: float


@dataclass(frozen=True)
class IsotonicCalibrator:
    """Monotone piecewise-constant probability calibrator."""

    upper_bounds: tuple[float, ...]
    values: tuple[float, ...]

    @classmethod
    def fit(
        cls, probabilities: Sequence[float], outcomes: Sequence[bool]
    ) -> "IsotonicCalibrator":
        """Fit by the pool-adjacent-violators algorithm."""
        if not probabilities or len(probabilities) != len(outcomes):
            raise ValueError("calibration needs equal non-empty probability and outcome lists")
        if any(not isfinite(value) or not 0 <= value <= 1 for value in probabilities):
            raise ValueError("calibration probabilities must be finite and between zero and one")

        grouped: list[list[float]] = []
        for probability, outcome in sorted(zip(probabilities, outcomes), key=lambda pair: pair[0]):
            if grouped and probability == grouped[-1][1]:
                grouped[-1][2] += float(outcome)
                grouped[-1][3] += 1
            else:
                grouped.append([probability, probability, float(outcome), 1])
        blocks: list[list[float]] = []
        for group in grouped:
            blocks.append(group)
            while len(blocks) > 1 and blocks[-2][2] / blocks[-2][3] > blocks[-1][2] / blocks[-1][3]:
                right = blocks.pop()
                left = blocks.pop()
                blocks.append([left[0], right[1], left[2] + right[2], left[3] + right[3]])
        return cls(
            tuple(block[1] for block in blocks),
            tuple(block[2] / block[3] for block in blocks),
        )

    def predict(self, probability: float) -> float:
        """Return the fitted monotone probability for one raw probability."""
        if not isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("probability must be finite and between zero and one")
        for upper, value in zip(self.upper_bounds, self.values, strict=True):
            if probability <= upper:
                return value
        return self.values[-1]


@dataclass(frozen=True)
class EventClassifier:
    """A zone model, its calibrator, and native TreeSHAP explanation path."""

    climate_zone: str
    feature_names: tuple[str, ...]
    booster: lgb.Booster
    calibrator: IsotonicCalibrator

    def _array(self, features: Sequence[float]) -> np.ndarray:
        if len(features) != len(self.feature_names):
            raise ValueError("feature count does not match the fitted model")
        return np.asarray([features], dtype=float)

    def uncalibrated_probability(self, features: Sequence[float]) -> float:
        """Return the LightGBM event probability before calibration."""
        return float(self.booster.predict(self._array(features), validate_features=True)[0])

    def probability(self, features: Sequence[float]) -> float:
        """Return the isotonic-calibrated event probability."""
        return self.calibrator.predict(self.uncalibrated_probability(features))

    def explain(self, features: Sequence[float]) -> dict[str, float]:
        """Return native TreeSHAP log-odds contributions plus expected value."""
        values = self.booster.predict(
            self._array(features), pred_contrib=True, validate_features=True
        )[0]
        names = (*self.feature_names, "expected_value")
        return {name: float(value) for name, value in zip(names, values, strict=True)}


def _validate(samples: Sequence[EventSample], feature_names: Sequence[str]) -> None:
    if not samples:
        raise ValueError("samples must not be empty")
    if not feature_names or len(set(feature_names)) != len(feature_names):
        raise ValueError("feature_names must be non-empty and unique")
    for sample in samples:
        if len(sample.features) != len(feature_names):
            raise ValueError("feature count does not match feature_names")
        if sample.lead_day < 1 or not sample.climate_zone:
            raise ValueError("samples need a climate zone and positive lead day")
        if any(not isfinite(value) for value in sample.features):
            raise ValueError("features must be finite")
        if not isfinite(sample.baseline_probability) or not 0 <= sample.baseline_probability <= 1:
            raise ValueError("baseline probability must be between zero and one")


def _fit_booster(samples: Sequence[EventSample], feature_names: Sequence[str]) -> lgb.Booster:
    labels = np.asarray([sample.observed for sample in samples], dtype=int)
    if len(set(labels.tolist())) < 2:
        raise ValueError("each classifier training set needs both event classes")
    dataset = lgb.Dataset(
        np.asarray([sample.features for sample in samples], dtype=float),
        label=labels,
        feature_name=list(feature_names),
    )
    return lgb.train(
        {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbosity": -1,
            "seed": 23,
            "num_threads": 1,
            "deterministic": True,
            "force_col_wise": True,
            "min_data_in_leaf": 1,
            "num_leaves": 7,
            "learning_rate": 0.1,
            "is_unbalance": True,
        },
        dataset,
        num_boost_round=40,
    )


def fit_event_classifiers(
    samples: Sequence[EventSample], *, feature_names: Sequence[str]
) -> dict[str, EventClassifier]:
    """Fit one classifier and in-sample calibrator per climate zone."""
    _validate(samples, feature_names)
    by_zone: dict[str, list[EventSample]] = defaultdict(list)
    for sample in samples:
        by_zone[sample.climate_zone].append(sample)
    models: dict[str, EventClassifier] = {}
    for zone, zone_samples in sorted(by_zone.items()):
        booster = _fit_booster(zone_samples, feature_names)
        raw = booster.predict(np.asarray([sample.features for sample in zone_samples], dtype=float))
        calibrator = IsotonicCalibrator.fit(raw.tolist(), [sample.observed for sample in zone_samples])
        models[zone] = EventClassifier(zone, tuple(feature_names), booster, calibrator)
    return models


def _fit_nested_classifiers(
    samples: Sequence[EventSample], feature_names: Sequence[str]
) -> dict[str, EventClassifier]:
    by_zone: dict[str, list[EventSample]] = defaultdict(list)
    for sample in samples:
        by_zone[sample.climate_zone].append(sample)
    models: dict[str, EventClassifier] = {}
    for zone, zone_samples in sorted(by_zone.items()):
        years = sorted({sample.year for sample in zone_samples})
        if len(years) < 2:
            raise ValueError("nested calibration requires at least two training years per zone")
        calibration_probabilities: list[float] = []
        calibration_outcomes: list[bool] = []
        for year in years:
            inner_train = [sample for sample in zone_samples if sample.year != year]
            inner_test = [sample for sample in zone_samples if sample.year == year]
            booster = _fit_booster(inner_train, feature_names)
            calibration_probabilities.extend(
                booster.predict(np.asarray([sample.features for sample in inner_test], dtype=float)).tolist()
            )
            calibration_outcomes.extend(sample.observed for sample in inner_test)
        final_booster = _fit_booster(zone_samples, feature_names)
        models[zone] = EventClassifier(
            zone,
            tuple(feature_names),
            final_booster,
            IsotonicCalibrator.fit(calibration_probabilities, calibration_outcomes),
        )
    return models


def evaluate_event_classifier(
    samples: Sequence[EventSample],
    *,
    feature_names: Sequence[str],
    reliability_bins: int = 10,
) -> dict[str, object]:
    """Evaluate nested-calibrated classifiers and baselines by held-out year."""
    _validate(samples, feature_names)
    years = sorted({sample.year for sample in samples})
    if len(years) < 3:
        raise ValueError("nested year evaluation requires at least three years")

    calibrated_pairs: list[tuple[EvaluationSample, float]] = []
    raw_pairs: list[tuple[EvaluationSample, float]] = []
    baseline_pairs: list[tuple[EvaluationSample, float]] = []
    folds: list[dict[str, object]] = []
    for held_out_year in years:
        train = [sample for sample in samples if sample.year != held_out_year]
        test = [sample for sample in samples if sample.year == held_out_year]
        models = _fit_nested_classifiers(train, feature_names)
        for sample in test:
            model = models[sample.climate_zone]
            evaluation_sample = EvaluationSample(
                sample.sample_id, sample.year, sample.climate_zone, sample.lead_day, sample.observed
            )
            raw_pairs.append((evaluation_sample, model.uncalibrated_probability(sample.features)))
            calibrated_pairs.append((evaluation_sample, model.probability(sample.features)))
            baseline_pairs.append((evaluation_sample, sample.baseline_probability))
        folds.append(
            {
                "held_out_year": held_out_year,
                "train_years": [year for year in years if year != held_out_year],
                "test_count": len(test),
            }
        )

    calibrated = score_predictions(calibrated_pairs, reliability_bins, 0.5)
    uncalibrated = score_predictions(raw_pairs, reliability_bins, 0.5)
    baseline = score_predictions(baseline_pairs, reliability_bins, 0.5)
    baseline_by_key = {(group["climate_zone"], group["lead_day"]): group for group in baseline}
    comparison = [
        {
            "climate_zone": group["climate_zone"],
            "lead_day": group["lead_day"],
            "classifier_brier": group["brier"],
            "baseline_brier": baseline_by_key[(group["climate_zone"], group["lead_day"])]["brier"],
            "beats_baseline_brier": group["brier"]
            < baseline_by_key[(group["climate_zone"], group["lead_day"])]["brier"],
        }
        for group in calibrated
    ]
    return {
        "protocol": "nested-leave-one-year-out",
        "years": years,
        "folds": folds,
        "uncalibrated": uncalibrated,
        "calibrated": calibrated,
        "baseline": baseline,
        "comparison": comparison,
    }
