#!/usr/bin/env bash
# Materialise ./secrets/<name> files for docker compose from .env.enc (preferred) or .env (dev).
# Each SECRET_FOO=value line becomes ./secrets/foo (mode 0600, no trailing newline).
# Usage: scripts/secrets-decrypt.sh [--from-plain-env]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SOURCE=""
if [ "${1:-}" = "--from-plain-env" ]; then
  [ -f .env ] || { echo ".env not found"; exit 1; }
  SOURCE="$(cat .env)"
  echo "using plaintext .env (dev only)"
elif [ -f .env.enc ]; then
  command -v sops >/dev/null || { echo "sops not found"; exit 1; }
  SOURCE="$(sops --decrypt --input-type dotenv --output-type dotenv .env.enc)"
  echo "decrypted .env.enc"
elif [ -f .env ]; then
  SOURCE="$(cat .env)"
  echo "no .env.enc yet — falling back to plaintext .env (dev only)"
else
  echo "neither .env.enc nor .env found"; exit 1
fi

mkdir -p secrets
umask 077
count=0
while IFS= read -r line; do
  case "$line" in
    SECRET_*=*)
      key="${line%%=*}"; val="${line#*=}"
      # strip optional surrounding quotes
      val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
      name="$(echo "${key#SECRET_}" | tr '[:upper:]' '[:lower:]')"
      printf '%s' "$val" > "secrets/$name"
      chmod 600 "secrets/$name"
      count=$((count+1))
      ;;
  esac
done <<< "$SOURCE"

# compose declares every secret file; create empty placeholders for the ones not set yet
for name in gitlab_webhook_secret pg_password tunnel_token telegram_token socraticode_key \
            llm_key_coordinator llm_key_dev_frontend llm_key_dev_backend llm_key_reviewer llm_key_devops llm_key_qa \
            gitlab_token_readonly gitlab_token_frontend gitlab_token_backend gitlab_token_ci gitlab_token_qa; do
  [ -f "secrets/$name" ] || { : > "secrets/$name"; chmod 600 "secrets/$name"; }
done

echo "wrote $count secret files into ./secrets/ (gitignored)"
[ -s secrets/gitlab_webhook_secret ] || echo "warning: secrets/gitlab_webhook_secret is empty — the gateway will refuse to start"
[ -s secrets/pg_password ]           || echo "warning: secrets/pg_password is empty"
