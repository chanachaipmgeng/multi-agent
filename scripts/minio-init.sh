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

# Fallback: ephemeral minio/mc on the compose network (no host mc needed).
# MSYS_NO_PATHCONV avoids Git-Bash rewriting /bin paths when invoking docker.
if docker inspect emaw-minio >/dev/null 2>&1; then
  NET="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{println $k}}{{end}}' emaw-minio | head -1)"
  if [ -n "$NET" ]; then
    MC_URL="http://${ROOT_USER}:${ROOT_PASS}@minio:9000"
    if MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" \
        -e "MC_HOST_emaw=${MC_URL}" \
        minio/mc:latest mb --ignore-existing "emaw/${BUCKET}" >/dev/null; then
      echo "minio bucket $BUCKET ready (via docker minio/mc)"
      exit 0
    fi
  fi
fi

echo "mc not installed and docker mc fallback failed — bucket may auto-create on first PUT"
exit 0
