"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHead, Pill } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Member, ROLES, Role } from "@/lib/types";

const ROLE_HELP: Record<Role, string> = {
  owner: "Everything, including other owners",
  admin: "Members, settings, audit log",
  technician: "Works tickets, assets, documents, memory",
  member: "Raises tickets, uses AI chat",
  viewer: "Read-only access to everything",
};

export default function MembersPage() {
  const { me, org, can, toast, refresh } = useSession();
  const [list, setList] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [invite, setInvite] = useState({ email: "", name: "", role: "member" as Role });
  const [created, setCreated] = useState<{ email: string; temp: string; emailed: boolean } | null>(null);
  const [confirm, setConfirm] = useState<{ id: string; action: "remove" | "mfa" | "signout" } | null>(null);
  const [orgName, setOrgName] = useState("");

  const load = useCallback(() => api<Member[]>("/orgs/current/members").then(setList).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  if (!can("admin")) return <PageHead title="Members" sub="Only admins and owners can manage members." />;
  const roles = ROLES.filter((r) => r !== "owner" || org.role === "owner");

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api<{ temporary_password: string | null; emailed: boolean }>("/orgs/current/members", { body: invite });
      if (r.temporary_password) setCreated({ email: invite.email, temp: r.temporary_password, emailed: r.emailed });
      else toast(`${invite.email} added`);
      setInvite({ email: "", name: "", role: "member" });
      load();
    } catch (err: any) { setError(err.message); }
  }

  async function act(fn: () => Promise<unknown>, msg: string) {
    setError(null);
    try { await fn(); toast(msg); setConfirm(null); load(); } catch (e: any) { setError(e.message); }
  }

  return (
    <>
      <PageHead title="Members" sub={`People with access to ${org.name} and what they can do.`} />
      <ErrorNote error={error} />
      {created && (
        <div className="note">
          <b>{created.email} was added.</b> {created.emailed ? "Sign-in details were emailed. " : "Email isn't set up, so share these details securely. "}
          Temporary password: <span className="mono" style={{ userSelect: "all" }}>{created.temp}</span>. They'll choose a new password at first sign-in.
          <div><button className="btn sm" style={{ marginTop: 8 }} onClick={() => setCreated(null)}>Done</button></div>
        </div>
      )}
      <div className="tw">
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>MFA</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {list.map((m) => {
              const self = m.user_id === me.id;
              const locked = m.role === "owner" && org.role !== "owner";
              const c = confirm?.id === m.user_id ? confirm.action : null;
              return (
                <tr key={m.user_id}>
                  <td>{m.name}{self && <span className="meta"> (you)</span>}</td>
                  <td className="mono">{m.email}</td>
                  <td>
                    <select aria-label={`Role for ${m.name}`} value={m.role} disabled={locked} className="inline"
                      onChange={(e) => act(() => api(`/orgs/current/members/${m.user_id}`, { method: "PATCH", body: { role: e.target.value } }).then(() => { if (self) return refresh(); }), `${m.name} is now ${e.target.value}`)}>
                      {(locked ? ROLES : roles).map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td>{m.mfa_enabled ? <Pill cls="ok">On</Pill> : <Pill cls={["owner", "admin", "technician"].includes(m.role) ? "warn" : "mute"}>Off</Pill>}</td>
                  <td className="meta">{fmtDate(m.last_login_at)}</td>
                  <td>
                    {!self && !locked && (
                      c ? (
                        <span className="row">
                          <button className="btn sm danger" onClick={() => act(
                            () => c === "remove" ? api(`/orgs/current/members/${m.user_id}`, { method: "DELETE" })
                              : c === "mfa" ? api(`/orgs/current/members/${m.user_id}/reset-mfa`, { method: "POST" })
                              : api(`/orgs/current/members/${m.user_id}/sign-out`, { method: "POST" }),
                            c === "remove" ? `${m.name} removed` : c === "mfa" ? `MFA reset for ${m.name}` : `${m.name} signed out everywhere`)}>
                            {c === "remove" ? "Confirm remove" : c === "mfa" ? "Confirm MFA reset" : "Confirm sign-out"}
                          </button>
                          <button className="btn sm" onClick={() => setConfirm(null)}>Cancel</button>
                        </span>
                      ) : (
                        <span className="row">
                          <button className="btn sm" onClick={() => setConfirm({ id: m.user_id, action: "signout" })}>Sign out</button>
                          {m.mfa_enabled && <button className="btn sm" onClick={() => setConfirm({ id: m.user_id, action: "mfa" })}>Reset MFA</button>}
                          <button className="btn sm danger" onClick={() => setConfirm({ id: m.user_id, action: "remove" })}>Remove</button>
                        </span>
                      )
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="g2">
        <form className="panel form" onSubmit={add}>
          <h2>Add a member</h2>
          <label>Email<input id="inv-email" type="email" required value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} /></label>
          <label>Name<input id="inv-name" required value={invite.name} onChange={(e) => setInvite({ ...invite, name: e.target.value })} /></label>
          <label>Role<select id="inv-role" value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value as Role })}>{roles.map((r) => <option key={r} value={r}>{r} · {ROLE_HELP[r]}</option>)}</select></label>
          <div><button className="btn pri">Add member</button></div>
        </form>
        <div className="list">
          <form className="panel form" onSubmit={(e) => { e.preventDefault(); act(() => api("/orgs/current", { method: "PATCH", body: { name: orgName } }).then(refresh), "Organization renamed"); }}>
            <h2>Organization</h2>
            <label>Name<input id="org-name" required minLength={2} value={orgName || org.name} onChange={(e) => setOrgName(e.target.value)} /></label>
            <div><button className="btn">Rename</button></div>
          </form>
          {me.is_superuser && (
            <form className="panel form" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); act(() => api("/orgs", { body: { name: f.get("name") } }).then(refresh), "Organization created. Switch to it from the top bar."); e.currentTarget.reset(); }}>
              <h2>New organization</h2>
              <span className="meta">Each organization's tickets, assets, documents and chats are kept separate.</span>
              <label>Name<input id="new-org" name="name" required minLength={2} placeholder="Acme Freight" /></label>
              <div><button className="btn">Create organization</button></div>
            </form>
          )}
        </div>
      </div>
    </>
  );
}
