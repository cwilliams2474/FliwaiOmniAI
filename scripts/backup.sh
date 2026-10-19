#!/usr/bin/env bash
# Back up the database and uploaded files, with SHA-256 checksums.
# Schedule nightly with cron, e.g.:  0 2 * * * /opt/omniai/scripts/backup.sh >> /var/log/omniai-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=/dev/null
source <(grep -E '^(POSTGRES_USER|POSTGRES_DB|BACKUP_DIR|BACKUP_KEEP_DAYS)=' .env)
POSTGRES_USER=${POSTGRES_USER:-omniai}
POSTGRES_DB=${POSTGRES_DB:-omniai}
BACKUP_DIR=${BACKUP_DIR:-./backups}
KEEP=${BACKUP_KEEP_DAYS:-14}

stamp=$(date +%Y%m%d-%H%M%S)
dest="$BACKUP_DIR/$stamp"
mkdir -p "$dest"
chmod 700 "$BACKUP_DIR" "$dest"

echo "[$(date -Is)] Dumping database to $dest/database.dump"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner > "$dest/database.dump"

echo "[$(date -Is)] Archiving uploaded files to $dest/uploads.tar.gz"
docker compose exec -T backend tar -czf - -C /data uploads > "$dest/uploads.tar.gz"

git_rev=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
migration=$(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version_num from alembic_version" 2>/dev/null || echo "unknown")
printf 'created=%s\nmigration=%s\ncode=%s\n' "$(date -Is)" "$migration" "$git_rev" > "$dest/MANIFEST"

(cd "$dest" && sha256sum database.dump uploads.tar.gz MANIFEST > SHA256SUMS)

# Quick self-check so a broken backup is noticed now, not during a restore.
"$(dirname "$0")/verify-backup.sh" "$dest" >/dev/null
echo "[$(date -Is)] Backup complete and verified: $dest ($(du -sh "$dest" | cut -f1))"

# Retention: remove backup folders older than KEEP days.
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime +"$KEEP" -print -exec rm -rf {} + || true
