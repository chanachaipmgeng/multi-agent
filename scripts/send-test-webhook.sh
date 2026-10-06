#!/usr/bin/env bash
# Fire a sample GitLab webhook at the gateway (mirrors GitLab's "Test → Issues events").
#
#   scripts/send-test-webhook.sh [issue|pipeline|job] [--bad-token] [--uuid <uuid>]
#
# Env: GATEWAY_URL (default http://127.0.0.1:8700), WEBHOOK_SECRET (default: ./secrets/gitlab_webhook_secret)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KIND="issue"; TOKEN_OVERRIDE=""; UUID="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || date +%s%N)"
while [ $# -gt 0 ]; do
  case "$1" in
    issue|pipeline|job) KIND="$1";;
    --bad-token) TOKEN_OVERRIDE="definitely-wrong-token";;
    --uuid) shift; UUID="$1";;
    *) echo "unknown arg $1"; exit 1;;
  esac
  shift
done

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8700}"
SECRET="${WEBHOOK_SECRET:-$(cat "$ROOT/secrets/gitlab_webhook_secret" 2>/dev/null || true)}"
[ -n "$TOKEN_OVERRIDE" ] && SECRET="$TOKEN_OVERRIDE"
[ -n "$SECRET" ] || { echo "no webhook secret: set WEBHOOK_SECRET or run make secrets-decrypt"; exit 1; }

case "$KIND" in
  issue)    EVENT="Issue Hook";    FIXTURE="issue_hook.json";;
  pipeline) EVENT="Pipeline Hook"; FIXTURE="pipeline_hook.json";;
  job)      EVENT="Job Hook";      FIXTURE="job_hook.json";;
esac

echo "POST $GATEWAY_URL/webhook/gitlab  ($EVENT, uuid=$UUID)"
curl -sS -w '\nHTTP %{http_code} in %{time_total}s\n' \
  -H "Content-Type: application/json" \
  -H "X-Gitlab-Event: $EVENT" \
  -H "X-Gitlab-Event-UUID: $UUID" \
  -H "X-Gitlab-Token: $SECRET" \
  --data-binary @"$ROOT/webhook-gateway/tests/fixtures/$FIXTURE" \
  "$GATEWAY_URL/webhook/gitlab"
