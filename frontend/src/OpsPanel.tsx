import { useEffect, useState } from "react";
import { Advisory, Allocation, AuditEntry, Task, User, getJson, qs, send, shortDate } from "./api";

const RESOURCE_LABEL: Record<string, string> = { water_point: "Water points", cooling_centre: "Cooling centres", ambulance_staging: "Ambulances staged", other: "Other" };
const LANGUAGES: [string, string][] = [["en", "English"], ["hi", "Hindi"]];
const LANGUAGE_LABEL: Record<string, string> = { en: "English", hi: "Hindi", gu: "Gujarati", ta: "Tamil", te: "Telugu", mr: "Marathi", bn: "Bengali", or: "Odia" };

type Props = { districtId: string; districtName: string; date: string; level: string; user: User | undefined; blocked: boolean };

function useLoad<T>(path: string | null, deps: unknown[]): [T | null, () => void, string] {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    getJson<T>(path, controller.signal).then((value) => { setData(value); setError(""); }, (reason: Error) => { if (reason.name !== "AbortError") setError(reason.message); });
    return () => controller.abort();
  }, [path, tick, ...deps]);
  return [data, () => setTick((value) => value + 1), error];
}

function Advisories({ districtId, date, level, user, blocked, onChange }: Props & { onChange: () => void }) {
  const [list, reload] = useLoad<{ items: Advisory[] }>(`/advisories/${districtId}?${qs({ forecast_date: date })}`, []);
  const [message, setMessage] = useState("");
  const [cap, setCap] = useState<Record<string, string>>({});
  const run = (action: Promise<unknown>, done: string) => action.then(() => { setMessage(done); reload(); onChange(); }, (error: Error) => setMessage(error.message));

  return (
    <div className="ops-body">
      <p className="hint">Advisories are drafted from approved templates for the alert on <b>{shortDate(date)}</b> ({level}). Nothing is sent until an officer approves.</p>
      <div className="row">
        {LANGUAGES.map(([code, label]) => (
          <button key={code} disabled={blocked || level === "green" || !user} onClick={() => run(send("POST", `/advisories/${districtId}?${qs({ forecast_date: date, language: code })}`), `${label} draft created`)}>Draft {label}</button>
        ))}
        <button className="ghost" disabled={blocked || level === "green" || !user} title="LLM translation of the approved English text; still needs approval" onClick={() => run(send("POST", `/advisories/${districtId}/regional?${qs({ forecast_date: date })}`), "Regional-language draft created (LLM translation)")}>Regional language (AI)</button>
      </div>
      {level === "green" && <p className="hint">Green alert: no advisory needed.</p>}
      {message && <p className="flash">{message}</p>}
      {list?.items.map((advisory) => (
        <article key={advisory.advisory_id} className="card">
          <header><b>{LANGUAGE_LABEL[advisory.language] ?? advisory.language}</b><span className={`chip ${advisory.status}`}>{advisory.status.replace("_", " ")}</span><small>{advisory.template_version}</small></header>
          <p className="advisory-text">{advisory.text}</p>
          <div className="row">
            {advisory.status === "pending_approval" && <>
              <button disabled={!user} onClick={() => run(send("PATCH", `/advisories/${advisory.advisory_id}/approve?${qs({ action: "approve" })}`), "Approved")}>Approve as {user?.username}</button>
              <button className="ghost" disabled={!user} onClick={() => run(send("PATCH", `/advisories/${advisory.advisory_id}/approve?${qs({ action: "reject" })}`), "Rejected")}>Reject</button>
            </>}
            {advisory.status === "approved" && <>
              <button onClick={() => getJson<{ cap_xml: string }>(`/advisories/${advisory.advisory_id}/cap`).then((value) => setCap({ ...cap, [advisory.advisory_id]: cap[advisory.advisory_id] ? "" : value.cap_xml }), (error: Error) => setMessage(error.message))}>CAP 1.2 XML</button>
              <button disabled={!user} onClick={() => run(send("POST", `/advisories/${advisory.advisory_id}/dispatch/sms`, { phone_numbers: ["+919800000001", "+919800000002"], idempotency_key: `${advisory.advisory_id}-sms-demo` }), "SMS accepted by simulated gateway")}>Dispatch SMS</button>
              <button disabled={!user} onClick={() => run(send("POST", `/advisories/${advisory.advisory_id}/dispatch/email`, { email_addresses: ["district-eoc@example.gov.in"], idempotency_key: `${advisory.advisory_id}-email-demo` }), "Email accepted by simulated gateway")}>Dispatch email</button>
              <button className="ghost" disabled={!user} onClick={() => run(send("POST", `/advisories/${advisory.advisory_id}/trigger/municipal`, { idempotency_key: `${advisory.advisory_id}-municipal-demo`, action_types: [] }), "Municipal trigger payload prepared; gateway integration pending")}>Prepare city trigger</button>
            </>}
          </div>
          {cap[advisory.advisory_id] && <pre className="cap">{cap[advisory.advisory_id]}</pre>}
        </article>
      ))}
    </div>
  );
}

function Resources({ districtId, date, user, blocked, onChange }: Props & { onChange: () => void }) {
  const [allocation, , allocationError] = useLoad<Allocation>(blocked ? null : `/allocation/${districtId}?${qs({ forecast_date: date })}`, []);
  const [tasks, reloadTasks] = useLoad<{ items: Task[] }>(`/tasks/${districtId}`, []);
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [message, setMessage] = useState("");
  useEffect(() => setEdits({}), [districtId, date]);

  const quantity = (wardId: string, kind: string, suggested: number) => edits[`${wardId}|${kind}`] ?? suggested;
  const createAll = async () => {
    if (!allocation) return;
    let count = 0;
    try {
      for (const ward of allocation.items) {
        for (const [kind, suggested] of Object.entries(ward.resources)) {
          const amount = quantity(ward.ward_id, kind, suggested);
          if (amount <= 0) continue;
          await send("POST", `/tasks/${districtId}?${qs({
            task_type: kind, title: `${RESOURCE_LABEL[kind]} × ${amount} — ${ward.name}`, ward_id: ward.ward_id, quantity: amount,
            priority: allocation.alert_level === "red" ? "critical" : allocation.alert_level === "orange" ? "high" : "normal",
            location_lat: ward.lat, location_lon: ward.lon, description: `Heat response for ${shortDate(date)} (${allocation.alert_level} alert)`,
          })}`);
          count += 1;
        }
      }
      setMessage(`${count} tasks created`);
    } catch (error) { setMessage((error as Error).message); }
    reloadTasks(); onChange();
  };
  const update = (task: Task, status: string) => send("PATCH", `/tasks/${task.task_id}?${qs({ status })}`).then(() => { reloadTasks(); onChange(); }, (error: Error) => setMessage(error.message));

  const kinds = Object.keys(allocation?.items.find((item) => Object.keys(item.resources).length)?.resources ?? {});
  return (
    <div className="ops-body">
      <h4>Suggested allocation · {shortDate(date)}</h4>
      {allocationError && <p className="hint">{allocationError}</p>}
      {allocation && !allocation.items.length && <p className="hint">No ward exposure data for this district; create district-level tasks below.</p>}
      {allocation && allocation.items.length > 0 && !kinds.length && <p className="hint">Green alert: no resources suggested.</p>}
      {allocation && kinds.length > 0 && <>
        <div className="table-wrap"><table>
          <thead><tr><th>Ward</th><th>People</th>{kinds.map((kind) => <th key={kind}>{RESOURCE_LABEL[kind]}</th>)}</tr></thead>
          <tbody>{allocation.items.map((ward) => (
            <tr key={ward.ward_id}><td>{ward.name}</td><td>{Math.round(ward.population_estimate).toLocaleString("en-IN")}</td>
              {kinds.map((kind) => <td key={kind}><input type="number" min={0} value={quantity(ward.ward_id, kind, ward.resources[kind] ?? 0)} onChange={(event) => setEdits({ ...edits, [`${ward.ward_id}|${kind}`]: Number(event.target.value) })} /></td>)}
            </tr>
          ))}</tbody>
        </table></div>
        <p className="hint">{allocation.basis}.</p>
        <button disabled={!user} onClick={createAll}>Create response tasks</button>
      </>}
      {message && <p className="flash">{message}</p>}
      <h4>Response tasks</h4>
      {!tasks?.items.length && <p className="hint">No tasks yet.</p>}
      {tasks?.items.map((task) => (
        <article key={task.task_id} className="card task">
          <header><b>{task.title}</b><span className={`chip ${task.priority}`}>{task.priority}</span></header>
          <div className="row">
            <select disabled={!user} value={task.status} onChange={(event) => update(task, event.target.value)}>
              {["pending", "in_progress", "completed", "cancelled"].map((status) => <option key={status} value={status}>{status.replace("_", " ")}</option>)}
            </select>
            <small>{RESOURCE_LABEL[task.task_type]}{task.quantity ? ` · qty ${task.quantity}` : ""}</small>
          </div>
        </article>
      ))}
    </div>
  );
}

function Audit({ refreshKey }: { refreshKey: number }) {
  const [log] = useLoad<{ items: AuditEntry[] }>(`/audit-log?limit=40`, [refreshKey]);
  return (
    <div className="ops-body">
      <p className="hint">Every approval, dispatch and task change is recorded with the acting user.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Detail</th></tr></thead>
        <tbody>{log?.items.map((entry) => (
          <tr key={entry.audit_id}><td>{new Date(entry.created_at).toLocaleString("en-IN", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })}</td><td>{entry.user_id.replace("user-", "")}</td><td>{entry.action}</td><td><code>{JSON.stringify(entry.new_value ?? "")?.slice(0, 60)}</code></td></tr>
        ))}</tbody>
      </table></div>
    </div>
  );
}

export function OpsPanel(props: Props) {
  const [tab, setTab] = useState<"advisories" | "resources" | "audit">("advisories");
  const [changes, setChanges] = useState(0);
  const onChange = () => setChanges((value) => value + 1);
  return (
    <section className="ops">
      <nav className="tabs">
        {(["advisories", "resources", "audit"] as const).map((key) => <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{{ advisories: "Advisories", resources: "Resources & tasks", audit: "Audit log" }[key]}</button>)}
      </nav>
      {tab === "advisories" && <Advisories key={`${props.districtId}-${props.date}`} {...props} onChange={onChange} />}
      {tab === "resources" && <Resources key={`${props.districtId}-${props.date}`} {...props} onChange={onChange} />}
      {tab === "audit" && <Audit refreshKey={changes} />}
    </section>
  );
}
