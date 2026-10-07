#!/usr/bin/env bash
# D2.4 — prune git worktrees idle > 7 days when no active task references them.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${WORKSPACE_ROOT:-$ROOT/workspace}"
DAYS="${WORKTREE_MAX_AGE_DAYS:-7}"
GATEWAY="${EMAW_GATEWAY_URL:-http://127.0.0.1:8700}"
DRY_RUN="${DRY_RUN:-0}"

echo "scanning worktrees under $WORKSPACE (idle > ${DAYS}d)"

# Collect active task worktree hints (best-effort)
ACTIVE=""
if [ -n "${API_SERVER_KEY:-}" ] && [ -n "${EMAW_USER_ID:-}" ]; then
  ACTIVE=$(curl -fsS "$GATEWAY/internal/tasks?limit=200" \
    -H "Authorization: Bearer $API_SERVER_KEY" \
    -H "X-EMAW-User-Id: $EMAW_USER_ID" 2>/dev/null \
    | python -c "import sys,json; d=json.load(sys.stdin); print(' '.join(
        str((t.get('result') or {}).get('worktree') or '') for t in d.get('tasks',[])
        if t.get('state') not in ('DONE','FAILED','CANCELLED','EXPIRED','REJECTED')))" 2>/dev/null || true)
fi

find_worktrees() {
  local repo="$1"
  [ -d "$repo/.git" ] || [ -f "$repo/.git" ] || return 0
  git -C "$repo" worktree list --porcelain 2>/dev/null | awk '
    /^worktree / { path=$2 }
    /^$/ {
      if (path != "" && path !~ /\/\.git$/) print path
      path=""
    }
  '
}

cutoff=$(date -d "-${DAYS} days" +%s 2>/dev/null || python -c "import time; print(int(time.time())-${DAYS}*86400)")

removed=0
# Named worktrees under workspace/.worktrees
if [ -d "$WORKSPACE/.worktrees" ]; then
  for wt in "$WORKSPACE/.worktrees"/*; do
    [ -d "$wt" ] || continue
    base=$(basename "$wt")
    # Skip if mentioned in active tasks
    if echo "$ACTIVE" | grep -q "$base"; then
      echo "skip active: $wt"
      continue
    fi
    # mtime of worktree dir
    mtime=$(stat -c %Y "$wt" 2>/dev/null || stat -f %m "$wt" 2>/dev/null || echo 0)
    if [ "$mtime" -lt "$cutoff" ]; then
      echo "stale (>${DAYS}d): $wt"
      if [ "$DRY_RUN" = "1" ]; then
        continue
      fi
      # Try to remove via owning repo if we can find it
      for repo in "$WORKSPACE"/*; do
        [ -d "$repo" ] || continue
        if git -C "$repo" worktree list 2>/dev/null | grep -q "$wt"; then
          git -C "$repo" worktree remove --force "$wt" 2>/dev/null \
            || rm -rf "$wt"
          git -C "$repo" worktree prune 2>/dev/null || true
          removed=$((removed + 1))
          break
        fi
      done
      if [ -d "$wt" ]; then
        rm -rf "$wt"
        removed=$((removed + 1))
      fi
    fi
  done
fi

echo "worktree-cleanup done (removed=$removed). cron tip: 0 4 * * * DRY_RUN=0 scripts/worktree-cleanup.sh"
