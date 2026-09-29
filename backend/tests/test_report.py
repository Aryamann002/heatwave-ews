import json
import tempfile
import unittest
from pathlib import Path

from models.report import generate_report


class EvaluationReportTests(unittest.TestCase):
    def test_missing_historical_input_generates_honest_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = generate_report(root / "missing.json", root / "report")
            markdown = (root / "report" / "evaluation.md").read_text(encoding="utf-8")

            self.assertEqual({path.name for path in paths}, {"evaluation.md", "evaluation.html", "evaluation.json"})
            self.assertIn("Skill status: Not established", markdown)
            self.assertIn("Humid-heat case study", markdown)
            self.assertIn("April 2023", markdown)
            self.assertIn("No historical input file", markdown)

    def test_generates_metrics_and_case_study_from_versioned_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "samples.json"
            samples = [
                {
                    "sample_id": f"{year}-{index}",
                    "year": year,
                    "climate_zone": "plains",
                    "lead_day": 1,
                    "observed": index % 2 == 0,
                    "features": [0.0],
                    "baseline_probability": 1.0 if index % 2 == 0 else 0.0,
                }
                for year in (2020, 2021, 2022)
                for index in range(8)
            ]
            input_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "feature_names": ["constant"],
                        "samples": samples,
                        "humid_heat_case_study": {
                            "title": "Supplied humid event",
                            "period": "2022-04",
                            "summary": "Operator-supplied case note.",
                            "sample_ids": ["2022-0", "2022-1"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            paths = generate_report(input_path, root / "report")
            markdown = (root / "report" / "evaluation.md").read_text(encoding="utf-8")
            payload = json.loads((root / "report" / "evaluation.json").read_text(encoding="utf-8"))

            self.assertIn("does not beat the supplied baseline", markdown)
            self.assertIn("Supplied humid event", markdown)
            self.assertIn("POD", markdown)
            self.assertEqual(payload["input_schema_version"], 1)
            self.assertTrue(any(path.suffix == ".svg" for path in paths))


if __name__ == "__main__":
    unittest.main()
