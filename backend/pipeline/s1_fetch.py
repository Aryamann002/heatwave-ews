"""Stage 1: immutable Open-Meteo forecast ingestion."""

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import urlopen

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_MODEL = "ecmwf_ifs025"  # ECMWF IFS 0.25 deg open data
BATCH_SIZE = 50
HOURLY_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "shortwave_radiation",
    "direct_radiation",
)


def fetch_bytes(
    url: str,
    *,
    timeout: float = 30,
    attempts: int = 4,
    wait_s: float = 15,
    opener: Callable[..., Any] = urlopen,
) -> bytes:
    """GET with retries on dropped connections, rate limits (429) and 5xx; other HTTP errors raise."""
    for attempt in range(attempts):
        try:
            with opener(url, timeout=timeout) as response:
                return response.read()
        except HTTPError as error:
            if error.code != 429 and error.code < 500 or attempt == attempts - 1:
                raise
        except OSError:  # URLError, TLS EOF, timeouts
            if attempt == attempts - 1:
                raise
        time.sleep(wait_s * (attempt + 1))
    raise AssertionError("unreachable")


def load_districts(path: str | Path = "config/districts.yaml") -> list[dict[str, Any]]:
    """Load pilot district point coordinates from JSON-compatible YAML."""
    districts = json.loads(Path(path).read_text(encoding="utf-8"))["districts"]
    required = {"id", "name", "state", "latitude", "longitude", "climate_zone"}
    if not districts or any(not required <= district.keys() for district in districts):
        raise ValueError("each pilot district must define identity, coordinates, and zone")
    return districts


def fetch_open_meteo(
    districts: list[dict[str, Any]],
    run_time: datetime,
    output_dir: str | Path = "data/raw/open-meteo",
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    """Fetch hourly SI forecasts once for a UTC run time and return its manifest."""
    if run_time.tzinfo is None:
        raise ValueError("run_time must be timezone-aware")
    run_time = run_time.astimezone(UTC)
    run_id = f"open-meteo-{run_time:%Y%m%dT%H%M%SZ}"
    run_dir = Path(output_dir) / run_id
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # Reuse only if it covers exactly the configured districts (config may have grown).
        if [item["district_id"] for item in manifest["files"]] == [d["id"] for d in districts]:
            return manifest

    run_dir.mkdir(parents=True, exist_ok=True)
    files = []
    # Many locations per request (Open-Meteo returns a list); keeps a 641-district run to ~13 requests.
    for start in range(0, len(districts), BATCH_SIZE):
        batch = districts[start:start + BATCH_SIZE]
        query = urlencode(
            {
                "latitude": ",".join(str(district["latitude"]) for district in batch),
                "longitude": ",".join(str(district["longitude"]) for district in batch),
                "hourly": ",".join(HOURLY_FIELDS),
                "forecast_days": 7,
                "timezone": "Asia/Kolkata",  # daily aggregation uses the local (IST) day
                "wind_speed_unit": "ms",
                # Explicit model, so live data match the history the Tmax corrector is trained on.
                "models": FORECAST_MODEL,
            }
        )
        parsed = json.loads(fetch_bytes(f"{OPEN_METEO_URL}?{query}", opener=opener))
        documents = parsed if isinstance(parsed, list) else [parsed]
        if len(documents) != len(batch):
            raise ValueError(f"Open-Meteo returned {len(documents)} locations for {len(batch)} requested")
        for district, document in zip(batch, documents, strict=True):
            if document.get("error") or "hourly" not in document:
                raise ValueError(f"Open-Meteo response invalid: {document.get('reason', 'missing hourly data')}")
            body = json.dumps(document).encode()
            raw_path = run_dir / f"{district['id']}.json"
            raw_path.write_bytes(body)
            files.append(
                {
                    "district_id": district["id"],
                    "path": raw_path.name,
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )

    manifest = {
        "run_id": run_id,
        "source": "open-meteo",
        "source_run_time": run_time.isoformat(),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "status": "complete",
        "files": files,
    }
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(manifest_path)
    return manifest
