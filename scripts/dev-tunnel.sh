#!/usr/bin/env bash
# Dev Quick Tunnel: public HTTPS → local webhook-gateway (no Cloudflare domain / DECISION-5).
# Usage: scripts/dev-tunnel.sh [http://127.0.0.1:8700]
#        make dev-tunnel
#
# Design §5.2: Quick Tunnel is for dev/test only (ephemeral URL, no Access).
# Production path: Named Tunnel via make tunnel-setup / make up-ingress (needs org domain).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORIGIN="${1:-http://127.0.0.1:${GATEWAY_PORT:-8700}}"

if ! command -v cloudflared >/dev/null 2>&1; then
  cat >&2 <<'EOF'
cloudflared not found on PATH.

Install (pick one):
  # Debian/Ubuntu
  curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
  sudo dpkg -i /tmp/cloudflared.deb

  # Or run via Docker (ephemeral):
  docker run --rm -it --network host cloudflare/cloudflared:latest tunnel --url http://127.0.0.1:8700

See docs/runbooks/tunnel.md § Dev without domain
EOF
  exit 1
fi

if ! curl -fsS --max-time 3 "${ORIGIN%/}/readyz" >/dev/null 2>&1; then
  echo "gateway not ready at ${ORIGIN%/}/readyz — run: make up (or make bootstrap)" >&2
  exit 1
fi

cat <<EOF
== EMAW dev Quick Tunnel ==
  origin:  $ORIGIN
  note:    ephemeral trycloudflare.com URL — not for production
  named:   blocked on DECISION-5 domain — see docs/org-unblock.md
  gitlab:  set webhook URL to https://<trycloudflare-host>/webhook/gitlab
           secret = contents of $ROOT/secrets/gitlab_webhook_secret
  local:   without a public URL use: make webhook-test

Press Ctrl+C to stop.
EOF

exec cloudflared tunnel --url "$ORIGIN"
