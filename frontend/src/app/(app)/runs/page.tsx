"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { RUN_STATUS, RunStatus, RunSummary } from "@/lib/types";

const FILTERS: [string, RunStatus[]][] = [
  ["Needs approval", ["awaiting_approval"]],
  ["Running", ["running"]],
  ["Failed or stopped", ["failed", "rejected", "cancelled"]],
  ["Completed", ["completed"]],
  ["All", []],
];

export default function RunsPage() {
  const { can } = useSession();
  const router = useRouter();
  const [filter, setFilter] = useState(4);
  const [data, setData] = useState<{ total: number; items: RunSummary[] }>({ total: 0, items: [] });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<{ total: number; items: RunSummary[] }>("/runs", { query: { status: FILTERS[filter][1], limit: 100 } }).then(setData).catch((e) => setError(e.message)), [filter]);
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);

  if (!can("technician")) return <PageHead title="Runs" sub="Automation is available to technicians and admins." />;
  const waiting = data.items.filter((r) => r.status === "awaiting_approval").length;

  return (
    <>
      <PageHead title="Runs & approvals" sub="Every agent and workflow run, step by step. Steps that change things wait here for an admin.">
        <Link className="btn" href="/agents">Run an agent</Link>
        <Link className="btn" href="/workflows">Workflows</Link>
      </PageHead>
      <ErrorNote error={error} />
      {can("admin") && waiting > 0 && filter !== 0 && <div className="note warn">{waiting} run{waiting === 1 ? " is" : "s are"} waiting for your approval. <button className="btn sm" onClick={() => setFilter(0)}>Show them</button></div>}
      <div className="row">{FILTERS.map(([l], i) => <button key={l} className={`btn sm ${i === filter ? "pri" : ""}`} onClick={() => setFilter(i)}>{l}</button>)}</div>
      <div className="tw">
        <table>
          <thead><tr><th>Run</th><th>Agent or workflow</th><th>Goal</th><th>Status</th><th>Started</th><th>By</th></tr></thead>
          <tbody>
            {data.items.length === 0 && <tr><td colSpan={6} className="empty">No runs here.</td></tr>}
            {data.items.map((r) => (
              <tr key={r.id} className="click" onClick={() => router.push(`/runs/${r.number}`)}>
                <td className="mono"><Link href={`/runs/${r.number}`} onClick={(e) => e.stopPropagation()}>#{r.number}</Link></td>
                <td>{r.source_name}<div className="meta">{r.kind}{r.trigger === "schedule" ? " · scheduled" : ""}</div></td>
                <td style={{ maxWidth: 320, overflowWrap: "anywhere" }}>{r.goal || <span className="meta">{r.step_count} fixed steps</span>}</td>
                <td><Pill cls={RUN_STATUS[r.status][1]}>{RUN_STATUS[r.status][0]}{r.waiting_step ? ` · step ${r.waiting_step}` : ""}</Pill></td>
                <td className="meta">{fmtDate(r.created_at)}</td>
                <td>{r.started_by?.name || <span className="meta">Scheduler</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
