"""Checks for the minimal live Open-Meteo operational pipeline."""

import unittest
from datetime import UTC, datetime, timedelta

from pipeline.operational import harmonise_district_forecast, solar_zenith_cosine


class OperationalPipelineTest(unittest.TestCase):
    def test_noaa_solar_geometry_near_equinox_noon(self) -> None:
        cosine = solar_zenith_cosine(datetime(2026, 3, 20, 12, tzinfo=UTC), 0, 0)
        self.assertGreater(cosine, 0.99)

    def test_harmonises_one_day_and_computes_finite_indices(self) -> None:
        start = datetime(2026, 5, 1, tzinfo=UTC)
        times = [(start + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M") for hour in range(24)]
        temperatures = [30.0] * 24
        temperatures[12] = 40.0
        document = {
            "hourly": {
                "time": times,
                "temperature_2m": temperatures,
                "relative_humidity_2m": [50.0] * 24,
                "surface_pressure": [1013.25] * 24,
                "wind_speed_10m": [2.0] * 24,
                "shortwave_radiation": [0.0] * 12 + [800.0] + [0.0] * 11,
                "direct_radiation": [0.0] * 12 + [500.0] + [0.0] * 11,
            }
        }
        result = harmonise_district_forecast(document, 23.0, 72.5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tmax_c"], 40.0)
        self.assertTrue(all(result[0][name] == result[0][name] for name in ("utci_c", "wbgt_est_c", "heat_index_c")))
        self.assertGreaterEqual(result[0]["utci_sun_c"], result[0]["utci_shade_c"])
        self.assertGreaterEqual(result[0]["stress_hours"], 0)

    def test_qc_rejects_out_of_range_humidity(self) -> None:
        document = {
            "hourly": {
                "time": ["2026-05-01T12:00"],
                "temperature_2m": [40.0],
                "relative_humidity_2m": [101.0],
                "surface_pressure": [1013.25],
                "wind_speed_10m": [2.0],
                "shortwave_radiation": [800.0],
                "direct_radiation": [500.0],
            }
        }
        with self.assertRaises(ValueError):
            harmonise_district_forecast(document, 23.0, 72.5)


if __name__ == "__main__":
    unittest.main()
