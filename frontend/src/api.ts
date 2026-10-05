export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type DataStatus = { state: string; age_hours: number | null; banner: string; run_id: string | null };
export type DistrictProps = { id?: string; name: string; state: string; climate_zone: string; boundary_vintage: string };
export type DistrictCollection = GeoJSON.FeatureCollection<GeoJSON.MultiPolygon, DistrictProps>;
export type OverviewRow = {
  district_id: string; date: string; level: string | null; track1_level: string | null; track2_level: string | null;
  tmax_c: number; departure_c: number | null; utci_c: number; utci_shade_c: number | null; utci_sun_c: number | null; stress_hours: number | null; htsi: number | null; wbgt_est_c: number; heat_index_c: number | null;
};
export type ReplayRow = OverviewRow & Alert & Forecast & Indices;
export type Scenario = { id: string; title: string; start: string; end: string; context: string };
export type Replay = Scenario & { mode: "replay"; source: string; note: string; items: ReplayRow[] };
export type Overview = { data_status: DataStatus; emission_blocked: boolean; items: OverviewRow[] };
export type Alert = { date: string; level: string; track1_level: string; track2_level: string; disagreement: boolean; reasoning: string[]; rule_version: string };
export type AlertResponse = { data_status: DataStatus; emission_blocked: boolean; items: Alert[] };
export type Forecast = { date: string; tmax_c: number; tmin_c: number; relative_humidity_pct: number; wind_speed_m_s: number; normal_tmax_c: number | null; departure_c: number | null };
export type Indices = { date: string; utci_c: number; utci_shade_c: number | null; utci_sun_c: number | null; stress_hours: number | null; htsi: number | null; wbgt_est_c: number; heat_index_c: number | null };
export type Ward = { ward_id: string; name: string; population_estimate: number; data_vintage: string; source_url: string; licence: string; rank: number; geometry: GeoJSON.MultiPolygon };
export type Vulnerability = { status: "available" | "unavailable"; data_vintage: string | null; items: Ward[] };
export type User = { user_id: string; username: string; role: string };
export type AuthConfig = { mode: "demo" | "strict"; production_ready: boolean; banner: string };
export type LoginResponse = { token: string; expires_in_seconds: number; user: User };
export type WardOutlookItem = Ward & { district_alert_level: string; exposure_percentile: number; response_priority_score: number; response_priority: "routine" | "watch" | "high" | "urgent" };
export type WardOutlook = { status: "available" | "unavailable"; meteorology_resolution: string; ward_meteorology_downscaled: false; basis: string; items: WardOutlookItem[] };
export type HealthDataStatus = { status: "connected" | "awaiting_approved_data"; operational_health_model: false; absolute_outcome_forecast_enabled: false; message: string; rows: number; wards: number };
export type HealthImpact = { status: string; warning: string; label: string; thermal_context: { stress_hours: number; utci_sun_c: number; utci_shade_c: number }; items: { ward_id: string; name: string; relative_risk_index: number; sensitivity_low: number; sensitivity_high: number; normalised_stress_score: number }[] };
export type ReadinessGate = { id: string; label: string; status: "pass" | "partial" | "blocked"; detail?: string };
export type Readiness = { product_status: string; official_imd_product: false; auth: AuthConfig; gates: ReadinessGate[]; provenance: { layer: string; source: string | string[]; kind: string; resolution?: string; vintage?: string; licence?: string; status?: string }[] };
export type Advisory = { advisory_id: string; language: string; alert_level: string; text: string; status: string; approved_by: string | null; template_version: string };
export type Task = { task_id: string; task_type: string; title: string; status: string; priority: string; ward_id: string | null; quantity: number | null; assigned_to: string | null; created_at: string };
export type AuditEntry = { audit_id: string; user_id: string; action: string; entity_type: string; entity_id: string; new_value: unknown; created_at: string };
export type Allocation = { alert_level: string; basis: string; items: { ward_id: string; name: string; population_estimate: number; lat: number; lon: number; resources: Record<string, number> }[] };

const TOKEN_KEY = "heatwatch-session";
export const getSessionToken = () => window.sessionStorage.getItem(TOKEN_KEY);
export const setSessionToken = (token: string | null) => token ? window.sessionStorage.setItem(TOKEN_KEY, token) : window.sessionStorage.removeItem(TOKEN_KEY);

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const token = getSessionToken();
  const response = await fetch(`${API}${path}`, {
    method,
    signal,
    headers: {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().then((json) => json.detail, () => undefined);
    if (response.status === 401 && path !== "/auth/login") window.dispatchEvent(new Event("heatwatch-auth-required"));
    throw new Error(typeof detail === "string" ? detail : `${method} ${path} failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const getJson = <T,>(path: string, signal?: AbortSignal) => request<T>("GET", path, undefined, signal);
export const send = <T,>(method: "POST" | "PATCH" | "DELETE", path: string, body?: unknown) => request<T>(method, path, body);
export const qs = (params: Record<string, string | number | undefined | null>) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => [k, String(v)])).toString();

export const LEVEL_COLOUR: Record<string, string> = { green: "#2f855a", yellow: "#e9b949", orange: "#e97824", red: "#c9362b", blocked: "#737b78" };
export const rank: Record<string, number> = { blocked: -1, green: 0, yellow: 1, orange: 2, red: 3 };
export const fmt = (value: number | null | undefined, digits = 1) => (value === null || value === undefined ? "—" : value.toFixed(digits));
export const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

// Map layers: colour bands follow each index's published stress scale.
export type LayerKey = "level" | "utci_c" | "wbgt_est_c" | "heat_index_c" | "departure_c";
export const LAYERS: Record<LayerKey, { label: string; bands: [number, string, string][] }> = {
  level: { label: "Alert level", bands: [] },
  utci_c: { label: "UTCI (sun-exposed)", bands: [[-99, "#2f855a", "< 26 no/moderate"], [26, "#9cc26a", "26 moderate"], [32, "#e9b949", "32 strong"], [38, "#e97824", "38 very strong"], [46, "#9b1c1c", "46 extreme"]] },
  wbgt_est_c: { label: "WBGT (est.)", bands: [[-99, "#2f855a", "< 25"], [25, "#9cc26a", "25"], [28, "#e9b949", "28"], [30, "#e97824", "30"], [32, "#9b1c1c", "32+"]] },
  heat_index_c: { label: "Heat Index", bands: [[-99, "#2f855a", "< 27"], [27, "#9cc26a", "27 caution"], [32, "#e9b949", "32 extreme caution"], [41, "#e97824", "41 danger"], [54, "#9b1c1c", "54 extreme danger"]] },
  departure_c: { label: "Tmax vs 1991–2020 normal", bands: [[-99, "#4d7fa8", "below normal"], [0, "#9cc26a", "0 to +2"], [2, "#e9b949", "+2"], [4.5, "#e97824", "+4.5 heat wave"], [6.5, "#9b1c1c", "+6.5 severe"]] },
};
