from math import exp
import unittest

from models.classifier import (
    EventSample,
    IsotonicCalibrator,
    evaluate_event_classifier,
    fit_event_classifiers,
)


class ClassifierTests(unittest.TestCase):
    def test_isotonic_calibration_matches_pool_adjacent_violators_example(self) -> None:
        calibrator = IsotonicCalibrator.fit(
            [0.1, 0.2, 0.3, 0.4], [False, True, False, True]
        )
        values = [calibrator.predict(value) for value in (0.1, 0.2, 0.3, 0.4)]
        self.assertEqual(values, [0.0, 0.5, 0.5, 1.0])
        self.assertEqual(values, sorted(values))

    def test_classifier_exposes_native_shap_contributions(self) -> None:
        samples = [
            EventSample(str(index), 2022, "plains", 1, index >= 10, (float(index),), 0.5)
            for index in range(20)
        ]
        model = fit_event_classifiers(samples, feature_names=("utci_c",))["plains"]

        contributions = model.explain((18.0,))
        raw_score = sum(contributions.values())
        expected_probability = 1 / (1 + exp(-raw_score))

        self.assertEqual(set(contributions), {"utci_c", "expected_value"})
        self.assertAlmostEqual(model.uncalibrated_probability((18.0,)), expected_probability)

    def test_nested_year_calibration_and_baseline_comparison(self) -> None:
        samples = [
            EventSample(
                f"{year}-{index}",
                year,
                "plains",
                1,
                index >= 10,
                (float(index),),
                0.5,
            )
            for year in (2020, 2021, 2022, 2023)
            for index in range(20)
        ]

        report = evaluate_event_classifier(samples, feature_names=("utci_c",), reliability_bins=4)

        self.assertEqual(report["years"], [2020, 2021, 2022, 2023])
        self.assertTrue(all(fold["held_out_year"] not in fold["train_years"] for fold in report["folds"]))
        comparison = report["comparison"][0]
        self.assertLess(comparison["classifier_brier"], comparison["baseline_brier"])
        self.assertTrue(comparison["beats_baseline_brier"])
        self.assertEqual(sum(point["count"] for point in report["calibrated"][0]["reliability"]), 80)

    def test_does_not_claim_to_beat_a_better_baseline(self) -> None:
        samples = [
            EventSample(
                f"{year}-{index}", year, "plains", 1, index % 2 == 0, (0.0,),
                1.0 if index % 2 == 0 else 0.0,
            )
            for year in (2020, 2021, 2022)
            for index in range(8)
        ]

        comparison = evaluate_event_classifier(samples, feature_names=("constant",))["comparison"][0]

        self.assertFalse(comparison["beats_baseline_brier"])
        self.assertEqual(comparison["baseline_brier"], 0.0)


if __name__ == "__main__":
    unittest.main()
