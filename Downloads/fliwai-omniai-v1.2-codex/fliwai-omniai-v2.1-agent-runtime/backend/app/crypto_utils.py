import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    if not value:
        return ''
    return _fernet().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt_secret(value: str) -> str:
    if not value:
        return ''
    try:
        return _fernet().decrypt(value.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError) as exc:
        raise ValueError('Stored integration secret could not be decrypted') from exc
