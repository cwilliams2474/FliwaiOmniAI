"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { MemoryEntry } from "@/lib/types";

export default function MemoryPage() {
  const { can, toast } = useSession();
  const [items, setItems] = useState<MemoryEntry[]>([]);
  const [editing, setEditing] = useState<MemoryEntry | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const edit = can("technician");

  const load = useCallback(() => api<MemoryEntry[]>("/memory").then(setItems).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  function start(m: MemoryEntry | null) {
    setEditing(m);
    setTitle(m?.title || "");
    setContent(m?.content || "");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (editing) await api(`/memory/${editing.id}`, { method: "PUT", body: { title, content } });
      else await api("/memory", { body: { title, content } });
      toast(editing ? "Memory updated" : "Saved. AI Chat will use this.");
      start(null);
      load();
    } catch (err: any) { setError(err.message); }
  }

  async function remove(m: MemoryEntry) {
    await api(`/memory/${m.id}`, { method: "DELETE" });
    toast("Memory entry deleted");
    if (editing?.id === m.id) start(null);
    load();
  }

  return (
    <>
      <PageHead title="Memory" sub="Short facts the AI treats as always true for this organization: maintenance windows, key servers, escalation contacts." />
      <ErrorNote error={error} />
      <div className={edit ? "g2" : ""}>
        <div className="list">
          {items.length === 0 && <div className="empty">No memory entries yet.</div>}
          {items.map((m) => (
            <div key={m.id} className="item">
              <div className="row between"><b>{m.title}</b>
                {edit && <span className="row"><button className="btn sm" onClick={() => start(m)}>Edit</button><button className="btn sm danger" onClick={() => remove(m)}>Delete</button></span>}
              </div>
              <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
              <span className="meta">Updated {fmtDate(m.updated_at)}</span>
            </div>
          ))}
        </div>
        {edit && (
          <form className="panel form" onSubmit={save} style={{ alignContent: "start" }}>
            <h2>{editing ? "Edit entry" : "Add entry"}</h2>
            <label>Title<input id="mem-title" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Maintenance window" /></label>
            <label>What should the AI remember?<textarea id="mem-content" required maxLength={4000} value={content} onChange={(e) => setContent(e.target.value)} placeholder="Production patching happens Sundays 01:00 to 04:00 Eastern." /></label>
            <div className="row"><button className="btn pri">{editing ? "Save changes" : "Save to memory"}</button>{editing && <button type="button" className="btn" onClick={() => start(null)}>Cancel</button>}</div>
          </form>
        )}
      </div>
    </>
  );
}
