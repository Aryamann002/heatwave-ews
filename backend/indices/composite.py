"""Assumption-based composite Human Thermal Stress Index."""

import json
from pathlib import Path

THERMAL_COMPONENTS = ("utci", "wbgt_est", "night", "duration")


def load_weights(path: str | Path = "config/htsi_weights.yaml") -> dict[str, float]:
    """Load dimensionless HTSI weights from the versioned JSON-compatible YAML file."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    weights = {name: float(value) for name, value in document["weights"].items()}
    if set(weights) != {*THERMAL_COMPONENTS, "vulnerability"}:
        raise ValueError("HTSI config must define all and only the documented weights")
    if any(value < 0 for value in weights.values()):
        raise ValueError("HTSI weights must be non-negative")
    if abs(sum(weights[name] for name in THERMAL_COMPONENTS) - 1) > 1e-9:
        raise ValueError("thermal HTSI weights must sum to 1")
    return weights


def calculate_htsi(
    utci_score: float,
    wbgt_est_score: float,
    night_score: float,
    duration_score: float,
    vulnerability: float,
    weights: dict[str, float],
) -> float:
    """Return dimensionless HTSI risk from inputs normalised to [0, 1]."""
    scores = {
        "utci": utci_score,
        "wbgt_est": wbgt_est_score,
        "night": night_score,
        "duration": duration_score,
    }
    if any(not 0 <= value <= 1 for value in (*scores.values(), vulnerability)):
        raise ValueError("HTSI component scores and vulnerability must be in [0, 1]")
    thermal_stress = sum(scores[name] * weights[name] for name in THERMAL_COMPONENTS)
    return thermal_stress * (1 + weights["vulnerability"] * vulnerability)


def sensitivity_analysis(
    utci_score: float,
    wbgt_est_score: float,
    night_score: float,
    duration_score: float,
    vulnerability: float,
    weights: dict[str, float],
    variation: float = 0.1,
) -> dict[str, dict[str, float]]:
    """Return HTSI after lowering/raising each thermal weight by a fraction."""
    if not 0 < variation < 1:
        raise ValueError("variation must be between 0 and 1")
    scores = (utci_score, wbgt_est_score, night_score, duration_score, vulnerability)
    result: dict[str, dict[str, float]] = {}
    for name in THERMAL_COMPONENTS:
        cases: dict[str, float] = {}
        for label, factor in (("lower", 1 - variation), ("higher", 1 + variation)):
            varied = weights.copy()
            varied[name] *= factor
            total = sum(varied[key] for key in THERMAL_COMPONENTS)
            for key in THERMAL_COMPONENTS:
                varied[key] /= total
            cases[label] = calculate_htsi(*scores, varied)
        result[name] = cases
    return result
