"""Illustrative health-impact index tests."""

import unittest

from models.health_impact import illustrative_relative_risk, load_health_impact_config, relative_risk_sensitivity


class HealthImpactTest(unittest.TestCase):
    def test_anchor_and_monotonicity(self) -> None:
        config = load_health_impact_config()
        anchor = config["anchor_relative_risk"]
        values = [illustrative_relative_risk(score, anchor) for score in (0, 0.25, 0.5, 0.75, 1)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[0], 1.0)
        self.assertAlmostEqual(values[-1], 2.34)

    def test_sensitivity_is_ordered_and_not_labelled_confidence(self) -> None:
        result = relative_risk_sensitivity(0.5, load_health_impact_config())
        self.assertLess(result["sensitivity_low"], result["relative_risk_index"])
        self.assertLess(result["relative_risk_index"], result["sensitivity_high"])
