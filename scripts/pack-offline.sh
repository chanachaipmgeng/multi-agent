#!/usr/bin/env bash
# Pack digest-pinned images + LLM/embedding volumes for air-gap transfer.
# See docs/offline-airgap.md
#
# Usage: scripts/pack-offline.sh
# Env:   PACK_DIR (default offline-pack/<UTC-ts>)
#        LOCAL_LLM_MODEL, SKIP_PULL=1, SKIP_BUILD=1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

_pre_model="${LOCAL_LLM_MODEL-}"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi
[ -n "${_pre_model}" ] && LOCAL_LLM_MODEL="${_pre_model}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${PACK_DIR:-$ROOT/offline-pack/$TS}"
mkdir -p "$OUT/volumes"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT")}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.local-free.yml)
PROFILES=(--profile agents --profile socraticode --profile onprem-llm --profile console --profile observability)
MODEL="${LOCAL_LLM_MODEL:-qwen2.5-coder:7b}"

vol_project() { echo "${COMPOSE_PROJECT}_$1"; }

echo "== pack-offline → $OUT =="

if [ "${SKIP_BUILD:-0}" != "1" ]; then
  echo "== build local images =="
  "${COMPOSE[@]}" "${PROFILES[@]}" build webhook-gateway router \
    adapter-dev-frontend adapter-dev-backend adapter-reviewer adapter-qa adapter-devops \
    operator-console 2>/dev/null \
    || "${COMPOSE[@]}" build webhook-gateway || true
  # Ensure adapter + gateway + console images exist
  docker compose -f docker-compose.yml build \
    webhook-gateway router \
    adapter-dev-frontend adapter-dev-backend adapter-reviewer adapter-qa adapter-devops \
    operator-console || true
fi

if [ "${SKIP_PULL:-0}" != "1" ]; then
  echo "== pull remote images (digest pins) =="
  "${COMPOSE[@]}" "${PROFILES[@]}" pull --ignore-buildable 2>/dev/null \
    || "${COMPOSE[@]}" "${PROFILES[@]}" pull || true
fi

echo "== collect image list =="
# Portable image list (avoid mapfile for older bash / Git Bash quirks)
IMAGES=()
while IFS= read -r img; do
  [ -n "$img" ] && IMAGES+=("$img")
done < <("${COMPOSE[@]}" "${PROFILES[@]}" config --images 2>/dev/null | sort -u)
IMAGES+=(alpine:3.20)
# Deduplicate
_dedup=""
while IFS= read -r img; do
  [ -n "$img" ] && _dedup="${_dedup}${img}"$'\n'
done < <(printf '%s\n' "${IMAGES[@]}" | sort -u)
IMAGES=()
while IFS= read -r img; do
  [ -n "$img" ] && IMAGES+=("$img")
done <<< "$_dedup"

if [ "${#IMAGES[@]}" -lt 2 ]; then
  echo "ERROR: compose config --images returned almost nothing. Is Docker Compose v2 installed?"
  exit 1
fi

MISSING=0
for img in "${IMAGES[@]}"; do
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "WARN: image not local: $img (try pull/build first)"
    MISSING=1
  fi
done
if [ "$MISSING" = "1" ] && [ "${PACK_ALLOW_MISSING:-0}" != "1" ]; then
  echo "Refusing to pack with missing images. Set PACK_ALLOW_MISSING=1 to override."
  exit 1
fi

echo "== docker save (${#IMAGES[@]} images) =="
# shellcheck disable=SC2086
docker save -o "$OUT/images.tar" "${IMAGES[@]}"
echo "  images.tar → $(du -h "$OUT/images.tar" | awk '{print $1}')"

echo "== volume export =="
# Compose project volumes + stable external SocratiCode names
VOL_SPECS=(
  "ollama-data:$(vol_project ollama-data)"
  "socraticode-ollama-data:socraticode_ollama_data"
  "socraticode-qdrant-data:socraticode_qdrant_data"
  "hermes-reviewer-data:$(vol_project hermes-reviewer-data)"
)

for spec in "${VOL_SPECS[@]}"; do
  name="${spec%%:*}"
  full="${spec#*:}"
  if ! docker volume inspect "$full" >/dev/null 2>&1; then
    echo "skip missing volume $full"
    continue
  fi
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "${full}:/src:ro" \
    -v "$OUT/volumes:/dst" \
    alpine:3.20 \
    tar czf "/dst/${name}.tar.gz" -C /src .
  echo "  $name → $(du -h "$OUT/volumes/${name}.tar.gz" | awk '{print $1}')"
done

# Record which models were intended
printf '%s\n' "$MODEL" > "$OUT/LOCAL_LLM_MODEL.txt"
printf '%s\n' "nomic-embed-text" > "$OUT/EMBED_MODEL.txt"

PYTHON="$(command -v python3 2>/dev/null || command -v python)"
"$PYTHON" - "$OUT" "$TS" "$MODEL" "${IMAGES[@]}" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path

out = Path(sys.argv[1])
ts, model = sys.argv[2], sys.argv[3]
image_names = sys.argv[4:]

def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()

sha = {}
for f in sorted(out.rglob("*")):
    if f.is_file() and f.name != "manifest.json":
        rel = f.relative_to(out).as_posix()
        print(f"hashing {rel} …", flush=True)
        sha[rel] = sha256_file(f)

images = {}
for img in image_names:
    try:
        dig = subprocess.check_output(
            ["docker", "image", "inspect", img, "--format", "{{index .RepoDigests 0}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        dig = "unknown"
    if not dig:
        try:
            dig = subprocess.check_output(
                ["docker", "image", "inspect", img, "--format", "{{.Id}}"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except subprocess.CalledProcessError:
            dig = "unknown"
    images[img] = dig or "unknown"

manifest = {
    "kind": "emaw-offline-pack",
    "created_at": ts,
    "local_llm_model": model,
    "embed_model": "nomic-embed-text",
    "sha256": sha,
    "images": images,
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out / 'manifest.json'} images={len(images)} files={len(sha)}")
PY

cat > "$OUT/README.txt" <<EOF
EMAW offline pack ($TS)
LOCAL_LLM_MODEL=$MODEL

On the air-gap host (repo checkout required):
  make load-offline PACK=$OUT
  # set .env: LLM_MODE=local LOCAL_LLM_MODEL=$MODEL
  make secrets-dev && make up-offline
  make local-free-check

See docs/offline-airgap.md
EOF

echo "pack ready: $OUT"
echo "$OUT"
