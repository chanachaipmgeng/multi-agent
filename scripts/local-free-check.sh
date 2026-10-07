#!/usr/bin/env bash
# Local-free smoke check (DECISION-15 + DECISION-6).
# Expects: make up-local-free (+ make local-llm-pull once).
#
# Usage: scripts/local-free-check.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.local-free.yml)
OLLAMA_PORT="${INFERENCE_OLLAMA_PORT:-11436}"
MODEL="${LOCAL_LLM_MODEL:-qwen2.5-coder:7b}"
AGENTS=(coordinator dev-frontend dev-backend reviewer qa devops)
ADAPTERS=(router adapter-dev-frontend adapter-dev-backend adapter-reviewer adapter-qa adapter-devops)

pass() { printf '  \033[32m✔\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; failed=1; }
failed=0

echo "== compose local-free services =="
for svc in inference-ollama socraticode-ollama socraticode-qdrant minio "${AGENTS[@]}" "${ADAPTERS[@]}"; do
  if docker compose "${COMPOSE_FILES[@]}" --profile agents --profile socraticode --profile onprem-llm \
       ps --status running 2>/dev/null | grep -qE "(${svc}|emaw-${svc}|emaw-inference-ollama|emaw-minio)"; then
    pass "$svc running"
  else
    # container_name may differ from service name
    if docker ps --format '{{.Names}}' | grep -qE "^(emaw-${svc}|${svc}|emaw-inference-ollama|emaw-minio|emaw-router)$"; then
      pass "$svc running (by container name)"
    else
      fail "$svc not running — run: make up-local-free"
    fi
  fi
done

echo "== inference Ollama http://127.0.0.1:${OLLAMA_PORT} =="
tags="$(curl -fsS --max-time 5 "http://127.0.0.1:${OLLAMA_PORT}/api/tags" 2>/dev/null)" || tags=""
if [ -n "$tags" ]; then
  pass "inference Ollama /api/tags reachable"
  if printf '%s' "$tags" | grep -q "\"name\":\"${MODEL}"; then
    pass "model present: ${MODEL}"
  else
    fail "missing model ${MODEL} — run: make local-llm-pull"
  fi
else
  fail "inference Ollama not reachable on 127.0.0.1:${OLLAMA_PORT}"
fi

echo "== Hermes model.provider (local-free agents) =="
for agent in "${AGENTS[@]}"; do
  cname="emaw-${agent}"
  if ! docker ps --format '{{.Names}}' | grep -qx "$cname"; then
    fail "$cname not running"
    continue
  fi
  provider="$(docker exec "$cname" hermes config get model.provider 2>/dev/null || true)"
  if [ "$provider" = "custom" ]; then
    pass "$cname model.provider=custom"
  else
    fail "$cname model.provider='${provider}' (expected custom) — is config.local-free.yaml mounted?"
  fi
done

echo "== SocratiCode infra =="
if [ -x "$ROOT/scripts/socraticode-infra-check.sh" ] || [ -f "$ROOT/scripts/socraticode-infra-check.sh" ]; then
  if bash "$ROOT/scripts/socraticode-infra-check.sh"; then
    pass "socraticode-infra-check OK"
  else
    fail "socraticode-infra-check failed"
  fi
fi

echo "== reviewer MCP readiness =="
if docker exec emaw-reviewer sh -c 'test -x /opt/data/.npm/_npx/*/node_modules/.bin/socraticode' 2>/dev/null; then
  pass "socraticode package cached under /opt/data/.npm/_npx"
elif docker exec emaw-reviewer sh -c 'ls /opt/data/.npm/_npx/*/node_modules/socraticode/package.json' >/dev/null 2>&1; then
  pass "socraticode package present in npm cache"
else
  printf '  \033[33m☐\033[0m socraticode not cached yet — first MCP spawn will npx-install\n'
fi
if docker exec emaw-reviewer sh -c 'curl -fsS --max-time 3 http://socraticode-ollama:11434/api/tags >/dev/null && curl -fsS --max-time 3 http://socraticode-qdrant:6333/readyz >/dev/null'; then
  pass "reviewer → socraticode-ollama + qdrant DNS OK"
else
  fail "reviewer cannot reach socraticode-ollama or qdrant on workers network"
fi
if docker exec emaw-reviewer sh -c 'grep -q "mcp_servers:" /opt/data/config.yaml && grep -q "command: npx" /opt/data/config.yaml'; then
  pass "reviewer config has mcp_servers.socraticode (npx)"
else
  fail "reviewer config missing enabled mcp_servers.socraticode"
fi

if [ "$failed" -ne 0 ]; then
  echo
  echo "local-free check FAILED"
  exit 1
fi
echo
echo "local-free check OK"
exit 0
