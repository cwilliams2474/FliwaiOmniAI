"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";

export default function ResetPage() {
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pw !== pw2) { setError("The two passwords don't match."); return; }
    const token = new URLSearchParams(window.location.search).get("token") || "";
    try {
      await api("/auth/password-reset/confirm", { body: { token, new_password: pw } });
      setDone(true);
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="auth">
      <form className="card" onSubmit={submit}>
        <h1>Choose a new password</h1>
        {done ? (
          <p className="sub">Password changed. You've been signed out everywhere. <Link href="/login">Sign in</Link> with the new password.</p>
        ) : (
          <>
            {error && <div className="alert">{error}</div>}
            <label>New password<input id="pw" type="password" autoComplete="new-password" required value={pw} onChange={(e) => setPw(e.target.value)} /></label>
            <label>Repeat password<input id="pw2" type="password" autoComplete="new-password" required value={pw2} onChange={(e) => setPw2(e.target.value)} /></label>
            <span className="meta">At least 12 characters, with upper and lower case letters and a number.</span>
            <button className="btn pri">Change password</button>
          </>
        )}
      </form>
    </div>
  );
}
