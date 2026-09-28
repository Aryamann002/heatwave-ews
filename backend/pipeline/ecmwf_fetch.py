"""Stage 1: immutable direct ECMWF IFS/AIFS open-data ingestion."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ecmwf.opendata import Client

PARAMETERS = ["2t", "2d", "10u", "10v", "sp", "ssrd"]
MODELS = {"ifs", "aifs-single"}


def _steps(model: str, cycle_hour: int) -> list[int]:
    if model == "aifs-single":
        return list(range(0, 169, 6))
    if cycle_hour in {6, 18}:
        return list(range(0, 91, 3))
    return [*range(0, 145, 3), *range(150, 169, 6)]


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_ecmwf(
    run_time: datetime,
    model: str = "ifs",
    source: str = "aws",
    output_dir: str | Path = "data/raw/ecmwf",
    client_factory: Callable[..., Any] = Client,
) -> dict[str, Any]:
    """Fetch free 0.25° forecast fields for one UTC model cycle into GRIB2."""
    if run_time.tzinfo is None:
        raise ValueError("run_time must be timezone-aware")
    run_time = run_time.astimezone(UTC)
    if run_time.hour not in {0, 6, 12, 18} or run_time.minute or run_time.second:
        raise ValueError("run_time must identify a 00/06/12/18 UTC model cycle")
    if model not in MODELS:
        raise ValueError(f"model must be one of {sorted(MODELS)}")

    run_id = f"ecmwf-{model}-{run_time:%Y%m%dT%H%M%SZ}"
    run_dir = Path(output_dir) / run_id
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("status") == "complete":
            return existing

    run_dir.mkdir(parents=True, exist_ok=True)
    raw_path = run_dir / "forecast.grib2"
    partial_path = raw_path.with_suffix(".grib2.part")
    request = {
        "date": run_time.strftime("%Y%m%d"),
        "time": run_time.hour,
        "stream": "oper",
        "type": "fc",
        "step": _steps(model, run_time.hour),
        "param": PARAMETERS,
        "target": str(partial_path),
    }
    base_manifest = {
        "run_id": run_id,
        "source": f"ecmwf-open-data:{source}",
        "model": model,
        "resolution_degrees": 0.25,
        "source_run_time": run_time.isoformat(),
        "parameters": PARAMETERS,
        "steps_hours": request["step"],
        "licence": "CC BY 4.0",
    }

    try:
        client = client_factory(
            source=source,
            model=model,
            resol="0p25",
            infer_stream_keyword=False,
            maximum_retries=3,
            retry_after=(1, 8, 2),
            use_server_retry_after=True,
        )
        client.retrieve(**request)
        if not partial_path.exists() or not partial_path.stat().st_size:
            raise OSError("ECMWF retrieval produced no data")
        partial_path.replace(raw_path)
    except Exception as error:
        partial_path.unlink(missing_ok=True)
        failed = {
            **base_manifest,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "files": [],
        }
        _write_manifest(manifest_path, failed)
        raise

    manifest = {
        **base_manifest,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "status": "complete",
        "files": [
            {
                "path": raw_path.name,
                "bytes": raw_path.stat().st_size,
                "sha256": _sha256(raw_path),
            }
        ],
    }
    _write_manifest(manifest_path, manifest)
    return manifest
