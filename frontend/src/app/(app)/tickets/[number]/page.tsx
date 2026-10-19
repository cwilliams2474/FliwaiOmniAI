"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Asset, Member, PRIORITY_CLASS, STATUS_CLASS, STATUS_LABEL, TicketDetail } from "@/lib/types";

interface Hit { filename: string; page: number | null; excerpt: string }

export default function TicketPage({ params }: { params: { number: string } }) {
  const { me, can, org, toast } = useSession();
  const [t, setT] = useState<TicketDetail | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [comment, setComment] = useState("");
  const [internal, setInternal] = useState(false);
  const [hints, setHints] = useState<Hit[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tech = can("technician");
  const n = params.number;

  const load = useCallback(() => api<TicketDetail>(`/tickets/${n}`).then(setT).catch((e) => setError(e.message)), [n]);
  useEffect(() => {
    load();
    if (tech) {
      api<Member[]>("/orgs/current/members").then(setMembers).catch(() => {});
      api<{ items: Asset[] }>("/assets", { query: { limit: 500 } }).then((r) => setAssets(r.items)).catch(() => {});
    }
  }, [load, tech]);

  async function patch(body: object) {
    setError(null);
    try { setT(await api<TicketDetail>(`/tickets/${n}`, { method: "PATCH", body })); toast("Ticket updated"); } catch (e: any) { setError(e.message); }
  }

  async function addComment(e: React.FormEvent) {
    e.preventDefault();
    try {
      setT(await api<TicketDetail>(`/tickets/${n}/comments`, { body: { body: comment, internal } }));
      setComment("");
      setInternal(false);
    } catch (err: any) { setError(err.message); }
  }

  async function suggest() {
    if (!t) return;
    try { setHints(await api<Hit[]>("/documents/search", { query: { q: `${t.title} ${t.description}`.slice(0, 480) } })); } catch (e: any) { setError(e.message); }
  }

  if (!t) return <><ErrorNote error={error} />{!error && <p className="meta">Loading…</p>}</>;
  const own = t.requester?.id === me.id && org.role !== "viewer";
  const asset = assets.find((a) => a.id === t.asset_id);

  return (
    <>
      <Link href="/tickets" className="meta">← All tickets</Link>
      <PageHead title={`${t.key} · ${t.title}`} sub={`Raised by ${t.requester?.name || "unknown"} on ${fmtDate(t.created_at)}`}>
        <Pill cls={PRIORITY_CLASS[t.priority]}>{t.priority}</Pill>
        <Pill cls={STATUS_CLASS[t.status]}>{STATUS_LABEL[t.status]}</Pill>
      </PageHead>
      <ErrorNote error={error} />
      <div className="g2" style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,1fr)" }}>
        <div className="list">
          <div className="panel"><h2>Description</h2><p style={{ whiteSpace: "pre-wrap" }}>{t.description || <span className="meta">No details given.</span>}</p></div>
          <div className="panel">
            <div className="ph"><h2>Conversation</h2></div>
            <div className="list">
              {t.comments.length === 0 && <span className="meta">No replies yet.</span>}
              {t.comments.map((c) => (
                <div key={c.id} className="item" style={c.internal ? { borderLeft: "3px solid var(--warn)" } : undefined}>
                  <div className="row between"><b>{c.author?.name || "Former member"}</b><span className="meta">{c.internal ? "Internal note · " : ""}{fmtDate(c.created_at)}</span></div>
                  <div style={{ whiteSpace: "pre-wrap" }}>{c.body}</div>
                </div>
              ))}
            </div>
            {org.role !== "viewer" && (
              <form className="form" onSubmit={addComment} style={{ marginTop: 12 }}>
                <textarea id="comment" required value={comment} onChange={(e) => setComment(e.target.value)} placeholder={tech ? "Reply to the requester, or add an internal note" : "Add details or reply"} />
                <div className="row">
                  <button className="btn pri">{internal ? "Add internal note" : "Send reply"}</button>
                  {tech && <label className="row" style={{ display: "flex", color: "var(--ink)" }}><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} style={{ width: "auto" }} />Internal note (hidden from requester)</label>}
                </div>
              </form>
            )}
          </div>
        </div>
        <div className="list">
          {tech && (
            <div className="panel form">
              <h2>Work this ticket</h2>
              <label>Status<select id="status" value={t.status} onChange={(e) => patch({ status: e.target.value })}>{Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
              <label>Priority<select id="priority" value={t.priority} onChange={(e) => patch({ priority: e.target.value })}>{["P1", "P2", "P3", "P4"].map((p) => <option key={p}>{p}</option>)}</select></label>
              <label>Assignee
                <select id="assignee" value={t.assignee?.id || ""} onChange={(e) => patch(e.target.value ? { assignee_id: e.target.value } : { unassign: true })}>
                  <option value="">Unassigned</option>
                  {members.filter((m) => ["owner", "admin", "technician"].includes(m.role)).map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
                </select>
              </label>
              <label>Related asset
                <select id="asset" value={t.asset_id || ""} onChange={(e) => e.target.value && patch({ asset_id: e.target.value })}>
                  <option value="">None</option>
                  {assets.map((a) => <option key={a.id} value={a.id}>{a.tag} · {a.name}</option>)}
                </select>
              </label>
              {asset && <span className="meta">{asset.asset_type} · {asset.os || "no OS recorded"} · {asset.location || "no location"}</span>}
              {t.status !== "resolved" && <button className="btn pri" onClick={() => patch({ status: "resolved" })}>Mark resolved</button>}
            </div>
          )}
          {!tech && own && (
            <div className="panel form">
              <h2>Your request</h2>
              {["resolved", "closed"].includes(t.status)
                ? <button className="btn" onClick={() => patch({ status: "open" })}>Reopen</button>
                : <button className="btn" onClick={() => patch({ status: "closed" })}>Close, it's fixed</button>}
            </div>
          )}
          <div className="panel form">
            <div className="row between"><h2>Related knowledge</h2><button className="btn sm" onClick={suggest}>Find articles</button></div>
            {hints === null ? <span className="meta">Search your documents for passages matching this ticket.</span> : hints.length === 0 ? <span className="meta">Nothing matched. Consider writing a runbook once this is fixed.</span> : hints.slice(0, 3).map((h, i) => (
              <div key={i} className="item"><span className="cite" style={{ justifySelf: "start", margin: 0 }}>{h.filename}{h.page ? ` · p.${h.page}` : ""}</span><div style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{h.excerpt.slice(0, 320)}{h.excerpt.length > 320 ? "…" : ""}</div></div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
