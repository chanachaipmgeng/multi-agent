#!/usr/bin/env bash
# Download a Linux amd64 gitleaks binary into tools/gitleaks for Hermes sandbox mounts (D4.2).
# Usage: scripts/install-gitleaks-bin.sh [version]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-8.21.2}"
DEST="$ROOT/tools/gitleaks"
mkdir -p "$ROOT/tools"

if [ -f "$DEST" ] && [ -s "$DEST" ]; then
  echo "already present: $DEST (Linux binary for Hermes mount; may not run on this host)"
  exit 0
fi

URL="https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}/gitleaks_${VERSION}_linux_x64.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "downloading $URL"
curl -fsSL "$URL" -o "$TMP/gitleaks.tgz"
tar -xzf "$TMP/gitleaks.tgz" -C "$TMP" gitleaks
install -m 0755 "$TMP/gitleaks" "$DEST"
echo "installed $DEST (for container mount /usr/local/bin/gitleaks)"
