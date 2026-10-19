"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";

interface Sess { id: string; created_at: string; last_seen_at: string; ip: string | null; user_agent: string | null; current: boolean }

function device(ua: string | null) {
  if (!ua) return "Unknown device";
  const b = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Windows/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "macOS" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Linux/.test(ua) ? "Linux" : "";
  return `${b}${os ? ` · ${os}` : ""}`;
}

export default function AccountPage() {
  const { me, refresh, toast } = useSession();
  const [error, setError] = useState<string | null>(null);
  const [first, setFirst] = useState(false);
  const [welcome, setWelcome] = useState(false);
  const [pw, setPw] = useState({ current: "", next: "", again: "" });
  const [mfa, setMfa] = useState<{ secret: string; qr: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [disable, setDisable] = useState({ password: "", code: "" });
  const [sessions, setSessions] = useState<Sess[]>([]);

  const loadSessions = useCallback(() => api<Sess[]>("/auth/sessions").then(setSessions).catch(() => {}), []);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setFirst(p.has("first") || me.must_change_password);
    setWelcome(p.has("welcome"));
    loadSessions();
  }, [loadSessions, me.must_change_password]);

  async function changePw(e: React.FormEvent) {
    e.preventDefault();
    if (pw.next !== pw.again) { setError("The new passwords don't match."); return; }
    setError(null);
    try {
      await api("/auth/password", { body: { current_password: pw.current, new_password: pw.next } });
      setPw({ current: "", next: "", again: "" });
      toast("Password changed. Other sessions were signed out.");
      await refresh();
      setFirst(false);
      loadSessions();
    } catch (err: any) { setError(err.message); }
  }

  async function startMfa() {
    setError(null);
    try { const r = await api<{ secret: string; qr_svg_data_uri: string }>("/auth/mfa/setup", { method: "POST" }); setMfa({ secret: r.secret, qr: r.qr_svg_data_uri }); } catch (e: any) { setError(e.message); }
  }

  async function enableMfa(e: React.FormEvent) {
    e.preventDefault();
    try { const r = await api<{ recovery_codes: string[] }>("/auth/mfa/enable", { body: { code } }); setCodes(r.recovery_codes); setMfa(null); setCode(""); await refresh(); } catch (err: any) { setError(err.message); }
  }

  async function disableMfa(e: React.FormEvent) {
    e.preventDefault();
    try { await api("/auth/mfa/disable", { body: disable }); setDisable({ password: "", code: "" }); toast("MFA turned off"); await refresh(); } catch (err: any) { setError(err.message); }
  }

  async function revoke(id: string) {
    await api(`/auth/sessions/${id}`, { method: "DELETE" });
    toast("Session signed out");
    loadSessions();
  }

  return (
    <>
      <PageHead title="Account & security" sub={`${me.name} · ${me.email}`} />
      {welcome && <div className="note">Your organization is ready. Next steps: turn on MFA below, upload a few documents, and add your team under Members.</div>}
      {first && <div className="note warn">Choose a new password to finish signing in. Your temporary password stops working after this.</div>}
      <ErrorNote error={error} />
      <div className="g2">
        <form className="panel form" onSubmit={changePw}>
          <h2>Password</h2>
          <label>Current password<input id="pw-cur" type="password" autoComplete="current-password" required value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></label>
          <label>New password<input id="pw-new" type="password" autoComplete="new-password" required value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></label>
          <label>Repeat new password<input id="pw-again" type="password" autoComplete="new-password" required value={pw.again} onChange={(e) => setPw({ ...pw, again: e.target.value })} /></label>
          <span className="meta">At least 12 characters, with upper and lower case letters and a number.</span>
          <div><button className="btn pri">Change password</button></div>
        </form>

        <div className="panel form" style={{ alignContent: "start" }}>
          <div className="row between"><h2>Two-step sign-in (MFA)</h2>{me.mfa_enabled ? <Pill cls="ok">On</Pill> : <Pill cls="warn">Off</Pill>}</div>
          {codes && (
            <>
              <div className="note">Save these recovery codes somewhere safe. Each works once if you lose your phone. They won't be shown again.</div>
              <div className="codes" style={{ userSelect: "all" }}>{codes.map((c) => <span key={c}>{c}</span>)}</div>
              <div><button className="btn" onClick={() => setCodes(null)}>I've saved them</button></div>
            </>
          )}
          {!me.mfa_enabled && !mfa && !codes && (
            <>
              <span className="meta">Use an authenticator app such as Microsoft Authenticator, Google Authenticator or 1Password.</span>
              <div><button className="btn pri" onClick={startMfa}>Set up MFA</button></div>
            </>
          )}
          {mfa && (
            <form className="form" onSubmit={enableMfa}>
              <span className="meta">Scan this code with your authenticator app, then enter the 6-digit code it shows.</span>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={mfa.qr} alt="MFA QR code" width={200} height={200} style={{ background: "#fff", borderRadius: 6 }} />
              <span className="meta">Can't scan? Enter this key: <span className="mono" style={{ userSelect: "all" }}>{mfa.secret}</span></span>
              <label>Code<input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} /></label>
              <div><button className="btn pri">Turn on MFA</button></div>
            </form>
          )}
          {me.mfa_enabled && !codes && (
            <form className="form" onSubmit={disableMfa}>
              <span className="meta">To turn MFA off, confirm your password and a current code.</span>
              <label>Password<input id="mfa-dis-pw" type="password" required value={disable.password} onChange={(e) => setDisable({ ...disable, password: e.target.value })} /></label>
              <label>Code<input id="mfa-dis-code" inputMode="numeric" required value={disable.code} onChange={(e) => setDisable({ ...disable, code: e.target.value })} /></label>
              <div><button className="btn danger">Turn off MFA</button></div>
            </form>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="ph"><h2>Where you're signed in</h2></div>
        <div className="list">
          {sessions.map((s) => (
            <div key={s.id} className="item">
              <div className="row between"><b>{device(s.user_agent)}{s.current && <span className="meta"> · this device</span>}</b>{!s.current && <button className="btn sm danger" onClick={() => revoke(s.id)}>Sign out</button>}</div>
              <span className="meta">{s.ip || "unknown IP"} · signed in {fmtDate(s.created_at)} · last active {fmtDate(s.last_seen_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
