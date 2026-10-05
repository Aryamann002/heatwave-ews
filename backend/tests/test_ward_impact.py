"""Ward response-priority tests."""

import unittest

from models.ward_impact import response_priority


class WardImpactTest(unittest.TestCase):
    def test_higher_exposure_ranks_first_without_changing_alert(self) -> None:
        first = response_priority("orange", 1, 10)
        last = response_priority("orange", 10, 10)
        self.assertGreater(first.priority_score, last.priority_score)
        self.assertEqual(first.priority, "urgent")

    def test_alert_level_is_monotone(self) -> None:
        scores = [response_priority(level, 5, 10).priority_score for level in ("green", "yellow", "orange", "red")]
        self.assertEqual(scores, sorted(scores))

    def test_rejects_invalid_rank(self) -> None:
        with self.assertRaises(ValueError):
            response_priority("yellow", 0, 5)
