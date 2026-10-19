"""Password hashing, tokens, MFA and encryption of stored secrets."""

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

log = logging.getLogger("omniai.security")
ALGO = "HS256"


# ---------- passwords ----------
def _prehash(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes; pre-hashing keeps long passphrases fully significant.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode())
    except ValueError:
        return False


# A real hash to compare against when the email doesn't exist, so timing doesn't reveal accounts.
DUMMY_HASH = hash_password("not-a-real-password-" + secrets.token_hex(8))


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 12:
        problems.append("Use at least 12 characters.")
    if password.lower() == password or password.upper() == password:
        problems.append("Mix upper and lower case letters.")
    if not any(c.isdigit() for c in password):
        problems.append("Include at least one number.")
    return problems


# ---------- tokens ----------
def _key() -> str:
    return get_settings().secret_key


def make_session_token(session_id: str, user_id: str, expires_at: datetime) -> str:
    return jwt.encode({"sid": session_id, "uid": user_id, "typ": "session", "exp": expires_at}, _key(), ALGO)


def make_mfa_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode({"uid": user_id, "typ": "mfa", "exp": exp}, _key(), ALGO)


def decode_token(token: str, typ: str) -> dict | None:
    try:
        data = jwt.decode(token, _key(), algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    return data if data.get("typ") == typ else None


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_url_token() -> str:
    return secrets.token_urlsafe(32)


# ---------- encryption of stored secrets ----------
def _fernet() -> Fernet:
    s = get_settings()
    if s.encryption_key:
        return Fernet(s.encryption_key.encode())
    if s.is_production:
        log.warning("ENCRYPTION_KEY is not set; deriving one from SECRET_KEY. Set ENCRYPTION_KEY in .env.")
    derived = base64.urlsafe_b64encode(hashlib.sha256(("enc:" + s.secret_key).encode()).digest())
    return Fernet(derived)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


# ---------- MFA (TOTP) ----------
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=get_settings().app_name)


def totp_qr_svg(uri: str) -> str:
    return segno.make(uri, error="m").svg_data_uri(scale=5, border=2)


def verify_totp(secret: str, code: str) -> bool:
    code = "".join(c for c in code if c.isdigit())
    return len(code) == 6 and pyotp.TOTP(secret).verify(code, valid_window=1)


def new_recovery_codes(n: int = 10) -> tuple[list[str], list[str]]:
    """Returns (plain codes to show once, hashes to store)."""
    plain = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]
    return plain, [sha256_hex(c) for c in plain]


def use_recovery_code(stored: list[str], code: str) -> list[str] | None:
    """If the code matches, returns the remaining hashes; otherwise None."""
    h = sha256_hex(code.strip().lower())
    for i, s in enumerate(stored):
        if hmac.compare_digest(s, h):
            return stored[:i] + stored[i + 1 :]
    return None
