"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { useTools } from "@/components/useTools";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { APPROVAL_LABEL, ApprovalMode, RunDetail, ToolSpec, Workflow, WorkflowStep } from "@/lib/types";

type Form = { name: string; description: string; steps: WorkflowStep[]; schedule: string; approval_mode: ApprovalMode; enabled: boolean };
const PRESETS: [string, string][] = [["Manual only", ""], ["Weekdays 07:00", "0 7 * * 1-5"], ["Daily 02:00", "0 2 * * *"], ["Every hour", "0 * * * *"], ["Mondays 08:00", "0 8 * * 1"], ["1st of month 08:00", "0 8 1 * *"]];

const TEMPLATES: { label: string; form: Form }[] = [
  {
    label: "Morning P1/P2 digest to Slack",
    form: {
      name: "Morning priority digest", description: "Summarize urgent open tickets and post to the team channel.", schedule: "0 7 * * 1-5", approval_mode: "none", enabled: true,
      steps: [
        { tool: "tickets.search", args: { priority: "P1" } },
        { tool: "tickets.search", args: { priority: "P2" } },
        { tool: "integration.send", args: { integration: "it-alerts", text: "Good morning. Urgent tickets for {{date}}:\n\nP1\n{{step 1}}\n\nP2\n{{step 2}}" } },
      ],
    },
  },
  {
    label: "Warranty check (monthly)",
    form: {
      name: "Warranty check", description: "Open a ticket listing assets whose warranty ends in the next 60 days.", schedule: "0 8 1 * *", approval_mode: "writes", enabled: true,
      steps: [
        { tool: "assets.search", args: { warranty_within_days: 60 } },
        { tool: "tickets.create", args: { title: "Warranties ending soon ({{date}})", description: "{{step 1}}", priority: "P4" } },
      ],
    },
  },
  {
    label: "Stale ticket nudge",
    form: {
      name: "Stale ticket nudge", description: "Tell technicians about active tickets nobody has touched in 3 days.", schedule: "0 9 * * 1-5", approval_mode: "none", enabled: true,
      steps: [
        { tool: "tickets.search", args: { status: "active", older_than_days: 3 } },
        { tool: "notify.team", args: { title: "Tickets untouched for 3+ days", body: "{{step 1}}" } },
      ],
    },
  },
];

function StepEditor({ i, step, tools, onChange, onRemove, onMove, count }: {
  i: number; step: WorkflowStep; tools: ToolSpec[]; count: number;
  onChange: (s: WorkflowStep) => void; onRemove: () => void; onMove: (d: -1 | 1) => void;
}) {
  const spec = tools.find((t) => t.name === step.tool);
  const setArg = (k: string, v: unknown) => {
    const args = { ...step.args };
    if (v === "" || v === undefined) delete args[k];
    else args[k] = v;
    onChange({ ...step, args });
  };
  return (
    <div className="stepedit">
      <div className="row between">
        <b>Step {i + 1}</b>
        <span className="row">
          <button type="button" className="btn sm" disabled={i === 0} onClick={() => onMove(-1)} aria-label="Move up">↑</button>
          <button type="button" className="btn sm" disabled={i === count - 1} onClick={() => onMove(1)} aria-label="Move down">↓</button>
          <button type="button" className="btn sm danger" onClick={onRemove}>Remove</button>
        </span>
      </div>
      <label>Action
        <select value={step.tool} onChange={(e) => onChange({ tool: e.target.value, args: {} })}>
          {tools.map((t) => <option key={t.name} value={t.name}>{t.name}{t.write ? " (changes things)" : ""} · {t.description}</option>)}
        </select>
      </label>
      {spec && Object.entries(spec.params).map(([k, p]) => {
        const v = step.args[k];
        const label = <>{k}{p.required ? " *" : ""} <span style={{ fontWeight: 400 }}>· {p.description}</span></>;
        if (p.type === "boolean") return <label key={k} className="check"><input type="checkbox" checked={!!v} onChange={(e) => setArg(k, e.target.checked || undefined)} />{label}</label>;
        if (p.enum) return <label key={k}>{label}<select value={(v as string) || ""} onChange={(e) => setArg(k, e.target.value)}><option value="">—</option>{p.enum.map((o) => <option key={o}>{o}</option>)}</select></label>;
        if (p.type === "integer") return <label key={k}>{label}<input value={v === undefined ? "" : String(v)} inputMode="numeric" onChange={(e) => setArg(k, e.target.value === "" ? "" : /^\d+$/.test(e.target.value) ? Number(e.target.value) : e.target.value)} /></label>;
        const long = ["body", "text", "description", "instruction"].includes(k);
        return <label key={k}>{label}{long ? <textarea value={(v as string) || ""} onChange={(e) => setArg(k, e.target.value)} /> : <input value={(v as string) || ""} onChange={(e) => setArg(k, e.target.value)} />}</label>;
      })}
      {i > 0 && <span className="meta">Use {"{{step 1}}"} … {`{{step ${i}}}`} to insert an earlier step's result, and {"{{date}}"} for today.</span>}
    </div>
  );
}

export default function WorkflowsPage() {
  const { can, toast } = useSession();
  const router = useRouter();
  const tools = useTools();
  const [list, setList] = useState<Workflow[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const admin = can("admin");

  const load = useCallback(() => api<Workflow[]>("/workflows").then(setList).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  if (!can("technician")) return <PageHead title="Workflows" sub="Automation is available to technicians and admins." />;

  function edit(w: Workflow | null, template?: Form) {
    setError(null);
    setEditId(w?.id || null);
    setForm(w ? { name: w.name, description: w.description, steps: w.steps, schedule: w.schedule, approval_mode: w.approval_mode, enabled: w.enabled }
      : template ? JSON.parse(JSON.stringify(template)) : { name: "", description: "", steps: [{ tool: "tickets.search", args: {} }], schedule: "", approval_mode: "writes", enabled: true });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    try {
      if (editId) await api(`/workflows/${editId}`, { method: "PUT", body: form });
      else await api("/workflows", { body: form });
      toast(`${form.name} saved`);
      setForm(null);
      load();
    } catch (err: any) { setError(err.message); }
  }

  async function remove() {
    if (!editId) return;
    try { await api(`/workflows/${editId}`, { method: "DELETE" }); toast("Workflow deleted"); setForm(null); load(); } catch (e: any) { setError(e.message); }
  }

  async function runNow(w: Workflow) {
    try { const r = await api<RunDetail>(`/workflows/${w.id}/run`, { method: "POST" }); router.push(`/runs/${r.number}`); } catch (e: any) { setError(e.message); }
  }

  const setStep = (i: number, s: WorkflowStep) => form && setForm({ ...form, steps: form.steps.map((x, j) => (j === i ? s : x)) });
  const move = (i: number, d: -1 | 1) => {
    if (!form) return;
    const steps = [...form.steps];
    [steps[i], steps[i + d]] = [steps[i + d], steps[i]];
    setForm({ ...form, steps });
  };

  return (
    <>
      <PageHead title="Workflows" sub="Fixed lists of steps you can run on demand or on a schedule. They need no AI model unless a step uses ai.summarize.">
        {admin && <button className="btn pri" onClick={() => edit(null)}>New workflow</button>}
      </PageHead>
      <ErrorNote error={error} />
      {admin && !form && (
        <div className="row"><span className="meta">Start from a template:</span>{TEMPLATES.map((t) => <button key={t.label} className="btn sm" onClick={() => edit(null, t.form)}>{t.label}</button>)}</div>
      )}

      {form && (
        <form className="panel form" onSubmit={save}>
          <h2>{editId ? `Edit ${form.name}` : "New workflow"}</h2>
          <div className="g2">
            <label>Name<input id="wf-name" required maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label>Approvals<select id="wf-mode" value={form.approval_mode} onChange={(e) => setForm({ ...form, approval_mode: e.target.value as ApprovalMode })}>{Object.entries(APPROVAL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          </div>
          <label>Description<input id="wf-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <div className="g2">
            <label>Schedule (cron: minute hour day month weekday)<input id="wf-cron" value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })} placeholder="Blank = manual only" className="mono" /></label>
            <div style={{ display: "grid", gap: 4, alignContent: "end" }}><span className="meta">Presets</span><div className="row">{PRESETS.map(([l, c]) => <button key={l} type="button" className={`btn sm ${form.schedule === c ? "pri" : ""}`} onClick={() => setForm({ ...form, schedule: c })}>{l}</button>)}</div></div>
          </div>
          {form.approval_mode === "none" && form.steps.some((s) => tools.find((t) => t.name === s.tool)?.write) && (
            <div className="note warn">This workflow changes things or sends messages without anyone approving each run. Make sure that's intended.</div>
          )}
          {form.steps.map((s, i) => (
            <StepEditor key={i} i={i} step={s} tools={tools} count={form.steps.length} onChange={(x) => setStep(i, x)}
              onRemove={() => setForm({ ...form, steps: form.steps.filter((_, j) => j !== i) })} onMove={(d) => move(i, d)} />
          ))}
          <div><button type="button" className="btn" disabled={form.steps.length >= 10} onClick={() => setForm({ ...form, steps: [...form.steps, { tool: "notify.team", args: {} }] })}>Add step</button></div>
          <label className="check"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />Enabled (scheduled runs only happen while enabled)</label>
          <div className="row">
            <button className="btn pri">Save workflow</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Cancel</button>
            {editId && <button type="button" className="btn danger" onClick={remove}>Delete workflow</button>}
          </div>
        </form>
      )}

      <div className="tw">
        <table>
          <thead><tr><th>Workflow</th><th>Steps</th><th>Schedule</th><th>Next run</th><th>Approvals</th><th /></tr></thead>
          <tbody>
            {list.length === 0 && <tr><td colSpan={6} className="empty">No workflows yet.</td></tr>}
            {list.map((w) => (
              <tr key={w.id}>
                <td><b>{w.name}</b>{!w.enabled && <> <Pill cls="mute">Off</Pill></>}{w.description && <div className="meta">{w.description}</div>}</td>
                <td><div className="chips">{w.steps.map((s, i) => <span key={i} className={`chip ${tools.find((t) => t.name === s.tool)?.write ? "write" : ""}`}>{s.tool}</span>)}</div></td>
                <td>{w.schedule_text}{w.schedule && <div className="meta mono">{w.schedule}</div>}</td>
                <td className="meta">{w.next_run_at ? fmtDate(w.next_run_at) : "—"}{w.last_run_at && <div>last {fmtDate(w.last_run_at)}</div>}</td>
                <td className="meta">{APPROVAL_LABEL[w.approval_mode]}</td>
                <td><span className="row"><button className="btn sm pri" onClick={() => runNow(w)}>Run now</button>{admin && <button className="btn sm" onClick={() => edit(w)}>Edit</button>}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
