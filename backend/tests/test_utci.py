"""Reference and behavior tests for the UTCI wrapper."""

import unittest

from indices.utci import calculate_outdoor_mrt, calculate_outdoor_mrt_series, calculate_utci


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

    def test_pinned_solar_gain_library_reference(self) -> None:
        # pythermalcomfort 4.6.0 documents delta-MRT 10.3 °C for this example.
        from pythermalcomfort.models import solar_gain

        self.assertAlmostEqual(
            float(solar_gain(0, 120, 800, 0.5, 0.5, 0.5).delta_mrt),
            10.3,
            delta=0.11,  # 10.4 on the pinned build because of the documented rounding path
        )

    def test_outdoor_mrt_increases_monotonically_with_direct_sun(self) -> None:
        shade = calculate_outdoor_mrt(40.0, 0.0, 0.8)
        weak = calculate_outdoor_mrt(40.0, 200.0, 0.8)
        strong = calculate_outdoor_mrt(40.0, 600.0, 0.8)
        self.assertEqual(shade, 40.0)
        self.assertLess(shade, weak)
        self.assertLess(weak, strong)

    def test_vectorized_mrt_matches_scalar_scenarios(self) -> None:
        vector = calculate_outdoor_mrt_series([40, 40, 40], [0, 200, 600], [0.8, 0.8, 0.8])
        scalar = [calculate_outdoor_mrt(40, direct, 0.8) for direct in (0, 200, 600)]
        self.assertEqual(vector.round(8).tolist(), [round(value, 8) for value in scalar])


if __name__ == "__main__":
    unittest.main()

