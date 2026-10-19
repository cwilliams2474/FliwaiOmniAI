#!/usr/bin/env bash
# Verify a backup folder: checksums match and both archives are readable.
# Usage: scripts/verify-backup.sh backups/20261017-020000
set -euo pipefail
dir=${1:?Usage: verify-backup.sh <backup-folder>}
[[ -f "$dir/SHA256SUMS" ]] || { echo "FAIL: $dir has no SHA256SUMS file."; exit 1; }

(cd "$dir" && sha256sum --check --quiet SHA256SUMS) || { echo "FAIL: checksum mismatch in $dir. Do not restore from it."; exit 1; }
echo "OK: checksums match"

tar -tzf "$dir/uploads.tar.gz" >/dev/null || { echo "FAIL: uploads.tar.gz is not a readable archive."; exit 1; }
echo "OK: uploads archive readable ($(tar -tzf "$dir/uploads.tar.gz" | grep -vc '/$') files)"

# Read the dump's table of contents with the same Postgres version the app uses.
docker run --rm -i postgres:16-alpine pg_restore --list < "$dir/database.dump" >/dev/null \
  || { echo "FAIL: database.dump can't be read by pg_restore."; exit 1; }
echo "OK: database dump readable"
echo "VERIFIED: $dir"
