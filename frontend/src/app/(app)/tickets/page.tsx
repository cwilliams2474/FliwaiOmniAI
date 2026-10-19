"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { PRIORITY_CLASS, STATUS_CLASS, STATUS_LABEL, Ticket } from "@/lib/types";

const FILTERS: [string, string[]][] = [
  ["Active", ["open", "in_progress", "waiting"]],
  ["Open", ["open"]],
  ["In progress", ["in_progress"]],
  ["Waiting", ["waiting"]],
  ["Resolved", ["resolved", "closed"]],
  ["All", []],
];

export default function TicketsPage() {
  const { can, org } = useSession();
  const router = useRouter();
  const [filter, setFilter] = useState(0);
  const [mine, setMine] = useState(false);
  const [q, setQ] = useState("");
  const [data, setData] = useState<{ total: number; items: Ticket[] }>({ total: 0, items: [] });
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [prio, setPrio] = useState("P3");

  useEffect(() => { if (new URLSearchParams(window.location.search).get("new")) setShowNew(true); }, []);

  const load = useCallback(() => {
    api<{ total: number; items: Ticket[] }>("/tickets", { query: { status: FILTERS[filter][1], q, assignee: mine ? "me" : undefined, limit: 100 } })
      .then(setData).catch((e) => setError(e.message));
  }, [filter, q, mine]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const t = await api<Ticket>("/tickets", { body: { title, description: desc, priority: prio } });
      router.push(`/tickets/${t.number}`);
    } catch (err: any) { setError(err.message); }
  }

  return (
    <>
      <PageHead title="IT Tickets" sub={can("technician") ? `Service requests for ${org.name}.` : "Your requests to IT."}>
        {org.role !== "viewer" && <button className="btn pri" onClick={() => setShowNew(!showNew)}>{showNew ? "Close" : "New ticket"}</button>}
      </PageHead>
      <ErrorNote error={error} />
      {showNew && (
        <form className="panel form" onSubmit={create}>
          <h2>New ticket</h2>
          <label>What's wrong?<input id="t-title" required minLength={3} maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="VPN connects but intranet won't load" /></label>
          <label>Details<textarea id="t-desc" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="What happened, when it started, what you've tried" /></label>
          <label>Priority
            <select id="t-prio" value={prio} onChange={(e) => setPrio(e.target.value)} className="inline">
              <option value="P1">P1 · Work is stopped</option><option value="P2">P2 · Work is slowed</option><option value="P3">P3 · Normal</option><option value="P4">P4 · Low</option>
            </select>
          </label>
          <div><button className="btn pri">Create ticket</button></div>
        </form>
      )}
      <div className="row">
        {FILTERS.map(([label], i) => <button key={label} className={`btn sm ${filter === i ? "pri" : ""}`} onClick={() => setFilter(i)}>{label}</button>)}
        {can("technician") && <label className="row" style={{ display: "flex", color: "var(--ink)", fontSize: 13 }}><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} style={{ width: "auto" }} />Assigned to me</label>}
        <input id="t-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title or IT-1042" style={{ flex: "1 1 200px", maxWidth: 320 }} />
      </div>
      <div className="tw">
        <table>
          <thead><tr><th>Ticket</th><th>Title</th><th>Priority</th><th>Status</th><th>Requester</th><th>Assignee</th><th>Updated</th></tr></thead>
          <tbody>
            {data.items.length === 0 && <tr><td colSpan={7} className="empty">No tickets match.</td></tr>}
            {data.items.map((t) => (
              <tr key={t.id} className="click" onClick={() => router.push(`/tickets/${t.number}`)}>
                <td className="mono"><Link href={`/tickets/${t.number}`} onClick={(e) => e.stopPropagation()}>{t.key}</Link></td>
                <td>{t.title}</td>
                <td><Pill cls={PRIORITY_CLASS[t.priority]}>{t.priority}</Pill></td>
                <td><Pill cls={STATUS_CLASS[t.status]}>{STATUS_LABEL[t.status]}</Pill></td>
                <td>{t.requester?.name || "—"}</td>
                <td>{t.assignee?.name || <span className="meta">Unassigned</span>}</td>
                <td className="meta">{fmtDate(t.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="meta">{data.total} ticket{data.total === 1 ? "" : "s"}</span>
    </>
  );
}
