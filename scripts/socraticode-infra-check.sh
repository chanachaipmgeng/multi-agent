#!/usr/bin/env bash
# Phase 2 — smoke-check SocratiCode compose infra (no license required).
# Expects: make up-socraticode (or containers already healthy).
#
# Usage: scripts/socraticode-infra-check.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

OLLAMA_PORT="${SOCRATICODE_OLLAMA_PORT:-11435}"
QDRANT_PORT="${SOCRATICODE_QDRANT_HTTP_PORT:-16333}"
EMBED_MODEL="${SOCRATICODE_EMBED_MODEL:-nomic-embed-text}"

pass() { printf '  \033[32m✔\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; failed=1; }
failed=0

echo "== compose profile socraticode =="
if docker compose --profile socraticode ps --status running 2>/dev/null | grep -q socraticode-ollama; then
  pass "socraticode-ollama running"
else
  fail "socraticode-ollama not running — run: make up-socraticode"
fi
if docker compose --profile socraticode ps --status running 2>/dev/null | grep -q socraticode-qdrant; then
  pass "socraticode-qdrant running"
else
  fail "socraticode-qdrant not running — run: make up-socraticode"
fi

echo "== Ollama http://127.0.0.1:${OLLAMA_PORT} =="
tags="$(curl -fsS --max-time 5 "http://127.0.0.1:${OLLAMA_PORT}/api/tags" 2>/dev/null)" || tags=""
if [ -n "$tags" ]; then
  pass "Ollama /api/tags reachable"
  if printf '%s' "$tags" | grep -q "\"name\":\"${EMBED_MODEL}"; then
    pass "embedding model present: ${EMBED_MODEL}"
  else
    fail "missing model ${EMBED_MODEL} — pull: docker exec socraticode-ollama ollama pull ${EMBED_MODEL}"
  fi
else
  fail "Ollama not reachable on 127.0.0.1:${OLLAMA_PORT}"
fi

echo "== Qdrant http://127.0.0.1:${QDRANT_PORT} =="
ready="$(curl -fsS --max-time 5 "http://127.0.0.1:${QDRANT_PORT}/readyz" 2>/dev/null)" || ready=""
if [ -n "$ready" ]; then
  pass "Qdrant /readyz: ${ready}"
else
  fail "Qdrant not reachable on 127.0.0.1:${QDRANT_PORT}"
fi

echo "== in-compose DNS (workers network) =="
pass "reviewer MCP should use http://socraticode-ollama:11434 and http://socraticode-qdrant:6333"
pass "host-side MCP should use http://127.0.0.1:${OLLAMA_PORT} and http://127.0.0.1:${QDRANT_PORT}"

if [ "$failed" -ne 0 ]; then
  echo
  echo "SocratiCode infra check FAILED"
  exit 1
fi
echo
echo "SocratiCode infra check OK (local AGPL — no API key; enable reviewer MCP via compose)"
exit 0
