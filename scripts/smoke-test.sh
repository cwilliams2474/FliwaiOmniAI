#!/usr/bin/env bash
set -euo pipefail

# Prefer an explicitly supplied base URL. When omitted, exercise the backend
# inside Docker so the check is independent of host port mappings.
API_BASE="${1:-}"

if [[ -n "$API_BASE" ]]; then
  API_BASE="${API_BASE%/}"
  for path in /health/live /health/ready /health/deep; do
    url="$API_BASE$path"
    echo "Checking $url"
    curl --fail --silent --show-error "$url" >/dev/null
  done
else
  echo "Checking backend health from inside the Docker network..."
  docker compose exec -T backend python - <<'PY'
import json
import urllib.request
for path in ('/health/live', '/health/ready', '/health/deep'):
    url = 'http://localhost:8000' + path
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.load(response)
        if not payload.get('status'):
            raise SystemExit(f'Unexpected response from {url}: {payload}')
        print(f'{path}: {payload.get("status")}')
PY
fi

echo "OmniAI smoke checks passed."
