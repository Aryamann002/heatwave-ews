"""Year-isolated evaluation for heat-event probability predictors."""

from collections import defaultdict
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
from typing import Callable, Sequence


@dataclass(frozen=True)
class EvaluationSample:
    """One labelled district-day sample used by the evaluation harness."""

    sample_id: str
    year: int
    climate_zone: str
    lead_day: int
    observed: bool


Predictor = Callable[
    [Sequence[EvaluationSample], Sequence[EvaluationSample]], Sequence[float]
]


def score_predictions(
    pairs: Sequence[tuple[EvaluationSample, float]], bins: int, threshold: float
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[tuple[EvaluationSample, float]]] = defaultdict(list)
    for sample, probability in pairs:
        grouped[(sample.climate_zone, sample.lead_day)].append((sample, probability))

    results: list[dict[str, object]] = []
    for (zone, lead_day), values in sorted(grouped.items()):
        tp = sum(sample.observed and probability >= threshold for sample, probability in values)
        fp = sum(not sample.observed and probability >= threshold for sample, probability in values)
        fn = sum(sample.observed and probability < threshold for sample, probability in values)
        tn = len(values) - tp - fp - fn
        reliability: list[dict[str, object]] = []
        for index in range(bins):
            lower, upper = index / bins, (index + 1) / bins
            selected = [
                (sample, probability)
                for sample, probability in values
                if lower <= probability < upper or (index == bins - 1 and probability == 1)
            ]
            reliability.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": len(selected),
                    "mean_probability": (
                        sum(probability for _, probability in selected) / len(selected)
                        if selected
                        else None
                    ),
                    "observed_frequency": (
                        sum(sample.observed for sample, _ in selected) / len(selected)
                        if selected
                        else None
                    ),
                }
            )
        results.append(
            {
                "climate_zone": zone,
                "lead_day": lead_day,
                "count": len(values),
                "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
                "pod": tp / (tp + fn) if tp + fn else None,
                "far": fp / (tp + fp) if tp + fp else None,
                "csi": tp / (tp + fp + fn) if tp + fp + fn else None,
                "brier": sum((probability - sample.observed) ** 2 for sample, probability in values)
                / len(values),
                "reliability": reliability,
            }
        )
    return results


def evaluate_leave_one_year_out(
    samples: Sequence[EvaluationSample],
    predictor: Predictor,
    *,
    reliability_bins: int = 10,
    event_threshold: float = 0.5,
) -> dict[str, object]:
    """Evaluate probabilities using whole-year holdouts, grouped by zone and lead."""
    years = sorted({sample.year for sample in samples})
    if len(years) < 2:
        raise ValueError("leave-one-year-out evaluation requires at least two years")
    if reliability_bins < 1:
        raise ValueError("reliability_bins must be positive")
    if not 0 <= event_threshold <= 1:
        raise ValueError("event_threshold must be between zero and one")
    if any(sample.lead_day < 1 for sample in samples):
        raise ValueError("lead_day must be positive")

    out_of_fold: list[tuple[EvaluationSample, float]] = []
    folds: list[dict[str, object]] = []
    for held_out_year in years:
        train = [sample for sample in samples if sample.year != held_out_year]
        test = [sample for sample in samples if sample.year == held_out_year]
        probabilities = list(predictor(train, test))
        if len(probabilities) != len(test):
            raise ValueError("predictor must return one probability per test sample")
        if any(not 0 <= probability <= 1 for probability in probabilities):
            raise ValueError("each probability must be between zero and one")
        pairs = list(zip(test, probabilities, strict=True))
        out_of_fold.extend(pairs)
        folds.append(
            {
                "held_out_year": held_out_year,
                "train_years": [year for year in years if year != held_out_year],
                "test_count": len(test),
                "groups": score_predictions(pairs, reliability_bins, event_threshold),
            }
        )

    return {
        "protocol": "leave-one-year-out",
        "years": years,
        "event_threshold": event_threshold,
        "reliability_bins": reliability_bins,
        "folds": folds,
        "groups": score_predictions(out_of_fold, reliability_bins, event_threshold),
    }


def _reliability_svg(group: dict[str, object]) -> str:
    points = [
        point
        for point in group["reliability"]
        if point["mean_probability"] is not None
    ]
    circles = "".join(
        f'<circle cx="{50 + 300 * point["mean_probability"]:.1f}" '
        f'cy="{350 - 300 * point["observed_frequency"]:.1f}" r="5" />'
        for point in points
    )
    title = escape(f'{group["climate_zone"]}, lead day {group["lead_day"]}')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" role="img" aria-label="Reliability diagram: {title}">
<rect width="400" height="400" fill="white"/><text x="200" y="24" text-anchor="middle">{title}</text>
<line x1="50" y1="350" x2="350" y2="50" stroke="#999" stroke-dasharray="4 4"/>
<line x1="50" y1="350" x2="350" y2="350" stroke="black"/><line x1="50" y1="350" x2="50" y2="50" stroke="black"/>
<text x="200" y="385" text-anchor="middle">Mean forecast probability</text>
<text x="15" y="200" text-anchor="middle" transform="rotate(-90 15 200)">Observed frequency</text>
<g fill="#c62828">{circles}</g></svg>"""


def write_evaluation(report: dict[str, object], output_dir: Path) -> list[Path]:
    """Write JSON metrics and one dependency-free SVG reliability plot per group."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evaluation.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = [json_path]
    for group in report["groups"]:
        slug = re.sub(r"[^a-z0-9]+", "-", str(group["climate_zone"]).lower()).strip("-")
        path = output_dir / f"reliability-{slug}-lead-{group['lead_day']}.svg"
        path.write_text(_reliability_svg(group), encoding="utf-8")
        paths.append(path)
    return paths
