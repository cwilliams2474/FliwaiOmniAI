"""Tests run against a real PostgreSQL database (full-text search and enums are Postgres features).

    export TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/omniai_test
    pytest -q
"""

import os
import tempfile

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/omniai_test")
os.environ.update(
    DATABASE_URL=TEST_DB,
    ENVIRONMENT="test",
    SECRET_KEY="test-secret-key-that-is-long-enough-1234567890",
    COOKIE_SECURE="false",
    AI_PROVIDER="none",
    UPLOAD_DIR=tempfile.mkdtemp(prefix="omni-uploads-"),
    LOGIN_MAX_ATTEMPTS="5",
    SCHEDULER_ENABLED="false",
    ENCRYPTION_KEY="",
)

import pyotp  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.auth import login_limiter  # noqa: E402

PASSWORD = "Correct-Horse-42"
HERE = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session", autouse=True)
def schema():
    with get_engine().begin() as c:
        c.execute(text("drop schema public cascade"))
        c.execute(text("create schema public"))
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean():
    yield
    with get_engine().begin() as c:
        tables = c.execute(text("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'")).scalars().all()
        c.execute(text("truncate " + ", ".join(tables) + " restart identity cascade"))
    login_limiter._hits.clear()


def new_client() -> TestClient:
    return TestClient(app)


class Api:
    """Signed-in client bound to an organization."""

    def __init__(self, client: TestClient, org_id: str):
        self.c = client
        self.org_id = org_id

    def _h(self):
        return {"X-Org-Id": self.org_id}

    def get(self, url, **kw):
        return self.c.get(url, headers=self._h(), **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self._h(), **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self._h(), **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self._h(), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h(), **kw)


@pytest.fixture
def owner() -> Api:
    c = new_client()
    r = c.post("/api/auth/setup", json={"org_name": "FLIWAI Internal", "name": "C. Williams", "email": "owner@example.com", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return Api(c, r.json()["organizations"][0]["id"])


def add_member(owner: Api, email: str, role: str) -> Api:
    r = owner.post("/api/orgs/current/members", json={"email": email, "name": email.split("@")[0], "role": role})
    assert r.status_code == 200, r.text
    temp = r.json()["temporary_password"]
    c = new_client()
    r = c.post("/api/auth/login", json={"email": email, "password": temp})
    assert r.status_code == 200, r.text
    return Api(c, owner.org_id)


def totp_now(secret: str) -> str:
    return pyotp.TOTP(secret).now()
