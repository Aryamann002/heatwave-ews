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
            self.assertIn("timezone=UTC", calls[0])
            self.assertIn("wind_speed_unit=ms", calls[0])
            self.assertIn("direct_radiation", calls[0])


if __name__ == "__main__":
    unittest.main()
