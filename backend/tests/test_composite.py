"""Tests for the assumption-based composite HTSI."""

import unittest

from indices.composite import calculate_htsi, load_weights, sensitivity_analysis


class CompositeHTSITest(unittest.TestCase):
    def test_loads_weights_and_applies_documented_formula(self) -> None:
        weights = load_weights()
        result = calculate_htsi(
            utci_score=1,
            wbgt_est_score=0.5,
            night_score=0.25,
            duration_score=0,
            vulnerability=0.4,
            weights=weights,
        )
        self.assertAlmostEqual(result, 0.69)

    def test_more_stress_does_not_reduce_score(self) -> None:
        weights = load_weights()
        low = calculate_htsi(0.2, 0.2, 0.2, 0.2, 0.5, weights)
        high = calculate_htsi(0.8, 0.8, 0.8, 0.8, 0.5, weights)
        self.assertGreater(high, low)

    def test_sensitivity_analysis_varies_each_thermal_weight(self) -> None:
        result = sensitivity_analysis(1, 0, 0, 0, 0, load_weights())
        self.assertEqual(set(result), {"utci", "wbgt_est", "night", "duration"})
        self.assertGreater(result["utci"]["higher"], result["utci"]["lower"])


if __name__ == "__main__":
    unittest.main()
