"""Reference and behavior tests for the UTCI wrapper."""

import unittest

from indices.utci import calculate_utci


class UTCITest(unittest.TestCase):
    def test_matches_library_reference_table(self) -> None:
        # pythermalcomfort v4.6.0 validation-data-comfort-models v1.0.0.
        self.assertAlmostEqual(calculate_utci(25, 27, 1, 50), 25.2, delta=0.1)

    def test_accepts_array_inputs(self) -> None:
        result = calculate_utci([25, 25], [27, 25], [1, 1], [50, 50])
        self.assertEqual(result.tolist(), [25.2, 24.6])

    def test_higher_humidity_does_not_reduce_hot_weather_stress(self) -> None:
        dry = calculate_utci(40, 40, 1, 20)
        humid = calculate_utci(40, 40, 1, 80)
        self.assertGreaterEqual(humid, dry)


if __name__ == "__main__":
    unittest.main()

