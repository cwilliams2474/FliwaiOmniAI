from tests.conftest import PASSWORD, add_member, new_client, totp_now


def test_first_run_setup_only_once(owner):
    c = new_client()
    assert c.get("/api/auth/status").json()["needs_setup"] is False
    r = c.post("/api/auth/setup", json={"org_name": "Second Org", "name": "Y", "email": "y@example.com", "password": PASSWORD})
    assert r.status_code == 409


def test_setup_rejects_weak_password():
    c = new_client()
    assert c.get("/api/auth/status").json()["needs_setup"] is True
    r = c.post("/api/auth/setup", json={"org_name": "Org", "name": "A", "email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_login_logout_and_session_revocation(owner):
    c = new_client()
    assert c.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong-Password-1"}).status_code == 401
    r = c.post("/api/auth/login", json={"email": "OWNER@example.com", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["me"]["email"] == "owner@example.com"
    assert c.get("/api/auth/me").status_code == 200

    # Owner's first client revokes the second session.
    sessions = owner.c.get("/api/auth/sessions").json()
    other = next(s for s in sessions if not s["current"])
    assert owner.c.delete(f"/api/auth/sessions/{other['id']}").status_code == 200
    assert c.get("/api/auth/me").status_code == 401

    assert owner.c.post("/api/auth/logout").status_code == 200
    assert owner.c.get("/api/auth/me").status_code == 401


def test_login_rate_limit(owner):
    c = new_client()
    for _ in range(5):
        c.post("/api/auth/login", json={"email": "owner@example.com", "password": "Wrong-password-1"})
    r = c.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert r.status_code == 429


def test_mfa_enroll_login_and_recovery_code(owner):
    setup = owner.c.post("/api/auth/mfa/setup").json()
    assert setup["qr_svg_data_uri"].startswith("data:image/svg+xml")
    assert owner.c.post("/api/auth/mfa/enable", json={"code": "000000"}).status_code == 400
    r = owner.c.post("/api/auth/mfa/enable", json={"code": totp_now(setup["secret"])})
    assert r.status_code == 200
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10

    c = new_client()
    step = c.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).json()
    assert step["mfa_required"] and step["me"] is None
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/mfa/verify", json={"mfa_token": step["mfa_token"], "code": "123456"}).status_code == 401
    assert c.post("/api/auth/mfa/verify", json={"mfa_token": step["mfa_token"], "code": totp_now(setup["secret"])}).status_code == 200

    # A recovery code works once.
    c2 = new_client()
    step = c2.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).json()
    assert c2.post("/api/auth/mfa/verify", json={"mfa_token": step["mfa_token"], "code": codes[0]}).status_code == 200
    c3 = new_client()
    step = c3.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).json()
    assert c3.post("/api/auth/mfa/verify", json={"mfa_token": step["mfa_token"], "code": codes[0]}).status_code == 401


def test_password_change_signs_out_other_sessions(owner):
    c = new_client()
    c.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    r = owner.c.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "Another-Strong-77"})
    assert r.status_code == 200
    assert owner.c.get("/api/auth/me").status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_password_reset_flow(owner, monkeypatch, caplog):
    sent = {}
    monkeypatch.setattr("app.routers.auth.send_mail", lambda to, subject, body: sent.update(to=to, body=body) or True)
    c = new_client()
    assert c.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"}).status_code == 200
    assert not sent
    c.post("/api/auth/password-reset/request", json={"email": "owner@example.com"})
    token = sent["body"].split("token=")[1].split()[0]
    assert c.post("/api/auth/password-reset/confirm", json={"token": token, "new_password": "Reset-Password-99"}).status_code == 200
    assert c.post("/api/auth/password-reset/confirm", json={"token": token, "new_password": "Reset-Password-98"}).status_code == 400
    assert c.post("/api/auth/login", json={"email": "owner@example.com", "password": "Reset-Password-99"}).status_code == 200


def test_invited_member_must_change_password(owner):
    m = add_member(owner, "tech@example.com", "technician")
    me = m.c.get("/api/auth/me").json()
    assert me["must_change_password"] is True
    assert me["organizations"][0]["role"] == "technician"
