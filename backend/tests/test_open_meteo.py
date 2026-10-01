"""Mocked HTTP and idempotency tests for Open-Meteo ingestion."""

import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pipeline.s1_fetch import fetch_open_meteo, load_districts


class OpenMeteoFetchTest(unittest.TestCase):
    def test_fetch_stores_manifest_and_is_idempotent(self) -> None:
        calls: list[str] = []
        payload = json.dumps(
            {
                "latitude": 23.0,
                "longitude": 72.5,
                "hourly": {"time": ["2026-05-01T00:00"], "temperature_2m": [35.0]},
            }
        ).encode()

        class Response(io.BytesIO):
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_: object) -> None:
                self.close()

        def opener(url: str, timeout: int) -> Response:
            calls.append(url)
            self.assertEqual(timeout, 30)
            return Response(payload)

        with tempfile.TemporaryDirectory() as directory:
            run_time = datetime(2026, 5, 1, tzinfo=UTC)
            district = load_districts()[0]
            first = fetch_open_meteo([district], run_time, directory, opener)
            second = fetch_open_meteo([district], run_time, directory, opener)

            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1)
            stored = Path(directory) / first["run_id"] / first["files"][0]["path"]
            self.assertTrue(stored.exists())
            self.assertEqual(len(first["files"][0]["sha256"]), 64)
            self.assertIn("timezone=Asia%2FKolkata", calls[0])
            self.assertIn("wind_speed_unit=ms", calls[0])
            self.assertIn("direct_radiation", calls[0])


    def test_batched_request_splits_locations_into_per_district_files(self) -> None:
        calls: list[str] = []

        class Response(io.BytesIO):
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_: object) -> None:
                self.close()

        def opener(url: str, timeout: int) -> Response:
            calls.append(url)
            return Response(json.dumps([
                {"latitude": 1.0, "hourly": {"time": ["2026-05-01T00:00"]}},
                {"latitude": 2.0, "hourly": {"time": ["2026-05-01T00:00"]}},
            ]).encode())

        with tempfile.TemporaryDirectory() as directory:
            manifest = fetch_open_meteo(load_districts()[:2], datetime(2026, 5, 1, tzinfo=UTC), directory, opener)
            self.assertEqual(len(calls), 1)
            stored = [json.loads((Path(directory) / manifest["run_id"] / item["path"]).read_text()) for item in manifest["files"]]
            self.assertEqual([doc["latitude"] for doc in stored], [1.0, 2.0])

    def test_fetch_retries_a_dropped_connection_but_not_a_bad_request(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        from pipeline.s1_fetch import fetch_bytes

        calls = []

        def flaky(url: str, timeout: float):
            calls.append(url)
            if len(calls) == 1:
                raise OSError("TLS EOF")
            return BytesIO(b"ok")

        self.assertEqual(fetch_bytes("https://test", wait_s=0, opener=flaky), b"ok")
        self.assertEqual(len(calls), 2)

        def bad_request(url: str, timeout: float):
            calls.append(url)
            raise HTTPError(url, 400, "bad", {}, None)

        calls.clear()
        with self.assertRaises(HTTPError):
            fetch_bytes("https://test", wait_s=0, opener=bad_request)
        self.assertEqual(len(calls), 1)

if __name__ == "__main__":
    unittest.main()
