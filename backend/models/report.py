"""Generate the reproducible Phase 2 evaluation report."""

import argparse
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
from typing import Any

from models.classifier import EventSample, evaluate_event_classifier
from models.evaluate import write_evaluation


def _format(value: object) -> str:
    return "—" if value is None else f"{float(value):.3f}"


def _missing_report(reason: str) -> str:
    return f"""# Heatwave EWS evaluation report

**Skill status: Not established.** {reason}

The evaluation harness is available, but no POD, FAR, CSI, Brier, calibration, or baseline-skill values are reported without labelled historical input.

## Humid-heat case study — April 2023 candidate

No historical input file was supplied, so the documented April 2023 humid-heat candidate cannot be scored. Add versioned samples and source metadata before making any case-study claim.
"""


def _render_report(evaluation: dict[str, Any], case_study: dict[str, Any]) -> str:
    calibrated = {
        (group["climate_zone"], group["lead_day"]): group
        for group in evaluation["calibrated"]
    }
    uncalibrated = {
        (group["climate_zone"], group["lead_day"]): group
        for group in evaluation["uncalibrated"]
    }
    baseline = {
        (group["climate_zone"], group["lead_day"]): group
        for group in evaluation["baseline"]
    }
    rows = []
    for key, group in calibrated.items():
        raw, base = uncalibrated[key], baseline[key]
        rows.append(
            f"| {key[0]} | {key[1]} | {_format(group['pod'])} | {_format(group['far'])} | "
            f"{_format(group['csi'])} | {_format(raw['brier'])} | {_format(group['brier'])} | "
            f"{_format(base['brier'])} |"
        )
    comparisons = evaluation["comparison"]
    if comparisons and all(item["beats_baseline_brier"] for item in comparisons):
        conclusion = "On the supplied held-out years, every reported classifier group has lower Brier score than the supplied baseline."
    else:
        conclusion = "The classifier does not beat the supplied baseline in every reported group; no tuning against held-out years was performed."
    sample_ids = case_study.get("sample_ids", [])
    return f"""# Heatwave EWS evaluation report

**Skill status:** Evaluated only on the supplied, checksummed input. {conclusion}

Protocol: nested leave-one-year-out. Held-out years: {', '.join(map(str, evaluation['years']))}. Metrics are grouped by climate zone and lead day; accuracy is intentionally omitted.

## Skill and calibration

| Zone | Lead | POD | FAR | CSI | Uncalibrated Brier | Calibrated Brier | Baseline Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

Reliability diagrams are emitted as SVG files beside this report. Empty bins remain visible in the machine-readable JSON.

## Humid-heat case study — {case_study.get('title', 'supplied event')}

- Period: {case_study.get('period', 'not supplied')}
- Included sample IDs: {len(sample_ids)}
- Operator note: {case_study.get('summary', 'No case-study summary supplied.')}

This section repeats operator-supplied metadata; it does not infer health outcomes.
"""


def generate_report(input_path: Path, output_dir: Path) -> list[Path]:
    """Generate Markdown, HTML, JSON, and reliability SVG evaluation artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evaluation.json"
    if not input_path.exists():
        markdown = _missing_report(f"No historical input file exists at `{input_path}`.")
        payload: dict[str, Any] = {"status": "unavailable", "reason": "historical input missing"}
        paths = [output_dir / "evaluation.md", output_dir / "evaluation.html", json_path]
    else:
        raw = input_path.read_bytes()
        document = json.loads(raw)
        if document.get("schema_version") != 1:
            raise ValueError("evaluation input schema_version must be 1")
        feature_names = tuple(document["feature_names"])
        samples = [
            EventSample(
                str(item["sample_id"]),
                int(item["year"]),
                str(item["climate_zone"]),
                int(item["lead_day"]),
                bool(item["observed"]),
                tuple(float(value) for value in item["features"]),
                float(item["baseline_probability"]),
            )
            for item in document["samples"]
        ]
        evaluation = evaluate_event_classifier(samples, feature_names=feature_names)
        case_study = document.get("humid_heat_case_study", {})
        markdown = _render_report(evaluation, case_study)
        payload = {
            "status": "evaluated",
            "input_schema_version": 1,
            "input_sha256": sha256(raw).hexdigest(),
            "evaluation": evaluation,
            "humid_heat_case_study": case_study,
        }
        paths = write_evaluation({"groups": evaluation["calibrated"]}, output_dir)
        paths = [output_dir / "evaluation.md", output_dir / "evaluation.html", *paths]

    markdown_path, html_path = output_dir / "evaluation.md", output_dir / "evaluation.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>Heatwave EWS evaluation</title>"
        f"<body><pre>{escape(markdown)}</pre></body></html>\n",
        encoding="utf-8",
    )
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return list(dict.fromkeys(paths))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(os.getenv("EVAL_INPUT", "data/evaluation/event_samples.json")),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.getenv("EVAL_OUTPUT", "data/evaluation/report")),
    )
    arguments = parser.parse_args()
    for path in generate_report(arguments.input, arguments.output):
        print(path)


if __name__ == "__main__":
    main()
