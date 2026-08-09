#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <backup-directory>" >&2
  exit 2
fi

BACKUP_DIR="$1"
python3 - "$BACKUP_DIR" <<'PY'
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


root = Path(sys.argv[1]).resolve()
manifest_path = root / 'manifest.json'
if not manifest_path.is_file():
    raise SystemExit(f'manifest.json not found in {root}')
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
if manifest.get('format_version') != 1:
    raise SystemExit('Unsupported backup format version')

def safe_child(base: Path, rel: str) -> Path:
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise SystemExit(f'Unsafe manifest path: {rel}') from exc
    return candidate


db_path = safe_child(root, manifest['database_file'])
uploads_dir = safe_child(root, manifest['uploads_directory'])
if not db_path.is_file():
    raise SystemExit(f'Database backup missing: {db_path}')
if db_path.stat().st_size < 100:
    raise SystemExit('Database backup is unexpectedly small')
if sha256(db_path) != manifest['database_sha256']:
    raise SystemExit('Database checksum mismatch')
if not uploads_dir.is_dir():
    raise SystemExit(f'Uploads directory missing: {uploads_dir}')
for item in manifest.get('uploads', []):
    path = safe_child(uploads_dir, item['path'])
    if not path.is_file():
        raise SystemExit(f"Upload backup missing: {item['path']}")
    if sha256(path) != item['sha256']:
        raise SystemExit(f"Upload checksum mismatch: {item['path']}")
print(f'Backup verification passed: {root}')
PY
