"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, getOrgId, setOrgId } from "./api";
import { Me, OrgM, ROLE_RANK, Role } from "./types";

interface Session {
  me: Me;
  org: OrgM;
  can: (min: Role) => boolean;
  switchOrg: (id: string) => void;
  refresh: () => Promise<void>;
  toast: (msg: string) => void;
}

const Ctx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession must be used inside SessionProvider");
  return s;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [orgId, setOrg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const refresh = useCallback(async () => {
    try {
      const m = await api<Me>("/auth/me");
      setMe(m);
      const saved = getOrgId();
      const pick = m.organizations.find((o) => o.id === saved) || m.organizations[0];
      if (pick) {
        setOrgId(pick.id);
        setOrg(pick.id);
      }
    } catch (e: any) {
      if (e.status === 401) window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      else setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toast = useCallback((m: string) => {
    setMsg(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(null), 2800);
  }, []);

  const org = me?.organizations.find((o) => o.id === orgId);
  const role = org?.role;
  const can = useCallback((min: Role) => !!role && ROLE_RANK[role] >= ROLE_RANK[min], [role]);
  const switchOrg = useCallback((id: string) => { setOrgId(id); setOrg(id); }, []);
  const value = useMemo<Session | null>(() => (me && org ? { me, org, can, switchOrg, refresh, toast } : null), [me, org, can, switchOrg, refresh, toast]);

  if (error) return <div className="auth"><div className="card"><h2>Couldn't load your account</h2><p className="sub">{error}</p><button className="btn" onClick={() => location.reload()}>Try again</button></div></div>;
  if (!me) return <div className="auth"><p className="meta">Loading…</p></div>;
  if (!org || !value) return <div className="auth"><div className="card"><h2>No organization yet</h2><p className="sub">Your account isn't a member of any organization. Ask an administrator to add you.</p></div></div>;

  return (
    <Ctx.Provider value={value}>
      {children}
      {msg && <div className="toast" role="status">{msg}</div>}
    </Ctx.Provider>
  );
}
