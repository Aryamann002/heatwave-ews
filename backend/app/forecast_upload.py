"""Validate and stage a short-lived, pre-fetched forecast bundle."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from pipeline.s1_fetch import load_districts

MAX_COMPRESSED_BYTES = 15_000_000
MAX_UNCOMPRESSED_BYTES = 30_000_000


def stage_bundle(body: bytes) -> tuple[datetime, Path]:
    """Return (forecast run time, private temp root) after verifying every raw file."""
    if not body or len(body) > MAX_COMPRESSED_BYTES:
        raise ValueError("Forecast bundle is empty or too large")
    try:
        archive = ZipFile(io.BytesIO(body))
        names = archive.namelist()
        if len(names) != len(set(names)) or sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("Forecast bundle has duplicate entries or exceeds the size limit")
        manifest_bytes = archive.read("manifest.json")
        if len(manifest_bytes) > 200_000:
            raise ValueError("Forecast manifest is too large")
        manifest = json.loads(manifest_bytes)
        run_time = datetime.fromisoformat(manifest["source_run_time"])
        retrieved = datetime.fromisoformat(manifest["retrieved_at"])
        if run_time.tzinfo is None or retrieved.tzinfo is None:
            raise ValueError("Forecast timestamps must include a time zone")
        run_time = run_time.astimezone(UTC)
        retrieved = retrieved.astimezone(UTC)
        now = datetime.now(UTC)
        expected_id = f"open-meteo-{run_time:%Y%m%dT%H%M%SZ}"
        if (manifest.get("run_id") != expected_id or manifest.get("source") != "open-meteo"
                or manifest.get("status") != "complete" or run_time.minute != 0
                or run_time.hour % 6 != 0 or now - run_time > timedelta(hours=8)
                or run_time - now > timedelta(minutes=5)
                or now - retrieved > timedelta(hours=2) or retrieved - now > timedelta(minutes=5)):
            raise ValueError("Forecast bundle is stale or has invalid provenance")

        configured = [district["id"] for district in load_districts()]
        files = manifest["files"]
        if not isinstance(files, list) or [item["district_id"] for item in files] != configured:
            raise ValueError("Forecast bundle does not cover every configured district")
        expected_names = {"manifest.json", *(f"{district_id}.json" for district_id in configured)}
        if set(names) != expected_names:
            raise ValueError("Forecast bundle has missing or unexpected files")

        checked: list[tuple[str, bytes]] = []
        for district_id, record in zip(configured, files, strict=True):
            filename = f"{district_id}.json"
            if record["path"] != filename:
                raise ValueError("Forecast manifest has an invalid file path")
            raw = archive.read(filename)
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("Forecast file checksum mismatch")
            document = json.loads(raw)
            if not isinstance(document, dict) or "hourly" not in document or document.get("error"):
                raise ValueError("Forecast file is not a valid hourly response")
            checked.append((filename, raw))
    except (BadZipFile, KeyError, TypeError, UnicodeDecodeError, OverflowError) as error:
        raise ValueError("Forecast bundle is malformed") from error

    root = Path(tempfile.mkdtemp(prefix="heatsafe-forecast-"))
    run_dir = root / expected_id
    run_dir.mkdir()
    (run_dir / "manifest.json").write_bytes(manifest_bytes)
    for filename, raw in checked:
        (run_dir / filename).write_bytes(raw)
    return run_time, root
