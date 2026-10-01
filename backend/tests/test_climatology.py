import unittest
from datetime import date, timedelta

import numpy as np

from pipeline.climatology import _bilinear, compute_normals
from pipeline.operational import consecutive_hot_nights, evaluate_days


class ClimatologyTest(unittest.TestCase):
    def test_normals_use_a_window_that_wraps_the_year_end(self) -> None:
        days = [date(2000, 1, 1) + timedelta(days=offset) for offset in range(366 * 2)]
        daily = {
            "time": [day.isoformat() for day in days],
            # Tmax equals the day of year, so the Jan 1 window mixes late-December values.
            "temperature_2m_max": [float(day.timetuple().tm_yday) for day in days],
            "temperature_2m_min": [10.0 if day.month == 6 else 0.0 for day in days],
        }
        normals = compute_normals(daily)
        self.assertEqual(len(normals), 366)
        self.assertAlmostEqual(normals[180][0], 180.0, delta=0.5)
        self.assertGreater(normals[1][0], 100)  # includes Dec values, not just Jan 1-8
        self.assertEqual(normals[170][2], 10.0)  # mid-June p90 Tmin

    def test_hot_nights_count_consecutive_days_above_p90_tmin(self) -> None:
        days = [{"tmin_c": value} for value in (30, 31, 25, 31, 32, 33)]
        normals = [(0.0, 0.0, 30.0)] * 5 + [None]
        self.assertEqual(consecutive_hot_nights(days, normals), [1, 2, 0, 1, 2, 0])


    def test_last_days_of_a_heat_spell_keep_their_persistence(self) -> None:
        # Plains, normal 40 C: three severe days (> +6.4 C) then a normal day.
        days = [{"tmax_c": t, "tmin_c": 20.0, "utci_c": 30.0, "wbgt_est_c": 25.0} for t in (47.5, 47.5, 47.5, 38.0)]
        levels = [track1.level for _, track1, _, _ in evaluate_days("plains", days, [(40.0, 42.0, 30.0)] * 4)]
        self.assertEqual(levels[:3], ["red", "red", "red"])  # day 3 is still red, not reset
        self.assertEqual(levels[3], "green")


    def test_bilinear_weights_on_a_descending_grid(self) -> None:
        latitudes = np.array([30.0, 29.75, 29.5])  # ERA5 latitudes run north to south
        lower, upper, weight = _bilinear(latitudes, np.array([29.6]))
        value = latitudes[lower] * (1 - weight) + latitudes[upper] * weight
        self.assertAlmostEqual(float(value[0]), 29.6)

if __name__ == "__main__":
    unittest.main()
