"""Model provider adapters.

openai    – any OpenAI-compatible /chat/completions endpoint (OpenAI, Azure OpenAI proxy,
            Ollama, vLLM, LM Studio, LiteLLM ...). Set AI_BASE_URL accordingly.
anthropic – Anthropic Messages API.
none      – no model; chat returns the most relevant passages instead of a generated answer.
"""

from dataclasses import dataclass

import httpx

from app.config import get_settings


class AIError(Exception):
    """A provider problem worth showing to the user (bad key, timeout, model missing)."""


@dataclass
class Completion:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


def provider_name() -> str:
    return get_settings().ai_provider.lower().strip()


def complete(system: str, messages: list[dict]) -> Completion:
    """messages: [{"role": "user"|"assistant", "content": str}, ...]"""
    s = get_settings()
    p = provider_name()
    try:
        if p == "openai":
            return _openai(s, system, messages)
        if p == "anthropic":
            return _anthropic(s, system, messages)
    except httpx.TimeoutException:
        raise AIError(f"The model didn't answer within {s.ai_timeout_seconds} seconds. Try again or use a faster model.")
    except httpx.HTTPError as e:
        raise AIError(f"Couldn't reach the model provider at {s.ai_base_url if p == 'openai' else 'api.anthropic.com'}: {e.__class__.__name__}.")
    raise AIError("No model provider is configured.")


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        detail = resp.json()
        err = detail.get("error") if isinstance(detail, dict) else None
        msg = err.get("message") if isinstance(err, dict) else (err or str(detail)[:300])
    except ValueError:
        msg = resp.text[:300]
    if resp.status_code in (401, 403):
        raise AIError("The model provider rejected the API key. Check AI_API_KEY in .env.")
    if resp.status_code == 404:
        raise AIError(f"The model or endpoint wasn't found. Check AI_MODEL and AI_BASE_URL. ({msg})")
    if resp.status_code == 429:
        raise AIError("The model provider is rate-limiting requests. Wait a moment and try again.")
    raise AIError(f"The model provider returned an error ({resp.status_code}): {msg}")


def _openai(s, system: str, messages: list[dict]) -> Completion:
    headers = {"Content-Type": "application/json"}
    if s.ai_api_key:
        headers["Authorization"] = f"Bearer {s.ai_api_key}"
    payload = {
        "model": s.ai_model,
        "messages": [{"role": "system", "content": system}, *messages],
        "max_tokens": s.ai_max_tokens,
        "temperature": 0.2,
    }
    r = httpx.post(f"{s.ai_base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=s.ai_timeout_seconds)
    _raise_for(r)
    data = r.json()
    usage = data.get("usage") or {}
    return Completion(
        text=(data["choices"][0]["message"].get("content") or "").strip(),
        model=data.get("model", s.ai_model),
        tokens_in=usage.get("prompt_tokens", 0),
        tokens_out=usage.get("completion_tokens", 0),
    )


def _anthropic(s, system: str, messages: list[dict]) -> Completion:
    headers = {"x-api-key": s.ai_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    base = s.ai_base_url if "anthropic" in s.ai_base_url else "https://api.anthropic.com"
    payload = {"model": s.ai_model, "system": system, "messages": messages, "max_tokens": s.ai_max_tokens, "temperature": 0.2}
    r = httpx.post(f"{base.rstrip('/')}/v1/messages", json=payload, headers=headers, timeout=s.ai_timeout_seconds)
    _raise_for(r)
    data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    usage = data.get("usage") or {}
    return Completion(text=text, model=data.get("model", s.ai_model), tokens_in=usage.get("input_tokens", 0), tokens_out=usage.get("output_tokens", 0))
