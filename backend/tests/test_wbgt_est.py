"""Reference and behavior tests for estimated outdoor WBGT."""

import unittest

from indices.wbgt_est import calculate_wbgt_est


class EstimatedWBGTTest(unittest.TestCase):
    def test_matches_thermofeel_reference_case(self) -> None:
        # ECMWF thermofeel v2.3.0 test vectors, first row.
        result = calculate_wbgt_est(
            air_temperature_c=36.85,
            relative_humidity_pct=15.9333804015635625,
            surface_pressure_hpa=1013.25,
            wind_speed_10m_m_s=2,
            shortwave_radiation_w_m2=604146.4934 / 3600,
            direct_radiation_fraction=374150.1613 / 604146.4934,
            cosine_solar_zenith=0.5,
        )
        self.assertAlmostEqual(result, 25.2840833516603, places=6)

    def test_higher_humidity_increases_hot_weather_stress(self) -> None:
        inputs = dict(
            air_temperature_c=40,
            surface_pressure_hpa=1013.25,
            wind_speed_10m_m_s=2,
            shortwave_radiation_w_m2=800,
            direct_radiation_fraction=0.6,
            cosine_solar_zenith=0.7,
        )
        self.assertGreater(
            calculate_wbgt_est(relative_humidity_pct=80, **inputs),
            calculate_wbgt_est(relative_humidity_pct=20, **inputs),
        )

    def test_accepts_array_inputs_including_zero_sun(self) -> None:
        result = calculate_wbgt_est(
            [35, 36], [40, 50], 1013.25, 2, [0, 800], [0, 0.6], [0, 0.7]
        )
        self.assertEqual(result.shape, (2,))
        self.assertTrue(all(result == result))  # neither value is NaN

    def test_rejects_invalid_relative_humidity(self) -> None:
        with self.assertRaises(ValueError):
            calculate_wbgt_est(40, 101, 1013.25, 2, 800, 0.6, 0.7)


if __name__ == "__main__":
    unittest.main()
