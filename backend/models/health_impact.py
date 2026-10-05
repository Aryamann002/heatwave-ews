"""Illustrative heat-health relative-risk index with explicit non-operational status."""

import json
from pathlib import Path
from typing import Any


def load_health_impact_config(path: str | Path = "config/health_impact.json") -> dict[str, Any]:
    """Load and validate the evidence anchor and sensitivity assumptions."""
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    anchor = float(config["anchor_relative_risk"])
    sensitivity = float(config["stress_score_sensitivity"])
    if anchor < 1 or not 0 < sensitivity < 0.5:
        raise ValueError("health-impact anchor or sensitivity is invalid")
    if config.get("operational_alert_input") is not False or config.get("absolute_count_prediction") is not False:
        raise ValueError("illustrative health impact must not drive alerts or absolute counts")
    return config


def illustrative_relative_risk(stress_score: float, anchor_relative_risk: float) -> float:
    """Return a monotone illustrative RR index for a normalised [0,1] stress score."""
    if not 0 <= stress_score <= 1:
        raise ValueError("stress_score must be in [0, 1]")
    if anchor_relative_risk < 1:
        raise ValueError("anchor_relative_risk must be at least one")
    return 1 + (anchor_relative_risk - 1) * stress_score**2


def relative_risk_sensitivity(stress_score: float, config: dict[str, Any]) -> dict[str, float]:
    """Return a transparent stress-score sensitivity range, not a confidence interval."""
    delta = float(config["stress_score_sensitivity"])
    anchor = float(config["anchor_relative_risk"])
    low_score = max(0.0, stress_score - delta)
    high_score = min(1.0, stress_score + delta)
    return {
        "relative_risk_index": round(illustrative_relative_risk(stress_score, anchor), 2),
        "sensitivity_low": round(illustrative_relative_risk(low_score, anchor), 2),
        "sensitivity_high": round(illustrative_relative_risk(high_score, anchor), 2),
    }
