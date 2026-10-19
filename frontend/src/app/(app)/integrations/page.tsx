"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Integration } from "@/lib/types";

type Kind = Integration["kind"];
type Form = { kind: Kind; name: string; url: string; auth_header_name: string; auth_header_value: string; enabled: boolean };
const HELP: Record<Kind, string> = {
  slack: "In Slack: Apps → Incoming Webhooks → Add to a channel, then paste the https://hooks.slack.com/… URL.",
  teams: "In Teams: the channel's … menu → Workflows → “Post to a channel when a webhook request is received”, then paste the URL it gives you.",
  webhook: "OmniAI sends a JSON POST with text, organization, source and sent_at. Add an auth header if the receiver needs one.",
};

export default function IntegrationsPage() {
  const { can, toast } = useSession();
  const [list, setList] = useState<Integration[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const admin = can("admin");

  const load = useCallback(() => api<Integration[]>("/integrations").then(setList).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  if (!can("technician")) return <PageHead title="Integrations" sub="Available to technicians and admins." />;

  function edit(i: Integration | null) {
    setError(null);
    setEditId(i?.id || null);
    setForm(i ? { kind: i.kind, name: i.name, url: "", auth_header_name: i.config.auth_header_name || "", auth_header_value: "", enabled: i.enabled }
      : { kind: "slack", name: "it-alerts", url: "", auth_header_name: "", auth_header_value: "", enabled: true });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    try {
      if (editId) await api(`/integrations/${editId}`, { method: "PUT", body: form });
      else await api("/integrations", { body: form });
      toast(`${form.name} saved. The secret is stored encrypted.`);
      setForm(null);
      load();
    } catch (err: any) { setError(err.message); }
  }

  async function test(i: Integration) {
    setTesting(i.id);
    try { const r = await api<{ ok: boolean; message: string }>(`/integrations/${i.id}/test`, { method: "POST" }); r.ok ? toast(r.message) : setError(r.message); load(); }
    catch (e: any) { setError(e.message); } finally { setTesting(null); }
  }

  async function remove() {
    if (!editId) return;
    try { await api(`/integrations/${editId}`, { method: "DELETE" }); toast("Integration deleted"); setForm(null); load(); } catch (e: any) { setError(e.message); }
  }

  return (
    <>
      <PageHead title="Integrations" sub="Where workflows and agents can send messages. Webhook URLs and tokens are encrypted at rest and never shown again after saving.">
        {admin && <button className="btn pri" onClick={() => edit(null)}>Add integration</button>}
      </PageHead>
      <ErrorNote error={error} />
      {form && (
        <form className="panel form" onSubmit={save}>
          <h2>{editId ? `Edit ${form.name}` : "Add integration"}</h2>
          <div className="g2">
            <label>Type<select id="ig-kind" value={form.kind} disabled={!!editId} onChange={(e) => setForm({ ...form, kind: e.target.value as Kind })}><option value="slack">Slack</option><option value="teams">Microsoft Teams</option><option value="webhook">Generic webhook</option></select></label>
            <label>Name (used in workflow steps)<input id="ig-name" required maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          </div>
          <span className="meta">{HELP[form.kind]}</span>
          <label>Webhook URL<input id="ig-url" type="url" required={!editId} value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder={editId ? "Leave blank to keep the saved URL" : "https://"} autoComplete="off" /></label>
          {form.kind === "webhook" && (
            <div className="g2">
              <label>Auth header name<input id="ig-hn" value={form.auth_header_name} onChange={(e) => setForm({ ...form, auth_header_name: e.target.value })} placeholder="Authorization" /></label>
              <label>Auth header value<input id="ig-hv" type="password" value={form.auth_header_value} onChange={(e) => setForm({ ...form, auth_header_value: e.target.value })} placeholder={editId ? "Leave blank to keep" : "Bearer …"} autoComplete="off" /></label>
            </div>
          )}
          <label className="check"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />Enabled</label>
          <div className="row">
            <button className="btn pri">Save</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Cancel</button>
            {editId && <button type="button" className="btn danger" onClick={remove}>Delete</button>}
          </div>
        </form>
      )}
      <div className="g3">
        {list.length === 0 && <div className="empty">No integrations yet.</div>}
        {list.map((i) => (
          <div key={i.id} className="panel" style={{ display: "grid", gap: 8, alignContent: "start" }}>
            <div className="row between"><h2>{i.name}</h2>{!i.enabled ? <Pill cls="mute">Off</Pill> : i.last_ok === false ? <Pill cls="crit">Failing</Pill> : i.last_ok ? <Pill cls="ok">Working</Pill> : <Pill cls="mute">Not tested</Pill>}</div>
            <span className="meta">{i.kind_label}</span>
            <span className="meta mono">{i.secret_hint} · encrypted</span>
            {i.last_used_at && <span className="meta">Last used {fmtDate(i.last_used_at)}</span>}
            {i.last_error && <span className="meta" style={{ color: "var(--crit)" }}>{i.last_error}</span>}
            {admin && <div className="row"><button className="btn sm" disabled={testing === i.id} onClick={() => test(i)}>{testing === i.id ? "Sending…" : "Send test"}</button><button className="btn sm" onClick={() => edit(i)}>Edit</button></div>}
          </div>
        ))}
      </div>
    </>
  );
}
