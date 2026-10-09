#!/usr/bin/env bash
# Simulate operator → coordinator control-plane calls (no Telegram Bot API).
# Usage:
#   scripts/simulate-operator.sh create-task [fixture.json]
#   scripts/simulate-operator.sh list-tasks [project] [state]
#   scripts/simulate-operator.sh list-approvals [pending|decided|approved|rejected]
#   scripts/simulate-operator.sh decide <nonce> [approved|rejected]
#   scripts/simulate-operator.sh audit --task-id ID | --trace-id ID
#   make simulate-operator CMD=create-task
#
# Auth: secrets/hermes_api_key + EMAW_USER_ID (default 987654321 from rbac.example)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:${GATEWAY_PORT:-8700}}"
FIXDIR="$ROOT/webhook-gateway/tests/fixtures/operator"
USER_ID="${EMAW_USER_ID:-987654321}"
KEY_FILE="$ROOT/secrets/hermes_api_key"
API_KEY="${HERMES_API_KEY:-}"
[ -z "$API_KEY" ] && [ -f "$KEY_FILE" ] && API_KEY="$(cat "$KEY_FILE")"
[ -n "$API_KEY" ] || { echo "missing HERMES_API_KEY or secrets/hermes_api_key — run make secrets-dev" >&2; exit 1; }

CMD="${1:-}"
shift || true

hdr=(-H "Authorization: Bearer ${API_KEY}" -H "X-EMAW-User-Id: ${USER_ID}" -H "Content-Type: application/json")

_curl() {
  curl -sS "${hdr[@]}" "$@"
}

case "$CMD" in
  create-task)
    FIX="${1:-$FIXDIR/create-task-feature.json}"
    [ -f "$FIX" ] || { echo "fixture not found: $FIX" >&2; exit 1; }
    # Inject unique idempotency_key when null so repeats succeed
    BODY="$(python3 - "$FIX" <<'PY'
import json, sys, uuid
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    body = json.load(f)
if not body.get("idempotency_key"):
    body["idempotency_key"] = f"sim-op:{uuid.uuid4().hex[:16]}"
print(json.dumps(body))
PY
)"
    echo "POST $GATEWAY_URL/internal/tasks  (user=$USER_ID)"
    echo "$BODY" | _curl -d @- "$GATEWAY_URL/internal/tasks"
    echo
    ;;
  list-tasks)
    PROJECT="${1:-}"; STATE="${2:-}"
    QS=""
    [ -n "$PROJECT" ] && QS="${QS}&project=${PROJECT}"
    [ -n "$STATE" ] && QS="${QS}&state=${STATE}"
    QS="${QS#&}"
    URL="$GATEWAY_URL/internal/tasks"
    [ -n "$QS" ] && URL="$URL?$QS"
    echo "GET $URL"
    _curl "$URL"
    echo
    ;;
  list-approvals)
    STATUS="${1:-pending}"
    echo "GET $GATEWAY_URL/internal/approvals?status=$STATUS"
    _curl "$GATEWAY_URL/internal/approvals?status=$STATUS"
    echo
    ;;
  decide)
    NONCE="${1:-}"; DECISION="${2:-approved}"
    [ -n "$NONCE" ] || { echo "usage: $0 decide <nonce> [approved|rejected]" >&2; exit 1; }
    FIX="$FIXDIR/decide-${DECISION}.json"
    [ -f "$FIX" ] || { echo "unknown decision '$DECISION' (need approved|rejected)" >&2; exit 1; }
    echo "POST $GATEWAY_URL/internal/approvals/$NONCE/decide"
    _curl -d @"$FIX" "$GATEWAY_URL/internal/approvals/$NONCE/decide"
    echo
    ;;
  audit)
    TID=""; TR=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --task-id) shift; TID="${1:-}";;
        --trace-id) shift; TR="${1:-}";;
        *) echo "unknown arg $1" >&2; exit 1;;
      esac
      shift || true
    done
    QS=""
    [ -n "$TID" ] && QS="task_id=$TID"
    [ -n "$TR" ] && QS="${QS:+$QS&}trace_id=$TR"
    [ -n "$QS" ] || { echo "usage: $0 audit --task-id ID | --trace-id ID" >&2; exit 1; }
    echo "GET $GATEWAY_URL/internal/audit?$QS"
    _curl "$GATEWAY_URL/internal/audit?$QS"
    echo
    ;;
  ""|-h|--help|help)
    cat <<EOF
Usage: $0 <command> [args]

Commands:
  create-task [fixture.json]     POST /internal/tasks (default: create-task-feature.json)
  list-tasks [project] [state]   GET  /internal/tasks
  list-approvals [status]        GET  /internal/approvals (pending|decided|approved|rejected)
  decide <nonce> [approved|rejected]
  audit --task-id ID | --trace-id ID

Env: GATEWAY_URL, HERMES_API_KEY / secrets/hermes_api_key, EMAW_USER_ID (default 987654321)
Fixtures: webhook-gateway/tests/fixtures/operator/
EOF
    ;;
  *)
    echo "unknown command: $CMD (try: $0 help)" >&2
    exit 1
    ;;
esac
