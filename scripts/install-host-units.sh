#!/usr/bin/env bash
# Install EMAW systemd units on a LAN host (W5). Does not enable/start them.
# Usage: sudo scripts/install-host-units.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$ROOT/deploy/systemd"
DEST=/etc/systemd/system

UNITS=(
  emaw.service
  emaw-backup.service
  emaw-backup.timer
  emaw-restore-drill.service
  emaw-restore-drill.timer
)

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root (or with sudo). Suggested:" >&2
  echo "  sudo $ROOT/scripts/install-host-units.sh" >&2
  echo "then:" >&2
  echo "  sudo systemctl daemon-reload" >&2
  echo "  sudo systemctl enable --now emaw.service" >&2
  echo "  sudo systemctl enable --now emaw-backup.timer emaw-restore-drill.timer" >&2
  exit 1
fi

for u in "${UNITS[@]}"; do
  src="$UNIT_DIR/$u"
  [[ -f "$src" ]] || { echo "missing $src" >&2; exit 1; }
  install -m 0644 "$src" "$DEST/$u"
  echo "installed $DEST/$u"
done

chmod 0755 "$ROOT/scripts/host-backup-timed.sh" "$ROOT/scripts/host-restore-drill-timed.sh"
systemctl daemon-reload
echo "daemon-reload ok — enable when ready:"
echo "  systemctl enable --now emaw.service"
echo "  systemctl enable --now emaw-backup.timer emaw-restore-drill.timer"
echo "  systemctl list-timers 'emaw-*'"
