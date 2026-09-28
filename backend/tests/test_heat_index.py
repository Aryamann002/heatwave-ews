"""Reference and behavior tests for the Heat Index wrapper."""

import unittest

from indices.heat_index import calculate_heat_index


class HeatIndexTest(unittest.TestCase):
    def test_matches_pinned_library_documented_example(self) -> None:
        self.assertEqual(calculate_heat_index(29, 50), 29.7)

    def test_accepts_array_inputs(self) -> None:
        result = calculate_heat_index([29, 35], [50, 50])
        self.assertEqual(result.shape, (2,))

    def test_higher_humidity_increases_hot_weather_stress(self) -> None:
        self.assertGreater(calculate_heat_index(40, 80), calculate_heat_index(40, 20))


if __name__ == "__main__":
    unittest.main()
