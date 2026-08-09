import base64, hashlib, hmac, secrets, struct, time
from urllib.parse import quote


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def _decode(secret: str) -> bytes:
    padded = secret.upper() + '=' * ((8 - len(secret) % 8) % 8)
    return base64.b32decode(padded)


def totp(secret: str, at_time: int | None = None, step: int = 30, digits: int = 6) -> str:
    counter = int((at_time if at_time is not None else time.time()) // step)
    digest = hmac.new(_decode(secret), struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % (10 ** digits)
    return f'{code:0{digits}d}'


def verify_totp(secret: str, code: str, at_time: int | None = None, window: int = 1) -> bool:
    if not code.isdigit() or len(code) != 6:
        return False
    now = at_time if at_time is not None else int(time.time())
    return any(hmac.compare_digest(totp(secret, now + offset * 30), code) for offset in range(-window, window + 1))


def provisioning_uri(secret: str, email: str, issuer: str = 'FLIWAI OmniAI') -> str:
    return f'otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30'

def protect_secret(secret: str) -> str:
    from app.crypto_utils import encrypt_secret
    return encrypt_secret(secret)

def reveal_secret(stored: str) -> str:
    if not stored:
        return ''
    from app.crypto_utils import decrypt_secret
    try:
        return decrypt_secret(stored)
    except ValueError:
        return stored  # backward compatibility for any pre-encryption enrollment
