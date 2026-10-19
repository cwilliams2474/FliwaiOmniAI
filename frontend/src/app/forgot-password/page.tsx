"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/password-reset/request", { body: { email } });
      setSent(true);
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="auth">
      <form className="card" onSubmit={submit}>
        <h1>Reset your password</h1>
        {sent ? (
          <p className="sub">If an account exists for {email}, a reset link is on its way. It works for one hour. If no email arrives, ask an administrator: the link is written to the server log when email isn't set up.</p>
        ) : (
          <>
            {error && <div className="alert">{error}</div>}
            <label>Email<input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            <button className="btn pri">Send reset link</button>
          </>
        )}
        <Link href="/login" className="meta">Back to sign in</Link>
      </form>
    </div>
  );
}
