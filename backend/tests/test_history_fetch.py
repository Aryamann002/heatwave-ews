"""Caching and resume tests for ERA5 history prefetch."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from pipeline.history_fetch import prefetch_history


class FakeCdsClient:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []
        self.fail_on_call = fail_on_call

    def retrieve(self, dataset: str, request: dict[str, object], target: str) -> None:
        self.calls.append((dataset, request, target))
        if len(self.calls) == self.fail_on_call:
            Path(target).write_bytes(b"partial")
            raise OSError("CDS queue failure")
        Path(target).write_bytes(f"{dataset}-{request['month']}".encode())


class HistoryFetchTest(unittest.TestCase):
    def test_prefetch_builds_monthly_era5_and_land_requests(self) -> None:
        client = FakeCdsClient()
        with tempfile.TemporaryDirectory() as directory:
            manifest = prefetch_history(
                2024,
                2024,
                months=[2],
                output_dir=directory,
                client=client,
            )

            self.assertEqual(len(client.calls), 2)
            era5_dataset, request, _ = client.calls[0]
            self.assertEqual(era5_dataset, "reanalysis-era5-single-levels")
            self.assertEqual(request["day"][-1], "29")
            self.assertEqual(request["area"], [38, 68, 6, 98])
            self.assertIn("2m_dewpoint_temperature", request["variable"])
            self.assertIn("surface_solar_radiation_downwards", request["variable"])
            self.assertEqual(manifest["status"], "complete")
            for item in manifest["files"]:
                path = Path(directory) / item["path"]
                self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_resume_skips_verified_files_after_interruption(self) -> None:
        first_client = FakeCdsClient(fail_on_call=2)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(OSError, "CDS queue failure"):
                prefetch_history(
                    2023,
                    2023,
                    datasets=["era5"],
                    months=[1, 2],
                    output_dir=directory,
                    client=first_client,
                )

            self.assertFalse(any(Path(directory).rglob("*.part")))
            second_client = FakeCdsClient()
            manifest = prefetch_history(
                2023,
                2023,
                datasets=["era5"],
                months=[1, 2],
                output_dir=directory,
                client=second_client,
            )

            self.assertEqual(len(second_client.calls), 1)
            self.assertEqual(second_client.calls[0][1]["month"], ["02"])
            self.assertEqual(manifest["status"], "complete")


if __name__ == "__main__":
    unittest.main()
