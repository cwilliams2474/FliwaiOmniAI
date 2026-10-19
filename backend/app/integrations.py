"""Outbound integrations: Slack, Microsoft Teams and generic webhooks.

Secrets (webhook URLs, auth header values) are stored encrypted with ENCRYPTION_KEY and are
never returned by the API; only a short hint such as "…/T0ab" is shown.
"""

import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.models import Integration
from app.security import decrypt, encrypt

KINDS = {
    "slack": {"label": "Slack incoming webhook", "secret_fields": ["webhook_url"], "config_fields": []},
    "teams": {"label": "Microsoft Teams webhook (Workflows)", "secret_fields": ["webhook_url"], "config_fields": []},
    "webhook": {"label": "Generic HTTPS webhook (JSON POST)", "secret_fields": ["url", "auth_header_value"], "config_fields": ["auth_header_name"]},
}


class IntegrationError(Exception):
    pass


def validate_url(url: str) -> str:
    p = urlparse(url.strip())
    if p.scheme not in ("https", "http") or not p.netloc:
        raise IntegrationError("Enter a full http(s):// URL.")
    return url.strip()


def hint_for(url: str) -> str:
    p = urlparse(url)
    tail = (p.path or "")[-4:]
    return f"{p.netloc}/…{tail}" if p.netloc else "set"


def seal(secrets: dict) -> str:
    return encrypt(json.dumps(secrets))


def unseal(integ: Integration) -> dict:
    raw = decrypt(integ.secret_enc or "")
    if raw is None:
        raise IntegrationError("The stored secret can't be decrypted. Was ENCRYPTION_KEY changed? Re-enter the secret.")
    return json.loads(raw)


def _payload(kind: str, text: str, org_name: str) -> dict:
    if kind == "slack":
        return {"text": text}
    if kind == "teams":
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [{"type": "TextBlock", "text": text, "wrap": True}],
                    },
                }
            ],
        }
    return {"text": text, "organization": org_name, "source": "omniai", "sent_at": datetime.now(timezone.utc).isoformat()}


def send(integ: Integration, text: str, org_name: str, timeout: float = 15.0) -> dict:
    """Send a message. Updates last_used/last_ok/last_error on the object (caller commits)."""
    if not integ.enabled:
        raise IntegrationError(f"Integration '{integ.name}' is turned off.")
    secrets = unseal(integ)
    url = secrets.get("webhook_url") or secrets.get("url")
    if not url:
        raise IntegrationError(f"Integration '{integ.name}' has no URL set.")
    headers = {"Content-Type": "application/json", "User-Agent": "OmniAI/3.1"}
    if integ.kind == "webhook" and secrets.get("auth_header_value"):
        headers[(integ.config or {}).get("auth_header_name") or "Authorization"] = secrets["auth_header_value"]
    integ.last_used_at = datetime.now(timezone.utc)
    try:
        r = httpx.post(url, json=_payload(integ.kind, text[:12000], org_name), headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        integ.last_ok, integ.last_error = False, f"Couldn't connect: {e.__class__.__name__}"
        raise IntegrationError(f"{integ.name}: {integ.last_error}")
    if r.status_code >= 400:
        integ.last_ok, integ.last_error = False, f"HTTP {r.status_code}: {r.text[:200]}"
        raise IntegrationError(f"{integ.name} rejected the message ({integ.last_error}).")
    integ.last_ok, integ.last_error = True, ""
    return {"status_code": r.status_code}
