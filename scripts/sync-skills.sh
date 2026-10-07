#!/usr/bin/env bash
# D0.5 / E13 — copy version-controlled skills into each agent's Hermes skills tree.
#
# skills/<agent>/<skill>.md      →  hermes-data/<agent>/skills/emaw/<skill>/SKILL.md
# skills/_dev-common/<skill>.md  →  dev-frontend + dev-backend
# skills/_shared/<skill>.md      →  every agent
#
# Hermes expects: ~/.hermes/skills/<category>/<skill>/SKILL.md (v0.21.5).
# Category is fixed to `emaw` for platform-owned skills.
#
# Usage: scripts/sync-skills.sh [--check]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1
AGENTS=(coordinator dev-frontend dev-backend reviewer devops qa)
CATEGORY=emaw
drift=0

sync_one() {
  local src="$1" agent="$2"
  local name; name="$(basename "$src" .md)"
  local dest="$ROOT/hermes-data/$agent/skills/$CATEGORY/$name/SKILL.md"
  if [ -f "$dest" ] && cmp -s "$src" "$dest"; then return; fi
  if [ "$CHECK" -eq 1 ]; then
    echo "out of date: hermes-data/$agent/skills/$CATEGORY/$name/SKILL.md"
    drift=1
    return
  fi
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
  echo "synced  $agent/$CATEGORY/$name"
}

for agent in "${AGENTS[@]}"; do
  for src in "$ROOT"/skills/_shared/*.md; do
    [ -e "$src" ] && [ "$(basename "$src")" != "README.md" ] && sync_one "$src" "$agent"
  done
  case "$agent" in
    dev-frontend|dev-backend)
      for src in "$ROOT"/skills/_dev-common/*.md; do [ -e "$src" ] && sync_one "$src" "$agent"; done
      ;;
  esac
  for src in "$ROOT"/skills/"$agent"/*.md; do
    [ -e "$src" ] && [ "$(basename "$src")" != "README.md" ] && sync_one "$src" "$agent"
  done
done

# Remove stale flat layout from older syncs (skills/<name>/SKILL.md without category)
if [ "$CHECK" -eq 0 ]; then
  for agent in "${AGENTS[@]}"; do
    for stale in "$ROOT"/hermes-data/"$agent"/skills/*/SKILL.md; do
      [ -e "$stale" ] || continue
      parent="$(basename "$(dirname "$stale")")"
      [ "$parent" = "$CATEGORY" ] && continue
      # only remove if a category copy exists or parent looks like a skill name (not emaw)
      if [ -d "$ROOT/hermes-data/$agent/skills/$CATEGORY" ]; then
        # leave non-emaw dirs that aren't single-skill dirs alone; remove old flat skill dirs
        if [ ! -d "$ROOT/hermes-data/$agent/skills/$parent/emaw" ] && \
           [ "$(basename "$(dirname "$stale")")" != "$CATEGORY" ] && \
           [ -f "$ROOT/hermes-data/$agent/skills/$CATEGORY/$parent/SKILL.md" ]; then
          rm -rf "$ROOT/hermes-data/$agent/skills/$parent"
          echo "removed stale flat skill dir: $agent/skills/$parent"
        fi
      fi
    done
  done
fi

if [ "$CHECK" -eq 1 ]; then
  [ "$drift" -eq 0 ] && echo "skills in sync" || exit 1
fi
