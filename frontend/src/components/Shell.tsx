"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Role } from "@/lib/types";
import { Logo } from "./Logo";

const NAV: [string, [string, string, Role?][]][] = [
  ["Assist", [["/", "Overview"], ["/chat", "AI Chat"], ["/documents", "Documents"], ["/memory", "Memory"]]],
  ["Operate", [["/tickets", "IT Tickets"], ["/assets", "Assets", "viewer"], ["/notifications", "Notifications"]]],
  ["Automate", [["/runs", "Runs & approvals", "technician"], ["/agents", "AI Agents", "technician"], ["/workflows", "Workflows", "technician"], ["/integrations", "Integrations", "technician"]]],
  ["Administration", [["/admin/members", "Members", "admin"], ["/admin/audit", "Audit log", "admin"], ["/admin/system", "System health", "admin"]]],
];

// Members (requesters and customer users) get the simpler support portal.
const PORTAL_NAV: [string, [string, string, Role?][]][] = [
  ["Support", [["/", "Home"], ["/tickets", "My requests"], ["/chat", "Ask AI"], ["/notifications", "Notifications"]]],
];

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, org, can, switchOrg } = useSession();
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const portal = org.role === "member";

  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    let alive = true;
    const poll = () => api<{ unread: number }>("/notifications/count").then((r) => alive && setUnread(r.unread)).catch(() => {});
    poll();
    const t = setInterval(poll, 30000);
    return () => { alive = false; clearInterval(t); };
  }, [org.id, path]);
  useEffect(() => {
    if (me.must_change_password && path !== "/account") router.replace("/account?first=1");
  }, [me.must_change_password, path, router]);

  const visible = (min?: Role) => (min === "viewer" ? org.role !== "member" : !min || can(min));
  const isActive = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  const initials = me.name.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();

  async function logout() {
    try { await api("/auth/logout", { method: "POST" }); } finally { window.location.href = "/login"; }
  }

  return (
    <div className="app">
      <aside className={`side ${open ? "open" : ""}`} aria-label="Modules">
        <div className="brand"><Logo /><div><b>OmniAI</b><small>{portal ? "Support portal" : "Self-hosted"}</small></div></div>
        {(portal ? PORTAL_NAV : NAV).map(([group, items]) => {
          const shown = items.filter(([, , min]) => visible(min));
          if (!shown.length) return null;
          return (
            <div key={group}>
              <div className="grp">{group}</div>
              <nav className="nav">
                {shown.map(([href, label]) => (
                  <Link key={href} href={href} aria-current={isActive(href) ? "page" : undefined}>{label}</Link>
                ))}
              </nav>
            </div>
          );
        })}
        <div className="grp">You</div>
        <nav className="nav">
          <Link href="/account" aria-current={isActive("/account") ? "page" : undefined}>Account &amp; security</Link>
          <a href="#" onClick={(e) => { e.preventDefault(); logout(); }}>Sign out</a>
        </nav>
      </aside>
      <div className={`scrim ${open ? "open" : ""}`} onClick={() => setOpen(false)} />
      <div style={{ minWidth: 0 }}>
        <header className="topbar">
          <button className="btn menu" onClick={() => setOpen(true)} aria-label="Open menu">☰</button>
          {me.organizations.length > 1 ? (
            <select aria-label="Active organization" value={org.id} onChange={(e) => { switchOrg(e.target.value); router.push("/"); }} style={{ width: "auto", maxWidth: 240 }}>
              {me.organizations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          ) : (
            <b>{org.name}</b>
          )}
          <span className="tag hide-sm">{org.role}</span>
          <div className="sp" />
          <Link href="/notifications" className="btn sm bell" aria-label={`Notifications, ${unread} unread`}>Alerts{unread > 0 && <span className="dot">{unread > 99 ? "99+" : unread}</span>}</Link>
          <div className="row"><div className="av" title={me.email}>{initials}</div><span className="hide-sm">{me.name}</span></div>
        </header>
        <main className="main"><div className="view" key={org.id}>{children}</div></main>
      </div>
    </div>
  );
}

export function PageHead({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div className="ph" style={{ margin: 0 }}>
      <div><h1>{title}</h1>{sub && <p className="sub">{sub}</p>}</div>
      {children && <div className="row">{children}</div>}
    </div>
  );
}

export function Pill({ cls, children }: { cls: string; children: React.ReactNode }) {
  return <span className={`pill ${cls}`}>{children}</span>;
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? <div className="alert" role="alert">{error}</div> : null;
}
