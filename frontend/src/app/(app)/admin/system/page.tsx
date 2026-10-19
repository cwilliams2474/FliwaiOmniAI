"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHead, Pill } from "@/components/Shell";

interface Health { status: string; version: string; uptime_seconds: number; checks: Record<string, { ok: boolean; [k: string]: unknown }> }

const LABEL: Record<string, string> = { database: "PostgreSQL", uploads: "Upload storage", ai_provider: "AI model provider", smtp: "Email (SMTP)" };

function describe(k: string, c: Health["checks"][string]): [string, string] {
  if (k === "database") return c.ok ? [`Connected · ${c.ms} ms · schema ${c.migration}`, "ok"] : ["Unreachable", "crit"];
  if (k === "uploads") return c.ok ? ["Writable", "ok"] : ["Not writable", "crit"];
  if (k === "ai_provider") return c.provider === "none" ? ["Not configured · search-only answers", "warn"] : [`${c.provider} · ${c.model}`, "ok"];
  if (k === "smtp") return c.configured ? ["Configured", "ok"] : ["Not configured · reset links go to the server log", "warn"];
  return [c.ok ? "OK" : "Problem", c.ok ? "ok" : "crit"];
}

export default function SystemPage() {
  const [h, setH] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/health", { credentials: "same-origin" });
      setH(await res.json());
      setErr(null);
    } catch {
      setErr("The backend didn't answer.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <PageHead title="System health" sub="Live checks from the backend. Backups run from the server; see the README for the backup and restore scripts.">
        <button className="btn" onClick={load}>Run checks</button>
      </PageHead>
      {err && <div className="alert">{err}</div>}
      {h && (
        <div className="panel list">
          <div className="row between"><b>OmniAI {h.version}</b><span className="meta">Up {Math.floor(h.uptime_seconds / 3600)} h {Math.floor((h.uptime_seconds % 3600) / 60)} min</span></div>
          {Object.entries(h.checks).map(([k, c]) => { const [text, cls] = describe(k, c); return (
            <div key={k} className="row between" style={{ borderTop: "1px solid var(--line)", paddingTop: 8 }}><span>{LABEL[k] || k}</span><Pill cls={cls}>{text}</Pill></div>
          ); })}
        </div>
      )}
    </>
  );
}
