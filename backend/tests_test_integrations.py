import json
from types import SimpleNamespace

import pytest

from app.crypto_utils import decrypt_secret, encrypt_secret
from app.integrations import execute_integration_action, public_connection


def test_secret_round_trip_and_ciphertext_differs():
    secret = 'very-secret-token'
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret


def test_public_connection_never_exposes_secret():
    row = SimpleNamespace(id=1, provider='github', name='Primary', config_json=json.dumps({'repo':'owner/repo'}), secret_encrypted='ciphertext', enabled=True, created_at=None, updated_at=None)
    value = public_connection(row)
    assert value['has_secret'] is True
    assert 'secret' not in value
    assert 'secret_encrypted' not in value


def test_unknown_integration_action_is_rejected_before_network():
    row = SimpleNamespace(provider='github', enabled=True, secret_encrypted='', config_json='{}')
    with pytest.raises(ValueError, match='Unsupported github action'):
        execute_integration_action(row, 'delete_repository', {})


def test_webhook_blocks_localhost_and_plain_http(monkeypatch):
    from app.integrations import validate_webhook_url
    with pytest.raises(ValueError, match='https'):
        validate_webhook_url('http://example.com/hook')
    with pytest.raises(ValueError, match='localhost'):
        validate_webhook_url('https://localhost/hook')
