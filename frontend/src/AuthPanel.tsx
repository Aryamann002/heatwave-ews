import { FormEvent, useEffect, useState } from "react";
import { AuthConfig, LoginResponse, User, getJson, send, setSessionToken } from "./api";

type Props = { user: User | null; onSession: (user: User | null) => void };

export function AuthPanel({ user, onSession }: Props) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [username, setUsername] = useState("officer");
  const [password, setPassword] = useState("officer-demo");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getJson<AuthConfig>("/auth/config").then((value) => {
      setConfig(value);
      if (value.mode === "strict") setPassword("");
    }, (reason: Error) => setError(reason.message));
    getJson<User>("/auth/session").then(onSession, () => undefined);
    const clear = () => { setSessionToken(null); onSession(null); };
    window.addEventListener("heatwatch-auth-required", clear);
    return () => window.removeEventListener("heatwatch-auth-required", clear);
  }, []);

  const login = (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    send<LoginResponse>("POST", "/auth/login", { username, password })
      .then((result) => { setSessionToken(result.token); onSession(result.user); setPassword(""); })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setBusy(false));
  };

  if (user) return (
    <div className="session-card">
      <span>Signed in</span>
      <b>{user.username}</b>
      <small>{user.role}</small>
      <button onClick={() => { setSessionToken(null); onSession(null); }}>Sign out</button>
    </div>
  );

  return (
    <form className="login-form" onSubmit={login} aria-label="Officer sign in">
      <div><b>Officer sign in</b><small>{config?.mode === "demo" ? "Demo access" : "Protected access"}</small></div>
      <label><span>Username</span><input required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
      <label><span>Password</span><input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
