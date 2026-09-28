import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { GeoJSONSource, Map as MapLibreMap, NavigationControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

const API = "http://localhost:8000";
const rank: Record<string, number> = { blocked: -1, green: 0, yellow: 1, orange: 2, red: 3 };

type DataStatus = { state: string; age_hours: number | null; banner: string; run_id: string | null };
type Alert = { date: string; level: string; track1_level: string; track2_level: string; disagreement: boolean; reasoning: string[]; rule_version: string };
type AlertResponse = { data_status: DataStatus; emission_blocked: boolean; items: Alert[] };
type Feature = GeoJSON.Feature<GeoJSON.MultiPolygon, { name: string; state: string; climate_zone: string; boundary_vintage: string; alert_level?: string }>;
type FeatureCollection = GeoJSON.FeatureCollection<GeoJSON.MultiPolygon, Feature["properties"]>;
type Forecast = { date: string; tmax_c: number; tmin_c: number; relative_humidity_pct: number; wind_speed_m_s: number };
type Indices = { date: string; utci_c: number; wbgt_est_c: number; heat_index_c: number | null };

function highestAlert(items: Alert[]): Alert | undefined {
  return items.reduce<Alert | undefined>((highest, item) => !highest || rank[item.level] > rank[highest.level] ? item : highest, undefined);
}

function App() {
  const mapNode = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [districts, setDistricts] = useState<FeatureCollection | null>(null);
  const [alerts, setAlerts] = useState<Record<string, AlertResponse>>({});
  const [selectedId, setSelectedId] = useState("");
  const [forecast, setForecast] = useState<Forecast[]>([]);
  const [indices, setIndices] = useState<Indices[]>([]);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    fetch(`${API}/districts`)
      .then((response) => {
        if (!response.ok) throw new Error(`District request failed (${response.status})`);
        return response.json() as Promise<FeatureCollection>;
      })
      .then(async (collection) => {
        const entries = await Promise.all(collection.features.map(async (feature) => {
          const id = String(feature.id);
          const response = await fetch(`${API}/alerts/${id}`);
          if (!response.ok) throw new Error(`Alert request failed (${response.status})`);
          return [id, await response.json()] as [string, AlertResponse];
        }));
        setDistricts(collection);
        setAlerts(Object.fromEntries(entries));
        setSelectedId(String(collection.features[0]?.id ?? ""));
      })
      .catch((error: Error) => setLoadError(error.message));
  }, []);

  const mapData = useMemo<FeatureCollection | null>(() => districts && ({
    ...districts,
    features: districts.features.map((feature) => ({
      ...feature,
      properties: {
        ...feature.properties,
        alert_level: alerts[String(feature.id)]?.emission_blocked ? "blocked" : highestAlert(alerts[String(feature.id)]?.items ?? [])?.level ?? "green",
      },
    })),
  }), [districts, alerts]);

  useEffect(() => {
    if (!mapNode.current || !mapData) return;
    if (!map.current) {
      const instance = new MapLibreMap({
        container: mapNode.current,
        center: [77.2, 21.8],
        zoom: 3.2,
        style: { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#edf1ec" } }] },
      });
      map.current = instance;
      instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
      instance.on("load", () => {
        instance.addSource("districts", { type: "geojson", data: mapData });
        instance.addLayer({
          id: "district-fill", type: "fill", source: "districts",
          paint: { "fill-color": ["match", ["get", "alert_level"], "red", "#c9362b", "orange", "#e97824", "yellow", "#e9b949", "green", "#2f855a", "#737b78"], "fill-opacity": 0.82 },
        });
        instance.addLayer({ id: "district-outline", type: "line", source: "districts", paint: { "line-color": "#17332a", "line-width": 1.5 } });
        instance.on("click", "district-fill", (event) => {
          const id = event.features?.[0]?.id;
          if (id !== undefined) setSelectedId(String(id));
        });
        instance.on("mouseenter", "district-fill", () => { instance.getCanvas().style.cursor = "pointer"; });
        instance.on("mouseleave", "district-fill", () => { instance.getCanvas().style.cursor = ""; });
      });
    } else if (map.current.isStyleLoaded()) {
      (map.current.getSource("districts") as GeoJSONSource | undefined)?.setData(mapData);
    }
  }, [mapData]);

  useEffect(() => () => map.current?.remove(), []);

  useEffect(() => {
    if (!selectedId) return;
    Promise.all([
      fetch(`${API}/forecast/${selectedId}`).then((response) => response.json()),
      fetch(`${API}/indices/${selectedId}`).then((response) => response.json()),
    ]).then(([forecastResponse, indexResponse]) => {
      setForecast(forecastResponse.items);
      setIndices(indexResponse.items);
    }).catch((error: Error) => setLoadError(error.message));
  }, [selectedId]);

  const selectedFeature = districts?.features.find((feature) => String(feature.id) === selectedId);
  const selectedAlerts = alerts[selectedId];
  const selectedAlert = highestAlert(selectedAlerts?.items ?? []);
  const status = selectedAlerts?.data_status ?? Object.values(alerts)[0]?.data_status;
  const headlineLevel = selectedAlerts?.emission_blocked ? "blocked" : selectedAlert?.level ?? "green";

  return (
    <main>
      <header className="topbar">
        <div><p className="eyebrow">Ministry of Earth Sciences challenge prototype</p><h1>Heatwatch India</h1></div>
        <div className="legend" aria-label="Alert legend">{["green", "yellow", "orange", "red"].map((level) => <span key={level}><i className={`dot ${level}`} />{level}</span>)}</div>
      </header>
      <div className={`status-banner ${status?.state ?? "unavailable"}`} role="status">
        <strong>{status?.state === "current" ? "DATA CURRENT" : "ALERTS BLOCKED"}</strong>
        <span>{loadError || status?.banner || "Connecting to forecast service…"}</span>
        {status?.run_id && <code>{status.run_id}</code>}
      </div>
      <section className="workspace">
        <div className="map-shell"><div ref={mapNode} className="map" aria-label="Pilot district alert map" /><div className="map-caption">Pilot boundaries · Census 2011 vintage</div></div>
        <aside className="panel">
          <div className="district-tabs">
            {districts?.features.map((feature) => {
              const id = String(feature.id);
              const level = alerts[id]?.emission_blocked ? "blocked" : highestAlert(alerts[id]?.items ?? [])?.level ?? "green";
              return <button key={id} className={id === selectedId ? "active" : ""} onClick={() => setSelectedId(id)}><i className={`dot ${level}`} />{feature.properties.name}</button>;
            })}
          </div>
          <div className="panel-heading">
            <div><p className="eyebrow">{selectedFeature?.properties.state}</p><h2>{selectedFeature?.properties.name ?? "Select a district"}</h2></div>
            <span className={`alert-badge ${headlineLevel}`}>{headlineLevel}</span>
          </div>
          {selectedAlerts?.emission_blocked ? (
            <div className="blocked-card"><h3>No current alert emitted</h3><p>The latest forecast is unavailable, stale, or failed quality checks. Last-known results are intentionally hidden.</p></div>
          ) : selectedAlert ? (
            <>
              <div className="metrics">
                <article><span>UTCI (shade estimate)</span><strong>{indices[0]?.utci_c?.toFixed(1) ?? "—"}°C</strong></article>
                <article><span>Estimated WBGT</span><strong>{indices[0]?.wbgt_est_c?.toFixed(1) ?? "—"}°C</strong></article>
                <article><span>Forecast Tmax</span><strong>{forecast[0]?.tmax_c?.toFixed(1) ?? "—"}°C</strong></article>
              </div>
              <section className="reasoning"><div className="section-title"><h3>Why this level</h3><span>{selectedAlert.date}</span></div><ol>{selectedAlert.reasoning.map((reason, index) => <li key={`${reason}-${index}`}>{reason}</li>)}</ol></section>
              <div className="tracks"><span>IMD criteria <b>{selectedAlert.track1_level}</b></span><span>Human stress <b>{selectedAlert.track2_level}</b></span>{selectedAlert.disagreement && <em>Tracks disagree · higher level selected</em>}</div>
            </>
          ) : <div className="blocked-card"><h3>No alert record</h3><p>Run the operational pipeline to populate this district.</p></div>}
          <footer>Decision-support prototype · Not an official IMD warning · Track 2 thresholds are assumptions</footer>
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
