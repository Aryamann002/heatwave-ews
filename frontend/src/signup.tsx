import { FormEvent, StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AuthConfig, LoginResponse, User, getJson, send, setSessionToken } from "./api";
import "./styles.css";
import "./login.css";

const requested = new URLSearchParams(window.location.search).get("next");
const destination = requested === "/dashboard.html" || (requested?.startsWith("/dashboard.html?replay=") && !/[\\\r\n#]/.test(requested)) ? requested : "/dashboard.html";

function Signup() {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setSessionToken(null);
    getJson<AuthConfig>("/auth/config").then(setConfig, () => setError("The account service is unavailable. Please try again shortly."));
    getJson<User>("/auth/session").then(() => window.location.replace(destination), () => undefined);
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (password !== confirmation) { setError("Passwords do not match. Re-enter them and try again."); return; }
    setBusy(true);
    setError("");
    send<LoginResponse>("POST", "/auth/register", { email: email.trim(), password })
      .then(() => { if (window.HeatSafeUI) window.HeatSafeUI.navigate(destination); else window.location.assign(destination); })
      .catch((reason: Error) => setError(reason.message === "Failed to fetch" ? "The account service is unavailable. Please try again shortly." : reason.message))
      .finally(() => setBusy(false));
  };

  return (
    <div className="auth-shell">
      <a className="auth-skip" href="#create-account">Skip to create account</a>
      <section className="auth-story" aria-label="About HeatSafe AI">
        <a className="auth-brand" href="/landing.html"><span className="auth-brand-mark" aria-hidden="true"><i /></span><span>HeatSafe AI</span></a>
        <div className="auth-story-content">
          <div className="auth-signal" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div>
          <h1>See the heat.<br /><em>Understand the risk.</em></h1>
          <p>One secure place to move from seven-day weather signals to human thermal stress, district priorities and reviewed heat-action plans.</p>
          <div className="auth-story-rule" />
          <ul>
            <li><span aria-hidden="true" />Explore district forecasts and thermal stress</li>
            <li><span aria-hidden="true" />Understand alert reasoning and data quality</li>
            <li><span aria-hidden="true" />Plan with human-reviewed heat actions</li>
          </ul>
        </div>
        <p className="auth-story-foot">HeatSafe AI · Human thermal stress</p>
      </section>
      <main className="auth-form-side" id="create-account">
        <div className="auth-topline"><span>Secure access</span><div className="auth-actions"><span id="heatsafe-theme-slot" /><a href="/landing.html">Back to overview <span aria-hidden="true">↗</span></a></div></div>
        <div className="auth-form-wrap">
          <h2>Create your account.</h2>
          <p className="auth-intro">Set up read-only access to the HeatSafe AI dashboard.</p>
          {config && !config.email_registration ? (
            <p className="auth-help">Account creation is not enabled here. <a href="/login.html">Return to sign in</a> or ask your administrator for access.</p>
          ) : (
            <form className="auth-form" onSubmit={submit}>
              <label htmlFor="signup-email">Email address</label>
              <input id="signup-email" required type="email" autoComplete="email" maxLength={80} value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.org" />
              <label htmlFor="signup-password">Password</label>
              <input id="signup-password" required type="password" autoComplete="new-password" minLength={12} maxLength={200} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Create a password" aria-describedby="signup-password-hint" />
              <p className="auth-field-note" id="signup-password-hint">Use at least 12 characters. Choose a unique password.</p>
              <label htmlFor="signup-confirm">Confirm password</label>
              <input id="signup-confirm" required type="password" autoComplete="new-password" minLength={12} maxLength={200} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="Enter the password again" />
              {error && <p className="auth-error" role="alert">{error}</p>}
              <button type="submit" disabled={busy || config === null}>{busy ? "Creating account…" : "Create account"}<span aria-hidden="true">→</span></button>
            </form>
          )}
          {!config && !error && <p className="auth-help" role="status">Checking account availability…</p>}
          <p className="auth-switch">Already have an account? <a href={`/login.html?next=${encodeURIComponent(destination)}`}>Sign in</a></p>
          <p className="auth-help">New accounts have viewer access. Officer and admin permissions are assigned separately.</p>
        </div>
        <p className="auth-legal">HeatSafe AI supports planning and response. For public warnings, follow IMD and local authorities.</p>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><Signup /></StrictMode>);
