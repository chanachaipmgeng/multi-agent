#!/usr/bin/env bash
# Daily backup for systemd timer (W5 / DECISION-19).
# Uses BACKUP_ROOT (default /srv/emaw-backups); falls back to <repo>/backups.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
PREFERRED="${BACKUP_ROOT:-/srv/emaw-backups}"

if [[ -d "$PREFERRED" ]] || mkdir -p "$PREFERRED" 2>/dev/null; then
  BACKUP_DIR="$PREFERRED"
else
  BACKUP_DIR="$ROOT/backups"
  mkdir -p "$BACKUP_DIR"
  echo "warning: cannot use $PREFERRED — writing to $BACKUP_DIR" >&2
fi

export BACKUP_DIR
echo "== host-backup-timed: BACKUP_DIR=$BACKUP_DIR keep=${KEEP_DAYS}d =="
make -C "$ROOT" backup

# Prune only UTC timestamp directories (YYYYMMDDTHHMMSSZ) older than KEEP_DAYS.
shopt -s nullglob
now_epoch="$(date +%s)"
keep_secs=$((KEEP_DAYS * 86400))
for dir in "$BACKUP_DIR"/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z; do
  [[ -d "$dir" ]] || continue
  mtime="$(stat -c %Y "$dir" 2>/dev/null || stat -f %m "$dir")"
  age=$((now_epoch - mtime))
  if (( age > keep_secs )); then
    echo "prune $dir (age ${age}s)"
    rm -rf "$dir"
  fi
done

echo "== host-backup-timed: done =="
