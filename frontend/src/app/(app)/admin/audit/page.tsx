"use client";

import { useEffect, useState } from "react";
import { ErrorNote, PageHead } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";

interface Entry { id: number; created_at: string; actor: string; action: string; target: string; ip: string | null; detail: Record<string, unknown> }
const PAGE = 50;

export default function AuditPage() {
  const { can } = useSession();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; items: Entry[] }>({ total: 0, items: [] });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!can("admin")) return;
    const t = setTimeout(() => api<{ total: number; items: Entry[] }>("/orgs/current/audit", { query: { q, limit: PAGE, offset } }).then(setData).catch((e) => setError(e.message)), q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q, offset, can]);

  if (!can("admin")) return <PageHead title="Audit log" sub="Only admins and owners can view the audit log." />;

  return (
    <>
      <PageHead title="Audit log" sub="Every sign-in, change and AI request in this organization. Entries can't be edited or deleted from the app." />
      <ErrorNote error={error} />
      <input id="audit-q" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} placeholder="Filter by action, person or target, e.g. ticket. or login_failed" style={{ maxWidth: 420 }} />
      <div className="tw">
        <table>
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Target</th><th>Details</th><th>IP</th></tr></thead>
          <tbody>
            {data.items.length === 0 && <tr><td colSpan={6} className="empty">No entries.</td></tr>}
            {data.items.map((a) => (
              <tr key={a.id}>
                <td className="mono" style={{ whiteSpace: "nowrap" }}>{fmtDate(a.created_at)}</td>
                <td>{a.actor}</td>
                <td className="mono">{a.action}</td>
                <td style={{ overflowWrap: "anywhere" }}>{a.target}</td>
                <td className="meta mono" style={{ overflowWrap: "anywhere", maxWidth: 260 }}>{Object.keys(a.detail).length ? JSON.stringify(a.detail) : ""}</td>
                <td className="mono meta">{a.ip || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row">
        <button className="btn sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</button>
        <button className="btn sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Older</button>
        <span className="meta">{data.total ? `${offset + 1}–${Math.min(offset + PAGE, data.total)} of ${data.total}` : ""}</span>
      </div>
    </>
  );
}
