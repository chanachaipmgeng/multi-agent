#!/usr/bin/env bash
# D1.1 — create the Cloudflare Named Tunnel, DNS route, config.yml and (optionally) the systemd service.
#
#   scripts/tunnel-setup.sh <hostname> [tunnel-name] [--service]
#   e.g. scripts/tunnel-setup.sh webhook.example.com emaw --service
#
# Prerequisites: a domain on Cloudflare (DECISION-5), `cloudflared` installed, `cloudflared tunnel login` done.
# On WSL2 the --service step needs systemd=true in /etc/wsl.conf (then `wsl --shutdown` once).
set -euo pipefail
HOSTNAME_="${1:-}"; NAME="${2:-emaw}"; SERVICE=0
for a in "$@"; do [ "$a" = "--service" ] && SERVICE=1; done
[ -n "$HOSTNAME_" ] && [ "$HOSTNAME_" != "--service" ] || { sed -n '2,9p' "$0"; exit 1; }
if [ "$NAME" = "--service" ]; then NAME="emaw"; fi

command -v cloudflared >/dev/null || { echo "cloudflared not installed → https://pkg.cloudflare.com/ (see cloudflared/README.md)"; exit 1; }
[ -f "$HOME/.cloudflared/cert.pem" ] || { echo "not logged in: run 'cloudflared tunnel login' first"; exit 1; }

ORIGIN_PORT="${GATEWAY_PORT:-8700}"
CFG_DIR="$HOME/.cloudflared"

if cloudflared tunnel list --output json | grep -q "\"name\": *\"$NAME\""; then
  echo "tunnel '$NAME' already exists — reusing"
else
  cloudflared tunnel create "$NAME"
fi
TUNNEL_ID="$(cloudflared tunnel list --output json | python3 -c "import sys,json; print(next(t['id'] for t in json.load(sys.stdin) if t['name']=='$NAME'))")"
echo "tunnel id: $TUNNEL_ID"

echo "→ DNS route $HOSTNAME_ → $NAME"
cloudflared tunnel route dns --overwrite-dns "$NAME" "$HOSTNAME_"

echo "→ writing $CFG_DIR/config.yml"
cat > "$CFG_DIR/config.yml" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CFG_DIR/$TUNNEL_ID.json
metrics: 127.0.0.1:2000

ingress:
  - hostname: $HOSTNAME_
    path: ^/webhook/.*
    service: http://localhost:$ORIGIN_PORT
    originRequest:
      connectTimeout: 10s
      noTLSVerify: false
  - service: http_status:404
EOF
cloudflared tunnel ingress validate --config "$CFG_DIR/config.yml"

if [ "$SERVICE" -eq 1 ]; then
  systemctl is-system-running >/dev/null 2>&1 || echo "warning: systemd not running (WSL2: set systemd=true in /etc/wsl.conf)"
  sudo cloudflared --config "$CFG_DIR/config.yml" service install || echo "service already installed"
  sudo systemctl enable --now cloudflared
  sudo systemctl --no-pager --lines=5 status cloudflared || true
else
  echo "not installing service (add --service). Test now with:  cloudflared tunnel --config $CFG_DIR/config.yml run"
fi

cat <<EOF

GitLab webhook URL:   https://$HOSTNAME_/webhook/gitlab
Compose alternative:  cloudflared tunnel token $NAME  → SECRET_TUNNEL_TOKEN in .env → make up-ingress
Status / runbook:     scripts/tunnel-status.sh · docs/runbooks/tunnel.md
EOF
