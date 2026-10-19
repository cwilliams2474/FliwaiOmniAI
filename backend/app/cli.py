"""Server-side admin commands for recovery when nobody can sign in.

Run inside the backend container, for example:
    docker compose exec backend python -m app.cli reset-password owner@example.com
    docker compose exec backend python -m app.cli reset-mfa owner@example.com
    docker compose exec backend python -m app.cli list-users
"""

import argparse
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.audit import record
from app.db import SessionLocal
from app.models import AuthSession, User
from app.security import hash_password, password_problems


def _user(db, email: str) -> User:
    u = db.scalar(select(User).where(User.email == email.lower()))
    if not u:
        sys.exit(f"No user with email {email}.")
    return u


def _revoke_all(db, u: User) -> None:
    now = datetime.now(timezone.utc)
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None))):
        s.revoked_at = now


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-users")
    rp = sub.add_parser("reset-password")
    rp.add_argument("email")
    rm = sub.add_parser("reset-mfa")
    rm.add_argument("email")
    su = sub.add_parser("make-superuser")
    su.add_argument("email")
    args = p.parse_args()

    db = SessionLocal()
    try:
        if args.cmd == "list-users":
            for u in db.scalars(select(User).order_by(User.email)):
                flags = ",".join(f for f, on in (("superuser", u.is_superuser), ("mfa", u.mfa_enabled), ("inactive", not u.is_active)) if on)
                print(f"{u.email:40} {u.name:30} {flags}")
            return
        u = _user(db, args.email)
        if args.cmd == "reset-password":
            pw = getpass.getpass("New password: ")
            if pw != getpass.getpass("Repeat: "):
                sys.exit("Passwords don't match.")
            problems = password_problems(pw)
            if problems:
                sys.exit(" ".join(problems))
            u.password_hash = hash_password(pw)
            _revoke_all(db, u)
            record(db, "cli.password_reset", u.email, actor="server-cli")
        elif args.cmd == "reset-mfa":
            u.mfa_enabled, u.mfa_secret_enc, u.recovery_codes = False, None, []
            _revoke_all(db, u)
            record(db, "cli.mfa_reset", u.email, actor="server-cli")
        elif args.cmd == "make-superuser":
            u.is_superuser = True
            record(db, "cli.superuser_granted", u.email, actor="server-cli")
        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
