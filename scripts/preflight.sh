#!/usr/bin/env bash
# EMAW preflight — placeholder / dispatcher / org.yaml checks (no secret values printed).
# Usage: scripts/preflight.sh [--require-cloud-keys]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ok=0; missing=0; warnings=0
pass() { printf '  \033[32m✔\033[0m %s\n' "$1"; ok=$((ok+1)); }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; missing=$((missing+1)); }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; warnings=$((warnings+1)); }
info() { printf '  · %s\n' "$1"; }

REQUIRE_CLOUD=0
for arg in "$@"; do
  case "$arg" in
    --require-cloud-keys) REQUIRE_CLOUD=1 ;;
  esac
done

# Load .env without printing values
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi

LLM_MODE="${LLM_MODE:-cloud}"
ADAPTER_DISPATCHER="${ADAPTER_DISPATCHER:-dryrun}"

is_placeholder() {
  local f="$1" needle="$2"
  [ -f "$f" ] || { echo missing; return; }
  local val
  val="$(tr -d '\r\n' < "$f" | head -c 200)"
  [ -z "$val" ] && { echo empty; return; }
  case "$val" in
    *"$needle"*) echo placeholder ;;
    *) echo ok ;;
  esac
}

echo "== LLM keys (secrets/llm_key_*) =="
llm_fail=0
for role in coordinator dev_frontend dev_backend reviewer devops qa; do
  f="secrets/llm_key_${role}"
  st="$(is_placeholder "$f" "placeholder")"
  case "$st" in
    ok) pass "llm_key_${role} set (non-placeholder)" ;;
    placeholder)
      if [ "$LLM_MODE" = "cloud" ] || [ "$REQUIRE_CLOUD" = "1" ]; then
        fail "llm_key_${role} still placeholder (LLM_MODE=${LLM_MODE})"
        llm_fail=1
      else
        warn "llm_key_${role} still placeholder (ok for LLM_MODE=local)"
      fi
      ;;
    *) fail "llm_key_${role} ${st}" ;;
  esac
done
if [ "$REQUIRE_CLOUD" = "1" ] && [ "$llm_fail" = "1" ]; then
  info "set SECRET_LLM_KEY_* in .env then: make secrets-dev && make up-cloud"
fi

echo "== Telegram / GitLab placeholders =="
tg="$(is_placeholder secrets/telegram_token "replace-with-botfather")"
case "$tg" in
  ok) pass "telegram_token set" ;;
  placeholder|empty|missing) warn "telegram_token ${tg} — Flow C blocked until BotFather token" ;;
esac
allowed="${TELEGRAM_ALLOWED_USERS:-}"
if [ -z "$allowed" ] || [ "$allowed" = "987654321" ]; then
  warn "TELEGRAM_ALLOWED_USERS unset or still example 987654321"
else
  pass "TELEGRAM_ALLOWED_USERS set"
fi
for f in secrets/gitlab_token_readonly secrets/gitlab_token_frontend secrets/gitlab_token_backend \
         secrets/gitlab_token_qa secrets/gitlab_token_ci; do
  base="$(basename "$f")"
  st="$(is_placeholder "$f" "placeholder")"
  case "$st" in
    ok) pass "${base} set" ;;
    *) warn "${base} ${st}" ;;
  esac
done

echo "== Adapter dispatcher =="
info "ADAPTER_DISPATCHER in .env → ${ADAPTER_DISPATCHER}"
if docker inspect emaw-adapter-dev-backend >/dev/null 2>&1; then
  running="$(docker inspect -f '{{.State.Running}}' emaw-adapter-dev-backend 2>/dev/null || echo false)"
  if [ "$running" = "true" ]; then
    live="$(docker exec emaw-adapter-dev-backend printenv DISPATCHER 2>/dev/null || echo unknown)"
    if [ "$live" = "dryrun" ]; then
      fail "emaw-adapter-dev-backend DISPATCHER=dryrun while agents expected live — run: make restart-adapters"
    elif [ "$live" = "hermes_api" ] || [ "$live" = "hermes_cli" ] || [ "$live" = "http" ]; then
      pass "emaw-adapter-dev-backend DISPATCHER=${live}"
    else
      warn "emaw-adapter-dev-backend DISPATCHER=${live}"
    fi
  else
    warn "emaw-adapter-dev-backend not running"
  fi
else
  warn "emaw-adapter-dev-backend container missing"
fi

echo "== config/org.yaml (DECISION placeholders) =="
if [ -f config/org.yaml ]; then
  pending="$(grep -c '<to confirm>' config/org.yaml 2>/dev/null || echo 0)"
  if [ "${pending:-0}" -gt 0 ]; then
    info "org.yaml still has ${pending} '<to confirm>' field(s) — see docs/org-unblock.md"
  else
    pass "org.yaml has no '<to confirm>' placeholders"
  fi
else
  fail "config/org.yaml missing"
fi

echo
echo "$ok passed, $warnings warnings, $missing failed."
[ "$missing" -eq 0 ]
