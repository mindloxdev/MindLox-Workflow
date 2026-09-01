import React, { useState } from "react";
import { api, setToken } from "../api.js";
import { ThemeToggle } from "./shell.jsx";

export default function Login({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError("");
    setBusy(true);
    try {
      const data = await api.login(email.trim(), password);
      setToken(data.token);
      onSignedIn(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wrap enter" style={{ maxWidth: 360, paddingTop: "14vh" }}>
      <h1 style={{ fontSize: 26 }}>Dispatch</h1>
      <p className="muted" style={{ marginTop: 6, marginBottom: 20 }}>
        Hand in your sheet, collect a list nobody else is working.
      </p>

      <div className="card pad stack" style={{ gap: 13 }}>
        <div>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={email} autoComplete="username"
                 style={{ width: "100%", marginTop: 5 }}
                 onChange={(e) => setEmail(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && submit()} />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} autoComplete="current-password"
                 style={{ width: "100%", marginTop: 5 }}
                 onChange={(e) => setPassword(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && submit()} />
        </div>
        {error && <div className="notice">{error}</div>}
        <button onClick={submit} disabled={busy || !email || !password}
                style={{ width: "100%" }}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </div>

      {/* Available before anybody signs in, because the sign-in screen is the
          first thing a dark room sees. */}
      <div className="row" style={{ marginTop: 14, justifyContent: "center" }}>
        <ThemeToggle />
      </div>
    </div>
  );
}
