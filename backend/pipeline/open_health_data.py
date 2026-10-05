"""Validated loader for public demographic and heat-health reference data."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg


def _project_root() -> Path:
    """Resolve both repository layout and the backend Docker image layout."""
    candidates = (Path.cwd(), Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[1])
    for candidate in candidates:
        if (candidate / "config" / "open_health_sources.json").exists():
            return candidate
    return Path.cwd()


ROOT = _project_root()
MANIFEST_PATH = ROOT / "config" / "open_health_sources.json"
DATA_DIR = ROOT / "data" / "reference" / "health"


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("operational_training") is not False:
        raise ValueError("open health reference sources must be marked operational_training=false")
    return manifest


def _read_checked_csv(source: dict[str, Any], data_dir: Path = DATA_DIR) -> list[dict[str, str]]:
    path = data_dir / source["file"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != source["sha256"]:
        raise ValueError(f"checksum mismatch for {path.name}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != source["expected_rows"]:
        raise ValueError(f"row-count mismatch for {path.name}")
    return rows


def validate_reference_files(
    manifest_path: Path = MANIFEST_PATH,
    data_dir: Path = DATA_DIR,
) -> dict[str, Any]:
    """Validate checksums, schemas, keys and published control totals."""
    manifest = load_manifest(manifest_path)
    sources = {source["source_id"]: source for source in manifest["sources"]}
    census = _read_checked_csv(sources["census-c14-2011"], data_dir)
    npcchh = _read_checked_csv(sources["npcchh-heat-surveillance-2021-2024"], data_dir)
    ncrb = _read_checked_csv(sources["ncrb-heat-sunstroke-deaths-2018-2022"], data_dir)

    if len({row["district_id"] for row in census}) != 640:
        raise ValueError("Census reference must contain 640 unique district IDs")
    for row in census:
        total = int(row["total_population"])
        elderly = int(row["elderly_60_plus"])
        share = float(row["elderly_share"])
        if total <= 0 or elderly < 0 or elderly > total or not 0 <= share <= 1:
            raise ValueError(f"invalid Census demographic row for {row['district_id']}")
        if abs(share - elderly / total) > 0.000001:
            raise ValueError(f"incorrect elderly share for {row['district_id']}")
    if sum(int(row["total_population"]) for row in census) != 1_210_854_977:
        raise ValueError("Census district population control total does not match published India total")

    def validate_outcomes(rows: list[dict[str, str]]) -> None:
        keys: set[tuple[str, str, int, str]] = set()
        for row in rows:
            key = (row["source_id"], row["geography_name"], int(row["year"]), row["outcome_type"])
            if key in keys:
                raise ValueError(f"duplicate public outcome key: {key}")
            keys.add(key)
            if row["operational_training"].lower() != "false":
                raise ValueError("coarse public outcomes cannot be operational training data")
            if row["count_status"] == "reported" and (row["count"] == "" or int(row["count"]) < 0):
                raise ValueError(f"invalid reported count: {key}")
            if row["count_status"] == "not_reported" and row["count"] != "":
                raise ValueError(f"not-reported count must remain blank: {key}")

    validate_outcomes(npcchh)
    validate_outcomes(ncrb)
    missing_2021 = [
        row for row in npcchh
        if row["year"] == "2021" and row["outcome_type"] == "confirmed_heatstroke_deaths"
    ]
    if len(missing_2021) != 1 or missing_2021[0]["count_status"] != "not_reported":
        raise ValueError("NPCCHH 2021 confirmed deaths must be preserved as not reported")
    national = {
        int(row["year"]): int(row["count"])
        for row in ncrb if row["geography_level"] == "nation"
    }
    if national != {2018: 890, 2019: 1274, 2020: 530, 2021: 374, 2022: 730}:
        raise ValueError("NCRB national control totals do not match the source table")
    return {
        "status": "validated",
        "district_demographic_rows": len(census),
        "outcome_reference_rows": len(npcchh) + len(ncrb),
        "source_ids": sorted(sources),
    }


def seed_open_health_reference(database_url: str) -> dict[str, Any]:
    """Replace reference tables from pinned files without touching operational outcomes."""
    summary = validate_reference_files()
    manifest = load_manifest()
    sources = {source["source_id"]: source for source in manifest["sources"]}
    census = _read_checked_csv(sources["census-c14-2011"])
    outcomes = (
        _read_checked_csv(sources["npcchh-heat-surveillance-2021-2024"])
        + _read_checked_csv(sources["ncrb-heat-sunstroke-deaths-2018-2022"])
    )
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM district_demographics WHERE source_id='census-c14-2011'")
        cursor.executemany(
            """
            INSERT INTO district_demographics
                (district_id, census_state_code, census_district_code,
                 census_national_district_code, total_population, elderly_60_plus,
                 elderly_share, source_id, data_vintage)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'census-c14-2011','2011')
            """,
            [(
                row["district_id"], int(row["census_state_code"]), int(row["census_district_code"]),
                int(row["census_national_district_code"]), int(row["total_population"]),
                int(row["elderly_60_plus"]), float(row["elderly_share"]),
            ) for row in census],
        )
        cursor.execute(
            "DELETE FROM health_reference_observations WHERE source_id IN (%s,%s)",
            ("npcchh-heat-surveillance-2021-2024", "ncrb-heat-sunstroke-deaths-2018-2022"),
        )
        cursor.executemany(
            """
            INSERT INTO health_reference_observations
                (source_id, geography_level, geography_name, year, period_end,
                 outcome_type, count, count_status, operational_training, note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,false,%s)
            """,
            [(
                row["source_id"], row["geography_level"], row["geography_name"], int(row["year"]),
                row["period_end"] or None, row["outcome_type"],
                int(row["count"]) if row["count"] else None, row["count_status"], row["note"],
            ) for row in outcomes],
        )
    return summary
