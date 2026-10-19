#!/usr/bin/env bash
# Restore a backup into a throwaway, isolated PostgreSQL container and check it.
# Production containers, volumes and networks are never touched.
# Usage: scripts/restore-test.sh backups/20261017-020000 [--keep]
set -euo pipefail
cd "$(dirname "$0")/.."
dir=${1:?Usage: restore-test.sh <backup-folder> [--keep]}
keep=${2:-}
name="omniai-restoretest-$$"
net="omniai-restoretest-net-$$"
work=$(mktemp -d)

cleanup() {
  if [[ "$keep" != "--keep" ]]; then
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker network rm "$net" >/dev/null 2>&1 || true
    rm -rf "$work"
  else
    echo "Kept container $name (network $net) and files in $work for inspection."
  fi
}
trap cleanup EXIT

scripts/verify-backup.sh "$dir"

echo "Starting isolated database container $name (no published ports)..."
docker network create --internal "$net" >/dev/null
docker run -d --name "$name" --network "$net" -e POSTGRES_PASSWORD=restoretest -e POSTGRES_USER=omniai -e POSTGRES_DB=omniai postgres:16-alpine >/dev/null
for _ in $(seq 1 30); do docker exec "$name" pg_isready -U omniai -d omniai >/dev/null 2>&1 && break; sleep 1; done

echo "Restoring database..."
docker exec -i "$name" pg_restore -U omniai -d omniai --no-owner --exit-on-error < "$dir/database.dump"

q() { docker exec "$name" psql -U omniai -d omniai -tAc "$1"; }
migration=$(q "select version_num from alembic_version")
users=$(q "select count(*) from users")
orgs=$(q "select count(*) from organizations")
tickets=$(q "select count(*) from tickets")
docs=$(q "select count(*) from documents")
chunks=$(q "select count(*) from document_chunks")
echo "Restored: migration $migration · $orgs organizations · $users users · $tickets tickets · $docs documents ($chunks passages)"
[[ "$users" -ge 1 && "$orgs" -ge 1 ]] || { echo "FAIL: restored database has no users or organizations."; exit 1; }

echo "Checking uploaded files against document records..."
tar -xzf "$dir/uploads.tar.gz" -C "$work"
missing=0
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  [[ -f "$work/uploads/$path" ]] || { echo "  missing file: $path"; missing=$((missing + 1)); }
done < <(q "select storage_path from documents")
[[ $missing -eq 0 ]] || { echo "FAIL: $missing document files are missing from uploads.tar.gz."; exit 1; }
echo "OK: all $docs document files present"

date -Is > "$dir/RESTORE_TEST_PASSED"
echo "PASSED: $dir restores cleanly. Recorded in $dir/RESTORE_TEST_PASSED."
