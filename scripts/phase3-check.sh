#!/usr/bin/env bash
# Phase 3 smoke checks (local): router, adapters, control keys, gateway internal.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
check() {
  local name="$1"; shift
  if "$@"; then echo "OK  $name"; else echo "FAIL $name"; fail=1; fi
}

check "router running" docker inspect -f '{{.State.Running}}' emaw-router 2>/dev/null | grep -q true
for role in dev-frontend dev-backend reviewer qa devops; do
  check "adapter-$role running" docker inspect -f '{{.State.Running}}' "emaw-adapter-$role" 2>/dev/null | grep -q true
done
for agent in coordinator dev-frontend dev-backend reviewer qa devops; do
  check "agent $agent running" docker inspect -f '{{.State.Running}}' "emaw-$agent" 2>/dev/null | grep -q true
done

check "gateway healthz" curl -fsS http://127.0.0.1:8700/healthz >/dev/null
check "minio live" curl -fsS http://127.0.0.1:9000/minio/health/live >/dev/null

# Pause / resume round-trip via redis if available
if docker exec emaw-router true 2>/dev/null; then
  docker exec "$(docker ps -qf name=emaw-redis || docker ps -qf ancestor=redis:7-alpine | head -1)" \
    redis-cli SET emaw:control:pause:all 1 >/dev/null 2>&1 || true
  docker exec "$(docker ps -qf name=emaw-redis || docker ps -qf ancestor=redis:7-alpine | head -1)" \
    redis-cli DEL emaw:control:pause:all >/dev/null 2>&1 || true
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
