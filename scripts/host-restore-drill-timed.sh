#!/usr/bin/env bash
# Weekly restore-drill for systemd timer (W5 / DECISION-19).
# Picks the newest backup under BACKUP_ROOT (or <repo>/backups) that has manifest.json.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PREFERRED="${BACKUP_ROOT:-/srv/emaw-backups}"
if [[ -d "$PREFERRED" ]]; then
  SEARCH="$PREFERRED"
elif [[ -d "$ROOT/backups" ]]; then
  SEARCH="$ROOT/backups"
  echo "warning: $PREFERRED missing — searching $SEARCH" >&2
else
  echo "error: no backup directory ($PREFERRED or $ROOT/backups)" >&2
  exit 1
fi

LATEST=""
# Newest timestamp dir (lexicographic UTC names sort by time) with manifest.json
for dir in $(ls -1d "$SEARCH"/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z 2>/dev/null | sort -r); do
  if [[ -f "$dir/manifest.json" ]]; then
    LATEST="$dir"
    break
  fi
done

if [[ -z "$LATEST" ]]; then
  echo "error: no backup with manifest.json under $SEARCH" >&2
  exit 1
fi

# make restore-drill expects a path relative to repo or absolute; pass absolute.
echo "== host-restore-drill-timed: BACKUP=$LATEST =="
make -C "$ROOT" restore-drill BACKUP="$LATEST"
echo "== host-restore-drill-timed: done =="
