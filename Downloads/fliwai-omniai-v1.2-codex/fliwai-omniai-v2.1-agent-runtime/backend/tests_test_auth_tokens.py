from types import SimpleNamespace

from app.security_utils import token_identity


def test_token_identity_contains_session_version():
    user = SimpleNamespace(email='user@example.com', token_version=7)
    assert token_identity(user) == {'sub': 'user@example.com', 'ver': 7}
