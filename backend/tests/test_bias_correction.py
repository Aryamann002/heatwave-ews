import unittest

from models.bias_correction import BiasSample, evaluate_bias_correction, fit_bias_correctors


class BiasCorrectionTests(unittest.TestCase):
    def test_models_are_trained_per_zone_and_remove_simple_bias(self) -> None:
        samples = [
            BiasSample(f"p-{year}-{index}", year, "plains", 1, raw, raw - 2.0, (raw,))
            for year in (2021, 2022, 2023)
            for index, raw in enumerate((38.0, 40.0, 42.0))
        ] + [
            BiasSample(f"c-{year}-{index}", year, "coastal", 1, raw, raw + 1.0, (raw,))
            for year in (2021, 2022, 2023)
            for index, raw in enumerate((34.0, 36.0, 38.0))
        ]

        models = fit_bias_correctors(samples, feature_names=("raw_temperature_c",))
        self.assertEqual(set(models), {"plains", "coastal"})
        self.assertAlmostEqual(models["plains"].correct(41.0, (41.0,)), 39.0, places=3)
        self.assertAlmostEqual(models["coastal"].correct(37.0, (37.0,)), 38.0, places=3)

        report = evaluate_bias_correction(samples, feature_names=("raw_temperature_c",))
        for group in report["groups"]:
            self.assertLess(group["corrected_mae_c"], group["raw_mae_c"])
            self.assertTrue(group["use_correction"])
            self.assertEqual(group["selected"], "corrected")
        self.assertEqual(report["years"], [2021, 2022, 2023])

    def test_worse_held_out_correction_is_reported_and_raw_is_selected(self) -> None:
        samples = [
            BiasSample("2022", 2022, "plains", 1, 40.0, 50.0, (40.0,)),
            BiasSample("2023", 2023, "plains", 1, 40.0, 30.0, (40.0,)),
        ]

        group = evaluate_bias_correction(samples, feature_names=("raw_temperature_c",))["groups"][0]

        self.assertGreater(group["corrected_mae_c"], group["raw_mae_c"])
        self.assertFalse(group["use_correction"])
        self.assertEqual(group["selected"], "raw")
        self.assertEqual(group["selected_mae_c"], group["raw_mae_c"])

    def test_rejects_invalid_training_shapes(self) -> None:
        sample = BiasSample("bad", 2022, "plains", 1, 40.0, 38.0, ())
        with self.assertRaisesRegex(ValueError, "feature"):
            fit_bias_correctors([sample], feature_names=("raw_temperature_c",))
        with self.assertRaisesRegex(ValueError, "at least two years"):
            evaluate_bias_correction(
                [BiasSample("one", 2022, "plains", 1, 40.0, 38.0, (40.0,))],
                feature_names=("raw_temperature_c",),
            )


if __name__ == "__main__":
    unittest.main()
