"""Regenerate the landing page hero map and district counts from the real data.

Reads config/districts.yaml, config/pilot_districts.geojson and the cached May 2024 replay
(data/replay/north-india-may-2024.json; run `python -m pipeline.replay` first) and rewrites the
map SVG and the numbers derived from it in frontend/landing.html. Run from the repository root:

    python scripts/build_landing_map.py
"""

import json
import math
import re
from pathlib import Path

LEVEL_COLOUR = {"green": "#2f855a", "yellow": "#e9b949", "orange": "#e97824", "red": "#c9362b"}
REPLAY_DATE = "2024-05-28"
LABELLED = ("banda", "new-delhi", "barmer", "kolkata", "chennai", "hyderabad", "ahmedabad", "leh", "guwahati")
WIDTH, HEIGHT = 540, 560
LON0, LON1, LAT0, LAT1 = 67.5, 97.8, 7.8, 36.2  # frame covering Ladakh, Arunachal and Tamil Nadu


def main() -> None:
    districts = json.loads(Path("config/districts.yaml").read_text(encoding="utf-8"))["districts"]
    by_code = {tuple(d["census_code"]): d for d in districts}
    features = json.loads(Path("config/pilot_districts.geojson").read_text(encoding="utf-8"))["features"]
    replay = json.loads(Path("data/replay/north-india-may-2024.json").read_text(encoding="utf-8"))
    day = {row["district_id"]: row for row in replay["items"] if row["date"] == REPLAY_DATE}
    missing = [d["id"] for d in districts if d["id"] not in day]
    if missing:
        raise SystemExit(f"replay cache lacks {len(missing)} districts (e.g. {missing[:3]}); rerun python -m pipeline.replay")

    kx = math.cos(math.radians((LAT0 + LAT1) / 2))
    scale = min(WIDTH / ((LON1 - LON0) * kx), HEIGHT / (LAT1 - LAT0))
    offset = (WIDTH - (LON1 - LON0) * kx * scale) / 2

    def xy(lon: float, lat: float) -> tuple[float, float]:
        return offset + (lon - LON0) * kx * scale, (LAT1 - lat) * scale

    paths, labels = [], []
    for feature in features:
        props = feature["properties"]
        district = by_code[(int(props["ST_CEN_CD"]), int(props["DT_CEN_CD"]))]
        row = day[district["id"]]
        polygons = feature["geometry"]["coordinates"]
        if feature["geometry"]["type"] == "Polygon":
            polygons = [polygons]
        d = ""
        for polygon in polygons:
            points = [xy(lon, lat) for lon, lat in polygon[0]]
            points = points[:: max(1, len(points) // 50)] + [points[0]]  # thin vertices for a small map
            d += "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in points) + "Z"
        departure = f" ({row['departure_c']:+.1f}°C vs normal)" if row["departure_c"] is not None else ""
        title = f"{district['name']}: {row['level']} · Tmax {row['tmax_c']:.1f}°C{departure} · UTCI {row['utci_c']:.1f}°C"
        paths.append(f'<path d="{d}" fill="{LEVEL_COLOUR[row["level"]]}" stroke="#14251f" stroke-width="0.5"><title>{title}</title></path>')
        if district["id"] in LABELLED:
            x, y = xy(district["longitude"], district["latitude"])
            name = district["name"].split(" (")[0]
            labels.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="#fbfcf7" stroke="#14251f" stroke-width="1"/>'
                f'<text x="{x + 5:.1f}" y="{y + 3:.1f}" font-family="DM Sans" font-size="9.5" font-weight="700" fill="#14251f" '
                f'paint-order="stroke" stroke="#f4f5ef" stroke-width="3">{name} {row["tmax_c"]:.1f}°</text>'
            )

    total, reds = len(districts), sum(row["level"] == "red" for row in day.values())
    svg = (
        f'<svg class="w-full h-full max-h-[480px] select-none" viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Alert levels in {total} monitored districts on 28 May 2024, replayed from ERA5 data">'
        + "".join(paths) + "".join(labels) + "</svg>"
    )
    banda = day["banda"]

    path = Path("frontend/landing.html")
    html = path.read_text(encoding="utf-8")
    html, count = re.subn(r'<svg class="w-full h-full max-h-\[\d+px\] select-none".*?</svg>', lambda _: svg, html, flags=re.S)
    assert count == 1, "hero map SVG not found"
    replacements = [
        (r"\d+ monitored districts · Replay", f"{total} monitored districts · Replay"),
        (r"28 May 2024 · \d+ red", f"28 May 2024 · {reds} red"),
        (r"On 28 May, \d+ of \d+ districts are red; Banda reaches [\d.]+°C, [+-][\d.]+°C above normal\.",
         f"On 28 May, {reds} of {total} districts are red; Banda reaches {banda['tmax_c']:.1f}°C, {banda['departure_c']:+.1f}°C above normal."),
        (r'(leading-none">)\d+(</span>\s*<div class="mt-3">\s*<p[^>]*>Coverage)', rf"\g<1>{total}\g<2>"),
        (r"heat-prone districts monitored", "districts monitored across India"),
        (r"\(\d+ District Polygons/Cells\)", f"({total} district polygons)"),
        (r"SVG Map Representation with \d+ key heatwave districts", f"Map of the {total} monitored districts"),
        (r"<!-- \d+ District Polygons cleanly positioned in India's geography -->", ""),
    ]
    for pattern, replacement in replacements:
        html, count = re.subn(pattern, replacement, html)
        assert count <= 1, pattern
    path.write_text(html, encoding="utf-8")
    print(f"landing map: {total} districts, {reds} red on {REPLAY_DATE}")


if __name__ == "__main__":
    main()
