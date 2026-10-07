#!/usr/bin/env bash
# Ensure secrets/dashboard_password exists and re-seed coordinator .env (DECISION-18).
# Usage: scripts/hermes-dashboard-auth.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p secrets
umask 077
if [ ! -s secrets/dashboard_password ]; then
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 24 | tr -d '\n' > secrets/dashboard_password
  else
    printf '%s' 'emaw-dashboard-dev' > secrets/dashboard_password
  fi
  chmod 600 secrets/dashboard_password
  echo "wrote secrets/dashboard_password"
fi

scripts/hermes-seed-env.sh
echo "Restart coordinator to apply: docker compose --profile agents up -d --force-recreate --no-deps coordinator"
echo "Then: curl -sS -o /dev/null -w '%{http_code}\\n' -u emaw:<password> http://127.0.0.1:9119/"
