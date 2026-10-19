"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtBytes, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { PRIORITY_CLASS, STATUS_CLASS, STATUS_LABEL, Ticket } from "@/lib/types";

interface Usage { members: number; open_tickets: number; p1_open: number; documents: number; storage_bytes: number; ai_messages_30d: number; ai_tokens_30d: number }

function PortalHome() {
  const { me, org, toast } = useSession();
  const [mine, setMine] = useState<Ticket[]>([]);
  const [f, setF] = useState({ title: "", description: "", priority: "P3" });
  const [error, setError] = useState<string | null>(null);
  const load = () => api<{ items: Ticket[] }>("/tickets", { query: { limit: 20 } }).then((r) => setMine(r.items)).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const t = await api<Ticket>("/tickets", { body: f });
      toast(`Request ${t.key} sent. You'll get a notification when IT replies.`);
      setF({ title: "", description: "", priority: "P3" });
      load();
    } catch (err: any) { setError(err.message); }
  }

  return (
    <>
      <PageHead title={`Hi ${me.name.split(" ")[0]}, how can IT help?`} sub={`${org.name} support. Ask the AI first for quick answers from our guides, or send a request to the team.`}>
        <Link className="btn" href="/chat">Ask AI</Link>
      </PageHead>
      <ErrorNote error={error} />
      <div className="g2">
        <form className="panel form" onSubmit={submit}>
          <h2>New request</h2>
          <label>What do you need?<input id="p-title" required minLength={3} maxLength={300} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Laptop won't connect to Wi-Fi" /></label>
          <label>Details<textarea id="p-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="What happened, when it started, what you've tried" /></label>
          <label>How urgent?
            <select id="p-prio" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
              <option value="P3">Normal</option><option value="P2">High: my work is slowed down</option><option value="P1">Critical: my work is stopped</option><option value="P4">Low: whenever you can</option>
            </select>
          </label>
          <div><button className="btn pri">Send request</button></div>
        </form>
        <div className="panel">
          <div className="ph"><h2>My requests</h2><Link href="/tickets" className="btn sm">See all</Link></div>
          <div className="list">
            {mine.length === 0 && <div className="empty">No requests yet.</div>}
            {mine.map((t) => (
              <Link key={t.id} href={`/tickets/${t.number}`} className="item">
                <div className="row between"><span className="mono">{t.key}</span><Pill cls={STATUS_CLASS[t.status]}>{STATUS_LABEL[t.status]}</Pill></div>
                <div>{t.title}</div>
                <span className="meta">Updated {fmtDate(t.updated_at)}{t.assignee ? ` · ${t.assignee.name} is on it` : ""}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

export default function Overview() {
  const { org } = useSession();
  return org.role === "member" ? <PortalHome /> : <StaffHome />;
}

function StaffHome() {
  const { me, org, can } = useSession();
  const [u, setU] = useState<Usage | null>(null);
  const [mine, setMine] = useState<Ticket[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Usage>("/orgs/current/usage").then(setU).catch((e) => setError(e.message));
    const q = can("technician") ? { assignee: "me", status: ["open", "in_progress", "waiting"] } : { status: ["open", "in_progress", "waiting"] };
    api<{ items: Ticket[] }>("/tickets", { query: { ...q, limit: 8 } }).then((r) => setMine(r.items)).catch(() => {});
  }, [can]);

  return (
    <>
      <PageHead title={`Good to see you, ${me.name.split(" ")[0]}`} sub={`${org.name} · AI answers from your documents, IT tickets and assets in one place.`}>
        <Link className="btn pri" href="/chat">Ask OmniAI</Link>
        <Link className="btn" href="/tickets?new=1">New ticket</Link>
      </PageHead>
      <ErrorNote error={error} />
      {u && (
        <div className="stats">
          <div className="stat"><span>Open tickets</span><b className="num">{u.open_tickets}</b><small className="meta">{u.p1_open} P1</small></div>
          <div className="stat"><span>Documents</span><b className="num">{u.documents}</b><small className="meta">{fmtBytes(u.storage_bytes)}</small></div>
          <div className="stat"><span>AI answers, 30 days</span><b className="num">{u.ai_messages_30d}</b><small className="meta">{u.ai_tokens_30d.toLocaleString()} tokens</small></div>
          <div className="stat"><span>Members</span><b className="num">{u.members}</b><small className="meta">your role: {org.role}</small></div>
        </div>
      )}
      <div className="panel">
        <div className="ph"><h2>{can("technician") ? "Assigned to you" : "Your open requests"}</h2><Link href="/tickets" className="btn sm">All tickets</Link></div>
        {mine.length === 0 ? (
          <div className="empty">Nothing open. {can("technician") ? "New tickets assigned to you will show here." : "Raise a ticket when something needs IT."}</div>
        ) : (
          <div className="list">
            {mine.map((t) => (
              <Link key={t.id} href={`/tickets/${t.number}`} className="item">
                <div className="row between"><span className="row"><span className="mono">{t.key}</span><Pill cls={PRIORITY_CLASS[t.priority]}>{t.priority}</Pill></span><Pill cls={STATUS_CLASS[t.status]}>{STATUS_LABEL[t.status]}</Pill></div>
                <div>{t.title}</div>
                <span className="meta">Updated {fmtDate(t.updated_at)}</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
