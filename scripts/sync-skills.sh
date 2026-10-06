#!/usr/bin/env bash
# D0.5 / E13 — copy version-controlled skills into each agent's data dir.
# skills/<agent>/<skill>.md      →  hermes-data/<agent>/skills/<skill>/SKILL.md
# skills/_dev-common/<skill>.md  →  dev-frontend + dev-backend
# skills/_shared/<skill>.md      →  every agent
#
# Skills are *only* promoted from git (reviewed) into hermes-data, never the other way round.
# Usage: scripts/sync-skills.sh [--check]     (--check: exit 1 if anything is out of date)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1
AGENTS=(coordinator dev-frontend dev-backend reviewer devops qa)
drift=0

sync_one() {
  local src="$1" agent="$2"
  local name; name="$(basename "$src" .md)"
  local dest="$ROOT/hermes-data/$agent/skills/$name/SKILL.md"
  if [ -f "$dest" ] && cmp -s "$src" "$dest"; then return; fi
  if [ "$CHECK" -eq 1 ]; then echo "out of date: hermes-data/$agent/skills/$name/SKILL.md"; drift=1; return; fi
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
  echo "synced  $agent/$name"
}

for agent in "${AGENTS[@]}"; do
  for src in "$ROOT"/skills/_shared/*.md; do
    [ -e "$src" ] && [ "$(basename "$src")" != "README.md" ] && sync_one "$src" "$agent"
  done
  case "$agent" in
    dev-frontend|dev-backend)
      for src in "$ROOT"/skills/_dev-common/*.md; do [ -e "$src" ] && sync_one "$src" "$agent"; done;;
  esac
  for src in "$ROOT"/skills/"$agent"/*.md; do [ -e "$src" ] && sync_one "$src" "$agent"; done
done

if [ "$CHECK" -eq 1 ]; then
  [ "$drift" -eq 0 ] && echo "skills in sync" || exit 1
fi
