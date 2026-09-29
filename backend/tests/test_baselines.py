"""Comparable baseline predictors for Phase 2 evaluation."""

from datetime import date
import unittest

from models.baselines import (
    BaselinePrediction,
    climatology_baseline,
    persistence_baseline,
    raw_forecast_imd_baseline,
)


class BaselinesTest(unittest.TestCase):
    def test_persistence_repeats_last_observed_label_by_lead_day(self) -> None:
        predictions = persistence_baseline("yellow", date(2026, 5, 1), 3)

        self.assertEqual(
            predictions,
            [
                BaselinePrediction("persistence", date(2026, 5, 1), 1, "yellow"),
                BaselinePrediction("persistence", date(2026, 5, 2), 2, "yellow"),
                BaselinePrediction("persistence", date(2026, 5, 3), 3, "yellow"),
            ],
        )

    def test_persistence_rejects_unknown_labels_and_nonpositive_horizon(self) -> None:
        with self.assertRaises(ValueError):
            persistence_baseline("blue", date(2026, 5, 1), 1)
        with self.assertRaises(ValueError):
            persistence_baseline("green", date(2026, 5, 1), 0)

    def test_raw_forecast_imd_baseline_uses_auditable_track1_rules(self) -> None:
        predictions = raw_forecast_imd_baseline(
            "plains",
            [
                (date(2026, 5, 1), 44.0, 38.0),
                (date(2026, 5, 2), 46.0, 38.0),
            ],
        )

        self.assertEqual([prediction.level for prediction in predictions], ["yellow", "green"])
        self.assertTrue(all(prediction.baseline == "raw_forecast_imd" for prediction in predictions))

    def test_climatology_baseline_compares_normal_temperature_to_imd_rules(self) -> None:
        predictions = climatology_baseline(
            "plains",
            [
                (date(2026, 5, 1), 39.0),
                (date(2026, 5, 2), 40.0),
            ],
        )

        self.assertEqual([prediction.level for prediction in predictions], ["green", "green"])
        self.assertEqual([prediction.lead_day for prediction in predictions], [1, 2])

    def test_raw_forecast_imd_baseline_rejects_empty_inputs(self) -> None:
        with self.assertRaises(ValueError):
            raw_forecast_imd_baseline("plains", [])
        with self.assertRaises(ValueError):
            climatology_baseline("plains", [])


if __name__ == "__main__":
    unittest.main()
