#!/usr/bin/env bash
# Create emaw-artifacts bucket + optional lifecycle (D3.7).
# Requires: minio client (mc) OR curl against MinIO; container emaw-minio running.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENDPOINT="${MINIO_ENDPOINT:-http://127.0.0.1:${MINIO_API_PORT:-9000}}"
ROOT_USER="${MINIO_ROOT_USER:-emaw}"
ROOT_PASS="${MINIO_ROOT_PASSWORD:-emaw-minio-dev-change-me}"
BUCKET="${MINIO_BUCKET:-emaw-artifacts}"
AGENT_SECRET="$(cat secrets/minio_agent_secret 2>/dev/null || echo emaw-minio-agent-dev)"

if ! curl -fsS "${ENDPOINT}/minio/health/live" >/dev/null 2>&1; then
  echo "minio not reachable at $ENDPOINT — skip init"
  exit 0
fi

if command -v mc >/dev/null 2>&1; then
  mc alias set emaw "$ENDPOINT" "$ROOT_USER" "$ROOT_PASS" >/dev/null
  mc mb --ignore-existing "emaw/$BUCKET"
  # 90-day expiry
  cat > /tmp/emaw-lifecycle.json <<'EOF'
{"Rules":[{"ID":"expire-90d","Status":"Enabled","Expiration":{"Days":90},"Filter":{"Prefix":""}}]}
EOF
  mc ilm import "emaw/$BUCKET" < /tmp/emaw-lifecycle.json 2>/dev/null || true
  # Agent user (best-effort; may already exist)
  mc admin user add emaw emaw "$AGENT_SECRET" 2>/dev/null || true
  mc admin policy attach emaw readwrite --user emaw 2>/dev/null || true
  echo "minio bucket $BUCKET ready (via mc)"
  exit 0
fi

# Fallback: create bucket with a simple authenticated PUT (path-style)
# MinIO accepts AWS Signature V2-ish via mc preferentially; without mc we only
# verify health and remind the operator.
echo "mc not installed — bucket will be auto-created on first PUT from adapters"
echo "optional: install minio client and re-run scripts/minio-init.sh"
exit 0
