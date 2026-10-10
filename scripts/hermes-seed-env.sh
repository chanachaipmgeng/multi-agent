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
  # Container Hermes UID != host author; bind-mount must be world-readable.
  chmod 644 "$dest"
  echo "wrote $dest"
}

# Optional GitHub token pairs (same role names as GitLab). Empty files are skipped.
_gh_pair() {
  local role="$1" file="$2"
  if [ -s "secrets/$file" ]; then
    printf '%s' "$role=$file"
  fi
}

write_env coordinator \
  TELEGRAM_BOT_TOKEN=telegram_token \
  OPENROUTER_API_KEY=llm_key_coordinator \
  GITLAB_TOKEN=gitlab_token_readonly \
  $(_gh_pair GITHUB_TOKEN github_token_readonly) \
  $(_gh_pair GH_TOKEN github_token_readonly)

# Dashboard basic auth (DECISION-18 / Hermes 0.21.5 HERMES_DASHBOARD_BASIC_AUTH_*).
# Env wins over config.yaml; plaintext password is hashed in-memory by Hermes.
_coord="hermes-data/coordinator/.env"
_dash_pw="$(secret dashboard_password)"
_dash_secret="$(secret dashboard_session_secret)"
[ -z "$_dash_secret" ] && _dash_secret="$(secret hermes_api_key)"
if [ -n "$_dash_pw" ]; then
  for k in HERMES_DASHBOARD_BASIC_AUTH_USERNAME HERMES_DASHBOARD_BASIC_AUTH_PASSWORD \
           HERMES_DASHBOARD_BASIC_AUTH_SECRET; do
    grep -q "^${k}=" "$_coord" 2>/dev/null && sed -i.bak "/^${k}=/d" "$_coord" && rm -f "${_coord}.bak"
  done
  printf 'HERMES_DASHBOARD_BASIC_AUTH_USERNAME=%s\n' "${DASHBOARD_USERNAME:-emaw}" >> "$_coord"
  printf 'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=%s\n' "$_dash_pw" >> "$_coord"
  if [ -n "$_dash_secret" ]; then
    printf 'HERMES_DASHBOARD_BASIC_AUTH_SECRET=%s\n' "$_dash_secret" >> "$_coord"
  fi
  echo "coordinator dashboard basic auth seeded (user=${DASHBOARD_USERNAME:-emaw})"
fi

write_env dev-frontend \
  OPENROUTER_API_KEY=llm_key_dev_frontend \
  GITLAB_TOKEN=gitlab_token_frontend \
  $(_gh_pair GITHUB_TOKEN github_token_frontend) \
  $(_gh_pair GH_TOKEN github_token_frontend)

write_env dev-backend \
  OPENROUTER_API_KEY=llm_key_dev_backend \
  GITLAB_TOKEN=gitlab_token_backend \
  $(_gh_pair GITHUB_TOKEN github_token_backend) \
  $(_gh_pair GH_TOKEN github_token_backend)

write_env reviewer \
  OPENROUTER_API_KEY=llm_key_reviewer \
  GITLAB_TOKEN=gitlab_token_readonly \
  $(_gh_pair GITHUB_TOKEN github_token_readonly) \
  $(_gh_pair GH_TOKEN github_token_readonly)
  # SOCRATICODE_API_KEY not required — DECISION-6 local AGPL (MCP uses Ollama+Qdrant)

write_env devops \
  OPENROUTER_API_KEY=llm_key_devops \
  GITLAB_TOKEN=gitlab_token_ci \
  $(_gh_pair GITHUB_TOKEN github_token_ci) \
  $(_gh_pair GH_TOKEN github_token_ci)

write_env qa \
  OPENROUTER_API_KEY=llm_key_qa \
  GITLAB_TOKEN=gitlab_token_qa \
  $(_gh_pair GITHUB_TOKEN github_token_qa) \
  $(_gh_pair GH_TOKEN github_token_qa)

# Shared non-secret defaults
for agent in coordinator dev-frontend dev-backend reviewer devops qa; do
  f="hermes-data/$agent/.env"
  grep -q '^GITLAB_HOST=' "$f" 2>/dev/null || echo "GITLAB_HOST=${GITLAB_BASE_URL:-https://gitlab.com}" >> "$f"
  if [ -n "${TELEGRAM_ALLOWED_USERS:-}" ] && [ "$agent" = "coordinator" ]; then
    grep -q '^TELEGRAM_ALLOWED_USERS=' "$f" 2>/dev/null || \
      echo "TELEGRAM_ALLOWED_USERS=$TELEGRAM_ALLOWED_USERS" >> "$f"
  fi
done

# LLM_MODE=local (DECISION-15): all 6 agents talk to inference-ollama via
# provider:custom (shared queue on one GPU). Hermes accepts a dummy API key.
if [ "${LLM_MODE:-cloud}" = "local" ]; then
  for agent in coordinator dev-frontend dev-backend reviewer qa devops; do
    f="hermes-data/$agent/.env"
    grep -q '^CUSTOM_API_KEY=' "$f" 2>/dev/null && sed -i.bak '/^CUSTOM_API_KEY=/d' "$f" && rm -f "${f}.bak"
    echo "CUSTOM_API_KEY=ollama" >> "$f"
    # Drop empty/placeholder OpenRouter key so Hermes prefers custom
    if grep -q '^OPENROUTER_API_KEY=$' "$f" 2>/dev/null || \
       grep -q 'sk-placeholder' "$f" 2>/dev/null; then
      sed -i.bak '/^OPENROUTER_API_KEY=/d' "$f" && rm -f "${f}.bak"
    fi
  done
  echo "LLM_MODE=local → CUSTOM_API_KEY=ollama for all 6 agents"
  # Keep config.local-free.yaml model names aligned with LOCAL_LLM_MODEL.
  if [ -x "$ROOT/scripts/sync-local-llm-model.sh" ] || [ -f "$ROOT/scripts/sync-local-llm-model.sh" ]; then
    bash "$ROOT/scripts/sync-local-llm-model.sh"
  fi
fi

for agent in coordinator dev-frontend dev-backend reviewer devops qa; do
  chmod 644 "hermes-data/$agent/.env" 2>/dev/null || true
done

echo "Hermes .env files ready. Ensure TELEGRAM_ALLOWED_USERS is set for coordinator."
