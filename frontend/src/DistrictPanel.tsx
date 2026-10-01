import { useEffect, useState } from "react";
import { AlertResponse, DistrictProps, Forecast, Indices, ReplayRow, Vulnerability, fmt, getJson, shortDate } from "./api";

type Series = { key: string; label: string; colour: string; values: (number | null)[]; dashed?: boolean };

function Chart({ dates, series, selected }: { dates: string[]; series: Series[]; selected: number }) {
  const width = 520, height = 190, pad = { left: 34, right: 10, top: 12, bottom: 26 };
  const values = series.flatMap((item) => item.values).filter((value): value is number => value !== null);
  if (!values.length) return null;
  const min = Math.floor(Math.min(...values) - 1), max = Math.ceil(Math.max(...values) + 1);
  const x = (index: number) => pad.left + (index * (width - pad.left - pad.right)) / Math.max(1, dates.length - 1);
  const y = (value: number) => pad.top + ((max - value) * (height - pad.top - pad.bottom)) / (max - min || 1);
  const ticks = Array.from({ length: 5 }, (_, index) => min + ((max - min) * index) / 4);
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Seven-day forecast of temperature and heat stress indices">
        {ticks.map((tick) => <g key={tick}><line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} className="grid" /><text x={pad.left - 6} y={y(tick) + 3} textAnchor="end">{tick.toFixed(0)}</text></g>)}
        <rect x={x(selected) - 14} y={pad.top} width={28} height={height - pad.top - pad.bottom} className="selected-day" />
        {dates.map((date, index) => <text key={date} x={x(index)} y={height - 8} textAnchor="middle">{shortDate(date).split(" ")[0]}</text>)}
        {series.map((item) => {
          const points = item.values.map((value, index) => (value === null ? null : `${x(index)},${y(value)}`)).filter(Boolean);
          return <g key={item.key}>
            <polyline points={points.join(" ")} fill="none" stroke={item.colour} strokeWidth={2} strokeDasharray={item.dashed ? "5 4" : undefined} />
            {!item.dashed && item.values.map((value, index) => value !== null && <circle key={index} cx={x(index)} cy={y(value)} r={2.6} fill={item.colour} />)}
          </g>;
        })}
      </svg>
      <figcaption>{series.map((item) => <span key={item.key}><i style={{ background: item.colour }} />{item.label}</span>)}</figcaption>
    </figure>
  );
}

type Props = { districtId: string; district?: DistrictProps; dayIndex: number; vulnerability: Vulnerability | null; refreshKey: number; replay?: ReplayRow[] };

export function DistrictPanel({ districtId, district, dayIndex, vulnerability, refreshKey, replay }: Props) {
  const [alerts, setAlerts] = useState<AlertResponse | null>(null);
  const [forecast, setForecast] = useState<Forecast[]>([]);
  const [indices, setIndices] = useState<Indices[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    if (replay) {  // replayed history carries the same fields as the live endpoints
      setAlerts({ data_status: { state: "current", age_hours: null, banner: "", run_id: null }, emission_blocked: false, items: replay });
      setForecast(replay);
      setIndices(replay);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      getJson<AlertResponse>(`/alerts/${districtId}`, controller.signal),
      getJson<{ items: Forecast[] }>(`/forecast/${districtId}`, controller.signal),
      getJson<{ items: Indices[] }>(`/indices/${districtId}`, controller.signal),
    ]).then(([alertResponse, forecastResponse, indexResponse]) => {
      setAlerts(alertResponse);
      setForecast(forecastResponse.items);
      setIndices(indexResponse.items);
    }).catch((reason: Error) => { if (reason.name !== "AbortError") setError(reason.message); });
    return () => controller.abort();
  }, [districtId, refreshKey, replay]);

  const alert = alerts?.items[dayIndex];
  const day = forecast[dayIndex];
  const index = indices[dayIndex];
  const level = alerts?.emission_blocked ? "blocked" : alert?.level ?? "green";
  const dates = forecast.map((item) => item.date);
  // Track 1 looks ahead: a day can carry an IMD warning because of heat-wave days later in the forecast.
  const conditionOf = (item: { reasoning: string[] }) => item.reasoning.find((reason) => reason.startsWith("condition="))?.slice(10);
  const aheadDays = alert && alert.track1_level !== "green" && conditionOf(alert) === "normal"
    ? (alerts?.items ?? []).slice(dayIndex + 1).filter((item) => conditionOf(item) !== "normal")
    : [];
  const aheadText = aheadDays.length
    ? `${aheadDays.some((item) => conditionOf(item) === "severe_heat_wave") ? "Severe heat wave" : "Heat wave"} forecast for ${
        aheadDays.length === 1 ? shortDate(aheadDays[0].date) : `${shortDate(aheadDays[0].date)} – ${shortDate(aheadDays[aheadDays.length - 1].date)}`
      } — the IMD-criteria warning starts early.`
    : "";

  return (
    <>
      <div className="panel-heading">
        <div><p className="eyebrow">{district?.state} · {district?.climate_zone} zone</p><h2>{district?.name ?? "Select a district"}</h2></div>
        <span className={`alert-badge ${level}`}>{level}</span>
      </div>
      {error && <div className="blocked-card"><h3>Could not load district</h3><p>{error}</p></div>}
      {alerts?.emission_blocked ? (
        <div className="blocked-card"><h3>No current alert emitted</h3><p>The latest forecast is unavailable, stale, or failed quality checks. Last-known results are intentionally hidden.</p></div>
      ) : alert && day ? (
        <>
          <div className="metrics">
            <article><span>Tmax · {shortDate(day.date)}</span><strong>{fmt(day.tmax_c)}°C</strong><small>{day.departure_c === null ? "normal not loaded" : `${day.departure_c >= 0 ? "+" : ""}${fmt(day.departure_c)}°C vs 1991–2020`}</small></article>
            <article><span>UTCI (shade)</span><strong>{fmt(index?.utci_c)}°C</strong><small>feels-like stress</small></article>
            <article><span>WBGT (est.)</span><strong>{fmt(index?.wbgt_est_c)}°C</strong><small>work/exercise limit</small></article>
            <article><span>Heat Index</span><strong>{fmt(index?.heat_index_c)}{index?.heat_index_c == null ? "" : "°C"}</strong><small>RH {fmt(day.relative_humidity_pct, 0)}% · Tmin {fmt(day.tmin_c)}°C</small></article>
          </div>
          <Chart
            dates={dates}
            selected={dayIndex}
            series={[
              { key: "tmax", label: "Tmax", colour: "#b92d24", values: forecast.map((item) => item.tmax_c) },
              { key: "normal", label: "Normal Tmax", colour: "#8a958f", values: forecast.map((item) => item.normal_tmax_c), dashed: true },
              { key: "utci", label: "UTCI", colour: "#e97824", values: indices.map((item) => item.utci_c) },
              { key: "wbgt", label: "WBGT", colour: "#2b6cb0", values: indices.map((item) => item.wbgt_est_c) },
              { key: "hi", label: "Heat Index", colour: "#6b46c1", values: indices.map((item) => item.heat_index_c) },
            ]}
          />
          <div className="tracks">
            <span>IMD criteria (Track 1) <b className={`level-text ${alert.track1_level}`}>{alert.track1_level}</b></span>
            <span>Human thermal stress (Track 2) <b className={`level-text ${alert.track2_level}`}>{alert.track2_level}</b></span>
            {alert.disagreement && <em>Tracks disagree · higher level issued (max-of-tracks)</em>}
            {aheadText && <em className="ahead">{aheadText}</em>}
          </div>
          <details className="reasoning">
            <summary>Why {level} on {shortDate(alert.date)} · rule {alert.rule_version}</summary>
            <ol>{alert.reasoning.map((reason, position) => <li key={`${reason}-${position}`}>{reason}</li>)}</ol>
          </details>
        </>
      ) : !error && <div className="blocked-card"><h3>No alert record</h3><p>Run the operational pipeline to populate this district.</p></div>}
      <section className="vulnerability">
        <div className="section-title"><h3>Ward population exposure</h3><span>{vulnerability?.data_vintage ?? ""}</span></div>
        {vulnerability?.status === "available" ? (
          <ol>{vulnerability.items.slice(0, 6).map((ward) => <li key={ward.ward_id}><b>#{ward.rank} {ward.name}</b><span>{Math.round(ward.population_estimate).toLocaleString("en-IN")} people</span></li>)}</ol>
        ) : <p>Ward-level exposure is loaded for the pilot cities (Ahmedabad, New Delhi, Chennai). District-level alerts apply here.</p>}
      </section>
    </>
  );
}
