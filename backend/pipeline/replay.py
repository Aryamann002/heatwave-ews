"""Replay a real historical heatwave through the live index and alert code.

Hourly ERA5 reanalysis for the scenario's 7 days is fetched once from the Open-Meteo archive
(the same variables as the live forecast) and run through harmonise_district_forecast and
evaluate_days. The computed result is cached to disk so a replay works without network.
"""

import json
from datetime import date
import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from app.alerts import load_alert_rules
from pipeline.climatology import load_normals
from pipeline.operational import evaluate_days, harmonise_district_forecast
from pipeline.s1_fetch import HOURLY_FIELDS, fetch_bytes, load_districts

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def load_scenarios(path: str | Path = "config/replay_scenarios.json") -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fetch_hourly(districts: list[dict[str, Any]], start: str, end: str, batch_size: int = 50) -> list[dict[str, Any]]:
    """Hourly ERA5 for many points, several locations per archive request (same order as districts)."""
    documents: list[dict[str, Any]] = []
    for offset in range(0, len(districts), batch_size):
        batch = districts[offset:offset + batch_size]
        query = urlencode(
            {
                "latitude": ",".join(str(district["latitude"]) for district in batch),
                "longitude": ",".join(str(district["longitude"]) for district in batch),
                "start_date": start,
                "end_date": end,
                "hourly": ",".join(HOURLY_FIELDS),
                "timezone": "Asia/Kolkata",
                "wind_speed_unit": "ms",
            }
        )
        parsed = json.loads(fetch_bytes(f"{ARCHIVE_URL}?{query}", timeout=120, attempts=6, wait_s=60))
        batch_documents = parsed if isinstance(parsed, list) else [parsed]
        if len(batch_documents) != len(batch) or any("hourly" not in document for document in batch_documents):
            raise ValueError(f"archive response invalid near {batch[0]['id']}")
        documents += batch_documents
    return documents


def _number(value: Any) -> float | None:
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)


def _score(district_days: list[tuple[dict[str, Any], list[dict[str, Any]]]], database_url: str) -> list[dict[str, Any]]:
    """Apply the current normals and alert rules to each district's daily values."""
    items = []
    for district, days in district_days:
        climatology = load_normals(database_url, district["id"])
        normals = [climatology.get(day["date"].timetuple().tm_yday) for day in days]
        for day, normal, (condition, track1, track2, combined) in zip(
            days, normals, evaluate_days(district["climate_zone"], days, normals), strict=True
        ):
            items.append(
                {
                    "district_id": district["id"],
                    "date": day["date"].isoformat(),
                    "level": combined.level,
                    "track1_level": track1.level,
                    "track2_level": track2.level,
                    "disagreement": combined.disagreement,
                    "reasoning": list(condition.reasons + track1.reasons + track2.reasons + combined.reasons),
                    "rule_version": track1.rule_version,
                    "tmax_c": day["tmax_c"],
                    "tmin_c": day["tmin_c"],
                    "relative_humidity_pct": day["relative_humidity_pct"],
                    "wind_speed_m_s": day["wind_speed_m_s"],
                    "normal_tmax_c": normal[0] if normal else None,
                    "departure_c": day["tmax_c"] - normal[0] if normal else None,
                    "utci_c": _number(day["utci_c"]),
                    "wbgt_est_c": _number(day["wbgt_est_c"]),
                    "heat_index_c": _number(day["heat_index_c"]),
                }
            )
    return items


def run_replay(scenario_id: str, cache_dir: str | Path = "data/replay") -> dict[str, Any]:
    """Return the scenario's per-district, per-day indices and alerts (cached after first run)."""
    document = load_scenarios()
    scenario = next((item for item in document["scenarios"] if item["id"] == scenario_id), None)
    if scenario is None:
        raise KeyError(scenario_id)
    cache = Path(cache_dir) / f"{scenario_id}.json"
    districts = load_districts()
    database_url = os.environ["DATABASE_URL"]
    if cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        # Reuse only if it covers the configured districts (the district list may have grown).
        if {row["district_id"] for row in cached["items"]} == {district["id"] for district in districts}:
            if all(row["rule_version"] == load_alert_rules()["version"] for row in cached["items"]):
                return cached
            # Rules changed: re-score the cached daily values; no need to download the weather again.
            by_district: dict[str, list[dict[str, Any]]] = {}
            for row in cached["items"]:
                by_district.setdefault(row["district_id"], []).append({**row, "date": date.fromisoformat(row["date"])})
            items = _score([(district, by_district[district["id"]]) for district in districts], database_url)
            cached["items"] = items
            cache.write_text(json.dumps(cached), encoding="utf-8")
            return cached

    hourly = _fetch_hourly(districts, scenario["start"], scenario["end"])
    items = _score(
        [
            (district, harmonise_district_forecast(document_hourly, district["latitude"], district["longitude"]))
            for district, document_hourly in zip(districts, hourly, strict=True)
        ],
        database_url,
    )
    result = {
        **scenario,
        "mode": "replay",
        "source": "ERA5 reanalysis via Open-Meteo archive; alerts computed by the live rules",
        "note": document["note"],
        "items": items,
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result), encoding="utf-8")
    return result


if __name__ == "__main__":  # pre-compute every scenario so the demo works offline
    for item in load_scenarios()["scenarios"]:
        run_replay(item["id"])
        print(f"cached replay {item['id']}")
