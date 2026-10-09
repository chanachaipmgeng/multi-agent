#!/usr/bin/env bash
# Preflight for air-gap pack/load (docs/offline-airgap.md).
#
# Usage:
#   scripts/preflight-offline.sh              # pack-host readiness (env/secrets/stack hints)
#   PACK=offline-pack/<ts> scripts/preflight-offline.sh   # verify a finished pack
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { printf '  \033[32m✔\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; failed=1; }
warn() { printf '  \033[33m☐\033[0m %s\n' "$1"; }
failed=0

_pre_model="${LOCAL_LLM_MODEL-}"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi
[ -n "${_pre_model}" ] && LOCAL_LLM_MODEL="${_pre_model}"

MODEL="${LOCAL_LLM_MODEL:-qwen2.5-coder:7b}"
OLLAMA_PORT="${INFERENCE_OLLAMA_PORT:-11436}"
SOCRATICODE_PORT="${SOCRATICODE_OLLAMA_PORT:-11435}"
MIN_DISK_GIB="${OFFLINE_MIN_DISK_GIB:-40}"

PACK="${PACK:-${PACK_DIR:-}}"
if [ -n "$PACK" ] && [[ "$PACK" != /* ]]; then
  PACK="$ROOT/$PACK"
fi

# ── Mode: verify finished pack ──────────────────────────────────────────────
if [ -n "$PACK" ]; then
  echo "== preflight-offline (pack) → $PACK =="
  [ -d "$PACK" ] || { echo "pack dir missing: $PACK"; exit 1; }
  [ -f "$PACK/images.tar" ] && pass "images.tar" || fail "missing images.tar"
  [ -f "$PACK/manifest.json" ] && pass "manifest.json" || fail "missing manifest.json"
  for v in ollama-data socraticode-ollama-data; do
    if [ -f "$PACK/volumes/${v}.tar.gz" ]; then
      pass "volume $v"
    else
      fail "missing volumes/${v}.tar.gz"
    fi
  done
  if [ -f "$PACK/volumes/hermes-reviewer-data.tar.gz" ]; then
    pass "volume hermes-reviewer-data (npm cache)"
  else
    warn "hermes-reviewer-data missing — warm npm on pack host before re-pack"
  fi
  if [ -f "$PACK/manifest.json" ]; then
    PYTHON="$(command -v python3 2>/dev/null || command -v python)"
    if "$PYTHON" - "$PACK" <<'PY'
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
m = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
bad = 0
for rel, expect in (m.get("sha256") or {}).items():
    p = pack / rel
    if not p.is_file():
        print(f"missing {rel}")
        bad += 1
        continue
    print(f"verify {rel}", flush=True)
    if sha256_file(p) != expect:
        print(f"sha256 mismatch {rel}")
        bad += 1
sys.exit(1 if bad else 0)
PY
    then
      pass "manifest sha256"
    else
      fail "manifest sha256 mismatch or missing files"
    fi
    packed_model="$("$PYTHON" - "$PACK/manifest.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("local_llm_model", ""))
PY
)"
    if [ -n "$packed_model" ]; then
      pass "packed LOCAL_LLM_MODEL=$packed_model"
      if [ "$packed_model" != "qwen2.5-coder:14b" ] && [ "${ALLOW_NON_14B_PACK:-0}" != "1" ]; then
        warn "7920 default is 14b — set ALLOW_NON_14B_PACK=1 to ignore (packed=$packed_model)"
      fi
    fi
  fi
  if [ "$failed" -ne 0 ]; then
    echo "preflight-offline PACK FAILED"
    exit 1
  fi
  echo "preflight-offline PACK OK"
  exit 0
fi

# ── Mode: pack-host readiness ───────────────────────────────────────────────
echo "== preflight-offline (pack host) =="

command -v docker >/dev/null && pass "docker CLI" || fail "docker not installed"
docker compose version >/dev/null 2>&1 && pass "docker compose v2" || fail "docker compose v2 missing"

if [ -f .env ]; then
  pass ".env present"
else
  fail "missing .env — copy config/env.offline-server.example"
fi

case "${LLM_MODE:-}" in
  local) pass "LLM_MODE=local" ;;
  *) fail "LLM_MODE must be local (got '${LLM_MODE:-unset}')" ;;
esac
pass "LOCAL_LLM_MODEL=$MODEL"

if [ -s secrets/hermes_api_key ]; then
  pass "secrets/hermes_api_key"
else
  fail "missing secrets/hermes_api_key — make secrets-dev"
fi
[ -f config/rbac.yaml ] && pass "config/rbac.yaml" || warn "config/rbac.yaml missing — copy from rbac.example.yaml"

# Disk free (GiB) on ROOT filesystem
PYTHON="$(command -v python3 2>/dev/null || command -v python)"
free_gib="$("$PYTHON" -c "import shutil; print(int(shutil.disk_usage('.').free/1024**3))")"
if [ "$free_gib" -ge "$MIN_DISK_GIB" ]; then
  pass "disk free ${free_gib} GiB (≥ ${MIN_DISK_GIB})"
else
  fail "disk free ${free_gib} GiB < ${MIN_DISK_GIB} (set OFFLINE_MIN_DISK_GIB to override)"
fi

tags="$(curl -fsS --max-time 5 "http://127.0.0.1:${OLLAMA_PORT}/api/tags" 2>/dev/null)" || tags=""
if [ -n "$tags" ]; then
  pass "inference Ollama :${OLLAMA_PORT}"
  if printf '%s' "$tags" | grep -q "\"name\":\"${MODEL}"; then
    pass "model present: $MODEL"
  else
    warn "model $MODEL not in inference — run: make local-llm-pull"
  fi
else
  warn "inference Ollama not up — run make up-local-free then local-llm-pull"
fi

etags="$(curl -fsS --max-time 5 "http://127.0.0.1:${SOCRATICODE_PORT}/api/tags" 2>/dev/null)" || etags=""
if [ -n "$etags" ]; then
  if printf '%s' "$etags" | grep -q 'nomic-embed-text'; then
    pass "embedding nomic-embed-text"
  else
    warn "pull embed: docker exec socraticode-ollama ollama pull nomic-embed-text"
  fi
else
  warn "socraticode-ollama not reachable on :${SOCRATICODE_PORT}"
fi

if docker ps --format '{{.Names}}' | grep -qx emaw-reviewer; then
  if docker exec emaw-reviewer sh -c \
      'ls /opt/data/.npm/_npx/*/node_modules/socraticode/package.json >/dev/null 2>&1 \
       || test -x /opt/data/.npm/_npx/*/node_modules/.bin/socraticode'; then
    pass "socraticode npm cache in reviewer"
  else
    warn "npm cache cold — run: make warm-socraticode-npm"
  fi
else
  warn "emaw-reviewer not running — warm npm after up-local-free"
fi

if [ "$failed" -ne 0 ]; then
  echo
  echo "preflight-offline FAILED"
  exit 1
fi
echo
echo "preflight-offline OK (warnings above are non-fatal; clear them before pack)"
exit 0
