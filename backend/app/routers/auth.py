import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import security as sec
from app.audit import record
from app.config import get_settings
from app.db import get_db
from app.deps import COOKIE_NAME, client_ip, get_current_user
from app.mailer import send_mail
from app.models import AuthSession, Membership, Organization, PasswordReset, Role, User
from app.ratelimit import SlidingWindow
from app.schemas import MeOut, Ok, iso, me_out

router = APIRouter(prefix="/auth", tags=["auth"])
_settings = get_settings()
login_limiter = SlidingWindow(_settings.login_max_attempts, _settings.login_window_seconds)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "org")[:60]


def unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while db.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def _check_password(pw: str) -> None:
    problems = sec.password_problems(pw)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, " ".join(problems))


def _start_session(db: Session, user: User, request: Request, response: Response) -> None:
    s = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(hours=s.session_hours)
    sess = AuthSession(
        user_id=user.id,
        expires_at=expires,
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400],
    )
    db.add(sess)
    user.last_login_at = datetime.now(timezone.utc)
    db.flush()
    token = sec.make_session_token(str(sess.id), str(user.id), expires)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        max_age=s.session_hours * 3600,
        path="/",
    )


# ---------- first-run setup ----------
class StatusOut(BaseModel):
    needs_setup: bool
    app_name: str
    ai_provider: str


@router.get("/status", response_model=StatusOut)
def auth_status(db: Session = Depends(get_db)):
    s = get_settings()
    return StatusOut(needs_setup=(db.scalar(select(func.count(User.id))) or 0) == 0, app_name=s.app_name, ai_provider=s.ai_provider)


class SetupIn(BaseModel):
    org_name: str = Field(min_length=2, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(max_length=200)


@router.post("/setup", response_model=MeOut)
def first_setup(body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    # Serialize concurrent setup attempts, then make sure nobody has set up yet.
    db.execute(select(func.pg_advisory_xact_lock(424242)))
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup is already complete. Sign in instead.")
    _check_password(body.password)
    user = User(email=body.email.lower(), name=body.name.strip(), password_hash=sec.hash_password(body.password), is_superuser=True)
    org = Organization(name=body.org_name.strip(), slug=unique_slug(db, body.org_name))
    db.add_all([user, org])
    db.flush()
    db.add(Membership(user_id=user.id, org_id=org.id, role=Role.owner))
    record(db, "setup.completed", org.name, user=user, org_id=org.id, request=request)
    _start_session(db, user, request, response)
    db.commit()
    db.refresh(user)
    return me_out(user)


# ---------- sign in ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class LoginOut(BaseModel):
    mfa_required: bool = False
    mfa_token: str | None = None
    me: MeOut | None = None


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    key = f"{client_ip(request)}|{email}"
    wait = login_limiter.blocked(key)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many attempts. Try again in {wait} seconds.")
    user = db.scalar(select(User).where(User.email == email))
    ok = sec.verify_password(body.password, user.password_hash if user else sec.DUMMY_HASH)
    if not user or not ok or not user.is_active:
        login_limiter.hit(key)
        record(db, "auth.login_failed", email, actor=email, request=request, commit=True)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")
    login_limiter.reset(key)
    if user.mfa_enabled:
        return LoginOut(mfa_required=True, mfa_token=sec.make_mfa_token(str(user.id)))
    _start_session(db, user, request, response)
    record(db, "auth.login", "password", user=user, request=request)
    db.commit()
    return LoginOut(me=me_out(user))


class MfaVerifyIn(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=20)


@router.post("/mfa/verify", response_model=LoginOut)
def mfa_verify(body: MfaVerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    data = sec.decode_token(body.mfa_token, "mfa")
    if not data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The sign-in step expired. Enter your password again.")
    user = db.get(User, uuid.UUID(data["uid"]))
    if not user or not user.is_active or not user.mfa_enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in again.")
    key = f"mfa|{user.id}"
    wait = login_limiter.blocked(key)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many codes tried. Wait {wait} seconds.")
    secret = sec.decrypt(user.mfa_secret_enc or "")
    method = "totp"
    if not (secret and sec.verify_totp(secret, body.code)):
        remaining = sec.use_recovery_code(user.recovery_codes or [], body.code)
        if remaining is None:
            login_limiter.hit(key)
            record(db, "auth.mfa_failed", user.email, user=user, request=request, commit=True)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code didn't match. Check your authenticator app's clock and try again.")
        user.recovery_codes = remaining
        method = "recovery_code"
    login_limiter.reset(key)
    _start_session(db, user, request, response)
    record(db, "auth.login", method, user=user, request=request, detail={"mfa": True})
    db.commit()
    return LoginOut(me=me_out(user))


@router.post("/logout", response_model=Ok)
def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sess = db.get(AuthSession, request.state.session_id)
    if sess:
        sess.revoked_at = datetime.now(timezone.utc)
    record(db, "auth.logout", "", user=user, request=request)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return Ok()


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return me_out(user)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.patch("/me", response_model=MeOut)
def update_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.name = body.name.strip()
    db.commit()
    return me_out(user)


# ---------- password ----------
class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=200)


@router.post("/password", response_model=Ok)
def change_password(body: PasswordIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not sec.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    _check_password(body.new_password)
    user.password_hash = sec.hash_password(body.new_password)
    user.must_change_password = False
    # Sign out every other session.
    now = datetime.now(timezone.utc)
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))):
        if s.id != request.state.session_id:
            s.revoked_at = now
    record(db, "auth.password_changed", user.email, user=user, request=request)
    db.commit()
    return Ok()


class ResetRequestIn(BaseModel):
    email: EmailStr


@router.post("/password-reset/request", response_model=Ok)
def reset_request(body: ResetRequestIn, request: Request, db: Session = Depends(get_db)):
    key = f"reset|{client_ip(request)}"
    if login_limiter.blocked(key):
        return Ok()  # Same response either way; don't reveal anything.
    login_limiter.hit(key)
    user = db.scalar(select(User).where(User.email == body.email.lower(), User.is_active.is_(True)))
    if user:
        token = sec.new_url_token()
        db.add(PasswordReset(user_id=user.id, token_hash=sec.sha256_hex(token), expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        record(db, "auth.password_reset_requested", user.email, user=user, request=request)
        db.commit()
        link = f"{get_settings().public_url.rstrip('/')}/reset-password?token={token}"
        send_mail(user.email, f"Reset your {get_settings().app_name} password", f"Use this link within one hour to choose a new password:\n\n{link}\n\nIf you didn't ask for this, ignore this email.")
    return Ok()


class ResetConfirmIn(BaseModel):
    token: str
    new_password: str = Field(max_length=200)


@router.post("/password-reset/confirm", response_model=Ok)
def reset_confirm(body: ResetConfirmIn, request: Request, db: Session = Depends(get_db)):
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == sec.sha256_hex(body.token)))
    now = datetime.now(timezone.utc)
    if not pr or pr.used_at or pr.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired. Request a new one.")
    _check_password(body.new_password)
    user = db.get(User, pr.user_id)
    user.password_hash = sec.hash_password(body.new_password)
    user.must_change_password = False
    pr.used_at = now
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))):
        s.revoked_at = now
    record(db, "auth.password_reset", user.email, user=user, request=request)
    db.commit()
    return Ok()


# ---------- MFA enrolment ----------
class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA is already on. Turn it off first to enroll a new device.")
    secret = sec.new_totp_secret()
    user.mfa_secret_enc = sec.encrypt(secret)
    db.commit()
    uri = sec.totp_uri(secret, user.email)
    return MfaSetupOut(secret=secret, otpauth_uri=uri, qr_svg_data_uri=sec.totp_qr_svg(uri))


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class RecoveryOut(BaseModel):
    recovery_codes: list[str]


@router.post("/mfa/enable", response_model=RecoveryOut)
def mfa_enable(body: CodeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = sec.decrypt(user.mfa_secret_enc or "")
    if not secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start MFA setup first.")
    if not sec.verify_totp(secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code didn't match. Enter the current 6-digit code from your app.")
    plain, hashes = sec.new_recovery_codes()
    user.mfa_enabled = True
    user.recovery_codes = hashes
    record(db, "auth.mfa_enabled", user.email, user=user, request=request)
    db.commit()
    return RecoveryOut(recovery_codes=plain)


class MfaDisableIn(BaseModel):
    password: str
    code: str = Field(min_length=6, max_length=20)


@router.post("/mfa/disable", response_model=Ok)
def mfa_disable(body: MfaDisableIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = sec.decrypt(user.mfa_secret_enc or "")
    if not sec.verify_password(body.password, user.password_hash) or not (secret and sec.verify_totp(secret, body.code)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password or code is incorrect.")
    user.mfa_enabled = False
    user.mfa_secret_enc = None
    user.recovery_codes = []
    record(db, "auth.mfa_disabled", user.email, user=user, request=request)
    db.commit()
    return Ok()


# ---------- own sessions ----------
class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: str
    last_seen_at: str
    ip: str | None
    user_agent: str | None
    current: bool


@router.get("/sessions", response_model=list[SessionOut])
def my_sessions(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
        .order_by(AuthSession.last_seen_at.desc())
    )
    return [
        SessionOut(id=s.id, created_at=iso(s.created_at), last_seen_at=iso(s.last_seen_at), ip=s.ip, user_agent=s.user_agent, current=s.id == request.state.session_id)
        for s in rows
    ]


@router.delete("/sessions/{session_id}", response_model=Ok)
def revoke_my_session(session_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(AuthSession, session_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    s.revoked_at = datetime.now(timezone.utc)
    record(db, "auth.session_revoked", str(session_id), user=user, request=request)
    db.commit()
    return Ok()
