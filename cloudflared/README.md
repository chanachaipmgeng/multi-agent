# cloudflared — permanent ingress (Phase 1)

Phase 0 does not need the tunnel: the gateway is exercised locally with
`make webhook-test`. This directory holds the placeholder so Phase 1 is a config change,
not a redesign.

## Blocked on

* **DECISION-5** — a domain on a *team* Cloudflare account (not personal). Until then only
  `cloudflared tunnel --url http://localhost:8700` (Quick Tunnel, dev only) works.

## Named Tunnel, once the domain exists

```bash
cloudflared tunnel login
cloudflared tunnel create emaw
cloudflared tunnel route dns emaw webhook.<org>.com

# Option A — host service (WSL2, needs systemd=true in /etc/wsl.conf)
cp cloudflared/config.yml.example ~/.cloudflared/config.yml   # fill in <TUNNEL_ID>, <USER>, <org>
sudo cloudflared service install && sudo systemctl enable --now cloudflared

# Option B — compose service (portable, used from Phase 3)
cloudflared tunnel token emaw        # → SECRET_TUNNEL_TOKEN in .env, then make secrets-encrypt / secrets-decrypt
make up-ingress
```

GitLab webhook URL is always `https://webhook.<org>.com/webhook/gitlab` with the secret token from
`SECRET_GITLAB_WEBHOOK_SECRET`, events *Issues*, *Pipeline*, *Job*, SSL verification on.

Cheat sheet: `systemctl status cloudflared`, `journalctl -u cloudflared -f`,
`cloudflared tunnel list`, metrics at `http://127.0.0.1:2000/metrics` (`cloudflared_tunnel_*`).
