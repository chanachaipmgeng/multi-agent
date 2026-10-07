#!/usr/bin/env bash
# EMAW restore (D4.5 / E10).
#
# Usage:
#   scripts/restore.sh backups/<ts>              # destructive restore into live stack
#   scripts/restore.sh backups/<ts> --drill      # non-destructive: temp postgres + volume check
#
# Env: COMPOSE_PROJECT_NAME (default: directory name)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SRC="${1:-}"
MODE="${2:-}"
[ -n "$SRC" ] || { echo "usage: $0 backups/<ts> [--drill]"; exit 1; }
[ -d "$SRC" ] || { echo "not a directory: $SRC"; exit 1; }
[ -f "$SRC/postgres.dump" ] || { echo "missing postgres.dump in $SRC"; exit 1; }
[ -f "$SRC/manifest.json" ] || { echo "missing manifest.json in $SRC"; exit 1; }

COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT")}"
vol() { echo "${COMPOSE_PROJECT}_$1"; }

PYTHON="$(command -v python3 2>/dev/null || command -v python)"
EXPECTED_TASKS="$("$PYTHON" -c "import json; print(json.load(open(r'$SRC/manifest.json'))['task_count'])")"

if [ "$MODE" = "--drill" ]; then
  echo "== restore drill (non-destructive) =="
  DRILL_CID="emaw-pg-restore-drill"
  docker rm -f "$DRILL_CID" >/dev/null 2>&1 || true
  docker run -d --name "$DRILL_CID" \
    -e POSTGRES_USER=emaw -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=emaw \
    postgres:16-alpine >/dev/null
  # wait ready
  for _ in $(seq 1 30); do
    if docker exec "$DRILL_CID" pg_isready -U emaw >/dev/null 2>&1; then break; fi
    sleep 1
  done
  # Stream dump into container; MSYS_NO_PATHCONV keeps /tmp path inside the container.
  MSYS_NO_PATHCONV=1 docker exec -i "$DRILL_CID" sh -c 'cat > /tmp/emaw.dump' < "$SRC/postgres.dump"
  MSYS_NO_PATHCONV=1 docker exec "$DRILL_CID" pg_restore -U emaw -d emaw --clean --if-exists /tmp/emaw.dump \
    || MSYS_NO_PATHCONV=1 docker exec "$DRILL_CID" pg_restore -U emaw -d emaw /tmp/emaw.dump || true
  GOT="$(docker exec "$DRILL_CID" psql -U emaw -d emaw -tAc 'SELECT count(*) FROM tasks;' 2>/dev/null | tr -d '[:space:]' || echo 0)"
  docker rm -f "$DRILL_CID" >/dev/null 2>&1 || true
  echo "manifest task_count=$EXPECTED_TASKS restored=$GOT"
  if [ "$GOT" = "$EXPECTED_TASKS" ]; then
    echo "restore-drill: PASSED"
    exit 0
  fi
  echo "restore-drill: FAILED (task count mismatch)"
  exit 1
fi

echo "== DESTRUCTIVE restore into live stack =="
echo "This stops agents/adapters and overwrites volumes. Ctrl-C within 5s to abort."
sleep 5

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.local-free.yml)
"${COMPOSE[@]}" --profile agents --profile onprem-llm --profile socraticode \
  stop coordinator dev-frontend dev-backend reviewer qa devops \
       router adapter-dev-frontend adapter-dev-backend adapter-reviewer adapter-qa adapter-devops \
       webhook-gateway || true

PG_CID="$(docker ps --format '{{.ID}} {{.Names}}' | awk '/postgres/ {print $1; exit}')"
[ -n "$PG_CID" ] || { echo "postgres must stay up for restore"; exit 1; }

echo "== pg_restore =="
MSYS_NO_PATHCONV=1 docker exec -i "$PG_CID" sh -c 'cat > /tmp/emaw.dump' < "$SRC/postgres.dump"
MSYS_NO_PATHCONV=1 docker exec "$PG_CID" pg_restore -U emaw -d emaw --clean --if-exists /tmp/emaw.dump \
  || MSYS_NO_PATHCONV=1 docker exec "$PG_CID" pg_restore -U emaw -d emaw /tmp/emaw.dump || true
MSYS_NO_PATHCONV=1 docker exec "$PG_CID" rm -f /tmp/emaw.dump

echo "== volume restore =="
for tar in "$SRC"/*.tar.gz; do
  [ -f "$tar" ] || continue
  base="$(basename "$tar" .tar.gz)"
  full="$(vol "$base")"
  if ! docker volume inspect "$full" >/dev/null 2>&1; then
    echo "skip unknown volume $full"
    continue
  fi
  # Wipe then extract (MSYS_NO_PATHCONV keeps /dst and /src as container paths)
  MSYS_NO_PATHCONV=1 docker run --rm -v "${full}:/dst" alpine:3.20 \
    sh -c 'rm -rf /dst/* /dst/.[!.]* 2>/dev/null || true'
  MSYS_NO_PATHCONV=1 docker run --rm -v "${full}:/dst" -v "$(cd "$(dirname "$tar")" && pwd):/src:ro" alpine:3.20 \
    tar xzf "/src/$(basename "$tar")" -C /dst
  echo "  restored $full"
done

GOT="$(docker exec "$PG_CID" psql -U emaw -d emaw -tAc 'SELECT count(*) FROM tasks;' | tr -d '[:space:]')"
echo "task_count expected=$EXPECTED_TASKS got=$GOT"

"${COMPOSE[@]}" --profile agents --profile onprem-llm --profile socraticode \
  start webhook-gateway router \
        adapter-dev-frontend adapter-dev-backend adapter-reviewer adapter-qa adapter-devops \
        coordinator dev-frontend dev-backend reviewer qa devops || true

echo "restore complete — verify with make phase3-check"
