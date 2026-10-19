"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { APPROVAL_LABEL, RUN_STATUS, RunDetail, STEP_STATUS } from "@/lib/types";

const LIVE = ["running"];

export default function RunPage({ params }: { params: { number: string } }) {
  const { me, can, toast } = useSession();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const n = params.number;

  const load = useCallback(() => api<RunDetail>(`/runs/${n}`).then(setRun).catch((e) => setError(e.message)), [n]);
  useEffect(() => { load(); }, [load]);
  // Refresh while steps are executing.
  useEffect(() => {
    if (!run || !LIVE.includes(run.status)) return;
    const t = setTimeout(load, 1500);
    return () => clearTimeout(t);
  }, [run, load]);

  async function decide(ordinal: number, action: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await api(`/runs/${n}/steps/${ordinal}/${action}`, { body: { note } });
      setNote("");
      toast(action === "approve" ? `Step ${ordinal} approved` : `Step ${ordinal} rejected. The run stopped.`);
      await load();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  async function cancel() {
    try { setRun(await api<RunDetail>(`/runs/${n}/cancel`, { method: "POST" })); toast("Run cancelled"); } catch (e: any) { setError(e.message); }
  }

  if (!run) return <><ErrorNote error={error} />{!error && <p className="meta">Loading…</p>}</>;
  const [label, cls] = RUN_STATUS[run.status];
  const open = run.status === "running" || run.status === "awaiting_approval";
  const mayCancel = open && (can("admin") || run.started_by?.id === me.id);

  return (
    <>
      <Link href="/runs" className="meta">← All runs</Link>
      <PageHead title={`Run #${run.number} · ${run.source_name}`} sub={`${run.trigger === "schedule" ? "Started by the scheduler" : `Started by ${run.started_by?.name || "a former member"}`} on ${fmtDate(run.created_at)} · ${APPROVAL_LABEL[run.approval_mode]}`}>
        <Pill cls={cls}>{label}</Pill>
        {mayCancel && <button className="btn danger" onClick={cancel}>Cancel run</button>}
      </PageHead>
      <ErrorNote error={error} />
      {run.goal && <div className="panel"><span className="meta">Goal</span><div style={{ whiteSpace: "pre-wrap" }}>{run.goal}</div></div>}
      {run.error && <div className={run.status === "cancelled" ? "note" : "alert"}>{run.error}</div>}
      <div className="panel steps">
        {run.steps.map((s) => {
          const [sl, sc] = STEP_STATUS[s.status] || [s.status, "mute"];
          const waiting = s.status === "awaiting_approval";
          return (
            <div key={s.ordinal} className={`step ${sc}`}>
              <span className="n">{s.status === "succeeded" ? "✓" : ["failed", "rejected"].includes(s.status) ? "✕" : s.ordinal}</span>
              <div style={{ display: "grid", gap: 6, minWidth: 0 }}>
                <div className="row between">
                  <span className="row"><span className={`chip ${s.write ? "write" : ""}`}>{s.tool}</span>{s.requires_approval && <span className="meta">needs approval</span>}</span>
                  <Pill cls={sc}>{sl}</Pill>
                </div>
                {s.why && <span className="meta">{s.why}</span>}
                {Object.keys(s.args).length > 0 && <div className="result">{Object.entries(s.args).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join("\n")}</div>}
                {s.result_summary && <div className="result" style={{ background: "var(--ok-soft)" }}>{s.result_summary}</div>}
                {s.error && <div className="alert">{s.error}</div>}
                {s.decided_by && <span className="meta">{s.status === "rejected" ? "Rejected" : "Approved"} by {s.decided_by.name} {fmtDate(s.decided_at)}{s.decision_note ? `: “${s.decision_note}”` : ""}</span>}
                {waiting && (can("admin") ? (
                  <div className="form" style={{ marginTop: 4 }}>
                    <input id="decision-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note for the audit log" maxLength={1000} />
                    <div className="row">
                      <button className="btn pri" disabled={busy} onClick={() => decide(s.ordinal, "approve")}>Approve step {s.ordinal}</button>
                      <button className="btn danger" disabled={busy} onClick={() => decide(s.ordinal, "reject")}>Reject and stop</button>
                    </div>
                  </div>
                ) : <span className="meta">Waiting for an admin to approve or reject this step.</span>)}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
