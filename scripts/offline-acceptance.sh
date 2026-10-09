#!/usr/bin/env bash
# End-to-end green check after up-offline / up-local-free + console + observability.
# See docs/offline-airgap.md Phase B / F.
#
# Usage: scripts/offline-acceptance.sh
# Env:   REQUIRE_CONSOLE=1 (default)  REQUIRE_OBS=1 (default)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REQUIRE_CONSOLE="${REQUIRE_CONSOLE:-1}"
REQUIRE_OBS="${REQUIRE_OBS:-1}"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:${GATEWAY_PORT:-8700}}"

pass() { printf '  \033[32m✔\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; failed=1; }
failed=0

echo "== offline-acceptance =="

echo "-- local-free-check --"
if bash scripts/local-free-check.sh; then
  pass "local-free-check"
else
  fail "local-free-check"
fi

echo "-- phase3-check --"
if bash scripts/phase3-check.sh; then
  pass "phase3-check"
else
  fail "phase3-check"
fi

echo "-- gateway --"
if curl -fsS --max-time 5 "$GATEWAY_URL/healthz" >/dev/null; then
  pass "gateway /healthz"
else
  fail "gateway /healthz"
fi

echo "-- operator console :8088 --"
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8088/ 2>/dev/null || true)"
code="${code:-000}"
# curl may print "000" on hard connect failure; normalize empty/garbage
case "$code" in
  [12345][0-9][0-9]) ;;
  *) code="000" ;;
esac
if [ "$code" = "200" ]; then
  pass "console HTTP $code"
elif [ "$REQUIRE_CONSOLE" = "1" ]; then
  fail "console HTTP $code (need make up-console / up-offline)"
else
  printf '  \033[33m☐\033[0m console HTTP %s (optional)\n' "$code"
fi

echo "-- observability --"
if curl -fsS --max-time 5 http://127.0.0.1:9090/-/healthy >/dev/null 2>&1; then
  pass "prometheus healthy"
  if curl -fsS --max-time 5 http://127.0.0.1:3000/login >/dev/null 2>&1 \
     || curl -fsS --max-time 5 -o /dev/null -w '' http://127.0.0.1:3000/ 2>/dev/null; then
    pass "grafana reachable"
  elif [ "$REQUIRE_OBS" = "1" ]; then
    fail "grafana not reachable"
  fi
elif [ "$REQUIRE_OBS" = "1" ]; then
  fail "prometheus not up (make up-observability / up-offline)"
else
  printf '  \033[33m☐\033[0m observability skipped\n'
fi

echo "-- simulate-operator create-task --"
if bash scripts/simulate-operator.sh create-task >/tmp/emaw-offline-accept-task.json 2>/tmp/emaw-offline-accept-task.err; then
  if grep -Eq 'task_id|idempotency|"ok"|created|queued' /tmp/emaw-offline-accept-task.json 2>/dev/null \
     || [ -s /tmp/emaw-offline-accept-task.json ]; then
    pass "simulate-operator create-task"
  else
    # Some gateways return 200 with JSON body — accept non-empty success exit
    pass "simulate-operator create-task (exit 0)"
  fi
else
  fail "simulate-operator create-task (see /tmp/emaw-offline-accept-task.err)"
  head -n 20 /tmp/emaw-offline-accept-task.err 2>/dev/null || true
fi

echo
if [ "$failed" -ne 0 ]; then
  echo "offline-acceptance FAILED"
  exit 1
fi
echo "offline-acceptance PASSED"
exit 0
