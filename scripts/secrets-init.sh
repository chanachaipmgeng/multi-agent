#!/usr/bin/env bash
# D0.6 — create an age key for this operator and wire it into .sops.yaml.
# Usage: scripts/secrets-init.sh [key-path]   (default: ~/.config/sops/age/keys.txt)
set -euo pipefail

KEY_PATH="${1:-${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

command -v age-keygen >/dev/null || { echo "age-keygen not found (apt install age)"; exit 1; }
command -v sops       >/dev/null || { echo "sops not found (https://github.com/getsops/sops/releases)"; exit 1; }

if [ -f "$KEY_PATH" ]; then
  echo "age key already exists at $KEY_PATH — reusing it"
else
  mkdir -p "$(dirname "$KEY_PATH")"
  (umask 077; age-keygen -o "$KEY_PATH")
  echo "created age key at $KEY_PATH (back it up offline; losing it = losing .env.enc)"
fi

PUB=$(grep -o 'age1[0-9a-z]*' "$KEY_PATH" | head -1)
[ -n "$PUB" ] || { echo "could not read public key from $KEY_PATH"; exit 1; }

if grep -q 'age1placeholder' "$ROOT/.sops.yaml"; then
  sed -i "s/age1placeholder[0-9a-z]*/$PUB/g" "$ROOT/.sops.yaml"
  echo "updated .sops.yaml recipient → $PUB"
else
  echo ".sops.yaml already has a recipient; add $PUB manually if this is a second operator"
fi

cat <<EOF

Next steps:
  cp .env.example .env     # fill in real values
  make secrets-encrypt     # → .env.enc (commit this)
  make secrets-decrypt     # → secrets/* files for docker compose
Export SOPS_AGE_KEY_FILE=$KEY_PATH in your shell profile.
EOF
