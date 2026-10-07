#!/usr/bin/env bash
# Quick health view of the ingress path: cloudflared (host service or compose) → gateway.
#   scripts/tunnel-status.sh [https://webhook.example.com]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_URL="${1:-${WEBHOOK_PUBLIC_URL:-}}"

echo "== cloudflared =="
if systemctl is-active --quiet cloudflared 2>/dev/null; then
  echo "  host service: active"
  journalctl -u cloudflared -n 5 --no-pager 2>/dev/null | sed 's/^/  /'
elif docker compose -f "$ROOT/docker-compose.yml" ps cloudflared 2>/dev/null | grep -q Up; then
  echo "  compose service: up"
  docker compose -f "$ROOT/docker-compose.yml" logs --tail=5 cloudflared | sed 's/^/  /'
else
  echo "  not running (host service inactive, compose profile 'ingress' not up)"
fi
if curl -fsS --max-time 2 http://127.0.0.1:2000/metrics 2>/dev/null | grep -E '^cloudflared_tunnel_(ha_connections|total_requests) ' | sed 's/^/  metric: /'; then :; else echo "  metrics :2000 not reachable (host-run only)"; fi
command -v cloudflared >/dev/null && cloudflared tunnel list 2>/dev/null | sed 's/^/  /'

echo "== gateway (local) =="
curl -fsS --max-time 3 "http://127.0.0.1:${GATEWAY_PORT:-8700}/readyz" && echo || echo "  gateway not reachable on 127.0.0.1:${GATEWAY_PORT:-8700}"

if [ -n "$PUBLIC_URL" ]; then
  echo "== public path =="
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST -H 'Content-Type: application/json' -H 'X-Gitlab-Event: Issue Hook' -d '{}' "$PUBLIC_URL/webhook/gitlab")
  case "$code" in
    401) echo "  $PUBLIC_URL/webhook/gitlab → 401 (tunnel + gateway OK, token check enforced) ✔";;
    000) echo "  $PUBLIC_URL unreachable ✘";;
    *)   echo "  $PUBLIC_URL/webhook/gitlab → HTTP $code (expected 401)";;
  esac
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$PUBLIC_URL/healthz")
  [ "$code" = "404" ] && echo "  /healthz not exposed publicly (ingress path filter OK) ✔" || echo "  /healthz → HTTP $code (expected 404 — only /webhook/* should be public)"
fi
