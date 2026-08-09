import json
import difflib
from pathlib import PurePosixPath
from typing import Any


def safe_relative_path(value: str) -> str:
    normalized = value.replace('\\', '/').strip()
    while normalized.startswith('./'):
        normalized = normalized[2:]
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or '..' in path.parts:
        raise ValueError('File path must be a safe relative path')
    return str(path)


def parse_codex_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith('```json') and cleaned.endswith('```'):
        cleaned = cleaned[7:-3].strip()
    elif cleaned.startswith('```') and cleaned.endswith('```'):
        cleaned = cleaned[3:-3].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {'summary': 'Codex response', 'answer': text, 'files': [], 'test_plan': [], 'risks': ['Response was not structured JSON.']}
    if not isinstance(data, dict):
        return {'summary': 'Codex response', 'answer': str(data), 'files': [], 'test_plan': [], 'risks': []}
    data.setdefault('summary', 'Codex response'); data.setdefault('answer', ''); data.setdefault('files', []); data.setdefault('test_plan', []); data.setdefault('risks', [])
    return data


def unified_content_diff(path: str, old: str, new: str) -> str:
    safe = safe_relative_path(path)
    return ''.join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f'a/{safe}', tofile=f'b/{safe}', lineterm='\n',
    ))
