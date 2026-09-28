"""Unit, range, gap, and Zarr tests for forecast harmonisation."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr

from pipeline.harmonise import QualityControlError, harmonise_dataset, write_harmonised_zarr


def source_dataset(times: list[str] | None = None) -> xr.Dataset:
    times = times or ["2026-05-01T00:00", "2026-05-01T01:00", "2026-05-01T02:00"]
    shape = (len(times), 1, 1)
    dataset = xr.Dataset(
        {
            "t2m": (("time", "latitude", "longitude"), np.full(shape, 303.15), {"units": "K"}),
            "d2m": (("time", "latitude", "longitude"), np.full(shape, 293.15), {"units": "K"}),
            "u10": (("time", "latitude", "longitude"), np.full(shape, 3.0), {"units": "m s-1"}),
            "v10": (("time", "latitude", "longitude"), np.full(shape, 4.0), {"units": "m s-1"}),
            "sp": (("time", "latitude", "longitude"), np.full(shape, 100_000.0), {"units": "Pa"}),
            "ssrd": (("time", "latitude", "longitude"), np.full(shape, 3_600_000.0), {"units": "J m-2"}),
        },
        coords={"time": np.asarray(times, dtype="datetime64[m]"), "latitude": [23.0], "longitude": [72.5]},
    )
    dataset["ssrd"].attrs["accumulation_seconds"] = 3600
    return dataset


class HarmoniseTest(unittest.TestCase):
    def test_converts_units_and_derives_humidity_and_wind(self) -> None:
        result = harmonise_dataset(source_dataset())

        self.assertAlmostEqual(float(result.temperature_c[0, 0, 0]), 30.0)
        self.assertAlmostEqual(float(result.relative_humidity_pct[0, 0, 0]), 55.1, places=1)
        self.assertAlmostEqual(float(result.wind_speed_m_s[0, 0, 0]), 5.0)
        self.assertAlmostEqual(float(result.shortwave_w_m2[0, 0, 0]), 1000.0)
        self.assertEqual(result.time.attrs["timezone"], "UTC")

    def test_rejects_hourly_gap(self) -> None:
        dataset = source_dataset(["2026-05-01T00:00", "2026-05-01T02:00"])
        with self.assertRaisesRegex(QualityControlError, "hourly gaps"):
            harmonise_dataset(dataset)

    def test_rejects_out_of_range_value(self) -> None:
        dataset = source_dataset()
        dataset["sp"][0, 0, 0] = -1
        with self.assertRaisesRegex(QualityControlError, "surface_pressure_pa"):
            harmonise_dataset(dataset)

    def test_qc_pass_writes_zarr_and_failure_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "forecast.zarr"
            write_harmonised_zarr(source_dataset(), output)
            reopened = xr.open_zarr(output)
            self.assertEqual(reopened.attrs["qc_status"], "pass")

            failed_output = Path(directory) / "failed.zarr"
            bad = source_dataset(["2026-05-01T00:00", "2026-05-01T02:00"])
            with self.assertRaises(QualityControlError):
                write_harmonised_zarr(bad, failed_output)
            self.assertFalse(failed_output.exists())


if __name__ == "__main__":
    unittest.main()
