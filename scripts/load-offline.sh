#!/usr/bin/env bash
# Load an offline pack created by scripts/pack-offline.sh
# See docs/offline-airgap.md
#
# Usage: scripts/load-offline.sh [PACK_DIR]
#        PACK=offline-pack/<ts> make load-offline
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PACK="${1:-${PACK:-${PACK_DIR:-}}}"
if [ -z "$PACK" ]; then
  echo "usage: scripts/load-offline.sh <offline-pack/<ts>>"
  echo "   or: PACK=offline-pack/<ts> make load-offline"
  exit 1
fi
# Resolve relative to ROOT
case "$PACK" in
  /*) ;;
  *) PACK="$ROOT/$PACK" ;;
esac
[ -d "$PACK" ] || { echo "pack dir not found: $PACK"; exit 1; }
[ -f "$PACK/images.tar" ] || { echo "missing $PACK/images.tar"; exit 1; }

COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT")}"
vol_project() { echo "${COMPOSE_PROJECT}_$1"; }

echo "== load images from $PACK/images.tar =="
docker load -i "$PACK/images.tar"

echo "== restore volumes =="
restore_vol() {
  local archive_name="$1"
  local docker_vol="$2"
  local archive="$PACK/volumes/${archive_name}.tar.gz"
  if [ ! -f "$archive" ]; then
    echo "skip missing archive $archive_name"
    return 0
  fi
  docker volume create "$docker_vol" >/dev/null
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "${docker_vol}:/dst" \
    -v "$PACK/volumes:/src:ro" \
    alpine:3.20 \
    sh -c "cd /dst && tar xzf \"/src/${archive_name}.tar.gz\""
  echo "  restored $docker_vol ← $archive_name"
}

restore_vol ollama-data "$(vol_project ollama-data)"
restore_vol socraticode-ollama-data socraticode_ollama_data
restore_vol socraticode-qdrant-data socraticode_qdrant_data
restore_vol hermes-reviewer-data "$(vol_project hermes-reviewer-data)"

if [ -f "$PACK/manifest.json" ]; then
  PYTHON="$(command -v python3 2>/dev/null || command -v python)"
  "$PYTHON" - "$PACK" <<'PY'
import hashlib, json, sys
from pathlib import Path

def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()

pack = Path(sys.argv[1])
manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
sha = manifest.get("sha256") or {}
bad = 0
for rel, expect in sha.items():
    path = pack / rel
    if not path.is_file():
        print(f"WARN: missing file from manifest: {rel}")
        bad += 1
        continue
    print(f"verify {rel}", flush=True)
    if sha256_file(path) != expect:
        print(f"FAIL: sha256 mismatch {rel}")
        bad += 1
if bad:
    print(f"checksum warnings: {bad} (continuing; images already loaded)")
else:
    print("manifest sha256 OK")
model = manifest.get("local_llm_model")
if model:
    print(f"packed LOCAL_LLM_MODEL={model} — set the same in .env before up-offline")
PY
elif [ -f "$PACK/LOCAL_LLM_MODEL.txt" ]; then
  echo "packed LOCAL_LLM_MODEL=$(cat "$PACK/LOCAL_LLM_MODEL.txt") — set the same in .env before up-offline"
fi

echo "load complete. Next:"
echo "  make secrets-dev   # or secrets-decrypt"
echo "  make up-offline"
echo "  make local-free-check"
