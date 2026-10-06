#!/usr/bin/env bash
# Encrypt .env → .env.enc with SOPS/age (design §6.3). The plaintext .env stays gitignored.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

[ -f .env ] || { echo ".env not found — cp .env.example .env and fill it in"; exit 1; }
command -v sops >/dev/null || { echo "sops not found"; exit 1; }
grep -q 'age1placeholder' .sops.yaml && { echo ".sops.yaml still has the placeholder recipient — run scripts/secrets-init.sh first"; exit 1; }

if command -v gitleaks >/dev/null; then
  # sanity: refuse to encrypt obviously-still-placeholder values into a file people will trust
  if grep -Eq '^(SECRET_[A-Z_]+)=(change-me|sk-placeholder|glpat-placeholder)' .env; then
    echo "warning: .env still contains placeholder values (change-me / *-placeholder)" >&2
  fi
fi

sops --encrypt --input-type dotenv --output-type dotenv .env > .env.enc
echo "wrote .env.enc ($(grep -c '^SECRET_' .env) secrets). Safe to commit."
