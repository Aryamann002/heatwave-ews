import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import { DistrictCollection, ForecastRefresh, LAYERS, LayerKey, Overview, OverviewRow, Readiness, Replay, Scenario, User, Vulnerability, getJson, rank, send, shortDate } from "./api";
import { AuthPanel } from "./AuthPanel";
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

function App({ user }: { user: User }) {
  const [districts, setDistricts] = useState<DistrictCollection | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [dayIndex, setDayIndex] = useState(0);
  const [layer, setLayer] = useState<LayerKey>("level");
  const [vulnerability, setVulnerability] = useState<Vulnerability | null>(null);
  const [loadError, setLoadError] = useState("");
  const [refresh, setRefresh] = useState<ForecastRefresh | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Landing-page links open a replay directly: /?replay=<scenario id>
  const [replayId, setReplayId] = useState(() => new URLSearchParams(window.location.search).get("replay") ?? "");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [replayState, setReplayState] = useState("");

  const [modelCard, setModelCard] = useState<ModelCard | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  useEffect(() => { getJson<ModelCard>("/model-card").then(setModelCard, () => undefined); }, []);
  useEffect(() => { getJson<Readiness>("/readiness").then(setReadiness, () => undefined); }, []);
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
  }, []);

  useEffect(() => {
    const load = () => getJson<Overview>("/overview").then((value) => { setOverview(value); setLoadError(""); }, (error: Error) => setLoadError(error.message));
    const requestRefresh = () => send<ForecastRefresh>("POST", "/forecast-refresh").then(setRefresh, () => undefined);
    load();
    requestRefresh();
    const timer = window.setInterval(() => { load(); requestRefresh(); setRefreshKey((key) => key + 1); }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (refresh?.state !== "running") return;
    const timer = window.setInterval(() => {
      getJson<ForecastRefresh>("/forecast-refresh/status").then((value) => {
        setRefresh(value);
        if (value.state !== "running") getJson<Overview>("/overview").then(setOverview, () => undefined);
      }, () => undefined);
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [refresh?.state]);

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

  // With many districts, show the top of the ranking plus a name/state search.
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);
  const nameOf = (id: string) => districts?.features.find((item) => String(item.id) === id)?.properties;
  const matches = search.trim()
    ? ranked.filter((id) => `${nameOf(id)?.name} ${nameOf(id)?.state}`.toLowerCase().includes(search.trim().toLowerCase()))
    : ranked;
  const visible = search.trim() || showAll ? matches : matches.slice(0, 12);

  const status = overview?.data_status;
  const counts = ranked.reduce<Record<string, number>>((acc, id) => ({ ...acc, [levelOf(id)]: (acc[levelOf(id)] ?? 0) + 1 }), {});
  const selected = districts?.features.find((feature) => String(feature.id) === selectedId);
  return (
    <main>
      <a className="skip-link" href="#district-panel">Skip to district details</a>
      <header className="topbar">
        <a className="brand" href="/landing.html"><h1>HeatSafe AI</h1><p>Impact-led heat action support</p></a>
        <QueryBox />
        <span id="heatsafe-theme-slot" />
        <AuthPanel user={user} />
      </header>
      {readiness?.auth.mode === "demo" && <div className="auth-banner" role="status">{readiness.auth.banner} Operational actions still require a signed session.</div>}
      {replayId ? (
        <div className="status-banner replay" role="status">
          <strong>HISTORICAL REPLAY</strong>
          <span>{replayState || `${replay?.title}: ${replay?.context} ${replay?.note}`}</span>
          <button className="exit" onClick={() => setReplayId("")}>Back to live forecast</button>
        </div>
      ) : <div className={`status-banner ${loadError ? "unavailable" : status?.state ?? "loading"}`} role="status">
        <strong>{loadError ? "SERVICE UNREACHABLE" : !status ? "LOADING" : status.state === "current" ? "DATA CURRENT" : "ALERTS BLOCKED"}</strong>
        <span>{loadError || (refresh?.state === "running" ? `${status?.banner ?? "No forecast available yet."} ${refresh.message}` : refresh?.state === "failed" ? `${status?.banner ?? "Forecast unavailable."} ${refresh.message}` : status?.banner || "Connecting to forecast service…")}</span>
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
            <div className="section-title"><h3>Districts by risk · {date && shortDate(date)}</h3>
              <span className="ranking-tools">
                <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find district or state" aria-label="Find district or state" />
                {!search.trim() && ranked.length > 12 && <button onClick={() => setShowAll(!showAll)}>{showAll ? "Top 12" : `All ${ranked.length}`}</button>}
              </span>
            </div>
            <div className="district-tabs">
              {visible.map((id) => {
                const feature = districts?.features.find((item) => String(item.id) === id);
                const row = rowsForDay[id];
                return <button key={id} className={id === selectedId ? "active" : ""} onClick={() => setSelectedId(id)}>
                  <i className={`dot ${levelOf(id)}`} />{feature?.properties.name}<small>{row ? `${row.tmax_c.toFixed(0)}°` : ""}</small>
                </button>;
              })}
            </div>
          </div>
        </div>
        <aside className="panel" id="district-panel">
          {selectedId ? <>
            <DistrictPanel districtId={selectedId} district={selected?.properties} dayIndex={dayIndex} forecastDate={date} vulnerability={vulnerability} refreshKey={refreshKey} replay={replayRows} />
            {replay ? <p className="hint ops">Operations run on the live forecast. Switch back to live to act.</p> : date && <OpsPanel districtId={selectedId} districtName={selected?.properties.name ?? selectedId} date={date} level={levelOf(selectedId)} user={user ?? undefined} blocked={blocked} />}
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
          {readiness && <details className="readiness-panel">
            <summary>Deployment readiness and provenance</summary>
            <p>Blocked items must be resolved by the deploying authority before operational use.</p>
            <ul>{readiness.gates.map((gate) => <li key={gate.id}><span className={`gate ${gate.status}`}>{gate.status}</span><b>{gate.label}</b>{gate.detail && <small>{gate.detail}</small>}</li>)}</ul>
            <h4>Data provenance</h4>
            <dl>{readiness.provenance.map((item) => <div key={item.layer}><dt>{item.layer}</dt><dd>{Array.isArray(item.source) ? item.source.join(", ") || "Not connected" : item.source}<small>{[item.kind, item.resolution, item.vintage].filter(Boolean).join(" · ")}</small></dd></div>)}</dl>
          </details>}
          <footer>Track 1 follows published IMD heat-wave criteria against 1991–2020 ERA5 normals · Track 2 thresholds and response-priority weights are documented assumptions · Forecast: ECMWF IFS 0.25° via Open-Meteo</footer>
        </aside>
      </section>
    </main>
  );
}

function AuthenticatedApp() {
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    const redirect = () => window.location.replace(`/login.html?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`);
    getJson<User>("/auth/session").then(setUser, redirect);
    window.addEventListener("heatsafe-auth-required", redirect);
    return () => window.removeEventListener("heatsafe-auth-required", redirect);
  }, []);
  return user ? <App user={user} /> : <div className="auth-loading" role="status">Checking your HeatSafe AI session…</div>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><AuthenticatedApp /></StrictMode>);
