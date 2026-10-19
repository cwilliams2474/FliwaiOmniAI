"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { NotificationItem } from "@/lib/types";

export default function NotificationsPage() {
  const [data, setData] = useState<{ unread: number; items: NotificationItem[] }>({ unread: 0, items: [] });
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<{ unread: number; items: NotificationItem[] }>("/notifications", { query: { unread_only: unreadOnly, limit: 100 } }).then(setData).catch((e) => setError(e.message)), [unreadOnly]);
  useEffect(() => { load(); }, [load]);

  async function readAll() { await api("/notifications/read-all", { method: "POST" }); load(); }
  function open(n: NotificationItem) { if (!n.read) api(`/notifications/${n.id}/read`, { method: "POST" }).catch(() => {}); }

  return (
    <>
      <PageHead title="Notifications" sub={`${data.unread} unread. Replies, assignments, approvals and automation results land here.`}>
        <label className="check"><input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />Unread only</label>
        <button className="btn" onClick={readAll} disabled={!data.unread}>Mark all read</button>
      </PageHead>
      <ErrorNote error={error} />
      <div className="list">
        {data.items.length === 0 && <div className="empty">Nothing here yet.</div>}
        {data.items.map((n) => {
          const inner = (
            <>
              <div className="row between"><b>{n.title}</b><span className="meta">{fmtDate(n.created_at)}</span></div>
              {n.body && <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{n.body}</div>}
            </>
          );
          const style = n.read ? { opacity: 0.65 } : { borderLeft: "3px solid var(--accent)" };
          return n.link
            ? <Link key={n.id} href={n.link} className="item" style={style} onClick={() => open(n)}>{inner}</Link>
            : <div key={n.id} className="item" style={style} onClick={() => open(n)}>{inner}</div>;
        })}
      </div>
    </>
  );
}
