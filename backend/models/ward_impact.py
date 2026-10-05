"""Transparent ward response-priority attribution.

This module never pretends that district-scale meteorology is a ward forecast. It
combines the shared district alert with within-city population exposure only to
rank where officers should review actions first.
"""

from dataclasses import dataclass


LEVEL_SCORE = {"green": 0.0, "yellow": 1 / 3, "orange": 2 / 3, "red": 1.0}


@dataclass(frozen=True)
class WardPriority:
    """Dimensionless ward response-priority result."""

    exposure_percentile: float
    priority_score: float
    priority: str


def response_priority(alert_level: str, rank: int, count: int) -> WardPriority:
    """Combine district alert and ward exposure rank into an auditable priority.

    ``rank`` is one-based with the highest-exposure ward first. The result is an
    operational queue, not a ward-resolution weather warning or health forecast.
    """
    if alert_level not in LEVEL_SCORE:
        raise ValueError("unknown alert level")
    if count <= 0 or rank < 1 or rank > count:
        raise ValueError("rank must be between one and count")
    exposure = 1.0 if count == 1 else 1 - (rank - 1) / (count - 1)
    score = 0.75 * LEVEL_SCORE[alert_level] + 0.25 * exposure
    priority = "routine" if score < 0.25 else "watch" if score < 0.5 else "high" if score < 0.75 else "urgent"
    return WardPriority(round(exposure, 4), round(score, 4), priority)
