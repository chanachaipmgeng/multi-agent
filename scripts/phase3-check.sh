#!/usr/bin/env bash
# Phase 3 smoke checks (local): router, adapters, control keys, gateway internal.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
check() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "OK  $name"
  else
    echo "FAIL $name"
    fail=1
  fi
}

running() {
  local name="$1"
  [ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || echo false)" = "true" ]
}

check "router running" running emaw-router
for role in dev-frontend dev-backend reviewer qa devops; do
  check "adapter-$role running" running "emaw-adapter-$role"
done
for agent in coordinator dev-frontend dev-backend reviewer qa devops; do
  check "agent $agent running" running "emaw-$agent"
done

check "gateway healthz" curl -fsS http://127.0.0.1:8700/healthz
check "minio live" curl -fsS http://127.0.0.1:9000/minio/health/live

# Pause / resume round-trip via redis if available
redis_cid="$(
  docker ps --format '{{.ID}} {{.Names}}' \
    | awk '/emaw-redis|multi-agent-redis|^[a-f0-9]+ .*redis/ {print $1; exit}'
)"
if [ -n "${redis_cid:-}" ] && running emaw-router; then
  docker exec "$redis_cid" redis-cli SET emaw:control:pause:all 1 >/dev/null 2>&1 || true
  docker exec "$redis_cid" redis-cli DEL emaw:control:pause:all >/dev/null 2>&1 || true
  echo "OK  pause key set/clear (best-effort)"
fi

# Config validates
check "compose config" docker compose -f docker-compose.yml config -q
check "local-free config" docker compose -f docker-compose.yml -f docker-compose.local-free.yml config -q
if [ -f docker-compose.prod.yml ]; then
  check "prod config" docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q
fi

if [ "$fail" -ne 0 ]; then
  echo "phase3-check: FAILED"
  exit 1
fi
echo "phase3-check: PASSED"
