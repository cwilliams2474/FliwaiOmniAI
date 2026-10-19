from tests.conftest import add_member


def test_ticket_lifecycle_and_visibility(owner):
    tech = add_member(owner, "tech@example.com", "technician")
    staff = add_member(owner, "staff@example.com", "member")
    t = staff.post("/api/tickets", json={"title": "VPN connects but intranet won't load", "priority": "P2"}).json()
    assert t["key"] == "IT-1001"
    other = owner.post("/api/tickets", json={"title": "Owner's own ticket"}).json()

    # Members only see their own tickets.
    assert [x["key"] for x in staff.get("/api/tickets").json()["items"]] == ["IT-1001"]
    assert staff.get(f"/api/tickets/{other['number']}").status_code == 404

    tech_id = next(m["user_id"] for m in owner.get("/api/orgs/current/members").json() if m["email"] == "tech@example.com")
    assert staff.patch("/api/tickets/1001", json={"assignee_id": tech_id}).status_code == 403
    r = tech.patch("/api/tickets/1001", json={"assignee_id": tech_id, "status": "in_progress"})
    assert r.status_code == 200 and r.json()["assignee"]["email"] == "tech@example.com"

    tech.post("/api/tickets/1001/comments", json={"body": "Checking DNS on the tunnel", "internal": True})
    tech.post("/api/tickets/1001/comments", json={"body": "Set DNS to 10.20.0.53 and reconnect, please."})
    assert len(staff.get("/api/tickets/1001").json()["comments"]) == 1
    assert len(tech.get("/api/tickets/1001").json()["comments"]) == 2
    assert staff.post("/api/tickets/1001/comments", json={"body": "x", "internal": True}).status_code == 403

    r = tech.patch("/api/tickets/1001", json={"status": "resolved"})
    assert r.json()["resolved_at"] is not None
    assert tech.get("/api/tickets", params={"q": "IT-1001"}).json()["total"] == 1
    assert tech.get("/api/tickets", params={"status": ["open", "in_progress"]}).json()["total"] == 1


def test_assets(owner):
    a = owner.post("/api/assets", json={"name": "omni-prod-01", "asset_type": "Server", "os": "Ubuntu 24.04", "warranty_end": "2026-11-01", "status": "in_service"})
    assert a.status_code == 201, a.text
    a = a.json()
    assert a["tag"] == "SER-0001"
    assert owner.post("/api/assets", json={"tag": "SER-0001", "name": "dup", "asset_type": "Server"}).status_code == 409
    r = owner.patch(f"/api/assets/{a['id']}", json={"location": "Rack A2"})
    assert r.json()["location"] == "Rack A2"
    owner.post("/api/tickets", json={"title": "Disk alert on prod", "asset_id": a["id"]})
    assert owner.get("/api/assets").json()["items"][0]["open_tickets"] == 1
    staff = add_member(owner, "staff@example.com", "member")
    assert staff.get("/api/assets").status_code == 403


def test_memory_crud(owner):
    m = owner.post("/api/memory", json={"title": "Maintenance window", "content": "Sundays 01:00-04:00 Eastern"}).json()
    owner.put(f"/api/memory/{m['id']}", json={"title": "Maintenance window", "content": "Sundays 02:00-05:00 Eastern"})
    assert owner.get("/api/memory").json()[0]["content"].startswith("Sundays 02:00")
    assert owner.delete(f"/api/memory/{m['id']}").status_code == 200
    assert owner.get("/api/memory").json() == []


def test_usage_and_health(owner):
    assert owner.get("/api/orgs/current/usage").json()["members"] == 1
    h = owner.c.get("/api/health").json()
    assert h["checks"]["database"]["ok"] and h["checks"]["database"]["migration"] == "0002"
