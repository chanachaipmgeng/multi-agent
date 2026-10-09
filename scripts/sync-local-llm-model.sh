#!/usr/bin/env bash
# Sync LOCAL_LLM_MODEL (+ optional LOCAL_LLM_FALLBACK) into all
# hermes-data/*/config.local-free.yaml (DECISION-15).
#
# Usage: scripts/sync-local-llm-model.sh
# Env:   LOCAL_LLM_MODEL (default qwen2.5-coder:7b)
#        LOCAL_LLM_FALLBACK (default = LOCAL_LLM_MODEL)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Load .env if present, but keep already-exported LOCAL_LLM_* from the caller.
_pre_model="${LOCAL_LLM_MODEL-}"
_pre_fallback="${LOCAL_LLM_FALLBACK-}"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi
[ -n "${_pre_model}" ] && LOCAL_LLM_MODEL="${_pre_model}"
[ -n "${_pre_fallback}" ] && LOCAL_LLM_FALLBACK="${_pre_fallback}"

MODEL="${LOCAL_LLM_MODEL:-qwen2.5-coder:7b}"
FALLBACK="${LOCAL_LLM_FALLBACK:-$MODEL}"
AGENTS=(coordinator dev-frontend dev-backend reviewer qa devops)

PYTHON="$(command -v python3 2>/dev/null || command -v python)"
"$PYTHON" - "$MODEL" "$FALLBACK" "${AGENTS[@]}" <<'PY'
import re
import sys
from pathlib import Path

model, fallback = sys.argv[1], sys.argv[2]
agents = sys.argv[3:]
root = Path(".")

def patch(text: str) -> str:
    lines = text.splitlines(keepends=True)
    out = []
    in_model = False
    in_fallback = False
    for line in lines:
        stripped = line.lstrip("\n\r")
        # top-level keys reset sections
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*:", stripped):
            key = stripped.split(":", 1)[0]
            in_model = key == "model"
            in_fallback = key == "fallback_providers"
        if in_model and re.match(r"^  default:\s*", line):
            nl = "\n" if line.endswith("\n") else ""
            line = f"  default: {model}{nl}"
        if in_fallback and re.match(r"^    model:\s*", line):
            nl = "\n" if line.endswith("\n") else ""
            line = f"    model: {fallback}{nl}"
        out.append(line)
    return "".join(out)

for agent in agents:
    path = root / "hermes-data" / agent / "config.local-free.yaml"
    if not path.is_file():
        print(f"skip missing {path}")
        continue
    old = path.read_text(encoding="utf-8")
    new = patch(old)
    if new != old:
        path.write_text(new, encoding="utf-8")
        print(f"updated {path} default={model} fallback={fallback}")
    else:
        print(f"unchanged {path} (already default={model})")
PY
