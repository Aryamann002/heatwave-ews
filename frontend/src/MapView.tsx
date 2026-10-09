import { useEffect, useRef } from "react";
import { GeoJSONSource, Map as MapLibreMap, NavigationControl, Popup } from "maplibre-gl";
import { DistrictCollection, LAYERS, LayerKey, LEVEL_COLOUR, OverviewRow, Ward, fmt } from "./api";

type Bounds = [[number, number], [number, number]];
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function boundsOf(geometries: (GeoJSON.Geometry | null)[]): Bounds {
  let west = 180, south = 90, east = -180, north = -90;
  const walk = (node: unknown): void => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number") {
      const [lng, lat] = node as [number, number];
      west = Math.min(west, lng); east = Math.max(east, lng);
      south = Math.min(south, lat); north = Math.max(north, lat);
    } else node.forEach(walk);
  };
  geometries.forEach((geometry) => walk(geometry && "coordinates" in geometry ? geometry.coordinates : null));
  return [[west, south], [east, north]];
}

function colourExpression(layer: LayerKey): unknown {
  if (layer === "level") {
    return ["match", ["coalesce", ["get", "level"], "blocked"], "red", LEVEL_COLOUR.red, "orange", LEVEL_COLOUR.orange, "yellow", LEVEL_COLOUR.yellow, "green", LEVEL_COLOUR.green, LEVEL_COLOUR.blocked];
  }
  const [[, first], ...rest] = LAYERS[layer].bands;
  return ["case", ["==", ["get", layer], null], LEVEL_COLOUR.blocked, ["step", ["get", layer], first, ...rest.flatMap(([limit, colour]) => [limit, colour])]];
}

type Props = {
  districts: DistrictCollection;
  rows: Record<string, OverviewRow | undefined>;
  layer: LayerKey;
  selectedId: string;
  wards: Ward[];
  onSelect: (id: string) => void;
};

export function MapView({ districts, rows, layer, selectedId, wards, onSelect }: Props) {
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const ready = useRef(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const districtData: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: districts.features.map((feature) => ({
      ...feature,
      properties: { ...feature.properties, ...(rows[String(feature.id)] ?? {}), id: String(feature.id), selected: String(feature.id) === selectedId },
    })),
  };
  const wardData: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: wards.map((ward) => ({ type: "Feature", geometry: ward.geometry, properties: { name: ward.name, population: Math.round(ward.population_estimate), rank: ward.rank } })),
  };
  const maxPopulation = Math.max(1, ...wards.map((ward) => ward.population_estimate));

  const sync = () => {
    const instance = map.current;
    if (!instance || !ready.current) return;
    (instance.getSource("districts") as GeoJSONSource).setData(districtData);
    (instance.getSource("wards") as GeoJSONSource).setData(wardData);
    instance.setPaintProperty("district-fill", "fill-color", colourExpression(layer) as never);
    instance.setPaintProperty("ward-fill", "fill-color", ["interpolate", ["linear"], ["get", "population"], 0, "#fde7d4", maxPopulation, "#7a1d10"] as never);
  };

  useEffect(() => {
    if (!node.current || map.current) return;
    const instance = new MapLibreMap({
      container: node.current,
      bounds: boundsOf(districts.features.map((feature) => feature.geometry)),
      fitBoundsOptions: { padding: 40 },
      style: {
        version: 8,
        sources: {
          base: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors", maxzoom: 19 },
        },
        layers: [
          { id: "background", type: "background", paint: { "background-color": "#edf1ec" } },
          { id: "base", type: "raster", source: "base", paint: { "raster-saturation": -0.6, "raster-opacity": 0.85 } },
        ],
      },
    });
    map.current = instance;
    const resizeObserver = new ResizeObserver(() => instance.resize());
    resizeObserver.observe(node.current);
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    instance.on("load", () => {
      instance.addSource("districts", { type: "geojson", data: EMPTY });
      instance.addSource("wards", { type: "geojson", data: EMPTY });
      instance.addLayer({ id: "district-fill", type: "fill", source: "districts", paint: { "fill-color": LEVEL_COLOUR.blocked, "fill-opacity": 0.72 } });
      instance.addLayer({ id: "district-outline", type: "line", source: "districts", paint: { "line-color": "#17332a", "line-width": ["case", ["get", "selected"], 3, 0.8] } });
      instance.addLayer({ id: "ward-fill", type: "fill", source: "wards", paint: { "fill-color": "#e97824", "fill-opacity": 0.55 } });
      instance.addLayer({ id: "ward-outline", type: "line", source: "wards", paint: { "line-color": "#ffffff", "line-width": 0.6 } });
      instance.on("click", "district-fill", (event) => {
        const id = event.features?.[0]?.properties?.id;
        if (id) onSelectRef.current(String(id));
      });
      instance.on("mousemove", "district-fill", (event) => {
        const p = event.features?.[0]?.properties;
        if (!p) return;
        instance.getCanvas().style.cursor = "pointer";
        popup.setLngLat(event.lngLat).setHTML(
          `<b>${p.name}</b> · ${p.state}<br/>Alert: <b>${p.level ?? "blocked"}</b><br/>Tmax ${fmt(p.tmax_c)}°C (${p.departure_c == null || p.departure_c === "null" ? "no normal" : `${Number(p.departure_c) >= 0 ? "+" : ""}${fmt(Number(p.departure_c))}°C vs normal`})<br/>UTCI ${fmt(Number(p.utci_c))} · WBGT ${fmt(Number(p.wbgt_est_c))} · HI ${p.heat_index_c == null || p.heat_index_c === "null" ? "—" : fmt(Number(p.heat_index_c))}`,
        ).addTo(instance);
      });
      instance.on("mouseleave", "district-fill", () => { instance.getCanvas().style.cursor = ""; popup.remove(); });
      instance.on("mousemove", "ward-fill", (event) => {
        const p = event.features?.[0]?.properties;
        if (p) popup.setLngLat(event.lngLat).setHTML(`<b>#${p.rank} ${p.name}</b><br/>${Number(p.population).toLocaleString("en-IN")} people (WorldPop 2020)`).addTo(instance);
      });
      ready.current = true;
      sync();
    });
    return () => { resizeObserver.disconnect(); instance.remove(); map.current = null; ready.current = false; };
  }, []);

  useEffect(sync);

  // Zoom in to a city's wards; otherwise keep (or return to) the national view.
  const national = useRef(true);
  useEffect(() => {
    if (!map.current) return;
    if (wards.length) {
      national.current = false;
      map.current.fitBounds(boundsOf(wards.map((ward) => ward.geometry)), { padding: 60, maxZoom: 11, duration: 800 });
    } else if (!national.current) {
      national.current = true;
      map.current.fitBounds(boundsOf(districts.features.map((feature) => feature.geometry)), { padding: 40, duration: 800 });
    }
  }, [selectedId, wards.length]);

  const legend = LAYERS[layer].bands;
  return (
    <div className="map-shell">
      <div ref={node} className="map" aria-label="District heat map" />
      <div className="map-legend">
        <b>{LAYERS[layer].label}</b>
        {layer === "level"
          ? ["green", "yellow", "orange", "red", "blocked"].map((level) => <span key={level}><i style={{ background: LEVEL_COLOUR[level] }} />{level}</span>)
          : legend.map(([, colour, label]) => <span key={label}><i style={{ background: colour }} />{label}</span>)}
        {wards.length > 0 && <span><i style={{ background: "linear-gradient(90deg,#fde7d4,#7a1d10)" }} />ward population</span>}
      </div>
      <div className="map-caption">Boundaries: Census 2011 (DataMeet) · Basemap © OpenStreetMap contributors</div>
    </div>
  );
}
