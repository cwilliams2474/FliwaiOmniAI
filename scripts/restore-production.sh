#!/usr/bin/env bash
# Restore a backup over the LIVE installation. Guard rails:
#   1. The backup must verify and must have passed scripts/restore-test.sh.
#   2. You must type the confirmation phrase.
#   3. A fresh backup of the current state is taken first, so this can be undone.
# Usage: scripts/restore-production.sh backups/20261017-020000
set -euo pipefail
cd "$(dirname "$0")/.."
dir=${1:?Usage: restore-production.sh <backup-folder>}
# shellcheck source=/dev/null
source <(grep -E '^(POSTGRES_USER|POSTGRES_DB|BACKUP_DIR)=' .env)
POSTGRES_USER=${POSTGRES_USER:-omniai}
POSTGRES_DB=${POSTGRES_DB:-omniai}
BACKUP_DIR=${BACKUP_DIR:-./backups}

scripts/verify-backup.sh "$dir"
[[ -f "$dir/RESTORE_TEST_PASSED" ]] || { echo "STOP: run scripts/restore-test.sh $dir first. Production restore needs a passed test restore."; exit 1; }
echo "Test restore passed at $(cat "$dir/RESTORE_TEST_PASSED")."
cat "$dir/MANIFEST" 2>/dev/null || true
echo
echo "This replaces ALL current data (database and uploaded files) with the contents of $dir."
read -rp "Type RESTORE PRODUCTION to continue: " answer
[[ "$answer" == "RESTORE PRODUCTION" ]] || { echo "Cancelled. Nothing was changed."; exit 1; }

echo "Taking a safety backup of the current state..."
scripts/backup.sh
safety=$(ls -1d "$BACKUP_DIR"/20* 2>/dev/null | sort | tail -1)
echo "Safety backup: $safety (restore it the same way if you need to undo)."

echo "Stopping the app (database stays up)..."
docker compose stop caddy frontend backend

echo "Restoring database..."
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$POSTGRES_DB' and pid <> pg_backend_pid();" \
  -c "drop database if exists \"$POSTGRES_DB\";" -c "create database \"$POSTGRES_DB\" owner \"$POSTGRES_USER\";"
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error < "$dir/database.dump"

echo "Restoring uploaded files..."
docker compose run --rm -T --no-deps --entrypoint sh backend -c 'rm -rf /data/uploads/* /data/uploads/.[!.]* 2>/dev/null; tar -xzf - -C /data' < "$dir/uploads.tar.gz"

echo "Starting the app..."
docker compose up -d
for _ in $(seq 1 40); do
  if docker compose exec -T backend curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "DONE: production restored from $dir and healthy."
    exit 0
  fi
  sleep 3
done
echo "WARNING: the backend isn't healthy after the restore. Check 'docker compose logs backend'. Safety backup: $safety"
exit 1
