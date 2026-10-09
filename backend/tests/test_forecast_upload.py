"""Restricted forecast bundle validation and route checks."""

import hashlib
import io
import json
import os
import shutil
import unittest
from datetime import UTC, datetime
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.forecast_upload import stage_bundle
from app.main import app


def bundle(*, corrupt: bool = False) -> bytes:
    now = datetime.now(UTC)
    run_time = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
    raw = b'{"hourly":{"time":["2026-10-09T00:00"]}}'
    manifest = {
        "run_id": f"open-meteo-{run_time:%Y%m%dT%H%M%SZ}",
        "source": "open-meteo", "source_run_time": run_time.isoformat(),
        "retrieved_at": now.isoformat(), "status": "complete",
        "files": [
            {"district_id": name, "path": f"{name}.json", "sha256": hashlib.sha256(raw).hexdigest()}
            for name in ("one", "two")
        ],
    }
    if corrupt:
        manifest["files"][0]["sha256"] = "0" * 64
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("one.json", raw)
        archive.writestr("two.json", raw)
    return output.getvalue()


class ForecastUploadTest(unittest.TestCase):
    def test_bundle_is_verified_before_staging(self) -> None:
        with patch("app.forecast_upload.load_districts", return_value=[{"id": "one"}, {"id": "two"}]):
            run_time, root = stage_bundle(bundle())
            try:
                self.assertTrue((root / f"open-meteo-{run_time:%Y%m%dT%H%M%SZ}" / "two.json").exists())
            finally:
                shutil.rmtree(root)
            with self.assertRaisesRegex(ValueError, "checksum"):
                stage_bundle(bundle(corrupt=True))

    def test_upload_requires_dedicated_secret(self) -> None:
        with patch.dict(os.environ, {"HEATSAFE_FORECAST_UPLOAD_TOKEN": "x" * 40}), TestClient(app) as client:
            self.assertEqual(client.post("/forecast-upload", content=bundle()).status_code, 401)
            self.assertEqual(client.get("/forecast-upload/status").status_code, 401)

    def test_valid_token_starts_only_checked_bundle(self) -> None:
        with patch.dict(os.environ, {"HEATSAFE_FORECAST_UPLOAD_TOKEN": "x" * 40}), \
             patch("app.main.stage_bundle", return_value=(datetime.now(UTC), "staged")) as staged, \
             patch("app.main.start_uploaded", return_value={"state": "running"}) as start, \
             TestClient(app) as client:
            response = client.post("/forecast-upload", content=b"zip", headers={"Authorization": "Bearer " + "x" * 40})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["state"], "running")
            staged.assert_called_once_with(b"zip")
            start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
