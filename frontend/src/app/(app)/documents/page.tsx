"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtBytes, fmtDate, getOrgId } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Doc } from "@/lib/types";

interface Hit { document_id: string; filename: string; page: number | null; excerpt: string; score: number }
const STATUS: Record<Doc["status"], [string, string]> = { processing: ["Indexing", "warn"], indexed: ["Indexed", "ok"], failed: ["Failed", "crit"] };

export default function DocumentsPage() {
  const { can, toast } = useSession();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api<Doc[]>("/documents").then(setDocs).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  // Poll while anything is still indexing.
  useEffect(() => {
    if (!docs.some((d) => d.status === "processing")) return;
    const t = setTimeout(load, 2000);
    return () => clearTimeout(t);
  }, [docs, load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setError(null);
    for (const f of Array.from(files)) {
      const form = new FormData();
      form.append("file", f);
      try {
        await api("/documents", { form });
      } catch (e: any) {
        setError(`${f.name}: ${e.message}`);
      }
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
    load();
  }

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim().length < 2) return;
    try { setHits(await api<Hit[]>("/documents/search", { query: { q } })); } catch (err: any) { setError(err.message); }
  }

  async function download(d: Doc) {
    // The org header can't ride on a plain link, so fetch the file and hand it to the browser.
    const res = await fetch(`/api/documents/${d.id}/download`, { headers: { "X-Org-Id": getOrgId() || "" }, credentials: "same-origin" });
    if (!res.ok) throw new Error(`Download failed (${res.status}).`);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = d.filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function remove(d: Doc) {
    try {
      await api(`/documents/${d.id}`, { method: "DELETE" });
      toast(`${d.filename} deleted`);
      setConfirm(null);
      load();
    } catch (e: any) { setError(e.message); }
  }

  return (
    <>
      <PageHead title="Documents" sub="Files here are split into passages and indexed so AI Chat can answer from them. PDF, Word, HTML, Markdown, CSV and text are supported.">
        {can("technician") && (
          <>
            <input ref={fileRef} id="upload" type="file" multiple hidden accept=".pdf,.docx,.html,.htm,.md,.markdown,.txt,.csv,.tsv,.json,.log,.yaml,.yml,.ini,.conf" onChange={(e) => upload(e.target.files)} />
            <button className="btn pri" disabled={uploading} onClick={() => fileRef.current?.click()}>{uploading ? "Uploading…" : "Upload documents"}</button>
          </>
        )}
      </PageHead>
      <ErrorNote error={error} />
      <form className="panel row" onSubmit={search}>
        <input id="doc-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search passages, e.g. restore production" style={{ flex: "1 1 240px" }} />
        <button className="btn">Search</button>
        {hits && <button type="button" className="btn" onClick={() => { setHits(null); setQ(""); }}>Clear</button>}
      </form>
      {hits && (
        <div className="list">
          {hits.length === 0 ? <div className="empty">No passages matched.</div> : hits.map((h, i) => (
            <div key={i} className="item"><span className="cite" style={{ justifySelf: "start", margin: 0 }}>{h.filename}{h.page ? ` · p.${h.page}` : ""}</span><div style={{ whiteSpace: "pre-wrap" }}>{h.excerpt}</div></div>
          ))}
        </div>
      )}
      <div className="tw">
        <table>
          <thead><tr><th>Document</th><th>Size</th><th>Passages</th><th>Status</th><th>Uploaded</th><th /></tr></thead>
          <tbody>
            {docs.length === 0 && <tr><td colSpan={6} className="empty">No documents yet. {can("technician") ? "Upload runbooks, policies and guides to get started." : "Ask a technician to upload company documents."}</td></tr>}
            {docs.map((d) => (
              <tr key={d.id}>
                <td style={{ overflowWrap: "anywhere" }}>{d.filename}{d.status === "failed" && <div className="meta" style={{ color: "var(--crit)" }}>{d.error}</div>}</td>
                <td className="num">{fmtBytes(d.size_bytes)}</td>
                <td className="num">{d.chunk_count || "—"}</td>
                <td><Pill cls={STATUS[d.status][1]}>{STATUS[d.status][0]}</Pill></td>
                <td>{d.uploaded_by?.name || "—"}<div className="meta">{fmtDate(d.created_at)}</div></td>
                <td>
                  {can("technician") && (
                    <div className="row">
                      <button className="btn sm" onClick={() => download(d).catch((e) => setError(e.message))}>Download</button>
                      {d.status === "failed" && <button className="btn sm" onClick={() => api(`/documents/${d.id}/reindex`, { method: "POST" }).then(load)}>Retry</button>}
                      {confirm === d.id ? (
                        <><button className="btn sm danger" onClick={() => remove(d)}>Confirm delete</button><button className="btn sm" onClick={() => setConfirm(null)}>Cancel</button></>
                      ) : <button className="btn sm danger" onClick={() => setConfirm(d.id)}>Delete</button>}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
