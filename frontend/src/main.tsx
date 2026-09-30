import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import { DistrictCollection, LAYERS, LayerKey, Overview, OverviewRow, Replay, Scenario, User, Vulnerability, getJson, rank, send, shortDate } from "./api";
import { MapView } from "./MapView";
import { DistrictPanel } from "./DistrictPanel";
import { OpsPanel } from "./OpsPanel";

type ModelCard = { status: string; model: string; samples: number; period: string[]; evaluation: { groups: { climate_zone: string; raw_mae_c: number; corrected_mae_c: number; use_correction: boolean }[] } };

const REFRESH_MS = 5 * 60 * 1000;

function QueryBox() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const ask = () => {
    if (!query.trim()) return;
    setBusy(true);
    send<{ answer: string }>("POST", "/query", { query })
      .then((result) => setAnswer(result.answer), (error: Error) => setAnswer(error.message))
      .finally(() => setBusy(false));
  };
  return (
    <form className="query" onSubmit={(event) => { event.preventDefault(); ask(); }}>
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ask: “Which wards are most exposed in Chennai?”" aria-label="Ask a question about the data" />
      <button disabled={busy}>{busy ? "…" : "Ask"}</button>
      {answer && <div className="answer" role="status"><button type="button" className="close" onClick={() => setAnswer("")} aria-label="Close">×</button>{answer}</div>}
    </form>
  );
}

function App() {
  const [districts, setDistricts] = useState<DistrictCollection | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserId] = useState("user-officer-1");
  const [selectedId, setSelectedId] = useState("");
  const [dayIndex, setDayIndex] = useState(0);
  const [layer, setLayer] = useState<LayerKey>("level");
  const [vulnerability, setVulnerability] = useState<Vulnerability | null>(null);
  const [loadError, setLoadError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Landing-page links open a replay directly: /?replay=<scenario id>
  const [replayId, setReplayId] = useState(() => new URLSearchParams(window.location.search).get("replay") ?? "");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [replayState, setReplayState] = useState("");

  const [modelCard, setModelCard] = useState<ModelCard | null>(null);
  useEffect(() => { getJson<ModelCard>("/model-card").then(setModelCard, () => undefined); }, []);
  useEffect(() => { getJson<{ scenarios: Scenario[] }>("/replay/scenarios").then((result) => setScenarios(result.scenarios), () => undefined); }, []);
  useEffect(() => {
    setReplay(null);
    setDayIndex(0);
    if (!replayId) return;
    setReplayState("Computing replay from ERA5 history (the first run fetches data and takes ~30 s)...");
    getJson<Replay>(`/replay/${replayId}`).then((value) => { setReplay(value); setReplayState(""); }, (error: Error) => setReplayState(error.message));
  }, [replayId]);

  useEffect(() => {
    getJson<DistrictCollection>("/districts").then(setDistricts, (error: Error) => setLoadError(error.message));
    getJson<{ items: User[] }>("/users").then((result) => setUsers(result.items), () => undefined);
  }, []);

  useEffect(() => {
    const load = () => getJson<Overview>("/overview").then((value) => { setOverview(value); setLoadError(""); }, (error: Error) => setLoadError(error.message));
    load();
    const timer = window.setInterval(() => { load(); setRefreshKey((key) => key + 1); }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setVulnerability(null);
    getJson<Vulnerability>(`/vulnerability/${selectedId}`, controller.signal).then(setVulnerability, () => undefined);
    return () => controller.abort();
  }, [selectedId]);

  const source: OverviewRow[] = useMemo(() => (replay ? replay.items : overview?.items ?? []), [replay, overview]);
  const dates = useMemo(() => [...new Set(source.map((row) => row.date))].sort(), [source]);
  const date = dates[Math.min(dayIndex, dates.length - 1)] ?? "";
  const rowsForDay = useMemo(() => Object.fromEntries(source.filter((row) => row.date === date).map((row) => [row.district_id, row])) as Record<string, OverviewRow>, [source, date]);
  const blocked = replay ? false : overview?.emission_blocked ?? false;
  const replayRows = useMemo(() => replay?.items.filter((row) => row.district_id === selectedId), [replay, selectedId]);
  const levelOf = (id: string) => (blocked ? "blocked" : rowsForDay[id]?.level ?? "green");

  // District ranking for the selected day: worst alert, then hottest UTCI.
  const ranked = useMemo(() => (districts?.features ?? []).map((feature) => String(feature.id)).sort((a, b) =>
    (rank[levelOf(b)] - rank[levelOf(a)]) || ((rowsForDay[b]?.utci_c ?? 0) - (rowsForDay[a]?.utci_c ?? 0))), [districts, rowsForDay, blocked]);
  useEffect(() => { if (!selectedId && ranked.length && overview) setSelectedId(ranked[0]); }, [ranked, overview]);

  const status = overview?.data_status;
  const counts = ranked.reduce<Record<string, number>>((acc, id) => ({ ...acc, [levelOf(id)]: (acc[levelOf(id)] ?? 0) + 1 }), {});
  const selected = districts?.features.find((feature) => String(feature.id) === selectedId);
  const user = users.find((item) => item.user_id === userId);

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="/landing.html"><p className="eyebrow">Extreme heat early warning · human thermal stress</p><h1>Heatwatch India</h1></a>
        <QueryBox />
        <label className="acting">Acting as
          <select value={userId} onChange={(event) => setUserId(event.target.value)}>
            {users.filter((item) => item.username !== "system").map((item) => <option key={item.user_id} value={item.user_id}>{item.username} ({item.role})</option>)}
          </select>
        </label>
      </header>
      {replayId ? (
        <div className="status-banner replay" role="status">
          <strong>HISTORICAL REPLAY</strong>
          <span>{replayState || `${replay?.title}: ${replay?.context} ${replay?.note}`}</span>
          <button className="exit" onClick={() => setReplayId("")}>Back to live forecast</button>
        </div>
      ) : <div className={`status-banner ${loadError ? "unavailable" : status?.state ?? "loading"}`} role="status">
        <strong>{loadError ? "SERVICE UNREACHABLE" : !status ? "LOADING" : status.state === "current" ? "DATA CURRENT" : "ALERTS BLOCKED"}</strong>
        <span>{loadError || status?.banner || "Connecting to forecast service…"}</span>
        <span className="counts">{(["red", "orange", "yellow", "green"] as const).map((level) => counts[level] ? <b key={level} className={`count ${level}`}>{counts[level]} {level}</b> : null)}</span>
        {status?.run_id && <code>{status.run_id}</code>}
      </div>}
      <div className="controls">
        <div className="layer-switch" role="radiogroup" aria-label="Map layer">
          {(Object.keys(LAYERS) as LayerKey[]).map((key) => <button key={key} role="radio" aria-checked={layer === key} className={layer === key ? "active" : ""} onClick={() => setLayer(key)}>{LAYERS[key].label}</button>)}
        </div>
        <div className="days" role="radiogroup" aria-label="Forecast day">
          {dates.map((value, index) => <button key={value} role="radio" aria-checked={index === dayIndex} className={index === dayIndex ? "active" : ""} onClick={() => setDayIndex(index)}>{index === 0 && !replay ? "Today" : shortDate(value)}</button>)}
        </div>
        <select className="replay-select" value={replayId} onChange={(event) => setReplayId(event.target.value)} aria-label="Data source">
          <option value="">Live 7-day forecast</option>
          {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>Replay: {scenario.title}</option>)}
        </select>
      </div>
      <section className="workspace">
        <div className="left">
          {districts && <MapView districts={districts} rows={rowsForDay} layer={layer} selectedId={selectedId} wards={vulnerability?.items ?? []} onSelect={setSelectedId} />}
          <div className="ranking">
            <div className="section-title"><h3>Districts by risk · {date && shortDate(date)}</h3><span>{ranked.length} monitored</span></div>
            <div className="district-tabs">
              {ranked.map((id) => {
                const feature = districts?.features.find((item) => String(item.id) === id);
                const row = rowsForDay[id];
                return <button key={id} className={id === selectedId ? "active" : ""} onClick={() => setSelectedId(id)}>
                  <i className={`dot ${levelOf(id)}`} />{feature?.properties.name}<small>{row ? `${row.tmax_c.toFixed(0)}°` : ""}</small>
                </button>;
              })}
            </div>
          </div>
        </div>
        <aside className="panel">
          {selectedId ? <>
            <DistrictPanel districtId={selectedId} district={selected?.properties} dayIndex={dayIndex} vulnerability={vulnerability} refreshKey={refreshKey} replay={replayRows} />
            {replay ? <p className="hint ops">Operations (advisories, resources) run on the live forecast. Switch back to live to act.</p> : date && <OpsPanel districtId={selectedId} districtName={selected?.properties.name ?? selectedId} date={date} level={levelOf(selectedId)} user={user} blocked={blocked} />}
          </> : <p className="hint">Loading districts…</p>}
          {modelCard?.status === "trained" && (
            <section className="model-card">
              <h4>AI bias correction · held-out skill</h4>
              <p className="hint">{modelCard.model}, trained on {modelCard.samples.toLocaleString("en-IN")} forecast/ERA5 day pairs ({modelCard.period.join(" to ")}), leave-one-year-out.</p>
              <table><thead><tr><th>Zone</th><th>Raw Tmax MAE</th><th>Corrected MAE</th><th>In use</th></tr></thead>
                <tbody>{modelCard.evaluation.groups.map((group) => <tr key={group.climate_zone}><td>{group.climate_zone}</td><td>{group.raw_mae_c.toFixed(2)} °C</td><td>{group.corrected_mae_c.toFixed(2)} °C</td><td>{group.corrected_mae_c < group.raw_mae_c - 0.05 ? "yes" : "no (raw kept)"}</td></tr>)}</tbody>
              </table>
            </section>
          )}
          <footer>Decision-support prototype · Not an official IMD warning · Track 1 follows IMD heat-wave criteria against 1991–2020 ERA5 normals; Track 2 (UTCI) thresholds are unvalidated assumptions · Forecast: ECMWF IFS 0.25° via Open-Meteo</footer>
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
