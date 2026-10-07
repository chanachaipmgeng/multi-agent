#!/usr/bin/env bash
# EMAW backup (D4.5 / E10): Postgres + named volumes → ./backups/<ts>/
# Optional: set RESTIC_REPOSITORY (+ RESTIC_PASSWORD) to push the directory to restic.
#
# Usage: scripts/backup.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR:-$ROOT/backups}/$TS"
mkdir -p "$OUT"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT")}"
vol() { echo "${COMPOSE_PROJECT}_$1"; }

PG_CID="$(docker ps --format '{{.ID}} {{.Names}}' | awk '/postgres/ {print $1; exit}')"
[ -n "$PG_CID" ] || { echo "postgres container not running"; exit 1; }

echo "== pg_dump =="
# Stream dump to host file (avoids Git-Bash / Windows docker-cp path mangling).
docker exec "$PG_CID" pg_dump -U emaw -d emaw -Fc > "$OUT/postgres.dump"
TASK_COUNT="$(docker exec "$PG_CID" psql -U emaw -d emaw -tAc 'SELECT count(*) FROM tasks;' | tr -d '[:space:]')"

echo "== volumes =="
# ollama-data is large and re-pullable — include only when BACKUP_OLLAMA=1
VOLUMES=(
  hermes-coordinator-data
  hermes-dev-frontend-data
  hermes-dev-backend-data
  hermes-reviewer-data
  hermes-qa-data
  hermes-devops-data
  minio-data
  redis-data
  adapter-outbox
  pg-data
)
if [ "${BACKUP_OLLAMA:-0}" = "1" ]; then
  VOLUMES+=(ollama-data)
fi
for v in "${VOLUMES[@]}"; do
  full="$(vol "$v")"
  if ! docker volume inspect "$full" >/dev/null 2>&1; then
    echo "skip missing volume $full"
    continue
  fi
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "${full}:/src:ro" \
    -v "$OUT:/dst" \
    alpine:3.20 \
    tar czf "/dst/${v}.tar.gz" -C /src .
  echo "  $v → $(du -h "$OUT/${v}.tar.gz" 2>/dev/null | awk '{print $1}')"
done

PYTHON="$(command -v python3 2>/dev/null || command -v python)"
"$PYTHON" - "$OUT" "$TS" "${TASK_COUNT:-0}" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path

out = Path(sys.argv[1])
ts, task_count = sys.argv[2], int(sys.argv[3] or 0)
sha = {
    f.name: hashlib.sha256(f.read_bytes()).hexdigest()
    for f in sorted(out.iterdir())
    if f.is_file() and f.name != "manifest.json"
}
images = {}
ps = subprocess.check_output(["docker", "ps", "--format", "{{.Image}}"], text=True)
for img in sorted(set(ps.splitlines())):
    try:
        dig = subprocess.check_output(
            ["docker", "image", "inspect", img, "--format", "{{index .RepoDigests 0}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        dig = "unknown"
    images[img] = dig or "unknown"
manifest = {"created_at": ts, "task_count": task_count, "sha256": sha, "images": images}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out / 'manifest.json'} tasks={task_count} files={len(sha)}")
PY

if [ -n "${RESTIC_REPOSITORY:-}" ]; then
  echo "== restic =="
  if command -v restic >/dev/null 2>&1; then
    restic backup "$OUT" --tag emaw --tag "$TS"
  else
    echo "restic not installed — skip remote"
  fi
fi

echo "backup ready: $OUT"
echo "$OUT"
