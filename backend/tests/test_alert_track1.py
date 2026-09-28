"""Table-driven tests for deterministic IMD-criteria Track 1."""

import unittest

from app.alerts import classify_track1_day, evaluate_track1


class Track1AlertTest(unittest.TestCase):
    def test_daily_criteria_across_zones_and_rule_paths(self) -> None:
        cases = (
            ("below zone threshold", "plains", 39, 34, "normal"),
            ("plains departure", "plains", 42, 37, "heat_wave"),
            ("coastal departure", "coastal", 38, 33, "heat_wave"),
            ("hills severe departure", "hills", 32, 25, "severe_heat_wave"),
            ("plains absolute", "plains", 45, 44, "heat_wave"),
            ("plains severe absolute", "plains", 47, 46, "severe_heat_wave"),
            ("absolute rule is plains only", "coastal", 45, 44, "normal"),
        )
        for label, zone, maximum, normal, expected in cases:
            with self.subTest(label):
                self.assertEqual(classify_track1_day(zone, maximum, normal).condition, expected)

    def test_persistence_maps_conditions_to_colours(self) -> None:
        self.assertEqual(evaluate_track1(["heat_wave", "heat_wave"]).level, "yellow")
        self.assertEqual(evaluate_track1(["heat_wave"] * 4).level, "orange")
        self.assertEqual(evaluate_track1(["severe_heat_wave"] * 3).level, "red")

    def test_missing_climatology_uses_only_plains_absolute_rule(self) -> None:
        self.assertEqual(classify_track1_day("plains", 45, None).condition, "heat_wave")
        self.assertEqual(classify_track1_day("coastal", 45, None).condition, "normal")


if __name__ == "__main__":
    unittest.main()
