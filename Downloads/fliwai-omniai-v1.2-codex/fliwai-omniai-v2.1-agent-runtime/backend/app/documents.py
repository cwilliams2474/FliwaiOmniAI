from __future__ import annotations

import re
from pathlib import Path


def extract_text(path: Path, extension: str) -> str:
    if extension in {'.txt', '.csv'}:
        return path.read_text(encoding='utf-8', errors='ignore')
    if extension == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return '\n'.join((page.extract_text() or '') for page in reader.pages)
    if extension == '.docx':
        from docx import Document as DocxDocument
        doc = DocxDocument(str(path))
        return '\n'.join(paragraph.text for paragraph in doc.paragraphs)
    return ''


def chunk_text(text: str, chunk_size: int = 1400, overlap: int = 180) -> list[str]:
    normalized = re.sub(r'\s+', ' ', text).strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def score_chunk(question: str, content: str) -> int:
    terms = {term for term in re.findall(r'[a-zA-Z0-9]{3,}', question.lower())}
    content_lower = content.lower()
    return sum(content_lower.count(term) for term in terms)
