import json
import tempfile
import unittest
from pathlib import Path

from models.evaluate import EvaluationSample, evaluate_leave_one_year_out, write_evaluation


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.samples = [
            EvaluationSample("2022-a", 2022, "plains", 1, True),
            EvaluationSample("2022-b", 2022, "plains", 1, False),
            EvaluationSample("2023-a", 2023, "plains", 1, True),
            EvaluationSample("2023-b", 2023, "plains", 1, False),
            EvaluationSample("2022-c", 2022, "coastal", 2, True),
            EvaluationSample("2023-c", 2023, "coastal", 2, False),
        ]

    def test_years_are_held_out_whole_and_metrics_are_grouped(self) -> None:
        calls: list[tuple[set[int], set[int]]] = []
        probabilities = {
            "2022-a": 0.8,
            "2022-b": 0.7,
            "2023-a": 0.6,
            "2023-b": 0.2,
            "2022-c": 0.4,
            "2023-c": 0.1,
        }

        def predict(train, test):
            calls.append(({sample.year for sample in train}, {sample.year for sample in test}))
            return [probabilities[sample.sample_id] for sample in test]

        report = evaluate_leave_one_year_out(self.samples, predict, reliability_bins=2)

        self.assertEqual(calls, [({2023}, {2022}), ({2022}, {2023})])
        plains = next(group for group in report["groups"] if group["climate_zone"] == "plains")
        self.assertEqual(plains["lead_day"], 1)
        self.assertEqual(plains["confusion"], {"tp": 2, "fp": 1, "fn": 0, "tn": 1})
        self.assertAlmostEqual(plains["pod"], 1.0)
        self.assertAlmostEqual(plains["far"], 1 / 3)
        self.assertAlmostEqual(plains["csi"], 2 / 3)
        self.assertAlmostEqual(plains["brier"], 0.1825)
        self.assertEqual(sum(point["count"] for point in plains["reliability"]), 4)

    def test_rejects_invalid_or_unusable_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two years"):
            evaluate_leave_one_year_out(self.samples[:1], lambda _train, _test: [0.5])
        with self.assertRaisesRegex(ValueError, "probability"):
            evaluate_leave_one_year_out(self.samples, lambda _train, test: [1.1] * len(test))
        with self.assertRaisesRegex(ValueError, "one probability"):
            evaluate_leave_one_year_out(self.samples, lambda _train, _test: [])

    def test_whole_year_holdout_prevents_year_label_memorisation_leak(self) -> None:
        samples = [
            EvaluationSample(f"2022-{index}", 2022, "plains", 1, False)
            for index in range(4)
        ] + [
            EvaluationSample(f"2023-{index}", 2023, "plains", 1, True)
            for index in range(4)
        ]

        def memorise_training_years(train, test):
            labels_by_year = {sample.year: float(sample.observed) for sample in train}
            return [labels_by_year.get(sample.year, 0.5) for sample in test]

        report = evaluate_leave_one_year_out(samples, memorise_training_years)

        # A row-wise split would expose both year labels and score Brier 0.0.
        # Whole-year folds hide the held-out year's label, giving the honest 0.25.
        self.assertEqual(report["groups"][0]["brier"], 0.25)

    def test_writes_machine_readable_report_and_reliability_svgs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = evaluate_leave_one_year_out(
                self.samples,
                lambda _train, test: [0.8 if sample.observed else 0.2 for sample in test],
            )
            paths = write_evaluation(report, output)

            self.assertEqual(json.loads((output / "evaluation.json").read_text()), report)
            self.assertEqual(len(paths), 3)
            for path in paths[1:]:
                self.assertIn("<svg", path.read_text())
                self.assertIn("Observed frequency", path.read_text())


if __name__ == "__main__":
    unittest.main()
