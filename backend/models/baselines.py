"""Simple comparable baseline predictors.

All temperatures are degrees C. Baselines return alert colours using the same
shape so the year-split evaluation harness can score them side by side.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from app.alerts import LEVEL_RANK, classify_track1_day, evaluate_track1


@dataclass(frozen=True)
class BaselinePrediction:
    """One baseline alert prediction for a district target day."""

    baseline: str
    target_date: date
    lead_day: int
    level: str


def _require_level(level: str) -> None:
    if level not in LEVEL_RANK:
        raise ValueError(f"unknown alert level: {level}")


def persistence_baseline(
    last_observed_level: str, first_target_date: date, horizon_days: int
) -> list[BaselinePrediction]:
    """Predict every lead day as the last observed alert level."""
    _require_level(last_observed_level)
    if horizon_days < 1:
        raise ValueError("horizon_days must be positive")
    return [
        BaselinePrediction(
            "persistence",
            first_target_date + timedelta(days=index),
            index + 1,
            last_observed_level,
        )
        for index in range(horizon_days)
    ]


def raw_forecast_imd_baseline(
    climate_zone: str, forecast_tmax: Iterable[tuple[date, float, float | None]]
) -> list[BaselinePrediction]:
    """Apply Track 1 IMD rules to raw forecast Tmax and optional normal Tmax."""
    days = list(forecast_tmax)
    if not days:
        raise ValueError("forecast_tmax must not be empty")
    conditions = [
        classify_track1_day(climate_zone, tmax_c, normal_tmax_c).condition
        for _, tmax_c, normal_tmax_c in days
    ]
    return [
        BaselinePrediction(
            "raw_forecast_imd",
            target_date,
            index + 1,
            evaluate_track1(conditions[index:]).level,
        )
        for index, (target_date, _, _) in enumerate(days)
    ]


def climatology_baseline(
    climate_zone: str, normal_tmax: Iterable[tuple[date, float]]
) -> list[BaselinePrediction]:
    """Apply Track 1 rules to climatological normal Tmax with zero departure."""
    days = list(normal_tmax)
    if not days:
        raise ValueError("normal_tmax must not be empty")
    return raw_forecast_imd_baseline(
        climate_zone,
        ((target_date, normal_c, normal_c) for target_date, normal_c in days),
    )
