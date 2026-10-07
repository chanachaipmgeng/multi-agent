#!/usr/bin/env bash
# Operator harness for EMAW verification skill.
# Location: .cursor/skills/verify-emaw/bin/ → repo root is ../../../../
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$ROOT"

RUN_ID="${VERIFY_EMAW_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVIDENCE="$ROOT/.cursor/skills/verify-emaw/evidence/$RUN_ID"
mkdir -p "$EVIDENCE"
STATE="$ROOT/.cursor/skills/verify-emaw/.last-run"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8700}"
API_KEY="$(tr -d '\r\n' < secrets/hermes_api_key 2>/dev/null || true)"
ADMIN_UID="${VERIFY_EMAW_USER_ID:-987654321}"

log() { printf '%s\n' "$*" | tee -a "$EVIDENCE/run.log"; }

doctor() {
  local fail=0
  check() {
    local name="$1"; shift
    if "$@" >>"$EVIDENCE/doctor.log" 2>&1; then
      log "OK  $name"
    else
      log "FAIL $name"
      fail=1
    fi
  }
  : >"$EVIDENCE/doctor.log"
  check "gateway healthz" curl -fsS "$GATEWAY_URL/healthz"
  check "gateway metrics" curl -fsS "$GATEWAY_URL/metrics"
  check "phase3-check" bash scripts/phase3-check.sh
  if curl -fsS http://127.0.0.1:9090/-/healthy >/dev/null 2>&1; then
    check "prometheus healthy" curl -fsS http://127.0.0.1:9090/-/healthy
    check "alertmanager healthy" curl -fsS http://127.0.0.1:9093/-/healthy
    check "grafana http 200" sh -c 'code=$(curl -fsS -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/login); [ "$code" = "200" ]'
  else
    log "SKIP observability (Prometheus not up — run make up-observability)"
  fi
  echo "$RUN_ID" >"$STATE"
  [ "$fail" -eq 0 ]
}

drive_gateway_health() {
  curl -fsS "$GATEWAY_URL/healthz" | tee "$EVIDENCE/gateway-healthz.json"
  curl -fsS "$GATEWAY_URL/metrics" | tee "$EVIDENCE/gateway-metrics.txt" >/dev/null
  head -n 40 "$EVIDENCE/gateway-metrics.txt" >"$EVIDENCE/gateway-metrics.head.txt"
  grep -q webhook_received_total "$EVIDENCE/gateway-metrics.txt"
  log "PROOF gateway-health: healthz + metrics captured"
}

drive_phase3_smoke() {
  bash scripts/phase3-check.sh | tee "$EVIDENCE/phase3-check.txt"
  grep -q "phase3-check: PASSED" "$EVIDENCE/phase3-check.txt"
  log "PROOF phase3-smoke: PASSED"
}

drive_observability() {
  curl -fsS http://127.0.0.1:9090/-/healthy | tee "$EVIDENCE/prometheus-healthy.txt"
  curl -fsS http://127.0.0.1:9093/-/healthy | tee "$EVIDENCE/alertmanager-healthy.txt"
  curl -fsS "http://127.0.0.1:9090/api/v1/targets" | tee "$EVIDENCE/prometheus-targets.json" >/dev/null
  grep -q 'webhook-gateway' "$EVIDENCE/prometheus-targets.json"
  AUTH=$(printf '%s' 'emaw:emaw-grafana-dev' | base64 | tr -d '\n')
  curl -fsS -H "Authorization: Basic $AUTH" "http://127.0.0.1:3000/api/search" \
    | tee "$EVIDENCE/grafana-search.json" >/dev/null
  grep -q "EMAW Operations" "$EVIDENCE/grafana-search.json"
  grep -q "EMAW Security" "$EVIDENCE/grafana-search.json"
  log "PROOF observability: prom/am healthy + dashboard titles present"
}

drive_webhook_enqueue() {
  UUID="verify-emaw-$RUN_ID"
  bash scripts/send-test-webhook.sh issue --uuid "$UUID" | tee "$EVIDENCE/webhook-response.txt"
  grep -Eq 'HTTP 200|queued|duplicate|recorded' "$EVIDENCE/webhook-response.txt"
  log "PROOF webhook-enqueue: response captured for uuid=$UUID"
}

drive_pause_control() {
  [ -n "$API_KEY" ] || { log "FAIL missing secrets/hermes_api_key"; return 1; }
  curl -fsS -X POST "$GATEWAY_URL/internal/control/pause" \
    -H "Authorization: Bearer $API_KEY" \
    -H "X-EMAW-User-Id: $ADMIN_UID" \
    -H "Content-Type: application/json" \
    -d '{"agent":"all"}' | tee "$EVIDENCE/pause.json"
  echo "paused" >"$EVIDENCE/pause.flag"
  curl -fsS -X POST "$GATEWAY_URL/internal/control/resume" \
    -H "Authorization: Bearer $API_KEY" \
    -H "X-EMAW-User-Id: $ADMIN_UID" \
    -H "Content-Type: application/json" \
    -d '{"agent":"all"}' | tee "$EVIDENCE/resume.json"
  rm -f "$EVIDENCE/pause.flag"
  log "PROOF pause-control: pause then resume OK"
}

cleanup() {
  if [ -f "$EVIDENCE/pause.flag" ] && [ -n "$API_KEY" ]; then
    curl -fsS -X POST "$GATEWAY_URL/internal/control/resume" \
      -H "Authorization: Bearer $API_KEY" \
      -H "X-EMAW-User-Id: $ADMIN_UID" \
      -H "Content-Type: application/json" \
      -d '{"agent":"all"}' >/dev/null 2>&1 || true
    rm -f "$EVIDENCE/pause.flag"
  fi
  if [ "${VERIFY_EMAW_STOP_OBS:-0}" = "1" ]; then
    docker compose --profile observability stop \
      grafana prometheus alertmanager loki tempo otel-collector promtail 2>/dev/null || true
  fi
  log "cleanup done; evidence kept at $EVIDENCE"
  echo "$EVIDENCE"
}

cmd="${1:-}"
case "$cmd" in
  doctor) doctor ;;
  drive)
    feature="${2:-}"
    echo "$RUN_ID" >"$STATE"
    case "$feature" in
      gateway-health) drive_gateway_health ;;
      phase3-smoke) drive_phase3_smoke ;;
      observability) drive_observability ;;
      webhook-enqueue) drive_webhook_enqueue ;;
      pause-control) drive_pause_control ;;
      *) echo "unknown feature: $feature"; exit 2 ;;
    esac
    ;;
  cleanup) cleanup ;;
  *)
    echo "usage: verify-emaw.sh doctor|drive <feature-id>|cleanup"
    exit 2
    ;;
esac
