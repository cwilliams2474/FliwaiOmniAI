"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Logo } from "@/components/Logo";

function nextUrl() {
  const n = new URLSearchParams(window.location.search).get("next") || "/";
  return n.startsWith("/") && !n.startsWith("//") ? n : "/";
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ needs_setup: boolean }>("/auth/status").then((s) => { if (s.needs_setup) window.location.href = "/setup"; }).catch(() => {});
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!mfaToken) {
        const r = await api<{ mfa_required: boolean; mfa_token: string | null }>("/auth/login", { body: { email, password } });
        if (r.mfa_required) { setMfaToken(r.mfa_token); setBusy(false); return; }
      } else {
        await api("/auth/mfa/verify", { body: { mfa_token: mfaToken, code } });
      }
      window.location.href = nextUrl();
    } catch (err: any) {
      setError(err.message);
      if (err.status === 401 && mfaToken && err.message.includes("expired")) setMfaToken(null);
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <form className="card" onSubmit={submit}>
        <div className="row"><Logo size={30} /><h1>Sign in to OmniAI</h1></div>
        {error && <div className="alert" role="alert">{error}</div>}
        {!mfaToken ? (
          <>
            <label>Email<input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            <label>Password<input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            <button className="btn pri" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
            <Link href="/forgot-password" className="meta">Forgot your password?</Link>
          </>
        ) : (
          <>
            <p className="sub">Enter the 6-digit code from your authenticator app, or one of your recovery codes.</p>
            <label>Code<input id="code" inputMode="numeric" autoComplete="one-time-code" autoFocus required value={code} onChange={(e) => setCode(e.target.value)} /></label>
            <button className="btn pri" disabled={busy}>{busy ? "Checking…" : "Verify"}</button>
            <button type="button" className="btn" onClick={() => { setMfaToken(null); setCode(""); }}>Back</button>
          </>
        )}
      </form>
    </div>
  );
}
