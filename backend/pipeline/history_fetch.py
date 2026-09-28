"""Cached, resumable ERA5 and ERA5-Land history prefetch."""

import argparse
import calendar
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cdsapi

DATASETS = {
    "era5": "reanalysis-era5-single-levels",
    "era5-land": "reanalysis-era5-land",
}
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_pressure",
    "surface_solar_radiation_downwards",
]
INDIA_AREA = [38, 68, 6, 98]  # north, west, south, east


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(path)


def prefetch_history(
    start_year: int,
    end_year: int,
    datasets: list[str] | tuple[str, ...] = ("era5", "era5-land"),
    months: list[int] | tuple[int, ...] = tuple(range(1, 13)),
    output_dir: str | Path = "data/raw/history",
    client: Any | None = None,
) -> dict[str, Any]:
    """Download monthly India subsets to NetCDF, resuming verified cached files."""
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    if any(name not in DATASETS for name in datasets):
        raise ValueError(f"datasets must be chosen from {sorted(DATASETS)}")
    if any(month not in range(1, 13) for month in months):
        raise ValueError("months must be in 1..12")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"source": "Copernicus Climate Data Store", "licence": "CC BY 4.0", "files": []}
    entries = {item["key"]: item for item in manifest["files"]}

    for dataset_name in datasets:
        for year in range(start_year, end_year + 1):
            for month in months:
                key = f"{dataset_name}-{year:04d}-{month:02d}"
                path = root / dataset_name / f"{year:04d}" / f"{month:02d}.nc"
                cached = entries.get(key)
                if (
                    cached
                    and cached.get("status") == "complete"
                    and path.exists()
                    and cached.get("sha256") == _sha256(path)
                ):
                    continue

                path.parent.mkdir(parents=True, exist_ok=True)
                partial = path.with_suffix(".nc.part")
                request = {
                    "variable": VARIABLES,
                    "year": [f"{year:04d}"],
                    "month": [f"{month:02d}"],
                    "day": [f"{day:02d}" for day in range(1, calendar.monthrange(year, month)[1] + 1)],
                    "time": [f"{hour:02d}:00" for hour in range(24)],
                    "area": INDIA_AREA,
                    "data_format": "netcdf",
                    "download_format": "unarchived",
                }
                if dataset_name == "era5":
                    request["product_type"] = ["reanalysis"]
                try:
                    if client is None:
                        client = cdsapi.Client()
                    client.retrieve(DATASETS[dataset_name], request, str(partial))
                    if not partial.exists() or not partial.stat().st_size:
                        raise OSError("CDS retrieval produced no data")
                    partial.replace(path)
                    entries[key] = {
                        "key": key,
                        "dataset": DATASETS[dataset_name],
                        "path": path.relative_to(root).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                        "status": "complete",
                    }
                except Exception as error:
                    partial.unlink(missing_ok=True)
                    entries[key] = {
                        "key": key,
                        "dataset": DATASETS[dataset_name],
                        "path": path.relative_to(root).as_posix(),
                        "status": "failed",
                        "error": f"{type(error).__name__}: {error}",
                    }
                    manifest.update(
                        {"status": "failed", "updated_at": datetime.now(UTC).isoformat(), "files": list(entries.values())}
                    )
                    _write_manifest(manifest_path, manifest)
                    raise

                manifest.update(
                    {"status": "running", "updated_at": datetime.now(UTC).isoformat(), "files": list(entries.values())}
                )
                _write_manifest(manifest_path, manifest)

    manifest.update({"status": "complete", "updated_at": datetime.now(UTC).isoformat(), "files": list(entries.values())})
    _write_manifest(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start_year", type=int)
    parser.add_argument("end_year", type=int)
    parser.add_argument("--dataset", action="append", choices=sorted(DATASETS), dest="datasets")
    parser.add_argument("--output-dir", default="data/raw/history")
    args = parser.parse_args()
    prefetch_history(
        args.start_year,
        args.end_year,
        datasets=args.datasets or list(DATASETS),
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
