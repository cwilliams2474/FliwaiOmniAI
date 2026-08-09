from typing import Any

from openai import OpenAI

from app.config import settings

CODEX_SYSTEM = '''You are the Codex Developer inside FLIWAI OmniAI.
You work only from the project files supplied in the prompt. Be precise, conservative, and security-conscious.
Never claim to have executed commands or tests. Never invent files that were not supplied unless the user explicitly asks to create them.
Return ONLY valid JSON with this shape:
{
  "summary": "short result",
  "answer": "analysis or explanation",
  "files": [{"path": "relative/path", "language": "language", "content": "FULL replacement content"}],
  "test_plan": ["verification step"],
  "risks": ["remaining risk"]
}
For ask/review/test_plan, files should normally be empty. For implement, include only files that should be created or replaced.
Never include absolute paths or paths containing .. .'''


from app.codex_utils import parse_codex_json


def run_codex_task(mode: str, instruction: str, files: list[dict[str, str]]) -> tuple[dict[str, Any], str]:
    if not settings.openai_api_key:
        return ({
            'summary': 'Codex is not configured',
            'answer': 'Add OPENAI_API_KEY to the root .env file and restart the backend.',
            'files': [], 'test_plan': [], 'risks': [],
        }, settings.openai_code_model)

    context_parts = []
    total = 0
    for item in files:
        block = f"\n--- FILE: {item['path']} ({item.get('language','text')}) ---\n{item.get('content','')}\n"
        if total + len(block) > 160000:
            break
        context_parts.append(block)
        total += len(block)

    prompt = f"Mode: {mode}\nTask: {instruction}\n\nProject files:\n{''.join(context_parts) or '(no files yet)'}"
    client = OpenAI(api_key=settings.openai_api_key, timeout=90.0, max_retries=2)

    response = client.chat.completions.create(
        model=settings.openai_code_model,
        messages=[{'role': 'system', 'content': CODEX_SYSTEM}, {'role': 'user', 'content': prompt}],
    )
    text = response.choices[0].message.content or '{}'
    return parse_codex_json(text), settings.openai_code_model
