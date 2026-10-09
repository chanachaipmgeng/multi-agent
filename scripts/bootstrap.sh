#!/usr/bin/env bash
# One-shot local platform bootstrap: prereqs → secrets → venv → up → smoke.
# Usage: scripts/bootstrap.sh   (or: make bootstrap)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== EMAW bootstrap =="

echo "-- prereqs"
make prereqs

if [ ! -f .env ]; then
  cp .env.example .env
  echo "  created .env from .env.example — edit SECRET_* before agents / cloud LLM"
else
  echo "  .env already present"
fi

if [ ! -f config/rbac.yaml ]; then
  cp config/rbac.example.yaml config/rbac.yaml
  echo "  created config/rbac.yaml from example"
else
  echo "  config/rbac.yaml already present"
fi

echo "-- secrets-dev (plaintext .env → ./secrets/*)"
make secrets-dev

echo "-- venv (gateway + adapter)"
make venv

echo "-- pre-commit hooks (best-effort)"
make hooks || echo "  ! hooks skipped (install pre-commit later with: make hooks)"

echo "-- platform stack"
make up

echo "-- wait for gateway readyz"
for i in $(seq 1 60); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${GATEWAY_PORT:-8700}/readyz" >/dev/null 2>&1; then
    echo "  gateway ready"
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "  gateway not ready after 60s — check: docker compose logs webhook-gateway" >&2
    exit 1
  fi
  sleep 1
done

echo "-- migrate (idempotent if initdb already applied)"
make migrate || echo "  ! migrate skipped or already applied"

echo "-- webhook-test"
make webhook-test

cat <<'EOF'

== bootstrap complete ==

Next steps (optional):
  make up-console          # Operator Console → http://127.0.0.1:8088  (tasks / HITL /audit)
  make up-observability    # Grafana :3000 · Loki · Prometheus
  make up-agents           # Hermes profiles (needs SECRET_HERMES_API_KEY + LLM keys)
  make up-local-free       # all 6 agents on local Ollama (no OpenRouter)
  make dev-tunnel          # Quick Tunnel for GitLab webhooks before DECISION-5 domain
  make simulate-operator CMD=create-task   # API-only drills without Telegram

Docs: docs/local-dev.md · docs/operator-console.md · docs/runbooks/tunnel.md
EOF
