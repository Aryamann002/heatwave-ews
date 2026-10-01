"""1991-2020 daily temperature normals per district.

IMD heat-wave criteria need the departure of Tmax from its climatological normal. The
normal for a calendar day is the mean Tmax over 1991-2020 within +/-7 days of that day;
hot nights use the 90th percentile of Tmin over the same window.

Normals are computed offline and committed to NORMALS_FILE; the pipeline only loads that file,
so it never blocks on a 30-year download. Offline sources:

    python -m pipeline.climatology cds         # Copernicus ERA5 hourly 2 m temperature for all districts,
                                               # sampled at each forecast point (needs CDSAPI_URL/CDSAPI_KEY)
    python -m pipeline.climatology open-meteo  # Open-Meteo ERA5 archive, one district per request (rate-limited)
    python -m pipeline.climatology load        # load the committed file into the database
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
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
CDS_SOURCE = (
    "Copernicus ERA5 hourly 2 m temperature, 1991-2020, IST daily max/min, bilinear at forecast point, "
    "lapse-rate adjusted to point elevation, +/-7 day window"
)
LAPSE_RATE_C_PER_M = 0.0065  # standard atmosphere, as in indices/downscaling.py
CDS_DATASET = "reanalysis-era5-single-levels"
CDS_HOURS_UTC = (22, 23, 0, 1, 7, 8, 9, 10, 11)  # 03:30-06:30 IST (minimum) and 12:30-16:30 IST (maximum)
INDIA_AREA = [37.5, 67.5, 6.0, 98.0]  # north, west, south, east
NORMALS_FILE = Path("data/climatology/normals_era5.json")
WINDOW_DAYS = 7

Normals = dict[int, tuple[float, float, float]]


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


def compute_normals(daily: dict[str, list]) -> Normals:
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


def load_normals(database_url: str, district_id: str) -> Normals:
    """Return stored normals for one district, or {} when not loaded yet."""
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT day_of_year, normal_tmax_c, p90_tmax_c, p90_tmin_c FROM climatology_daily"
            " WHERE district_id = %s",
            (district_id,),
        )
        return {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}


def main(*, missing_only: bool = False, path: Path = NORMALS_FILE) -> None:
    """Load committed normals into the database (no network); only districts not yet loaded from it if asked."""
    if not path.exists():
        print(f"no committed normals at {path}; Track 1 uses absolute thresholds only", flush=True)
        return
    database_url = os.environ["DATABASE_URL"]
    ensure_operational_tables(database_url)
    document = json.loads(path.read_text(encoding="utf-8"))
    configured = {district["id"] for district in load_districts()}
    wanted = configured & document["districts"].keys()
    if missing_only:
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT district_id FROM climatology_daily WHERE source = %s", (document["source"],))
            wanted -= {row[0] for row in cursor.fetchall()}
    rows = [
        (district_id, doy, *values, document["source"])
        for district_id in sorted(wanted)
        for doy, values in enumerate(document["districts"][district_id]["normals"], start=1)
    ]
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO climatology_daily VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (district_id, day_of_year) DO UPDATE SET
                normal_tmax_c = EXCLUDED.normal_tmax_c, p90_tmax_c = EXCLUDED.p90_tmax_c,
                p90_tmin_c = EXCLUDED.p90_tmin_c, source = EXCLUDED.source
            """,
            rows,
        )
    missing = len(configured - document["districts"].keys())
    print(f"loaded normals for {len(wanted)} districts; {missing} configured districts have none", flush=True)


def write_normals(normals: dict[str, Normals], districts: list[dict[str, Any]], source: str, path: Path = NORMALS_FILE) -> None:
    """Commit-friendly file: 366 rows of (normal Tmax, p90 Tmax, p90 Tmin) per district, rounded to 0.01 C."""
    points = {district["id"]: district for district in districts}
    document = {
        "source": source,
        "period": list(PERIOD),
        "window_days": WINDOW_DAYS,
        "columns": ["normal_tmax_c", "p90_tmax_c", "p90_tmin_c"],
        "districts": {
            district_id: {
                "latitude": points[district_id]["latitude"],
                "longitude": points[district_id]["longitude"],
                "normals": [[round(value, 2) for value in values[doy]] for doy in range(1, 367)],
            }
            for district_id, values in sorted(normals.items())
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")


def _bilinear(grid: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lower index, upper index and upper weight of each value on a monotonic 1-D grid."""
    order = np.argsort(grid)
    position = np.interp(values, grid[order], np.arange(len(grid)))
    lower = np.floor(position).astype(int).clip(0, len(grid) - 2)
    return order[lower], order[lower + 1], position - lower


def point_elevations(districts: list[dict[str, Any]], runs_dir: Path = Path("data/raw/open-meteo")) -> np.ndarray:
    """Elevation (m) Open-Meteo uses for each forecast point, from the newest forecast run that has it."""
    found: dict[str, float] = {}
    for run in sorted(runs_dir.glob("open-meteo-*"), reverse=True):
        for district in districts:
            path = run / f"{district['id']}.json"
            if district["id"] not in found and path.exists():
                found[district["id"]] = float(json.loads(path.read_text(encoding="utf-8"))["elevation"])
        if len(found) == len(districts):
            break
    missing = [district["id"] for district in districts if district["id"] not in found]
    if missing:
        raise ValueError(f"no forecast run has elevations for {len(missing)} districts (e.g. {missing[:3]}); run the pipeline first")
    return np.array([found[district["id"]] for district in districts])


def build_from_cds(cache_dir: Path = Path("data/raw/era5_hourly"), years_per_request: int = 6) -> None:
    """Download hourly ERA5 2 m temperature for India at the hours around the daily peak and minimum,
    derive IST daily Tmax/Tmin at each forecast point, and write normals.

    Daily max uses 12:30-16:30 IST (07-11 UTC); daily min uses 03:30-06:30 IST (22-01 UTC). The
    forecast's daily Tmax is likewise the hottest forecast hour, so normals and forecasts share one definition.
    """
    import cdsapi
    import xarray as xr

    client = cdsapi.Client()  # reads CDSAPI_URL / CDSAPI_KEY
    first, last = int(PERIOD[0][:4]), int(PERIOD[1][:4])
    chunks = [(year, min(year + years_per_request - 1, last)) for year in range(first, last + 1, years_per_request)]

    def fetch(chunk: tuple[int, int]) -> Path:
        target = cache_dir / f"t2m_{chunk[0]}_{chunk[1]}.nc"
        if target.exists() and target.stat().st_size:
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".nc.part")
        client.retrieve(CDS_DATASET, {
            "product_type": ["reanalysis"],
            "variable": ["2m_temperature"],
            "year": [str(year) for year in range(chunk[0], chunk[1] + 1)],
            "month": [f"{month:02d}" for month in range(1, 13)],
            "day": [f"{day:02d}" for day in range(1, 32)],
            "time": [f"{hour:02d}:00" for hour in CDS_HOURS_UTC],
            "area": INDIA_AREA,
            "data_format": "netcdf",
            "download_format": "unarchived",
        }, str(partial))
        partial.replace(target)
        print(f"downloaded {target.name}", flush=True)
        return target

    # ERA5 surface geopotential (time-invariant): the grid-cell terrain height the temperatures refer to.
    orography = cache_dir / "orography.nc"
    if not orography.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        client.retrieve(CDS_DATASET, {
            "product_type": ["reanalysis"], "variable": ["geopotential"], "year": ["2020"], "month": ["01"],
            "day": ["01"], "time": ["00:00"], "area": INDIA_AREA, "data_format": "netcdf", "download_format": "unarchived",
        }, str(orography))

    with ThreadPoolExecutor(len(chunks)) as pool:
        files = list(pool.map(fetch, chunks))

    districts = load_districts()
    point_lat = np.array([district["latitude"] for district in districts])
    point_lon = np.array([district["longitude"] for district in districts])
    daily_max: dict[np.datetime64, np.ndarray] = {}
    daily_min: dict[np.datetime64, np.ndarray] = {}
    for path in files:
        with xr.open_dataset(path) as dataset:
            field = dataset["t2m"].squeeze(drop=True)
            time_dim = next(dim for dim in field.dims if dim not in ("latitude", "longitude"))
            field = field.transpose(time_dim, "latitude", "longitude")
            i0, i1, wi = _bilinear(field["latitude"].values, point_lat)
            j0, j1, wj = _bilinear(field["longitude"].values, point_lon)
            times = field[time_dim].values.astype("datetime64[m]") + np.timedelta64(330, "m")  # -> IST
            for block in range(0, len(times), 1000):
                grid = field.isel({time_dim: slice(block, block + 1000)}).values - 273.15  # K -> degrees C
                sampled = (
                    grid[:, i0, j0] * (1 - wi) * (1 - wj) + grid[:, i1, j0] * wi * (1 - wj)
                    + grid[:, i0, j1] * (1 - wi) * wj + grid[:, i1, j1] * wi * wj
                )
                for when, row in zip(times[block:block + 1000], sampled):
                    day, hour = when.astype("datetime64[D]"), int((when - when.astype("datetime64[D]")) / np.timedelta64(1, "h"))
                    target, combine = (daily_max, np.maximum) if 12 <= hour <= 16 else (daily_min, np.minimum)
                    target[day] = combine(target[day], row) if day in target else row
    days = sorted(set(daily_max) & set(daily_min))
    tmax = np.array([daily_max[day] for day in days])
    tmin = np.array([daily_min[day] for day in days])

    # The forecast is for the point's real elevation; ERA5 is for the grid cell's mean terrain. In mountains
    # these differ by up to ~2 km, so shift the normals with the standard lapse rate.
    with xr.open_dataset(orography) as dataset:
        height = (dataset["z"].squeeze(drop=True).transpose("latitude", "longitude") / 9.80665).values
        i0, i1, wi = _bilinear(dataset["latitude"].values, point_lat)
        j0, j1, wj = _bilinear(dataset["longitude"].values, point_lon)
        cell_height = (height[i0, j0] * (1 - wi) * (1 - wj) + height[i1, j0] * wi * (1 - wj)
                       + height[i0, j1] * (1 - wi) * wj + height[i1, j1] * wi * wj)
    shift = LAPSE_RATE_C_PER_M * (cell_height - point_elevations(districts))
    tmax, tmin = tmax + shift, tmin + shift
    print(f"elevation adjustment: median {np.median(np.abs(shift)):.2f} C, max {shift.max():+.2f} C, min {shift.min():+.2f} C", flush=True)
    labels = [str(day) for day in days]
    normals = {
        district["id"]: compute_normals({"time": labels, "temperature_2m_max": tmax[:, index].tolist(),
                                         "temperature_2m_min": tmin[:, index].tolist()})
        for index, district in enumerate(districts)
    }
    write_normals(normals, districts, CDS_SOURCE)
    print(f"wrote {NORMALS_FILE} for {len(normals)} districts from {len(days)} days", flush=True)


def build_from_open_meteo(cache_dir: Path = Path("data/raw/climatology"), *, cached_only: bool = False) -> None:
    """Point normals from the Open-Meteo archive, one 30-year request per district (cached)."""
    districts = load_districts()
    normals = {}
    for district in districts:
        if cached_only and not (cache_dir / f"{district['id']}.json").exists():
            continue
        try:
            normals[district["id"]] = compute_normals(fetch_daily_history(district, cache_dir)["daily"])
        except OSError as error:  # rate limit or network: keep what we have, rerun later
            print(f"stopped at {district['id']}: {error}", flush=True)
            break
    write_normals(normals, districts, SOURCE)
    print(f"wrote {NORMALS_FILE} for {len(normals)} districts", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", choices=["cds", "open-meteo", "load"], help="build normals from a source, or only load the committed file")
    choice = parser.parse_args().source
    if choice == "cds":
        build_from_cds()
    elif choice == "open-meteo":
        build_from_open_meteo()
    main()
