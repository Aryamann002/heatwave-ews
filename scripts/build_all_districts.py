"""Build the all-India district list (Census 2011, 641 districts) and its boundary file.

Inputs (git-ignored, see docs/PROJECT_OVERVIEW.md "Adding districts"):
  data/raw/boundaries/all_districts.geojson   DataMeet 2011_Dist.shp, mapshaper -simplify 6% precision 0.001
  data/raw/boundaries/all_points.geojson      mapshaper -points inner (a point guaranteed inside each polygon)
  data/raw/boundaries/india_coastline.geojson Natural Earth 10m coastline (public domain), clipped to India

Climate zones for districts not already configured follow a documented rule (not an IMD list):
  hills   - from 7 seeded sample points inside the district (Open-Meteo elevation API, Copernicus 90 m DEM):
            median >= 1000 m, or median >= 400 m with >= 800 m relief (max - min). The relief test
            separates hill districts (Idukki, Darjeeling) from high flat plateaus (Bangalore, Mysore).
  coastal - district boundary within 25 km of the coastline (PostGIS geography distance)
  plains  - everything else
Existing districts keep their configured id, name, forecast point and zone.

Run inside the backend container (needs DATABASE_URL for the PostGIS distance query):
  docker compose run --rm -v "$PWD/scripts:/app/scripts" -v "$PWD/config:/app/config" -v "$PWD/data:/app/data" \
      -e PYTHONPATH=/app backend python scripts/build_all_districts.py
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode

import psycopg

from pipeline.s1_fetch import fetch_bytes

RAW = Path("data/raw/boundaries")
HILLS_MIN_ELEVATION_M = 1000
RUGGED_MIN_MEDIAN_M = 400
RUGGED_MIN_RELIEF_M = 800
COAST_KM = 25
SAMPLES_PER_DISTRICT = 7  # Open-Meteo bills each coordinate as one call (10,000/day)
# Census 2011 spellings and pre-2014 Andhra Pradesh -> current state/UT names.
STATE_NAMES = {
    "Orissa": "Odisha", "Arunanchal Pradesh": "Arunachal Pradesh", "Andaman & Nicobar Island": "Andaman and Nicobar Islands",
    "Dadara & Nagar Havelli": "Dadra and Nagar Haveli", "Daman & Diu": "Daman and Diu", "Delhi & NCR": "Delhi",
}
NAME_FIXES = {"Y.s.r.": "YSR Kadapa", "Janjgir-champa": "Janjgir-Champa", "Kaimur (bhabua)": "Kaimur (Bhabua)", "Sant Ravi Das Nagar(bhadohi)": "Sant Ravi Das Nagar (Bhadohi)", "Saraikela-kharsawan": "Saraikela-Kharsawan", "Saran (chhapra)": "Saran (Chhapra)"}  # Census 2011 casing slips
TELANGANA_CODES = {(28, code) for code in range(1, 11)}  # Adilabad ... Khammam, Census 2011


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def elevations(points: list[tuple[float, float]], cache_path: Path = RAW / "elevations.json") -> list[float]:
    """Metres above sea level at (lat, lon) points, 100 per request, cached so a rate limit loses no work."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    key = lambda lat, lon: f"{lat:.4f},{lon:.4f}"  # noqa: E731
    todo = [point for point in dict.fromkeys(points) if key(*point) not in cache]
    try:
        for start in range(0, len(todo), 100):
            chunk = todo[start:start + 100]
            query = urlencode({
                "latitude": ",".join(f"{lat:.4f}" for lat, _ in chunk),
                "longitude": ",".join(f"{lon:.4f}" for _, lon in chunk),
            })
            heights = json.loads(fetch_bytes(f"https://api.open-meteo.com/v1/elevation?{query}"))["elevation"]
            cache.update({key(*point): height for point, height in zip(chunk, heights, strict=True)})
    finally:
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
    return [cache[key(*point)] for point in points]


def terrain(features: list[dict]) -> tuple[set[tuple[int, int]], dict[tuple[int, int], list[float]]]:
    """(codes within COAST_KM of the coastline, sorted sampled elevations in m per code)."""
    coast = json.loads((RAW / "india_coastline.geojson").read_text(encoding="utf-8"))["features"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TEMP TABLE coast (geom geography)")
        cursor.executemany("INSERT INTO coast VALUES (ST_GeomFromGeoJSON(%s)::geography)",
                           [(json.dumps(f["geometry"]),) for f in coast])
        cursor.execute("CREATE TEMP TABLE district_shapes (st int, dt int, geom geography)")
        cursor.executemany(
            "INSERT INTO district_shapes VALUES (%s, %s, ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)::geography)",
            [(f["properties"]["ST_CEN_CD"], f["properties"]["DT_CEN_CD"], json.dumps(f["geometry"])) for f in features],
        )
        cursor.execute(
            "SELECT DISTINCT d.st, d.dt FROM district_shapes d JOIN coast c ON ST_DWithin(d.geom, c.geom, %s)",
            (COAST_KM * 1000,),
        )
        coastal = {(st, dt) for st, dt in cursor.fetchall()}
        cursor.execute(
            f"""SELECT st, dt, ST_Y(p.geom), ST_X(p.geom)
                FROM district_shapes, ST_Dump(ST_GeneratePoints(geom::geometry, {SAMPLES_PER_DISTRICT}, 17)) AS p
                ORDER BY st, dt"""
        )
        samples = cursor.fetchall()
    heights = elevations([(lat, lon) for _, _, lat, lon in samples])
    by_code: dict[tuple[int, int], list[float]] = {}
    for (st, dt, _, _), height in zip(samples, heights, strict=True):
        by_code.setdefault((st, dt), []).append(height)
    return coastal, {code: sorted(values) for code, values in by_code.items()}


def is_hills(heights: list[float]) -> bool:
    median, relief = heights[len(heights) // 2], heights[-1] - heights[0]
    return median >= HILLS_MIN_ELEVATION_M or (median >= RUGGED_MIN_MEDIAN_M and relief >= RUGGED_MIN_RELIEF_M)


def main() -> None:
    features = json.loads((RAW / "all_districts.geojson").read_text(encoding="utf-8"))["features"]
    points = {
        (f["properties"]["ST_CEN_CD"], f["properties"]["DT_CEN_CD"]): f["geometry"]["coordinates"]
        for f in json.loads((RAW / "all_points.geojson").read_text(encoding="utf-8"))["features"]
    }
    config_path = Path("config/districts.yaml")
    existing = json.loads(config_path.read_text(encoding="utf-8"))["districts"]
    by_code = {tuple(d["census_code"]): d for d in existing}
    used_ids = {d["id"] for d in existing}

    new = []
    for feature in features:
        props = feature["properties"]
        code = (props["ST_CEN_CD"], props["DT_CEN_CD"])
        if code in by_code:
            continue
        state = " ".join(props["ST_NM"].split())
        state = "Telangana" if code in TELANGANA_CODES else STATE_NAMES.get(state, state)
        name = NAME_FIXES.get(props["DISTRICT"].strip(), props["DISTRICT"].strip())
        district_id = slug(name)
        if district_id in used_ids:  # e.g. Aurangabad (Bihar and Maharashtra)
            district_id = f"{district_id}-{slug(state)}"
        used_ids.add(district_id)
        lon, lat = points[code]
        new.append({"id": district_id, "name": name, "state": state, "latitude": round(lat, 4),
                    "longitude": round(lon, 4), "climate_zone": None, "census_code": list(code)})

    new_codes = {tuple(d["census_code"]) for d in new}
    coastal, sampled_heights = terrain(
        [f for f in features if (f["properties"]["ST_CEN_CD"], f["properties"]["DT_CEN_CD"]) in new_codes]
    )
    for district in new:
        district["climate_zone"] = (
            "hills" if is_hills(sampled_heights[tuple(district["census_code"])])
            else "coastal" if tuple(district["census_code"]) in coastal
            else "plains"
        )

    districts = existing + new
    assert len({d["id"] for d in districts}) == len(districts), "duplicate district ids"
    lines = ",\n".join("    " + json.dumps(d, ensure_ascii=False) for d in districts)
    config_path.write_text('{\n  "districts": [\n' + lines + "\n  ]\n}\n", encoding="utf-8", newline="\n")
    boundaries = {"type": "FeatureCollection", "features": features}
    Path("config/pilot_districts.geojson").write_text(json.dumps(boundaries, separators=(",", ":")), encoding="utf-8", newline="\n")
    zones: dict[str, int] = {}
    for district in new:
        zones[district["climate_zone"]] = zones.get(district["climate_zone"], 0) + 1
    print(f"{len(districts)} districts ({len(existing)} kept, {len(new)} added); new zones: {zones}")


if __name__ == "__main__":
    main()
