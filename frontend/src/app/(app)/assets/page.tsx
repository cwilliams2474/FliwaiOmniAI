"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { ASSET_STATUS, Asset, Member } from "@/lib/types";

const TYPES = ["Laptop", "Desktop", "Server", "Network", "Storage", "Printer", "Phone", "Tablet", "Display", "Other"];
type Form = { tag: string; name: string; asset_type: string; os: string; location: string; status: Asset["status"]; serial_number: string; warranty_end: string; assigned_to_id: string; notes: string };
const EMPTY: Form = { tag: "", name: "", asset_type: "Laptop", os: "", location: "", status: "in_stock", serial_number: "", warranty_end: "", assigned_to_id: "", notes: "" };

export default function AssetsPage() {
  const { can, org, toast } = useSession();
  const [items, setItems] = useState<Asset[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [q, setQ] = useState("");
  const [expiring, setExpiring] = useState(false);
  const [form, setForm] = useState<Form | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tech = can("technician");

  const load = useCallback(() => api<{ items: Asset[] }>("/assets", { query: { q, expiring, limit: 500 } }).then((r) => setItems(r.items)).catch((e) => setError(e.message)), [q, expiring]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);
  useEffect(() => { api<Member[]>("/orgs/current/members").then(setMembers).catch(() => {}); }, []);

  if (org.role === "member") return <PageHead title="Assets" sub="Asset records are visible to IT staff only." />;

  function open(a: Asset | null) {
    setError(null);
    setConfirmDel(false);
    setEditId(a?.id || null);
    setForm(a ? { tag: a.tag, name: a.name, asset_type: a.asset_type, os: a.os, location: a.location, status: a.status, serial_number: a.serial_number, warranty_end: a.warranty_end || "", assigned_to_id: a.assigned_to?.id || "", notes: a.notes } : { ...EMPTY });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    const body: Record<string, unknown> = { ...form, warranty_end: form.warranty_end || null, assigned_to_id: form.assigned_to_id || null };
    try {
      if (editId) {
        if (!form.assigned_to_id) { delete body.assigned_to_id; body.unassign = true; }
        await api(`/assets/${editId}`, { method: "PATCH", body });
        toast(`${form.tag} saved`);
      } else {
        const a = await api<Asset>("/assets", { body });
        toast(`${a.tag} added`);
      }
      setForm(null);
      load();
    } catch (err: any) { setError(err.message); }
  }

  async function remove() {
    if (!editId) return;
    try { await api(`/assets/${editId}`, { method: "DELETE" }); toast("Asset deleted"); setForm(null); load(); } catch (e: any) { setError(e.message); }
  }

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm({ ...form!, [k]: e.target.value });

  return (
    <>
      <PageHead title="Assets" sub={`Hardware and systems owned by ${org.name}.`}>{tech && <button className="btn pri" onClick={() => open(null)}>Add asset</button>}</PageHead>
      <ErrorNote error={error} />
      {form && (
        <form className="panel form" onSubmit={save}>
          <h2>{editId ? `Edit ${form.tag}` : "Add asset"}</h2>
          <div className="g3">
            <label>Name<input id="a-name" required value={form.name} onChange={set("name")} placeholder="omni-prod-01" /></label>
            <label>Type<select id="a-type" value={form.asset_type} onChange={set("asset_type")}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
            <label>Tag<input id="a-tag" value={form.tag} onChange={set("tag")} placeholder="Leave blank to generate" /></label>
            <label>Status<select id="a-status" value={form.status} onChange={set("status")}>{Object.entries(ASSET_STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <label>Operating system<input id="a-os" value={form.os} onChange={set("os")} placeholder="Ubuntu 24.04" /></label>
            <label>Location<input id="a-loc" value={form.location} onChange={set("location")} placeholder="Rack A2" /></label>
            <label>Serial number<input id="a-serial" value={form.serial_number} onChange={set("serial_number")} /></label>
            <label>Warranty ends<input id="a-war" type="date" value={form.warranty_end} onChange={set("warranty_end")} /></label>
            <label>Assigned to<select id="a-user" value={form.assigned_to_id} onChange={set("assigned_to_id")}><option value="">Nobody</option>{members.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}</select></label>
          </div>
          <label>Notes<textarea id="a-notes" value={form.notes} onChange={set("notes")} /></label>
          <div className="row">
            <button className="btn pri">{editId ? "Save" : "Add asset"}</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Cancel</button>
            {editId && can("admin") && (confirmDel
              ? <button type="button" className="btn danger" onClick={remove}>Confirm delete</button>
              : <button type="button" className="btn danger" onClick={() => setConfirmDel(true)}>Delete</button>)}
          </div>
        </form>
      )}
      <div className="row">
        <input id="a-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tag, name, serial, location" style={{ flex: "1 1 220px", maxWidth: 360 }} />
        <label className="row" style={{ display: "flex", color: "var(--ink)", fontSize: 13 }}><input type="checkbox" checked={expiring} onChange={(e) => setExpiring(e.target.checked)} style={{ width: "auto" }} />Warranty ends within 60 days</label>
      </div>
      <div className="tw">
        <table>
          <thead><tr><th>Tag</th><th>Name</th><th>Type</th><th>OS</th><th>Assigned to</th><th>Location</th><th>Status</th><th>Warranty</th><th>Tickets</th></tr></thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={9} className="empty">No assets match.</td></tr>}
            {items.map((a) => (
              <tr key={a.id} className={tech ? "click" : ""} onClick={() => tech && open(a)}>
                <td className="mono">{a.tag}</td><td>{a.name}</td><td>{a.asset_type}</td><td>{a.os || "—"}</td>
                <td>{a.assigned_to?.name || "—"}</td><td>{a.location || "—"}</td>
                <td><Pill cls={ASSET_STATUS[a.status][1]}>{ASSET_STATUS[a.status][0]}</Pill></td>
                <td className="mono" style={a.warranty_expiring ? { color: "var(--warn)" } : undefined}>{a.warranty_end || "—"}{a.warranty_expiring ? " ▲" : ""}</td>
                <td className="num">{a.open_tickets || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
