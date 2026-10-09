#!/usr/bin/env bash
# Pre-warm SocratiCode under reviewer npm cache so air-gap pack does not need registry.
# Requires: emaw-reviewer running (make up-local-free).
#
# Usage: scripts/warm-socraticode-npm.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CNAME="${REVIEWER_CONTAINER:-emaw-reviewer}"
if ! docker ps --format '{{.Names}}' | grep -qx "$CNAME"; then
  echo "container $CNAME not running — make up-local-free first" >&2
  exit 1
fi

echo "== warm socraticode npm cache in $CNAME =="
# Use the same cache path as mcp_servers.socraticode env (config.local-free.yaml)
docker exec -e npm_config_cache=/opt/data/.npm "$CNAME" \
  sh -c 'mkdir -p /opt/data/.npm && npx -y socraticode --help >/tmp/socraticode-warm.out 2>&1 || true'

if docker exec "$CNAME" sh -c \
    'ls /opt/data/.npm/_npx/*/node_modules/socraticode/package.json >/dev/null 2>&1 \
     || test -x /opt/data/.npm/_npx/*/node_modules/.bin/socraticode'; then
  echo "warm-socraticode-npm OK"
  exit 0
fi

echo "warm-socraticode-npm FAILED — npx could not install socraticode (need network on pack host)" >&2
docker exec "$CNAME" sh -c 'tail -n 40 /tmp/socraticode-warm.out 2>/dev/null' || true
exit 1
