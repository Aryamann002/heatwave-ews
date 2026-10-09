"""Fetch fresh Open-Meteo data off Render, then upload it for normal QC.

GitHub Actions runs this without a laptop. A dedicated upload token authorizes
only the forecast bundle endpoint; no Render API key or database URL is used.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline.s1_fetch import fetch_open_meteo, load_districts  # noqa: E402

BASE_URL = os.environ.get("HEATSAFE_BASE_URL", "https://heatsafe-ai-demo.onrender.com").rstrip("/")
POLL_SECONDS = 30
MAX_SECONDS = 75 * 60


def request_json(method: str, path: str, token: str, body: bytes | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/zip"
    request = Request(BASE_URL + path, data=body, method=method, headers=headers)
    for attempt in range(4):
        try:
            with urlopen(request, timeout=120) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {502, 503, 504} or attempt == 3:
                raise RuntimeError(f"{path} returned HTTP {error.code}") from None
        except (TimeoutError, URLError):
            if attempt == 3:
                raise RuntimeError(f"{path} did not respond after retries") from None
        time.sleep(15 * (attempt + 1))
    raise AssertionError("unreachable")


def zip_run(run_dir: Path) -> bytes:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    payload = io.BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(run_dir / "manifest.json", "manifest.json")
        for record in manifest["files"]:
            archive.write(run_dir / record["path"], record["path"])
    return payload.getvalue()


def build_bundle() -> bytes:
    existing = os.environ.get("HEATSAFE_PRELOAD_RAW_DIR")
    if existing:
        print("Using a locally pre-fetched forecast bundle.", flush=True)
        return zip_run(Path(existing).resolve())
    now = datetime.now(UTC)
    run_time = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
    with tempfile.TemporaryDirectory(prefix="heatsafe-fetch-") as temporary:
        manifest = fetch_open_meteo(load_districts(ROOT / "config" / "districts.yaml"), run_time, temporary)
        return zip_run(Path(temporary) / manifest["run_id"])


def seven_day_overview(token: str) -> tuple[bool, str]:
    overview = request_json("GET", "/forecast-upload/verify", token)
    status = overview.get("data_status", {})
    if (status.get("state") != "current" or overview.get("day_count") != 7
            or overview.get("district_count") != 641 or overview.get("alert_count") != 641 * 7
            or overview.get("missing_level_count") != 0):
        return False, str(status.get("state", "unavailable"))
    return True, str(status.get("run_id", "unknown run"))


def main() -> int:
    token = os.environ.get("HEATSAFE_FORECAST_UPLOAD_TOKEN", "")
    parsed = urlparse(BASE_URL)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.path:
        print("HEATSAFE_BASE_URL must be an HTTPS origin without credentials or a path.", file=sys.stderr)
        return 2
    if len(token) < 32:
        print("Set the restricted HEATSAFE_FORECAST_UPLOAD_TOKEN secret first.", file=sys.stderr)
        return 2
    try:
        bundle = build_bundle()
        print(f"Fetched and packaged {len(bundle):,} bytes of seven-day forecast data.", flush=True)
        state = request_json("POST", "/forecast-upload", token, bundle)
        started = time.monotonic()
        print(f"Forecast processing: {state.get('state', 'unknown')}", flush=True)
        while time.monotonic() - started < MAX_SECONDS:
            if state.get("state") == "failed":
                print("Forecast quality checks or processing failed; see Render logs.", file=sys.stderr)
                return 1
            if state.get("state") == "succeeded":
                complete, detail = seven_day_overview(token)
                if complete:
                    print(f"Fresh seven-day forecast is ready: {detail}", flush=True)
                    return 0
            time.sleep(POLL_SECONDS)
            state = request_json("GET", "/forecast-upload/status", token)
            print(f"Forecast processing: {state.get('state', 'unknown')}", flush=True)
        print("Forecast did not complete within 75 minutes.", file=sys.stderr)
        return 1
    except (RuntimeError, KeyError, ValueError, OSError) as error:
        print(f"Preload failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
