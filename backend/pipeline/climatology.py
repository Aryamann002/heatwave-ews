"""1991-2020 daily temperature normals per district from the Open-Meteo ERA5 archive.

IMD heat-wave criteria need the departure of Tmax from its climatological normal. The
normal for a calendar day is the mean Tmax over 1991-2020 within +/-7 days of that day;
hot nights use the 90th percentile of Tmin over the same window.
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import psycopg

from app.repository import ensure_operational_tables
from pipeline.s1_fetch import fetch_bytes, load_districts

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
PERIOD = ("1991-01-01", "2020-12-31")
SOURCE = "Open-Meteo historical archive (ERA5), 1991-2020, +/-7 day window"
WINDOW_DAYS = 7


def fetch_daily_history(
    district: dict[str, Any], cache_dir: Path, opener: Callable[..., Any] = urlopen
) -> dict[str, Any]:
    """Fetch (or reuse cached) 30-year daily Tmax/Tmin for one district point."""
    path = cache_dir / f"{district['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    query = urlencode(
        {
            "latitude": district["latitude"],
            "longitude": district["longitude"],
            "start_date": PERIOD[0],
            "end_date": PERIOD[1],
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "Asia/Kolkata",
        }
    )
    # 30 years counts as many calls against the archive rate limit, so back off generously.
    body = fetch_bytes(f"{ARCHIVE_URL}?{query}", timeout=120, attempts=5, wait_s=60, opener=opener)
    document = json.loads(body)
    if "daily" not in document:
        raise ValueError(f"archive response invalid for {district['id']}: {document.get('reason')}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return document


def compute_normals(daily: dict[str, list]) -> dict[int, tuple[float, float, float]]:
    """Return {day_of_year: (normal_tmax, p90_tmax, p90_tmin)} over a +/-7 day window."""
    doys = np.array([date.fromisoformat(value).timetuple().tm_yday for value in daily["time"]])
    tmax = np.array(daily["temperature_2m_max"], dtype=float)
    tmin = np.array(daily["temperature_2m_min"], dtype=float)
    normals = {}
    for doy in range(1, 367):
        distance = np.abs(doys - doy)
        in_window = np.minimum(distance, 366 - distance) <= WINDOW_DAYS
        window_tmax = tmax[in_window & np.isfinite(tmax)]
        window_tmin = tmin[in_window & np.isfinite(tmin)]
        normals[doy] = (
            float(window_tmax.mean()),
            float(np.percentile(window_tmax, 90)),
            float(np.percentile(window_tmin, 90)),
        )
    return normals


def load_normals(database_url: str, district_id: str) -> dict[int, tuple[float, float, float]]:
    """Return stored normals for one district, or {} when not loaded yet."""
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT day_of_year, normal_tmax_c, p90_tmax_c, p90_tmin_c FROM climatology_daily"
            " WHERE district_id = %s",
            (district_id,),
        )
        return {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}


def main(*, missing_only: bool = False, cache_dir: str | Path = "data/raw/climatology") -> None:
    """Load normals for every configured district (only missing ones if asked)."""
    database_url = os.environ["DATABASE_URL"]
    ensure_operational_tables(database_url)
    districts = load_districts()
    if missing_only:
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT district_id FROM climatology_daily")
            loaded = {row[0] for row in cursor.fetchall()}
        districts = [district for district in districts if district["id"] not in loaded]
    for district in districts:
        normals = compute_normals(fetch_daily_history(district, Path(cache_dir))["daily"])
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO climatology_daily VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (district_id, day_of_year) DO UPDATE SET
                    normal_tmax_c = EXCLUDED.normal_tmax_c, p90_tmax_c = EXCLUDED.p90_tmax_c,
                    p90_tmin_c = EXCLUDED.p90_tmin_c, source = EXCLUDED.source
                """,
                [(district["id"], doy, *values, SOURCE) for doy, values in normals.items()],
            )
        print(f"Loaded climatology for {district['id']}", flush=True)


if __name__ == "__main__":
    main()
