"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { useTools } from "@/components/useTools";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { APPROVAL_LABEL, Agent, ApprovalMode, RunDetail } from "@/lib/types";

type Form = Omit<Agent, "id">;
const EMPTY: Form = { name: "", description: "", instructions: "", tools: ["tickets.search", "knowledge.search"], approval_mode: "writes", max_steps: 6, enabled: true };

export default function AgentsPage() {
  const { can, toast } = useSession();
  const router = useRouter();
  const tools = useTools();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [goals, setGoals] = useState<Record<string, string>>({});
  const [planning, setPlanning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const admin = can("admin");

  const load = useCallback(() => api<Agent[]>("/agents").then(setAgents).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  if (!can("technician")) return <PageHead title="AI Agents" sub="Automation is available to technicians and admins." />;

  function edit(a: Agent | null) {
    setError(null);
    setEditId(a?.id || null);
    setForm(a ? { ...a } : { ...EMPTY });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    try {
      if (editId) await api(`/agents/${editId}`, { method: "PUT", body: form });
      else await api("/agents", { body: form });
      toast(`${form.name} saved`);
      setForm(null);
      load();
    } catch (err: any) { setError(err.message); }
  }

  async function remove() {
    if (!editId) return;
    try { await api(`/agents/${editId}`, { method: "DELETE" }); toast("Agent deleted"); setForm(null); load(); } catch (e: any) { setError(e.message); }
  }

  async function run(a: Agent) {
    const goal = (goals[a.id] || "").trim();
    if (goal.length < 3) { setError("Describe what the agent should do."); return; }
    setPlanning(a.id);
    setError(null);
    try {
      const r = await api<RunDetail>(`/agents/${a.id}/runs`, { body: { goal } });
      router.push(`/runs/${r.number}`);
    } catch (e: any) { setError(e.message); setPlanning(null); }
  }

  const toggleTool = (name: string) => form && setForm({ ...form, tools: form.tools.includes(name) ? form.tools.filter((t) => t !== name) : [...form.tools, name] });

  return (
    <>
      <PageHead title="AI Agents" sub="Give an agent a goal. It plans a short list of steps using only its allowed tools; steps that change things wait for an admin's approval.">
        {admin && <button className="btn pri" onClick={() => edit(null)}>New agent</button>}
      </PageHead>
      <ErrorNote error={error} />

      {form && (
        <form className="panel form" onSubmit={save}>
          <h2>{editId ? `Edit ${form.name}` : "New agent"}</h2>
          <div className="g2">
            <label>Name<input id="ag-name" required maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Helpdesk triage" /></label>
            <label>Approvals<select id="ag-mode" value={form.approval_mode} onChange={(e) => setForm({ ...form, approval_mode: e.target.value as ApprovalMode })}>{Object.entries(APPROVAL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          </div>
          <label>What it's for<input id="ag-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Looks at new tickets and suggests next steps" /></label>
          <label>Instructions the agent follows when planning<textarea id="ag-inst" value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} placeholder="Always search the knowledge base before replying. Never change priority to P1." /></label>
          <label>Most steps per run<input id="ag-max" type="number" min={1} max={10} value={form.max_steps} onChange={(e) => setForm({ ...form, max_steps: Number(e.target.value) })} style={{ maxWidth: 120 }} /></label>
          <div>
            <span className="meta">Allowed tools. Amber ones change data or send messages.</span>
            <div className="g2" style={{ marginTop: 6 }}>
              {tools.map((t) => (
                <label key={t.name} className="check"><input type="checkbox" checked={form.tools.includes(t.name)} onChange={() => toggleTool(t.name)} />
                  <span><span className={`chip ${t.write ? "write" : ""}`}>{t.name}</span> {t.description}{t.needs_ai ? " (needs AI model)" : ""}</span></label>
              ))}
            </div>
          </div>
          <label className="check"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />Enabled</label>
          <div className="row">
            <button className="btn pri">Save agent</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Cancel</button>
            {editId && <button type="button" className="btn danger" onClick={remove}>Delete agent</button>}
          </div>
        </form>
      )}

      <div className="list">
        {agents.length === 0 && <div className="empty">No agents yet. {admin ? "Create one to get started." : "Ask an admin to create one."}</div>}
        {agents.map((a) => (
          <div key={a.id} className="panel" style={{ display: "grid", gap: 10 }}>
            <div className="row between">
              <div><h2>{a.name}</h2>{a.description && <span className="meta">{a.description}</span>}</div>
              <span className="row">{!a.enabled && <Pill cls="mute">Off</Pill>}<Pill cls={a.approval_mode === "none" ? "warn" : "info"}>{APPROVAL_LABEL[a.approval_mode]}</Pill>{admin && <button className="btn sm" onClick={() => edit(a)}>Edit</button>}</span>
            </div>
            <div className="chips">{a.tools.map((t) => <span key={t} className={`chip ${tools.find((x) => x.name === t)?.write ? "write" : ""}`}>{t}</span>)}</div>
            {a.enabled && (
              <div className="row">
                <input id={`goal-${a.id}`} value={goals[a.id] || ""} onChange={(e) => setGoals({ ...goals, [a.id]: e.target.value })} placeholder="Goal, e.g. Find unassigned P2 tickets older than 2 days and add a note with relevant docs" style={{ flex: "1 1 280px" }}
                  onKeyDown={(e) => { if (e.key === "Enter") run(a); }} />
                <button className="btn pri" disabled={planning === a.id} onClick={() => run(a)}>{planning === a.id ? "Planning…" : "Plan and run"}</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
