#!/usr/bin/env python3
"""
fix_heatwave_ews.py  --  run from the repo root (the folder containing Makefile,
backend/, frontend/, config/):

    python fix_heatwave_ews.py            # apply fixes (originals saved as *.bak)
    python fix_heatwave_ews.py --check    # dry run, only report what would change

Idempotent: running it twice is safe. Every patch verifies its anchor text and
reports SKIP (already applied) or FAIL (file drifted from what this script expects).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()
DRY = "--check" in sys.argv
results: list[tuple[str, str, str]] = []


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)


def patch(path: str, label: str, old: str, new: str, done_marker: str | None = None) -> None:
    """Replace exactly one occurrence of `old` with `new` in `path`."""
    p = ROOT / path
    if not p.exists():
        results.append(("FAIL", label, f"{path} not found - are you in the repo root?"))
        return
    text = p.read_text(encoding="utf-8")
    if done_marker and done_marker in text:
        results.append(("SKIP", label, "already applied"))
        return
    if text.count(old) != 1:
        results.append(("FAIL", label, f"anchor found {text.count(old)}x in {path} (expected 1)"))
        return
    if not DRY:
        backup(p)
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    results.append(("OK", label, path))


def write(path: str, label: str, content: str, done_marker: str) -> None:
    p = ROOT / path
    if p.exists() and done_marker in p.read_text(encoding="utf-8"):
        results.append(("SKIP", label, "already applied"))
        return
    if not DRY:
        if p.exists():
            backup(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
    results.append(("OK", label, path))


# ---------------------------------------------------------------------------
# 0. sanity
# ---------------------------------------------------------------------------
if not (ROOT / "backend" / "app" / "main.py").exists():
    sys.exit("Run this from the repo root (backend/app/main.py not found).")


# ---------------------------------------------------------------------------
# 1. MAP: MapLibre silently drops non-numeric feature ids, so clicking a district
#    did nothing (event.features[0].id was undefined). Also the districts are tiny
#    at zoom 3.5 (never fit to data), updates were dropped if the style had not
#    finished loading, and the fetches did not check HTTP status.
# ---------------------------------------------------------------------------
F = "frontend/src/main.tsx"

patch(F, "frontend: API base configurable",
      'const API = "http://localhost:8000";',
      'const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";',
      done_marker="VITE_API_URL")

patch(F, "frontend: add id to feature properties type",
      "type Feature = GeoJSON.Feature<GeoJSON.MultiPolygon, { name: string;",
      "type Feature = GeoJSON.Feature<GeoJSON.MultiPolygon, { id?: string; name: string;",
      done_marker="{ id?: string; name: string;")

HELPERS = '''
type Bounds = [[number, number], [number, number]];

function boundsOf(collection: FeatureCollection): Bounds {
  let west = 180, south = 90, east = -180, north = -90;
  const walk = (node: unknown): void => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number") {
      const [lng, lat] = node as [number, number];
      west = Math.min(west, lng); east = Math.max(east, lng);
      south = Math.min(south, lat); north = Math.max(north, lat);
    } else node.forEach(walk);
  };
  collection.features.forEach((feature) => walk(feature.geometry?.coordinates));
  return [[west, south], [east, north]];
}

// Districts are small next to a national view, so also draw a marker at each centre.
function centroids(collection: FeatureCollection): GeoJSON.FeatureCollection<GeoJSON.Point, Feature["properties"]> {
  return {
    type: "FeatureCollection",
    features: collection.features.map((feature) => {
      const [[west, south], [east, north]] = boundsOf({ type: "FeatureCollection", features: [feature] });
      return {
        type: "Feature",
        id: feature.id,
        properties: feature.properties,
        geometry: { type: "Point", coordinates: [(west + east) / 2, (south + north) / 2] },
      };
    }),
  };
}

function getJson<T>(url: string): Promise<T> {
  return fetch(url).then((response) => {
    if (!response.ok) throw new Error(`${url} failed (${response.status})`);
    return response.json() as Promise<T>;
  });
}

function highestAlert('''
patch(F, "frontend: map helpers (bounds, centroids, getJson)",
      "\nfunction highestAlert(", HELPERS, done_marker="function boundsOf(")

patch(F, "frontend: put id into properties",
      "        ...feature.properties,\n        alert_level:",
      "        ...feature.properties,\n        id: String(feature.id),\n        alert_level:",
      done_marker="id: String(feature.id),")

# Replace the whole map-lifecycle block (creation effect + cleanup effect).
p = ROOT / F
if p.exists():
    text = p.read_text(encoding="utf-8")
    start_marker = "  useEffect(() => {\n    if (!mapNode.current || !mapData) return;"
    end_marker = "  useEffect(() => () => map.current?.remove(), []);\n"
    if "dataRef" in text:
        results.append(("SKIP", "frontend: rewrite map lifecycle", "already applied"))
    elif text.count(start_marker) == 1 and text.count(end_marker) == 1:
        a = text.index(start_marker)
        b = text.index(end_marker) + len(end_marker)
        NEW_BLOCK = '''  const dataRef = useRef<FeatureCollection | null>(null);

  useEffect(() => {
    dataRef.current = mapData;
    if (!mapNode.current || !mapData) return;
    if (map.current) {
      // Sources only exist after the style's "load"; the load handler reads dataRef, so nothing is lost.
      (map.current.getSource("districts") as GeoJSONSource | undefined)?.setData(mapData);
      (map.current.getSource("district-points") as GeoJSONSource | undefined)?.setData(centroids(mapData));
      return;
    }
    const instance = new MapLibreMap({
      container: mapNode.current,
      bounds: boundsOf(mapData),
      fitBoundsOptions: { padding: 90, maxZoom: 7 },
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png", "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "&copy; OpenStreetMap contributors",
            maxzoom: 19,
          },
        },
        layers: [
          { id: "background", type: "background", paint: { "background-color": "#edf1ec" } },
          { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.9 } },
        ],
      },
    });
    map.current = instance;
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      const data = dataRef.current;
      if (!data) return;
      const colour = ["match", ["get", "alert_level"], "red", "#c9362b", "orange", "#e97824", "yellow", "#e9b949", "green", "#2f855a", "#737b78"] as never;
      instance.addSource("districts", { type: "geojson", data });
      instance.addSource("district-points", { type: "geojson", data: centroids(data) });
      instance.addLayer({ id: "district-fill", type: "fill", source: "districts", paint: { "fill-color": colour, "fill-opacity": 0.75 } });
      instance.addLayer({ id: "district-outline", type: "line", source: "districts", paint: { "line-color": "#17332a", "line-width": 1.5 } });
      instance.addLayer({ id: "district-marker", type: "circle", source: "district-points", paint: { "circle-radius": 9, "circle-color": colour, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2.5 } });
      // Feature ids are strings ("ahmedabad"); MapLibre drops those, so read the id from properties.
      const select = (event: { features?: GeoJSON.Feature[] }) => {
        const id = event.features?.[0]?.properties?.id;
        if (id) setSelectedId(String(id));
      };
      for (const layer of ["district-fill", "district-marker"]) {
        instance.on("click", layer, select);
        instance.on("mouseenter", layer, () => { instance.getCanvas().style.cursor = "pointer"; });
        instance.on("mouseleave", layer, () => { instance.getCanvas().style.cursor = ""; });
      }
    });
  }, [mapData]);

  useEffect(() => () => { map.current?.remove(); map.current = null; }, []);
'''
        if not DRY:
            backup(p)
            p.write_text(text[:a] + NEW_BLOCK + text[b:], encoding="utf-8", newline="\n")
        results.append(("OK", "frontend: rewrite map lifecycle (click, fit-to-data, markers, safe updates)", F))
    else:
        results.append(("FAIL", "frontend: rewrite map lifecycle", "anchors not found (file changed?)"))

patch(F, "frontend: status-checked fetches for panel data",
      '''    Promise.all([
      fetch(`${API}/forecast/${selectedId}`).then((response) => response.json()),
      fetch(`${API}/indices/${selectedId}`).then((response) => response.json()),
      fetch(`${API}/vulnerability/${selectedId}`).then((response) => response.json()),
    ]).then(''',
      '''    Promise.all([
      getJson<{ items: Forecast[] }>(`${API}/forecast/${selectedId}`),
      getJson<{ items: Indices[] }>(`${API}/indices/${selectedId}`),
      getJson<Vulnerability>(`${API}/vulnerability/${selectedId}`),
    ]).then(''',
      done_marker="getJson<{ items: Forecast[] }>")


# ---------------------------------------------------------------------------
# 2. API: CORS only allowed GET from localhost:5173 (POST/PATCH/DELETE blocked in
#    the browser, 127.0.0.1:5173 blocked entirely). Audit-log FK to 'user-system-1'
#    which was never seeded -> every task create/update/delete returned HTTP 500.
# ---------------------------------------------------------------------------
M = "backend/app/main.py"
patch(M, "api: CORS origins",
      'allow_origins=["http://localhost:5173"],',
      'allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],',
      done_marker="http://127.0.0.1:5173")
patch(M, "api: CORS methods",
      'allow_methods=["GET"],',
      'allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],',
      done_marker='allow_methods=["GET", "POST"')
patch(M, "api: seed the system user the audit log references",
      "('user-admin-1', 'admin', 'admin')\n",
      "('user-admin-1', 'admin', 'admin'),\n                ('user-system-1', 'system', 'admin')\n",
      done_marker="'user-system-1', 'system'")


# ---------------------------------------------------------------------------
# 3. DATA (vulnerability / population exposure panel was permanently empty)
#    a) Delhi + Chennai SHA-256s in config were fabricated (63 hex chars, a
#       sequential pattern) so every fetch died with "checksum mismatch".
#    b) Delhi URL 404s (real file is Delhi/Delhi_Wards.geojson).
#    c) The loader required properties.Name; only Ahmedabad has it. Delhi uses
#       Ward_Name/Ward_No, Chennai only Ward_No/Zone_Name.
#    d) Nothing ever ran the vulnerability loader.
# ---------------------------------------------------------------------------
cfg_path = ROOT / "config/vulnerability_source.json"
if cfg_path.exists():
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    wb = cfg["ward_boundaries"]
    DELHI_SHA = "f331e967962383127eae891c01ed3f3762f2b029feb892641f2466787b3bed55"
    CHENNAI_SHA = "2dff80b6f514e644b9a428696909216e9d22aedd07c8ebab33192ec9e3cb1ab2"
    DELHI_URL = wb["new-delhi"]["url"].replace("/Delhi/Wards.geojson", "/Delhi/Delhi_Wards.geojson")
    if (wb["new-delhi"]["sha256"], wb["chennai"]["sha256"], wb["new-delhi"]["url"]) == (DELHI_SHA, CHENNAI_SHA, DELHI_URL):
        results.append(("SKIP", "config: ward checksums + Delhi URL", "already applied"))
    else:
        wb["new-delhi"].update(sha256=DELHI_SHA, url=DELHI_URL)
        wb["chennai"].update(sha256=CHENNAI_SHA)
        if not DRY:
            backup(cfg_path)
            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        results.append(("OK", "config: real ward checksums + correct Delhi URL", "config/vulnerability_source.json"))
else:
    results.append(("FAIL", "config: ward checksums", "config/vulnerability_source.json not found"))

V = "backend/pipeline/vulnerability.py"

patch(V, "vulnerability: show actual digest on checksum mismatch (boundaries)",
      '                    raise ValueError(f"checksum mismatch for {district_id}")',
      '                    raise ValueError(f"checksum mismatch for {district_id}: got {checksum}, config expects {item[\'sha256\']}")',
      done_marker="config expects {item[")
patch(V, "vulnerability: show actual digest on checksum mismatch (population)",
      '                raise ValueError("checksum mismatch for population raster")',
      '                raise ValueError(f"checksum mismatch for population raster: got {checksum}, config expects {pop[\'sha256\']}")',
      done_marker="config expects {pop[")

patch(V, "vulnerability: ward identity helper",
      "def aggregate_ward_population(",
      '''def _ward_identity(properties: dict[str, Any], index: int) -> tuple[str, str]:
    """Return (display name, id key) across the three DataMeet schemas in use."""
    name = str(properties.get("Name") or "").strip()
    if name:  # Ahmedabad
        return name, name
    number = str(properties.get("Ward_No") if properties.get("Ward_No") is not None else "").strip()
    ward_name = str(properties.get("Ward_Name") or "").strip()
    zone = str(properties.get("Zone_Name") or "").strip().title()
    if ward_name:  # Delhi: Ward_Name repeats, Ward_No is unique
        return ward_name.title(), number or ward_name
    if number:  # Chennai: only a number and a zone
        return (f"Ward {number} ({zone})" if zone else f"Ward {number}"), number
    return f"Unnamed ward {index}", f"unnamed-{index}"  # e.g. one unlabeled Delhi polygon; keep it, label honestly


def aggregate_ward_population(''',
      done_marker="def _ward_identity(")

patch(V, "vulnerability: accept all ward property schemas",
      '''            name = str(feature.get("properties", {}).get("Name", "")).strip()
            geometry = feature.get("geometry")''',
      '''            name, key = _ward_identity(feature.get("properties") or {}, index)
            geometry = feature.get("geometry")''',
      done_marker="_ward_identity(feature.get")
patch(V, "vulnerability: slug from identity key",
      '            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")',
      '            slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")',
      done_marker="key.lower()")

patch(V, "vulnerability: tolerate wards smaller than one raster pixel",
      '            clipped = raster.rio.clip([geometry], crs="EPSG:4326", drop=True)\n            population = float(clipped.sum(skipna=True).item())',
      '''            try:
                clipped = raster.rio.clip([geometry], crs="EPSG:4326", drop=True)
            except NoDataInBounds:
                try:  # ward smaller than a 1 km pixel: fall back to touched pixels
                    clipped = raster.rio.clip([geometry], crs="EPSG:4326", drop=True, all_touched=True)
                except NoDataInBounds:
                    clipped = None
            population = 0.0 if clipped is None else float(clipped.sum(skipna=True).item())''',
      done_marker="except NoDataInBounds")
patch(V, "vulnerability: import NoDataInBounds",
      "import rioxarray\n",
      "import rioxarray\nfrom rioxarray.exceptions import NoDataInBounds\n",
      done_marker="import NoDataInBounds")

write("backend/pipeline/__main__.py", "pipeline: run vulnerability load + report failures", '''"""Operational pipeline command (forecast cycle + one-time ward exposure load)."""

import os
import sys

import psycopg

from pipeline.operational import run_operational


def _scalar(database_url: str, query: str):
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()
        return row[0] if row else None


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    ok = run_operational(database_url)
    if ok:
        print("forecast run: OK", flush=True)
    else:
        reason = _scalar(
            database_url,
            "SELECT failure_reason FROM model_runs ORDER BY init_time DESC LIMIT 1",
        )
        print(f"forecast run: FAILED - {reason}", file=sys.stderr, flush=True)

    # Ward exposure was never loaded by anything, so the dashboard panel stayed empty.
    try:
        if not _scalar(database_url, "SELECT count(*) FROM vulnerability_wards"):
            from pipeline.vulnerability import main as load_vulnerability

            load_vulnerability()
    except Exception as error:  # non-fatal: forecast alerts must not depend on this
        print(f"vulnerability load skipped: {error}", file=sys.stderr, flush=True)


main()
''', done_marker="ward exposure load")


# ---------------------------------------------------------------------------
# 4. FRESHNESS: alerts are blocked once the latest run is >12 h old, but the
#    pipeline only ran once at startup, so the whole map went grey ("ALERTS
#    BLOCKED") half a day later. Add a scheduler that re-runs every ~6 h.
# ---------------------------------------------------------------------------
patch("docker-compose.yml", "compose: 6-hourly refresh so alerts do not go stale",
      "\nvolumes:\n  postgres_data:",
      '''
  scheduler:
    build:
      context: .
      dockerfile: backend/Dockerfile
    command: ["sh", "-c", "while true; do sleep 21660; python -m pipeline; done"]
    depends_on:
      pipeline:
        condition: service_completed_successfully
    environment:
      DATABASE_URL: postgresql://heatwave@postgres:5432/heatwave
    volumes:
      - ./data:/app/data
    restart: unless-stopped

volumes:
  postgres_data:''',
      done_marker="  scheduler:")


# ---------------------------------------------------------------------------
# 5. MAP ACTUALLY BLANK (root cause found by reproducing in headless Chromium):
#    maplibre-gl 6 loads its web worker from a file next to its main module.
#    `vite dev` pre-bundles maplibre-gl into node_modules/.vite/deps/ and leaves
#    the worker behind -> GET .../maplibre-gl-worker.mjs = 404. Without the worker
#    no GeoJSON layer is ever parsed: base map draws, polygons/markers never do,
#    and there is no visible error. Fix: do not pre-bundle maplibre-gl.
# ---------------------------------------------------------------------------
write("frontend/vite.config.ts", "frontend: vite.config.ts (serve maplibre worker, fixes blank map)",
      """import { defineConfig } from "vite";

// maplibre-gl >= 5 loads its web worker via import.meta.url next to its own module file.
// Vite's dependency pre-bundling moves the main file into node_modules/.vite/deps/ but
// leaves the worker behind (HTTP 404), so GeoJSON layers never render. Serve it from the package.
export default defineConfig({
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: { host: "0.0.0.0", port: 5173 },
});
""", done_marker='exclude: ["maplibre-gl"]')

# tsconfig only includes src/, so vite.config.ts is not type-checked by `npm run build`; nothing to change.

# ---------------------------------------------------------------------------
# 6. POPULATION PANEL: the WorldPop raster's pinned SHA-256 could not be verified
#    (I cannot reach data.worldpop.org from my sandbox). If it is wrong, the loader
#    refuses the file - by design - but the failure is only visible in the pipeline
#    container log. Add an explicit, opt-in override and make the failure loud.
#    Default behaviour is unchanged: mismatch = refuse.
# ---------------------------------------------------------------------------
patch("backend/pipeline/vulnerability.py", "vulnerability: import os",
      "import json\nfrom math import isfinite",
      "import json\nimport os\nfrom math import isfinite",
      done_marker="import json\nimport os\n")

patch("backend/pipeline/vulnerability.py", "vulnerability: opt-in ALLOW_UNPINNED_POPULATION override",
      """            if checksum != pop["sha256"]:
                raise ValueError(f"checksum mismatch for population raster: got {checksum}, config expects {pop['sha256']}")
""",
      """            if checksum != pop["sha256"]:
                if os.environ.get("ALLOW_UNPINNED_POPULATION") == "1":
                    print(
                        f"WARNING: population raster sha256 {checksum} != pinned {pop['sha256']}; "
                        "accepting because ALLOW_UNPINNED_POPULATION=1. Pin this value in "
                        "config/vulnerability_source.json once you have verified the file.",
                        flush=True,
                    )
                    pop = {**pop, "sha256": checksum}
                else:
                    raise ValueError(f"checksum mismatch for population raster: got {checksum}, config expects {pop['sha256']}")
""",
      done_marker="ALLOW_UNPINNED_POPULATION")

patch("docker-compose.yml", "compose: pass ALLOW_UNPINNED_POPULATION to the pipeline (default off)",
      """    command: ["python", "-m", "pipeline"]
    depends_on:
      backend:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://heatwave@postgres:5432/heatwave
""",
      """    command: ["python", "-m", "pipeline"]
    depends_on:
      backend:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://heatwave@postgres:5432/heatwave
      ALLOW_UNPINNED_POPULATION: ${ALLOW_UNPINNED_POPULATION:-0}
""",
      done_marker="ALLOW_UNPINNED_POPULATION")


# ---------------------------------------------------------------------------
print(("DRY RUN - nothing written\n" if DRY else "") + "-" * 72)
for status, label, detail in results:
    print(f"[{status:4}] {label}  ({detail})")
print("-" * 72)
failed = [r for r in results if r[0] == "FAIL"]
if failed:
    print(f"{len(failed)} patch(es) failed; the rest were applied. Send me the FAIL lines.")
    sys.exit(1)
if not DRY:
    print("Done. Rebuild and reload data:")
    print("  docker compose down && docker compose up --build")
    print("(add -v to `down` only if you want to wipe the database)")
    print("Population panel still empty? run:  docker compose logs pipeline | grep -i vulnerab")
