"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Logo } from "@/components/Logo";

export default function SetupPage() {
  const [f, setF] = useState({ org_name: "", name: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ needs_setup: boolean }>("/auth/status").then((s) => { if (!s.needs_setup) window.location.href = "/login"; }).catch(() => {});
  }, []);

  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (f.password !== f.confirm) { setError("The two passwords don't match."); return; }
    setBusy(true);
    setError(null);
    try {
      await api("/auth/setup", { body: { org_name: f.org_name, name: f.name, email: f.email, password: f.password } });
      window.location.href = "/account?welcome=1";
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <form className="card" onSubmit={submit}>
        <div className="row"><Logo size={30} /><h1>Set up OmniAI</h1></div>
        <p className="sub">Create the first organization and its owner account. This page only works once.</p>
        {error && <div className="alert" role="alert">{error}</div>}
        <label>Organization name<input id="org_name" required value={f.org_name} onChange={set("org_name")} placeholder="FLIWAI" /></label>
        <label>Your name<input id="name" required value={f.name} onChange={set("name")} /></label>
        <label>Email<input id="email" type="email" autoComplete="username" required value={f.email} onChange={set("email")} /></label>
        <label>Password<input id="password" type="password" autoComplete="new-password" required value={f.password} onChange={set("password")} /></label>
        <span className="meta">At least 12 characters, with upper and lower case letters and a number.</span>
        <label>Repeat password<input id="confirm" type="password" autoComplete="new-password" required value={f.confirm} onChange={set("confirm")} /></label>
        <button className="btn pri" disabled={busy}>{busy ? "Creating…" : "Create organization"}</button>
      </form>
    </div>
  );
}
