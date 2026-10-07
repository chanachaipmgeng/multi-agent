#!/usr/bin/env bash
# D0.2 / D0.3 — configure host-installed Hermes Agent for Phase 0 (single agent on WSL2/Linux).
#
# Real Hermes v0.21.5 keys (DECISION-1 / docs/hermes-capability-check.md):
#   UPPER_SNAKE → ~/.hermes/.env via `hermes config set`
#   dotted keys → ~/.hermes/config.yaml
#
# Usage: TELEGRAM_ALLOWED_USERS=987654321 scripts/hermes-configure.sh
# Secrets are read from ./secrets/* (make secrets-decrypt / secrets-dev).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v hermes >/dev/null || {
  echo "hermes CLI not found — install: https://github.com/NousResearch/hermes-agent"
  echo "  curl -fsSLO https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh && bash install.sh"
  exit 1
}
[ -n "${TELEGRAM_ALLOWED_USERS:-}" ] || {
  echo "set TELEGRAM_ALLOWED_USERS=<telegram user id[,id...]> (checklist D0.3)"
  exit 1
}

secret() { [ -s "secrets/$1" ] && cat "secrets/$1" || true; }

echo "→ sandbox: terminal.backend=docker (checklist #1, P2) — host/WSL2 path"
hermes config set terminal.backend docker
# Prefer the official sandbox image when using docker backend
hermes config set terminal.docker_image "${HERMES_SANDBOX_IMAGE:-nousresearch/hermes-sandbox:desktop}" || true
hermes config set terminal.docker_mount_cwd_to_workspace true || true

echo "→ approvals: smart + platform deny rules (never push main, no prune)"
hermes config set approvals.mode smart
# deny list is YAML; set via a small python/heredoc into config if needed —
# documented in hermes-data/*/config.yaml; host install can copy those deny globs.

echo "→ worktree isolation"
hermes config set worktree true || true
hermes config set worktree_sync true || true

echo "→ telegram allowlist: $TELEGRAM_ALLOWED_USERS"
hermes config set TELEGRAM_ALLOWED_USERS "$TELEGRAM_ALLOWED_USERS"
tg="$(secret telegram_token)"
if [ -n "$tg" ]; then
  hermes config set TELEGRAM_BOT_TOKEN "$tg"
else
  echo "  (secrets/telegram_token empty — skipped)"
fi

echo "→ gitlab (for glab / API from sandbox)"
hermes config set GITLAB_HOST "${GITLAB_BASE_URL:-https://gitlab.com}"
gl="$(secret gitlab_token_readonly)"
if [ -n "$gl" ]; then
  hermes config set GITLAB_TOKEN "$gl"
else
  echo "  (secrets/gitlab_token_readonly empty — skipped; Phase 1)"
fi

echo "→ API server (for queue-adapter DISPATCHER=hermes_api)"
hermes config set API_SERVER_ENABLED true
hermes config set API_SERVER_HOST "${API_SERVER_HOST:-127.0.0.1}"
hermes config set API_SERVER_PORT "${API_SERVER_PORT:-8642}"
api_key="$(secret hermes_api_key)"
if [ -n "$api_key" ]; then
  hermes config set API_SERVER_KEY "$api_key"
else
  echo "  (secrets/hermes_api_key empty — generate one before enabling hermes_api dispatcher)"
fi

# LLM key: prefer coordinator / generic openrouter secret file names
for name in llm_key_coordinator llm_key_dev_backend openrouter_api_key; do
  k="$(secret "$name")"
  if [ -n "$k" ]; then
    hermes config set OPENROUTER_API_KEY "$k"
    echo "→ OPENROUTER_API_KEY from secrets/$name"
    break
  fi
done

echo "→ verifying terminal.backend"
backend="$(hermes config get terminal.backend 2>/dev/null || true)"
# strip quotes/whitespace
backend="$(echo "$backend" | tr -d '\"' | tr -d '[:space:]')"
case "$backend" in
  docker) echo "  terminal.backend=docker ✔" ;;
  *) echo "  terminal.backend is '$backend' (expected docker on host install) ✘"; exit 1 ;;
esac

cat <<'EOF'

Done. Remaining manual steps:
  hermes setup                      # primary + fallback provider (D0.2, checklist #6)
  hermes chat --oneshot -Q -q "id"  # or: hermes run "id" if available — sandbox uid ≠ host
  make skills-sync                  # promote skills/ → hermes-data/*/skills/emaw/
  # copy hermes-data/<agent>/skills into ~/.hermes/skills/ (or symlink) for host install
  hermes gateway run                # Telegram bot + API server :8642

Queue-adapter (compose):
  ADAPTER_DISPATCHER=hermes_api
  HERMES_API_URL=http://127.0.0.1:8642
  # or hermes_cli with:
  # HERMES_CLI_TEMPLATE='hermes chat --oneshot -Q --query-file {prompt_file} -s {skill}'
EOF
