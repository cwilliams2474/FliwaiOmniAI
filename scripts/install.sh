#!/usr/bin/env bash
# First-time install on Ubuntu with Docker. Creates .env with fresh secrets, builds and starts OmniAI.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "Docker is not installed. See README.md, step 1."; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "The Docker Compose plugin is missing. Install docker-compose-plugin."; exit 1; }
command -v openssl >/dev/null || { echo "openssl is required (sudo apt install openssl)."; exit 1; }

if [[ -f .env ]]; then
  echo ".env already exists; keeping it. Delete it first if you want fresh secrets."
else
  read -rp "Domain name for OmniAI (e.g. omni.example.com), or leave blank for plain HTTP on port 80: " domain
  cp .env.example .env
  set_kv() { sed -i "s|^$1=.*|$1=$2|" .env; }
  set_kv SECRET_KEY "$(openssl rand -hex 32)"
  set_kv ENCRYPTION_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"
  set_kv POSTGRES_PASSWORD "$(openssl rand -hex 24)"
  if [[ -n "$domain" ]]; then
    set_kv SITE_ADDRESS "$domain"
    set_kv PUBLIC_URL "https://$domain"
    set_kv COOKIE_SECURE true
  else
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    set_kv SITE_ADDRESS ":80"
    set_kv PUBLIC_URL "http://${ip:-localhost}"
    set_kv COOKIE_SECURE false
  fi
  chmod 600 .env
  echo "Created .env with new secrets. Back it up somewhere safe: without ENCRYPTION_KEY, MFA seeds can't be read."
fi

docker compose build
docker compose up -d
echo "Waiting for the backend to become healthy..."
for _ in $(seq 1 60); do
  if docker compose exec -T backend curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then
    url=$(grep '^PUBLIC_URL=' .env | cut -d= -f2-)
    echo "OmniAI is running. Open ${url}/setup to create the first organization and owner account."
    exit 0
  fi
  sleep 3
done
echo "The backend didn't become healthy. Check: docker compose logs backend"
exit 1
