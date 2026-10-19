import httpx

from tests.conftest import add_member


class FakeResp:
    def __init__(self, code=200, text="ok"):
        self.status_code, self.text = code, text


def test_integration_secrets_are_hidden_and_send_works(owner, monkeypatch):
    sent = []
    monkeypatch.setattr("app.integrations.httpx.post", lambda url, json, headers, timeout: sent.append((url, json, headers)) or FakeResp())
    r = owner.post("/api/integrations", json={"kind": "slack", "name": "it-alerts", "url": "https://hooks.slack.com/services/T000/B000/SECRETxyz"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "SECRET" not in str(body) and body["secret_hint"].startswith("hooks.slack.com/")
    assert owner.post(f"/api/integrations/{body['id']}/test").json()["ok"] is True
    assert sent[0][0].endswith("SECRETxyz") and "Test message" in sent[0][1]["text"]

    # Editing without a URL keeps the stored secret.
    assert owner.put(f"/api/integrations/{body['id']}", json={"kind": "slack", "name": "it-alerts", "url": ""}).status_code == 200

    wf = owner.post("/api/workflows", json={"name": "post", "approval_mode": "none", "steps": [
        {"tool": "memory.list", "args": {}},
        {"tool": "integration.send", "args": {"integration": "it-alerts", "text": "Memory:\n{{step 1}}"}},
    ]}).json()
    n = owner.post(f"/api/workflows/{wf['id']}/run").json()["number"]
    assert owner.get(f"/api/runs/{n}").json()["status"] == "completed"
    assert sent[-1][1]["text"].startswith("Memory:") and sent[-1][0].endswith("SECRETxyz")


def test_integration_failure_is_reported(owner, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr("app.integrations.httpx.post", boom)
    i = owner.post("/api/integrations", json={"kind": "webhook", "name": "hook", "url": "https://example.com/in", "auth_header_name": "X-Token", "auth_header_value": "abc"}).json()
    r = owner.post(f"/api/integrations/{i['id']}/test").json()
    assert r["ok"] is False and "connect" in r["message"].lower()
    assert owner.get("/api/integrations").json()[0]["last_ok"] is False


def test_integration_permissions_and_validation(owner):
    tech = add_member(owner, "tech@example.com", "technician")
    assert tech.post("/api/integrations", json={"kind": "slack", "name": "x", "url": "https://hooks.slack.com/x"}).status_code == 403
    assert owner.post("/api/integrations", json={"kind": "slack", "name": "x", "url": "ftp://nope"}).status_code == 422
    assert owner.post("/api/integrations", json={"kind": "carrier-pigeon", "name": "x", "url": "https://a.b"}).status_code == 422


def test_ticket_notifications(owner):
    staff = add_member(owner, "staff@example.com", "member")
    tech = add_member(owner, "tech@example.com", "technician")
    staff.post("/api/tickets", json={"title": "Printer offline", "priority": "P3"})
    assert any(n["kind"] == "ticket.new" for n in tech.get("/api/notifications").json()["items"])
    tech.post("/api/tickets/1001/comments", json={"body": "On my way"})
    tech.post("/api/tickets/1001/comments", json={"body": "secret note", "internal": True})
    items = staff.get("/api/notifications").json()
    assert items["unread"] == 1 and items["items"][0]["link"] == "/tickets/1001"
    assert staff.post("/api/notifications/read-all").status_code == 200
    assert staff.get("/api/notifications/count").json()["unread"] == 0
