"""Deterministic, auditable alert rules."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONDITION_RANK = {"normal": 0, "heat_wave": 1, "severe_heat_wave": 2}
LEVEL_RANK = {"green": 0, "yellow": 1, "orange": 2, "red": 3}


@dataclass(frozen=True)
class RuleResult:
    """A rule outcome with its versioned reasoning trace."""

    level: str
    reasons: tuple[str, ...]
    rule_version: str
    condition: str = ""
    disagreement: bool = False


def load_alert_rules(path: str | Path = "config/alert_rules.yaml") -> dict[str, Any]:
    """Load versioned rules from the JSON-compatible YAML file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classify_track1_day(
    climate_zone: str,
    maximum_temperature_c: float,
    normal_maximum_temperature_c: float | None,
    rules_document: dict[str, Any] | None = None,
) -> RuleResult:
    """Classify one day using published IMD maximum-temperature criteria."""
    document = rules_document or load_alert_rules()
    rules = document["track1"]
    if climate_zone not in rules["minimum_tmax_c"]:
        raise ValueError(f"unknown climate zone: {climate_zone}")

    departure = (
        None
        if normal_maximum_temperature_c is None
        else maximum_temperature_c - normal_maximum_temperature_c
    )
    minimum = rules["minimum_tmax_c"][climate_zone]
    reasons = (
        f"zone={climate_zone}",
        f"tmax={maximum_temperature_c:.1f}C",
        "departure=unavailable" if departure is None else f"departure={departure:.1f}C",
        f"zone_minimum={minimum:.1f}C",
    )
    condition = "normal"
    if maximum_temperature_c >= minimum:
        if departure is not None and departure > rules["departure_c"]["severe_min_exclusive"]:
            condition = "severe_heat_wave"
        elif departure is not None and departure >= rules["departure_c"]["heat_wave_min"]:
            condition = "heat_wave"

        if climate_zone == "plains":
            absolute = rules["plains_absolute_tmax_c"]
            if maximum_temperature_c >= absolute["severe_heat_wave"]:
                condition = "severe_heat_wave"
            elif maximum_temperature_c >= absolute["heat_wave"]:
                condition = max(condition, "heat_wave", key=CONDITION_RANK.get)

    return RuleResult(
        level=condition,
        condition=condition,
        reasons=reasons + (f"condition={condition}",),
        rule_version=document["version"],
    )


def _longest_run(conditions: list[str], minimum_rank: int) -> int:
    longest = current = 0
    for condition in conditions:
        if CONDITION_RANK[condition] >= minimum_rank:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def evaluate_track1(
    conditions: list[str], rules_document: dict[str, Any] | None = None
) -> RuleResult:
    """Map a forecast condition sequence to the published IMD warning colour."""
    if any(condition not in CONDITION_RANK for condition in conditions):
        raise ValueError("unknown Track 1 condition")
    document = rules_document or load_alert_rules()
    persistence = document["track1"]["persistence_days"]
    severe_run = _longest_run(conditions, CONDITION_RANK["severe_heat_wave"])
    heat_run = _longest_run(conditions, CONDITION_RANK["heat_wave"])
    hot_days = sum(CONDITION_RANK[condition] > 0 for condition in conditions)

    if (
        severe_run >= persistence["red_severe"]
        or hot_days > persistence["red_total_exclusive"]
    ):
        level = "red"
    elif (
        severe_run >= persistence["orange_severe"]
        or heat_run >= persistence["orange_any_heat"]
    ):
        level = "orange"
    elif heat_run >= persistence["yellow_heat_wave"]:
        level = "yellow"
    else:
        level = "green"

    return RuleResult(
        level=level,
        reasons=(
            f"longest_heat_run={heat_run}",
            f"longest_severe_run={severe_run}",
            f"total_heat_days={hot_days}",
            f"track1_level={level}",
        ),
        rule_version=document["version"],
    )


def evaluate_track2(
    utci_c: float,
    wbgt_est_c: float,
    consecutive_hot_nights: int,
    calibrated_probability: float | None,
    rules_document: dict[str, Any] | None = None,
) -> RuleResult:
    """Map human-stress inputs to a colour using explicit assumption rules."""
    if not math.isfinite(utci_c) or not math.isfinite(wbgt_est_c):
        raise ValueError("thermal indices must be finite")
    if consecutive_hot_nights < 0:
        raise ValueError("consecutive hot nights must be non-negative")
    if calibrated_probability is not None and not 0 <= calibrated_probability <= 1:
        raise ValueError("calibrated probability must be in [0, 1]")

    document = rules_document or load_alert_rules()
    rules = document["track2"]
    candidates = ["green"]
    for level in ("red", "orange", "yellow"):
        if utci_c >= rules["utci_c"][level]:
            candidates.append(level)
            break
    if consecutive_hot_nights >= rules["consecutive_hot_nights"]["orange"]:
        candidates.append("orange")
    elif consecutive_hot_nights >= rules["consecutive_hot_nights"]["yellow"]:
        candidates.append("yellow")
    if calibrated_probability is not None:
        for level in ("red", "orange", "yellow"):
            if calibrated_probability >= rules["calibrated_probability"][level]:
                candidates.append(level)
                break
    level = max(candidates, key=LEVEL_RANK.get)
    probability_text = (
        "unavailable" if calibrated_probability is None else f"{calibrated_probability:.3f}"
    )
    return RuleResult(
        level=level,
        reasons=(
            f"utci={utci_c:.1f}C",
            f"estimated_wbgt={wbgt_est_c:.1f}C (reasoning only)",
            f"consecutive_hot_nights={consecutive_hot_nights}",
            f"calibrated_probability={probability_text}",
            f"track2_level={level}",
            f"track2_status={rules['status']}",
        ),
        rule_version=document["version"],
    )


def combine_tracks(track1_level: str, track2_level: str) -> RuleResult:
    """Return the higher alert colour and explicitly log track disagreement."""
    if track1_level not in LEVEL_RANK or track2_level not in LEVEL_RANK:
        raise ValueError("unknown alert level")
    disagreement = track1_level != track2_level
    level = max((track1_level, track2_level), key=LEVEL_RANK.get)
    return RuleResult(
        level=level,
        reasons=(
            f"track1_level={track1_level}",
            f"track2_level={track2_level}",
            f"track_disagreement={str(disagreement).lower()}",
            "selection=max_of_tracks",
        ),
        rule_version="max-of-tracks-v1",
        disagreement=disagreement,
    )
