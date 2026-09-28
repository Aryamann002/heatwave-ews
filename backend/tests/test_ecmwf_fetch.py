"""Contract tests for direct ECMWF open-data ingestion."""

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pipeline.ecmwf_fetch import fetch_ecmwf


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, **options: object) -> None:
        self.options = options
        self.requests: list[dict[str, object]] = []
        self.__class__.instances.append(self)

    def retrieve(self, **request: object) -> None:
        self.requests.append(request)
        Path(str(request["target"])).write_bytes(b"grib-test-data")


class EcmwfFetchTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeClient.instances.clear()

    def test_ifs_fetch_is_checksummed_retry_configured_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_time = datetime(2026, 5, 1, 0, tzinfo=UTC)
            first = fetch_ecmwf(run_time, output_dir=directory, client_factory=FakeClient)
            second = fetch_ecmwf(run_time, output_dir=directory, client_factory=FakeClient)

            self.assertEqual(first, second)
            self.assertEqual(len(FakeClient.instances), 1)
            client = FakeClient.instances[0]
            self.assertEqual(client.options["source"], "aws")
            self.assertEqual(client.options["model"], "ifs")
            self.assertEqual(client.options["retry_after"], (1, 8, 2))
            self.assertEqual(client.options["maximum_retries"], 3)

            request = client.requests[0]
            self.assertEqual(request["date"], "20260501")
            self.assertEqual(request["time"], 0)
            self.assertEqual(request["stream"], "oper")
            self.assertEqual(request["type"], "fc")
            self.assertEqual(request["param"], ["2t", "2d", "10u", "10v", "sp", "ssrd"])
            self.assertEqual(request["step"][0], 0)
            self.assertEqual(request["step"][-1], 168)

            raw_path = Path(directory) / first["run_id"] / first["files"][0]["path"]
            self.assertEqual(first["files"][0]["sha256"], hashlib.sha256(raw_path.read_bytes()).hexdigest())
            self.assertEqual(first["status"], "complete")

    def test_aifs_uses_documented_six_hour_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = fetch_ecmwf(
                datetime(2026, 5, 1, 6, tzinfo=UTC),
                model="aifs-single",
                output_dir=directory,
                client_factory=FakeClient,
            )

            request = FakeClient.instances[0].requests[0]
            self.assertEqual(request["step"], list(range(0, 169, 6)))
            stored_manifest = json.loads(
                (Path(directory) / manifest["run_id"] / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(stored_manifest["model"], "aifs-single")

    def test_failed_retrieval_records_failure_and_no_partial_grib(self) -> None:
        class FailingClient(FakeClient):
            def retrieve(self, **request: object) -> None:
                Path(str(request["target"])).write_bytes(b"partial")
                raise OSError("network unavailable")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(OSError, "network unavailable"):
                fetch_ecmwf(
                    datetime(2026, 5, 1, tzinfo=UTC),
                    output_dir=directory,
                    client_factory=FailingClient,
                )

            run_dir = Path(directory) / "ecmwf-ifs-20260501T000000Z"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertFalse((run_dir / "forecast.grib2").exists())
            self.assertFalse((run_dir / "forecast.grib2.part").exists())


if __name__ == "__main__":
    unittest.main()
