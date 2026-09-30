"""Replay a real historical heatwave through the live index and alert code.

Hourly ERA5 reanalysis for the scenario's 7 days is fetched once from the Open-Meteo archive
(the same variables as the live forecast) and run through harmonise_district_forecast and
evaluate_days. The computed result is cached to disk so a replay works without network.
"""

import json
import math
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from pipeline.climatology import load_normals
from pipeline.operational import evaluate_days, harmonise_district_forecast
from pipeline.s1_fetch import HOURLY_FIELDS, load_districts

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def load_scenarios(path: str | Path = "config/replay_scenarios.json") -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fetch_hourly(district: dict[str, Any], start: str, end: str) -> dict[str, Any]:
    query = urlencode(
        {
            "latitude": district["latitude"],
            "longitude": district["longitude"],
            "start_date": start,
            "end_date": end,
            "hourly": ",".join(HOURLY_FIELDS),
            "timezone": "Asia/Kolkata",
            "wind_speed_unit": "ms",
        }
    )
    for attempt in range(4):  # archive API: transient TLS timeouts and 429s under load
        try:
            with urlopen(f"{ARCHIVE_URL}?{query}", timeout=60) as response:
                document = json.loads(response.read())
            break
        except OSError:
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))
    if "hourly" not in document:
        raise ValueError(f"archive response invalid for {district['id']}: {document.get('reason')}")
    return document


def _number(value: Any) -> float | None:
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)


def run_replay(scenario_id: str, cache_dir: str | Path = "data/replay") -> dict[str, Any]:
    """Return the scenario's per-district, per-day indices and alerts (cached after first run)."""
    document = load_scenarios()
    scenario = next((item for item in document["scenarios"] if item["id"] == scenario_id), None)
    if scenario is None:
        raise KeyError(scenario_id)
    cache = Path(cache_dir) / f"{scenario_id}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    database_url = os.environ["DATABASE_URL"]
    items = []
    for district in load_districts():
        days = harmonise_district_forecast(
            _fetch_hourly(district, scenario["start"], scenario["end"]),
            district["latitude"],
            district["longitude"],
        )
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
