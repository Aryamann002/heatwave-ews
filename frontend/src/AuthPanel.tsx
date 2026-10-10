import { useState } from "react";
import { User, send, setSessionToken } from "./api";

export function AuthPanel({ user }: { user: User }) {
  const [error, setError] = useState("");
  const signOut = async () => {
    setError("");
    try {
      await send<{ signed_out: boolean }>("POST", "/auth/logout");
      setSessionToken(null);
      if (window.HeatSafeUI) window.HeatSafeUI.navigate("/login.html");
      else window.location.assign("/login.html");
    } catch {
      setError("Could not sign out. Please try again.");
    }
  };

  return (
    <div className="session-card" aria-label="Current session">
      <span>Signed in</span>
      <b>{user.display_name ?? user.username}</b>
      <small>{user.role}</small>
      <button type="button" onClick={signOut}>Sign out</button>
      {error && <small role="alert">{error}</small>}
    </div>
  );
}
