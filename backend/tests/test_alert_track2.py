"""Tests for human-stress Track 2 and max-of-tracks combination."""

import unittest

from app.alerts import combine_tracks, evaluate_track2


class Track2AlertTest(unittest.TestCase):
    def test_utci_and_modifiers_are_deterministic(self) -> None:
        self.assertEqual(evaluate_track2(25.9, 29, 0, None).level, "green")
        self.assertEqual(evaluate_track2(26, 29, 0, None).level, "yellow")
        self.assertEqual(evaluate_track2(32, 29, 0, None).level, "orange")
        self.assertEqual(evaluate_track2(38, 29, 0, None).level, "red")
        self.assertEqual(evaluate_track2(20, 29, 3, None).level, "orange")
        self.assertEqual(evaluate_track2(20, 29, 0, 0.9).level, "red")

    def test_tracks_agree_without_disagreement(self) -> None:
        result = combine_tracks("orange", "orange")
        self.assertEqual(result.level, "orange")
        self.assertFalse(result.disagreement)

    def test_tracks_disagree_and_higher_level_wins(self) -> None:
        result = combine_tracks("yellow", "red")
        self.assertEqual(result.level, "red")
        self.assertTrue(result.disagreement)
        self.assertIn("track_disagreement=true", result.reasons)


if __name__ == "__main__":
    unittest.main()
