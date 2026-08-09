#!/usr/bin/env bash
set -euo pipefail

CONFIRM="false"
BACKUP_DIR=""
for arg in "$@"; do
  case "$arg" in
    --confirm-restore) CONFIRM="true" ;;
    -h|--help)
      echo "Usage: $0 <backup-directory> --confirm-restore"
      exit 0
      ;;
    *)
      if [[ -z "$BACKUP_DIR" ]]; then BACKUP_DIR="$arg"; else echo "Unexpected argument: $arg" >&2; exit 2; fi
      ;;
  esac
done

if [[ -z "$BACKUP_DIR" ]]; then
  echo "Backup directory is required" >&2
  exit 2
fi
if [[ "$CONFIRM" != "true" ]]; then
  echo "Restore is destructive. Re-run with --confirm-restore after confirming the target environment." >&2
  exit 2
fi

"$(dirname "$0")/verify-backup.sh" "$BACKUP_DIR"

DB_FILE="$(python3 - "$BACKUP_DIR" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
m = json.loads((root/'manifest.json').read_text())
p = (root/m['database_file']).resolve(); p.relative_to(root)
print(p)
PY
)"
UPLOADS_DIR="$(python3 - "$BACKUP_DIR" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
m = json.loads((root/'manifest.json').read_text())
p = (root/m['uploads_directory']).resolve(); p.relative_to(root)
print(p)
PY
)"

echo "Restoring database..."
cat "$DB_FILE" | docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'

echo "Restoring uploads..."
docker compose exec -T backend sh -c 'find /app/uploads -mindepth 1 -maxdepth 1 -exec rm -rf {} +'
tar -C "$UPLOADS_DIR" -cf - . | docker compose exec -T backend sh -c 'tar -xf - -C /app/uploads'

docker compose restart backend >/dev/null

echo "Restore complete. Run ./scripts/smoke-test.sh and verify sign-in before declaring recovery complete."
