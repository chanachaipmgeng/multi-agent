#!/usr/bin/env bash
# Materialise hermes-data/<agent>/.env from ./secrets/* for compose agents profile.
# Hermes v0.21.5 reads UPPER_SNAKE secrets from /opt/data/.env (not config.yaml).
#
# Usage: scripts/hermes-seed-env.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

secret() { [ -s "secrets/$1" ] && cat "secrets/$1" || true; }

write_env() {
  local agent="$1"
  shift
  local dest="hermes-data/$agent/.env"
  umask 077
  : > "$dest"
  for pair in "$@"; do
    local key="${pair%%=*}"
    local file="${pair#*=}"
    local val
    val="$(secret "$file")"
    if [ -n "$val" ]; then
      # Escape nothing exotic — secrets are single-line tokens
      printf '%s=%s\n' "$key" "$val" >> "$dest"
    fi
  done
  # Always set API server defaults for adapter integration
  grep -q '^API_SERVER_ENABLED=' "$dest" 2>/dev/null || echo "API_SERVER_ENABLED=true" >> "$dest"
  grep -q '^API_SERVER_HOST=' "$dest" 2>/dev/null || echo "API_SERVER_HOST=0.0.0.0" >> "$dest"
  grep -q '^API_SERVER_PORT=' "$dest" 2>/dev/null || echo "API_SERVER_PORT=8642" >> "$dest"
  local api
  api="$(secret hermes_api_key)"
  if [ -n "$api" ]; then
    grep -q '^API_SERVER_KEY=' "$dest" && sed -i.bak '/^API_SERVER_KEY=/d' "$dest" && rm -f "${dest}.bak"
    printf 'API_SERVER_KEY=%s\n' "$api" >> "$dest"
  fi
  echo "wrote $dest"
}

write_env coordinator \
  TELEGRAM_BOT_TOKEN=telegram_token \
  OPENROUTER_API_KEY=llm_key_coordinator \
  GITLAB_TOKEN=gitlab_token_readonly

write_env dev-frontend \
  OPENROUTER_API_KEY=llm_key_dev_frontend \
  GITLAB_TOKEN=gitlab_token_frontend

write_env dev-backend \
  OPENROUTER_API_KEY=llm_key_dev_backend \
  GITLAB_TOKEN=gitlab_token_backend

write_env reviewer \
  OPENROUTER_API_KEY=llm_key_reviewer \
  GITLAB_TOKEN=gitlab_token_readonly \
  SOCRATICODE_API_KEY=socraticode_key

write_env devops \
  OPENROUTER_API_KEY=llm_key_devops \
  GITLAB_TOKEN=gitlab_token_ci

write_env qa \
  OPENROUTER_API_KEY=llm_key_qa \
  GITLAB_TOKEN=gitlab_token_qa

# Shared non-secret defaults
for agent in coordinator dev-frontend dev-backend reviewer devops qa; do
  f="hermes-data/$agent/.env"
  grep -q '^GITLAB_HOST=' "$f" 2>/dev/null || echo "GITLAB_HOST=${GITLAB_BASE_URL:-https://gitlab.com}" >> "$f"
  if [ -n "${TELEGRAM_ALLOWED_USERS:-}" ] && [ "$agent" = "coordinator" ]; then
    grep -q '^TELEGRAM_ALLOWED_USERS=' "$f" 2>/dev/null || \
      echo "TELEGRAM_ALLOWED_USERS=$TELEGRAM_ALLOWED_USERS" >> "$f"
  fi
done

echo "Hermes .env files ready. Ensure TELEGRAM_ALLOWED_USERS is set for coordinator."
