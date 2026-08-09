#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-./backups}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
BUNDLE="${OUTPUT_DIR%/}/omniai-backup-${STAMP}"
UPLOADS_DIR="$BUNDLE/uploads"
DB_FILE="$BUNDLE/database.sql"
MANIFEST_FILE="$BUNDLE/manifest.json"

mkdir -p "$UPLOADS_DIR"

echo "Backing up PostgreSQL..."
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$DB_FILE"
if [[ ! -s "$DB_FILE" ]]; then
  echo "Database backup is empty" >&2
  exit 1
fi

echo "Backing up uploaded files..."
docker compose exec -T backend sh -c 'cd /app/uploads && tar -cf - .' | tar -xf - -C "$UPLOADS_DIR"

python3 - "$DB_FILE" "$UPLOADS_DIR" "$MANIFEST_FILE" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


db_file = Path(sys.argv[1])
uploads_dir = Path(sys.argv[2])
manifest_file = Path(sys.argv[3])
items = []
for path in sorted(p for p in uploads_dir.rglob('*') if p.is_file()):
    items.append({
        'path': path.relative_to(uploads_dir).as_posix(),
        'sha256': sha256(path),
        'bytes': path.stat().st_size,
    })
manifest = {
    'format_version': 1,
    'created_at': datetime.now(timezone.utc).isoformat(),
    'database_file': db_file.name,
    'database_sha256': sha256(db_file),
    'uploads_directory': uploads_dir.name,
    'uploads': items,
}
manifest_file.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
PY

echo "Backup complete: $BUNDLE"
echo "Verify it with: ./scripts/verify-backup.sh '$BUNDLE'"
