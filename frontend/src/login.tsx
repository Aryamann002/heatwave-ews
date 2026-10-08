import { FormEvent, StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { API, AuthConfig, LoginResponse, User, getJson, send, setSessionToken } from "./api";
import "./styles.css";
import "./login.css";

type Provider = "google" | "github" | "microsoft";
const providers: { id: Provider; label: string; mark: string }[] = [
  { id: "google", label: "Google", mark: "G" },
  { id: "github", label: "GitHub", mark: "GH" },
  { id: "microsoft", label: "Microsoft", mark: "M" },
];

function safeDestination() {
  const value = new URLSearchParams(window.location.search).get("next");
  return value === "/dashboard.html" || (value?.startsWith("/dashboard.html?replay=") && !/[\\\r\n#]/.test(value)) ? value : "/dashboard.html";
}

function Login() {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(() => {
    const code = new URLSearchParams(window.location.search).get("error");
    return code === "provider_denied" ? "Sign-in was cancelled. Choose a method to try again." : code === "provider_failed" ? "The provider could not complete sign-in. Please retry or use your assigned account." : "";
  });
  const destination = safeDestination();

  useEffect(() => {
    setSessionToken(null);
    getJson<AuthConfig>("/auth/config").then(setConfig, () => setError("The sign-in service is unavailable. Please wait a moment and try again."));
    getJson<User>("/auth/session").then(() => window.location.replace(destination), () => undefined);
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    send<LoginResponse>("POST", "/auth/login", { username: username.trim(), password })
      .then(() => window.location.assign(destination))
      .catch((reason: Error) => setError(reason.message === "Failed to fetch" ? "The sign-in service is unavailable. Please wait a moment and try again." : reason.message))
      .finally(() => setBusy(false));
  };

  return (
    <div className="auth-shell">
      <a className="auth-skip" href="#sign-in">Skip to sign in</a>
      <section className="auth-story" aria-label="About HeatSafe AI">
        <a className="auth-brand" href="/landing.html"><span className="auth-brand-mark" aria-hidden="true"><i /></span><span>HeatSafe AI</span></a>
        <div className="auth-story-content">
          <div className="auth-signal" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div>
          <h1>See the heat.<br /><em>Understand the risk.</em></h1>
          <p>One secure place to move from seven-day weather signals to human thermal stress, district priorities and reviewed heat-action plans.</p>
          <div className="auth-story-rule" />
          <ul>
            <li><span aria-hidden="true" />District-scale forecast and thermal-stress view</li>
            <li><span aria-hidden="true" />Explainable alerts with quality gates</li>
            <li><span aria-hidden="true" />Human approval before any outbound action</li>
          </ul>
        </div>
        <p className="auth-story-foot">Decision-support prototype · Not an official IMD warning</p>
      </section>

      <main className="auth-form-side" id="sign-in">
        <div className="auth-topline"><span>Secure access</span><a href="/landing.html">Back to overview <span aria-hidden="true">↗</span></a></div>
        <div className="auth-form-wrap">
          <h2>Welcome back.</h2>
          <p className="auth-intro">Sign in to open the HeatSafe AI dashboard.</p>
          <div className="auth-provider-list" aria-label="Continue with a provider">
            {providers.map(({ id, label, mark }) => {
              const enabled = config?.providers.includes(id) ?? false;
              return <a key={id} className={`auth-provider ${enabled ? "" : "unavailable"}`} href={enabled ? `${API}/auth/oauth/${id}/start?next=${encodeURIComponent(destination)}` : undefined} aria-disabled={!enabled} tabIndex={enabled ? 0 : -1}>
                <span className={`auth-provider-mark ${id}`} aria-hidden="true">{mark}</span>
                <span>Continue with {label}</span>
                <small>{enabled ? "→" : "Not configured"}</small>
              </a>;
            })}
          </div>
          <div className="auth-divider"><span>or use your assigned account</span></div>
          <form className="auth-form" onSubmit={submit}>
            <label htmlFor="auth-username">Email or assigned username</label>
            <input id="auth-username" required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="you@example.org" />
            <label htmlFor="auth-password">Password</label>
            <input id="auth-password" required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" />
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in to dashboard"}<span aria-hidden="true">→</span></button>
          </form>
          {config?.mode === "demo" && <p className="auth-demo">Local demo access: <code>officer</code> / <code>officer-demo</code>. This account is for demonstration only.</p>}
          {config?.mode === "strict" && <p className="auth-help">Need access? Ask your HeatSafe AI administrator to provision your account. New provider sign-ins receive viewer access only.</p>}
          {!config && !error && <p className="auth-help" role="status">Checking available sign-in methods…</p>}
        </div>
        <p className="auth-legal">HeatSafe AI supports planning and response. For public warnings, follow IMD and local authorities.</p>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><Login /></StrictMode>);
