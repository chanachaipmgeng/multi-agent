#!/usr/bin/env bash
# D0.2 / D0.3 — configure the host-installed Hermes Agent for Phase 0 (single agent on WSL2).
#
# Config keys follow the source documents; verify against `hermes config list` on your
# version (design DECISION-1 / ASSUMPTION A1) and adjust if a key is named differently.
#
# Usage: TELEGRAM_ALLOWED_USERS=987654321 scripts/hermes-configure.sh
# Secrets (telegram token, gitlab token) are read from ./secrets/* produced by make secrets-decrypt.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v hermes >/dev/null || { echo "hermes CLI not found — install: https://github.com/NousResearch/hermes-agent"; exit 1; }
[ -n "${TELEGRAM_ALLOWED_USERS:-}" ] || { echo "set TELEGRAM_ALLOWED_USERS=<telegram user id[,id...]> (checklist D0.3)"; exit 1; }

secret() { [ -s "secrets/$1" ] && cat "secrets/$1" || true; }

echo "→ sandbox: every shell command runs in Docker (checklist #1, P2)"
hermes config set terminal.backend docker

echo "→ telegram allowlist: $TELEGRAM_ALLOWED_USERS"
hermes config set telegram.allowed_users "$TELEGRAM_ALLOWED_USERS"
tg="$(secret telegram_token)"
if [ -n "$tg" ]; then hermes config set telegram.token "$tg"; else echo "  (secrets/telegram_token empty — skipped)"; fi

echo "→ gitlab"
hermes config set gitlab.base_url "${GITLAB_BASE_URL:-https://gitlab.com}"
gl="$(secret gitlab_token_readonly)"
if [ -n "$gl" ]; then hermes config set gitlab.token "$gl"; else echo "  (secrets/gitlab_token_readonly empty — skipped; Phase 1)"; fi

echo "→ verifying"
backend="$(hermes config get terminal.backend 2>/dev/null || true)"
[ "$backend" = "docker" ] && echo "  terminal.backend=docker ✔" || { echo "  terminal.backend is '$backend' ✘"; exit 1; }

cat <<'EOF'

Done. Remaining manual steps:
  hermes setup                      # choose primary + fallback LLM provider (D0.2, checklist #6)
  hermes run "id"                   # must print the sandbox uid, not your host user (checklist #1)
  make skills-sync                  # copy skills/ into hermes-data/<agent>/skills/ (D0.5)
  hermes gateway run                # start Telegram bot
EOF
