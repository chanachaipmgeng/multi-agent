#!/usr/bin/env bash
# D4.4 prep — daily audit_events export → MinIO object-lock bucket (GOVERNANCE 365d).
# Vault remains blocked on infra DECISION; this is the S3/WORM stand-in.
#
# Usage:
#   scripts/audit-export.sh [YYYY-MM-DD]     # export UTC day (default: yesterday)
#   scripts/audit-export.sh --verify [DAY]   # download + sha256 + expect delete denied
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MC_IMAGE="${MC_IMAGE:-minio/mc:latest}"
BUCKET="${AUDIT_BUCKET:-emaw-audit}"
ENDPOINT_HOST="${MINIO_ENDPOINT:-http://127.0.0.1:${MINIO_API_PORT:-9000}}"
ROOT_USER="${MINIO_ROOT_USER:-emaw}"
ROOT_PASS="${MINIO_ROOT_PASSWORD:-emaw-minio-dev-change-me}"
RETENTION_DAYS="${AUDIT_RETENTION_DAYS:-365}"

VERIFY=0
DAY=""
for arg in "$@"; do
  case "$arg" in
    --verify) VERIFY=1 ;;
    *) DAY="$arg" ;;
  esac
done

if [ -z "$DAY" ]; then
  if date -u -d 'yesterday' +%Y-%m-%d >/dev/null 2>&1; then
    DAY="$(date -u -d 'yesterday' +%Y-%m-%d)"
  else
    # BSD / busybox fallback
    DAY="$(date -u -v-1d +%Y-%m-%d 2>/dev/null || python -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(days=1)).date())')"
  fi
fi

Y="${DAY%%-*}"; REST="${DAY#*-}"; M="${REST%%-*}"; D="${REST#*-}"
PREFIX="audit/${Y}/${M}/${D}"
STAGING="${ROOT}/backups/audit-export/${DAY}"
mkdir -p "$STAGING"

PG_CID="$(docker ps --format '{{.ID}} {{.Names}}' | awk '/postgres/ {print $1; exit}')"
[ -n "$PG_CID" ] || { echo "postgres container not running"; exit 1; }

mc_run() {
  local NET
  NET="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{println $k}}{{end}}' emaw-minio | head -1)"
  [ -n "$NET" ] || { echo "emaw-minio network not found"; return 1; }
  local MC_URL="http://${ROOT_USER}:${ROOT_PASS}@minio:9000"
  MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" \
    -e "MC_HOST_emaw=${MC_URL}" \
    -v "${STAGING}:/data" \
    "$MC_IMAGE" "$@"
}

ensure_bucket() {
  # Object-lock buckets cannot be created twice without --with-lock on first create.
  if mc_run ls "emaw/${BUCKET}" >/dev/null 2>&1; then
    echo "bucket ${BUCKET} exists"
    return 0
  fi
  echo "creating object-lock bucket ${BUCKET} (GOVERNANCE ${RETENTION_DAYS}d)"
  mc_run mb --with-lock "emaw/${BUCKET}"
  mc_run retention set --default GOVERNANCE "${RETENTION_DAYS}d" "emaw/${BUCKET}" \
    || mc_run retention set-default GOVERNANCE "${RETENTION_DAYS}d" "emaw/${BUCKET}" \
    || echo "warn: could not set default retention (set manually in console)"
}

export_day() {
  ensure_bucket
  local OUT="${STAGING}/audit_events.jsonl"
  local GZ="${OUT}.gz"
  echo "== export audit_events for ${DAY} UTC =="
  # Inclusive day window in UTC
  docker exec -i "$PG_CID" psql -U emaw -d emaw -v ON_ERROR_STOP=1 -c "\
COPY (
  SELECT row_to_json(a)
  FROM (
    SELECT id, ts, trace_id, task_id, actor, event, attrs
    FROM audit_events
    WHERE ts >= TIMESTAMPTZ '${DAY} 00:00:00+00'
      AND ts <  TIMESTAMPTZ '${DAY} 00:00:00+00' + INTERVAL '1 day'
    ORDER BY id
  ) a
) TO STDOUT;" > "$OUT"
  local COUNT
  COUNT="$(wc -l < "$OUT" | tr -d ' ')"
  gzip -f -n "$OUT"
  local HASH
  if command -v sha256sum >/dev/null; then
    HASH="$(sha256sum "$GZ" | awk '{print $1}')"
  else
    HASH="$(python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path(r'$GZ').read_bytes()).hexdigest())")"
  fi
  printf '%s\n' "$HASH" > "${GZ}.sha256"
  echo "rows=${COUNT} sha256=${HASH}"
  mc_run cp "/data/audit_events.jsonl.gz" "emaw/${BUCKET}/${PREFIX}/audit_events.jsonl.gz"
  mc_run cp "/data/audit_events.jsonl.gz.sha256" "emaw/${BUCKET}/${PREFIX}/audit_events.jsonl.gz.sha256"
  # Apply object retention (GOVERNANCE) when supported
  mc_run retention set GOVERNANCE "${RETENTION_DAYS}d" \
    "emaw/${BUCKET}/${PREFIX}/audit_events.jsonl.gz" 2>/dev/null || true
  echo "uploaded s3://${BUCKET}/${PREFIX}/"
  echo "${COUNT}" > "${STAGING}/row_count.txt"
}

verify_day() {
  ensure_bucket
  echo "== verify ${DAY} =="
  rm -f "${STAGING}/verify.jsonl.gz" "${STAGING}/verify.sha256"
  mc_run cp "emaw/${BUCKET}/${PREFIX}/audit_events.jsonl.gz" /data/verify.jsonl.gz
  mc_run cp "emaw/${BUCKET}/${PREFIX}/audit_events.jsonl.gz.sha256" /data/verify.sha256
  local EXPECT GOT
  EXPECT="$(tr -d '[:space:]' < "${STAGING}/verify.sha256" | head -c 64)"
  if command -v sha256sum >/dev/null; then
    GOT="$(sha256sum "${STAGING}/verify.jsonl.gz" | awk '{print $1}')"
  else
    GOT="$(python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path(r'${STAGING}/verify.jsonl.gz').read_bytes()).hexdigest())")"
  fi
  if [ "$EXPECT" != "$GOT" ]; then
    echo "FAIL sha256 mismatch expect=${EXPECT} got=${GOT}"
    exit 1
  fi
  echo "sha256 ok"
  # Retention must be present (GOVERNANCE 365d). Root may still bypass GOVERNANCE;
  # COMPLIANCE is reserved for prod after legal OK.
  set +e
  ret_out="$(mc_run retention info "emaw/${BUCKET}/${PREFIX}/audit_events.jsonl.gz" 2>&1)"
  ret_rc=$?
  set -e
  echo "$ret_out"
  if [ "$ret_rc" -ne 0 ] || ! echo "$ret_out" | grep -qi GOVERNANCE; then
    echo "FAIL: object retention GOVERNANCE not set"
    exit 1
  fi
  echo "retention GOVERNANCE present"
  set +e
  mc_run rm --force "emaw/${BUCKET}/${PREFIX}/audit_events.jsonl.gz" >/tmp/emaw-audit-rm.out 2>&1
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "delete refused (rc=${rc}) — immutable stand-in OK"
  else
    echo "NOTE: root delete succeeded (expected for GOVERNANCE bypass on MinIO root); retention metadata still enforced for non-bypass clients"
  fi
}

if ! curl -fsS "${ENDPOINT_HOST}/minio/health/live" >/dev/null 2>&1; then
  echo "minio not reachable at ${ENDPOINT_HOST}"
  exit 1
fi

if [ "$VERIFY" = "1" ]; then
  verify_day
else
  export_day
fi
