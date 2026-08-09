import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from app.crypto_utils import decrypt_secret
from app.models.core import IntegrationConnection

PROVIDERS = {
    'github': {'label': 'GitHub', 'actions': ['create_issue']},
    'google': {'label': 'Google Workspace', 'actions': ['send_email', 'create_calendar_event']},
    'microsoft': {'label': 'Microsoft 365', 'actions': ['send_email', 'create_calendar_event']},
    'webhook': {'label': 'Webhook', 'actions': ['post']},
}



def validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise ValueError('Webhook URL must use https')
    host = parsed.hostname
    if not host:
        raise ValueError('Webhook URL must include a hostname')
    if host.lower() in {'localhost', 'localhost.localdomain'}:
        raise ValueError('Webhook URL cannot target localhost')
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError('Webhook hostname could not be resolved') from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError('Webhook URL cannot target private or special-use networks')
    return url

def public_connection(row: IntegrationConnection) -> dict[str, Any]:
    config = json.loads(row.config_json or '{}')
    return {
        'id': row.id, 'provider': row.provider, 'name': row.name, 'config': config,
        'enabled': row.enabled, 'has_secret': bool(row.secret_encrypted),
        'actions': PROVIDERS.get(row.provider, {}).get('actions', []),
        'created_at': row.created_at, 'updated_at': row.updated_at,
    }


def _secret(row: IntegrationConnection) -> str:
    return decrypt_secret(row.secret_encrypted)


def execute_integration_action(row: IntegrationConnection, action: str, params: dict[str, Any]) -> dict[str, Any]:
    if not row.enabled:
        raise ValueError('Integration is disabled')
    if action not in PROVIDERS.get(row.provider, {}).get('actions', []):
        raise ValueError(f'Unsupported {row.provider} action: {action}')
    token = _secret(row)
    config = json.loads(row.config_json or '{}')
    timeout = 15.0

    if row.provider == 'github' and action == 'create_issue':
        repo = str(params.get('repo') or config.get('repo') or '')
        if '/' not in repo:
            raise ValueError('GitHub repo must be owner/name')
        if not token:
            raise ValueError('GitHub token is not configured')
        payload = {'title': str(params.get('title') or 'OmniAI issue')[:256], 'body': str(params.get('body') or '')[:60000]}
        r = httpx.post(f'https://api.github.com/repos/{repo}/issues', headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}, json=payload, timeout=timeout)
        r.raise_for_status(); data = r.json()
        return {'provider': 'github', 'action': action, 'id': data.get('id'), 'number': data.get('number'), 'url': data.get('html_url')}

    if row.provider == 'google' and action == 'send_email':
        # Gmail API requires RFC 2822 base64url content; callers provide a prepared raw value.
        raw = str(params.get('raw') or '')
        if not token or not raw:
            raise ValueError('Google access token and raw message are required')
        r = httpx.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', headers={'Authorization': f'Bearer {token}'}, json={'raw': raw}, timeout=timeout)
        r.raise_for_status(); data = r.json(); return {'provider': 'google', 'action': action, 'id': data.get('id')}

    if row.provider == 'google' and action == 'create_calendar_event':
        if not token:
            raise ValueError('Google access token is not configured')
        calendar_id = str(params.get('calendar_id') or config.get('calendar_id') or 'primary')
        event = params.get('event') or {}
        r = httpx.post(f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events', headers={'Authorization': f'Bearer {token}'}, json=event, timeout=timeout)
        r.raise_for_status(); data=r.json(); return {'provider':'google','action':action,'id':data.get('id'),'url':data.get('htmlLink')}

    if row.provider == 'microsoft' and action == 'send_email':
        if not token:
            raise ValueError('Microsoft Graph access token is not configured')
        message = params.get('message') or {}
        r = httpx.post('https://graph.microsoft.com/v1.0/me/sendMail', headers={'Authorization': f'Bearer {token}'}, json={'message': message, 'saveToSentItems': True}, timeout=timeout)
        r.raise_for_status(); return {'provider':'microsoft','action':action,'status':'sent'}

    if row.provider == 'microsoft' and action == 'create_calendar_event':
        if not token:
            raise ValueError('Microsoft Graph access token is not configured')
        event = params.get('event') or {}
        r = httpx.post('https://graph.microsoft.com/v1.0/me/events', headers={'Authorization': f'Bearer {token}'}, json=event, timeout=timeout)
        r.raise_for_status(); data=r.json(); return {'provider':'microsoft','action':action,'id':data.get('id'),'url':data.get('webLink')}

    if row.provider == 'webhook' and action == 'post':
        url = str(params.get('url') or config.get('url') or '')
        validate_webhook_url(url)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        payload = params.get('payload') or {}
        r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status(); return {'provider':'webhook','action':action,'status_code':r.status_code}

    raise ValueError('Integration action was not handled')


def test_connection(row: IntegrationConnection) -> dict[str, Any]:
    token = _secret(row)
    config = json.loads(row.config_json or '{}')
    if row.provider == 'github':
        if not token: raise ValueError('GitHub token is not configured')
        r=httpx.get('https://api.github.com/user', headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json'}, timeout=10.0); r.raise_for_status(); data=r.json()
        return {'ok': True, 'identity': data.get('login')}
    if row.provider == 'google':
        if not token: raise ValueError('Google access token is not configured')
        r=httpx.get('https://www.googleapis.com/oauth2/v3/userinfo', headers={'Authorization':f'Bearer {token}'}, timeout=10.0); r.raise_for_status(); data=r.json()
        return {'ok': True, 'identity': data.get('email') or data.get('sub')}
    if row.provider == 'microsoft':
        if not token: raise ValueError('Microsoft Graph access token is not configured')
        r=httpx.get('https://graph.microsoft.com/v1.0/me?$select=displayName,userPrincipalName', headers={'Authorization':f'Bearer {token}'}, timeout=10.0); r.raise_for_status(); data=r.json()
        return {'ok': True, 'identity': data.get('userPrincipalName') or data.get('displayName')}
    if row.provider == 'webhook':
        return {'ok': bool(config.get('url')), 'identity': config.get('url', '')}
    raise ValueError('Unknown provider')
