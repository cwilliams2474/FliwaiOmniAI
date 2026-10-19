from tests.conftest import Api, add_member


def test_org_isolation(owner):
    r = owner.c.post("/api/orgs", json={"name": "Acme Freight"})
    acme_id = next(o["id"] for o in r.json()["organizations"] if o["name"] == "Acme Freight")
    acme = Api(owner.c, acme_id)

    owner.post("/api/tickets", json={"title": "Internal VPN issue"})
    acme.post("/api/tickets", json={"title": "Acme tablet sync"})
    assert [t["title"] for t in owner.get("/api/tickets").json()["items"]] == ["Internal VPN issue"]
    assert [t["title"] for t in acme.get("/api/tickets").json()["items"]] == ["Acme tablet sync"]

    # A member of FLIWAI can't reach Acme by switching the header.
    tech = add_member(owner, "tech@example.com", "technician")
    assert Api(tech.c, acme_id).get("/api/tickets").status_code == 404
    assert tech.c.get("/api/tickets").status_code == 400  # no org header


def test_roles_and_last_owner(owner):
    admin = add_member(owner, "admin@example.com", "admin")
    members = owner.get("/api/orgs/current/members").json()
    owner_id = next(m["user_id"] for m in members if m["role"] == "owner")
    admin_id = next(m["user_id"] for m in members if m["role"] == "admin")

    # Admin can't touch owners or grant owner.
    assert admin.patch(f"/api/orgs/current/members/{owner_id}", json={"role": "viewer"}).status_code == 403
    assert admin.post("/api/orgs/current/members", json={"email": "x@example.com", "name": "X", "role": "owner"}).status_code == 403
    # Owner can't demote the last owner.
    assert owner.patch(f"/api/orgs/current/members/{owner_id}", json={"role": "admin"}).status_code == 409
    # Promote admin to owner, then the first owner may step down.
    assert owner.patch(f"/api/orgs/current/members/{admin_id}", json={"role": "owner"}).status_code == 200
    assert owner.patch(f"/api/orgs/current/members/{owner_id}", json={"role": "admin"}).status_code == 200


def test_viewer_cannot_change_things(owner):
    v = add_member(owner, "viewer@example.com", "viewer")
    assert v.post("/api/tickets", json={"title": "Should fail"}).status_code == 403
    assert v.post("/api/assets", json={"name": "Laptop", "asset_type": "Laptop"}).status_code == 403
    assert v.get("/api/orgs/current/audit").status_code == 403


def test_audit_records_actions(owner):
    owner.post("/api/tickets", json={"title": "Printer jam on floor 2"})
    items = owner.get("/api/orgs/current/audit").json()["items"]
    actions = [i["action"] for i in items]
    assert "ticket.created" in actions and "setup.completed" in actions


def test_admin_resets_member_mfa(owner):
    m = add_member(owner, "staff@example.com", "member")
    secret = m.c.post("/api/auth/mfa/setup").json()["secret"]
    from tests.conftest import totp_now

    m.c.post("/api/auth/mfa/enable", json={"code": totp_now(secret)})
    uid = next(x["user_id"] for x in owner.get("/api/orgs/current/members").json() if x["email"] == "staff@example.com")
    assert owner.post(f"/api/orgs/current/members/{uid}/reset-mfa").status_code == 200
    assert next(x for x in owner.get("/api/orgs/current/members").json() if x["user_id"] == uid)["mfa_enabled"] is False
