"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNote, PageHead } from "@/components/Shell";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Conversation, Message } from "@/lib/types";

export default function ChatPage() {
  const { toast } = useSession();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  const loadList = useCallback(async () => {
    const list = await api<Conversation[]>("/chat/conversations");
    setConvs(list);
    return list;
  }, []);

  useEffect(() => {
    loadList().then((l) => { if (l[0]) setActive(l[0].id); }).catch((e) => setError(e.message));
  }, [loadList]);

  useEffect(() => {
    if (!active) { setMessages([]); return; }
    api<{ messages: Message[] }>(`/chat/conversations/${active}`).then((c) => setMessages(c.messages)).catch((e) => setError(e.message));
  }, [active]);

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [messages, busy]);

  async function newConv() {
    const c = await api<Conversation>("/chat/conversations", { body: {} });
    setConvs([c, ...convs]);
    setActive(c.id);
    return c.id;
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    const id = active || (await newConv());
    setMessages((m) => [...m, { id: "pending", role: "user", content: text, citations: [], model: "", created_at: "" }]);
    setInput("");
    try {
      const r = await api<{ user_message: Message; assistant_message: Message }>(`/chat/conversations/${id}/messages`, { body: { content: text } });
      setMessages((m) => [...m.filter((x) => x.id !== "pending"), r.user_message, r.assistant_message]);
      loadList();
    } catch (err: any) {
      setMessages((m) => m.filter((x) => x.id !== "pending"));
      setInput(text);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    await api(`/chat/conversations/${id}`, { method: "DELETE" });
    const l = await loadList();
    setActive(l[0]?.id || null);
    toast("Conversation deleted");
  }

  return (
    <>
      <PageHead title="AI Chat" sub="Answers come from your organization's documents and memory, with the sources listed. Conversations are private to you.">
        {active && <button className="btn" onClick={() => remove(active).catch((e) => setError(e.message))}>Delete conversation</button>}
      </PageHead>
      <ErrorNote error={error} />
      <div className="split">
        <div className="list">
          <button className="btn pri" onClick={() => newConv().catch((e) => setError(e.message))}>New conversation</button>
          {convs.map((c) => (
            <button key={c.id} className={`item ${c.id === active ? "sel" : ""}`} onClick={() => setActive(c.id)}>
              <b style={{ overflowWrap: "anywhere" }}>{c.title}</b>
              <span className="meta">{new Date(c.updated_at).toLocaleDateString()}</span>
            </button>
          ))}
        </div>
        <div className="chatbox">
          <div className="msgs">
            {messages.length === 0 && <div className="empty">Ask about your systems, policies or procedures. For example: &ldquo;How do we restore from backup?&rdquo;</div>}
            {messages.map((m) => (
              <div key={m.id} className={`msg ${m.role}`}>
                {m.content}
                {m.citations.length > 0 && (
                  <div>{m.citations.map((c) => <span key={c.n} className="cite" title={c.excerpt}>[{c.n}] {c.filename}{c.page ? ` · p.${c.page}` : ""}</span>)}</div>
                )}
              </div>
            ))}
            {busy && <div className="msg assistant meta">Thinking…</div>}
            <div ref={end} />
          </div>
          <form className="composer" onSubmit={send}>
            <input id="chat-input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question" autoComplete="off" maxLength={8000} />
            <button className="btn pri" disabled={busy || !input.trim()}>Send</button>
          </form>
        </div>
      </div>
    </>
  );
}
