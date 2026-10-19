import io

from app.rag import chunk_pages, to_or_query

RUNBOOK = b"""# Backup and Restore Runbook

Database and uploaded-file backups run nightly at 02:00. Each archive has a SHA-256 checksum.

Never restore straight to production. Restore to the isolated restore-test instance first,
run the health checks, and get sign-off before a production restore.
"""

VPN = b"""VPN guide

If the VPN connects but internal sites do not load, set the DNS server to 10.20.0.53 and restart the tunnel.
"""


def _upload(api, name, data):
    return api.post("/api/documents", files={"file": (name, io.BytesIO(data), "text/plain")})


def test_upload_index_search_and_isolation(owner):
    r = _upload(owner, "Backup-Runbook.md", RUNBOOK)
    assert r.status_code == 201, r.text
    _upload(owner, "VPN.txt", VPN)
    docs = owner.get("/api/documents").json()
    assert {d["status"] for d in docs} == {"indexed"}  # background task runs inside TestClient

    hits = owner.get("/api/documents/search", params={"q": "how do I restore production?"}).json()
    assert hits and hits[0]["filename"] == "Backup-Runbook.md"
    hits = owner.get("/api/documents/search", params={"q": "intranet DNS vpn"}).json()
    assert hits[0]["filename"] == "VPN.txt"

    assert _upload(owner, "copy.md", RUNBOOK).status_code == 409
    assert _upload(owner, "virus.exe", b"MZ").status_code == 415

    other = owner.c.post("/api/orgs", json={"name": "Other Org"}).json()
    other_id = next(o["id"] for o in other["organizations"] if o["name"] == "Other Org")
    from tests.conftest import Api

    assert Api(owner.c, other_id).get("/api/documents/search", params={"q": "restore production"}).json() == []


def test_chat_without_model_returns_sources(owner):
    _upload(owner, "VPN.txt", VPN)
    conv = owner.post("/api/chat/conversations", json={}).json()
    r = owner.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "VPN works but intranet doesn't load"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "10.20.0.53" in body["assistant_message"]["content"]
    assert body["assistant_message"]["citations"][0]["filename"] == "VPN.txt"
    assert body["conversation"]["title"].startswith("VPN works")
    assert len(owner.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]) == 2


def test_chat_with_model_uses_prompt_and_citations(owner, monkeypatch):
    _upload(owner, "VPN.txt", VPN)
    owner.post("/api/memory", json={"title": "Escalation", "content": "Page J. Moreno for P1 incidents"})
    seen = {}

    from app.ai.provider import Completion

    def fake_complete(system, messages):
        seen["system"], seen["messages"] = system, messages
        return Completion(text="Set DNS to 10.20.0.53 [1].", model="fake-model", tokens_in=100, tokens_out=12)

    monkeypatch.setattr("app.routers.chat.provider_name", lambda: "openai")
    monkeypatch.setattr("app.routers.chat.complete", fake_complete)
    conv = owner.post("/api/chat/conversations", json={}).json()
    body = owner.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "intranet won't load on VPN"}).json()
    assert "Page J. Moreno" in seen["system"] and "[1] VPN.txt" in seen["system"]
    assert body["assistant_message"]["model"] == "fake-model"
    assert [c["n"] for c in body["assistant_message"]["citations"]] == [1]
    assert owner.get("/api/orgs/current/usage").json()["ai_tokens_30d"] == 112


def test_chat_is_private_to_author(owner):
    from tests.conftest import add_member

    conv = owner.post("/api/chat/conversations", json={}).json()
    tech = add_member(owner, "tech@example.com", "technician")
    assert tech.get(f"/api/chat/conversations/{conv['id']}").status_code == 404


def test_chunking_and_query_sanitizing():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(20))
    chunks = chunk_pages([(3, text)])
    assert len(chunks) > 3 and all(len(c) <= 1400 for _, c in chunks) and all(p == 3 for p, _ in chunks)
    assert to_or_query("what's DNS & VPN?! ':*") == "what | dns | vpn"
    assert to_or_query("!!!") is None
