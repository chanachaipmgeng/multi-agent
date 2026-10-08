# Runbook — Cloudflare Tunnel (ingress)

Scope: Named Tunnel `emaw` → `https://webhook.<org>.com/webhook/gitlab` (and `/webhook/github`) → webhook-gateway `:8700`.
Design §5.2, checklist E1. Blocked until DECISION-5 (domain on the team's Cloudflare account).

## Setup (once)

```bash
cloudflared tunnel login                                   # browser → pick the zone
scripts/tunnel-setup.sh webhook.<org>.com emaw --service   # create, DNS, config.yml, systemd
scripts/tunnel-status.sh https://webhook.<org>.com         # 401 on /webhook/gitlab = healthy; 404 on /healthz = path filter OK
```

Compose variant (portable, Phase 3): `cloudflared tunnel token emaw` → `SECRET_TUNNEL_TOKEN` in `.env`
→ `make secrets-encrypt && make secrets-decrypt && make up-ingress`.

WSL2: `/etc/wsl.conf` needs `[boot] systemd=true`; after editing run `wsl --shutdown` from PowerShell.
Keep Windows awake and schedule `wsl -d Ubuntu-24.04 -- true` at logon so the distro (and the
service) starts without opening a terminal.

## Symptoms → actions

| Symptom | Check | Action |
|---|---|---|
| GitLab webhook log shows timeouts / `Hook execution failed` | `scripts/tunnel-status.sh` → cloudflared inactive | `sudo systemctl restart cloudflared` (host) or `docker compose --profile ingress restart cloudflared`; GitLab retries automatically once the tunnel is back |
| `cloudflared` active but public URL → 502/530 | gateway down: `curl 127.0.0.1:8700/readyz` | `make up` / `docker compose logs webhook-gateway`; check Redis/Postgres health |
| Public URL → 401 for real GitLab events | secret mismatch | compare GitLab webhook "Secret token" with `secrets/gitlab_webhook_secret`; re-run `scripts/gitlab-webhook-register.sh` |
| Public URL → 403 | project not allowlisted | add real `gitlab_project_id` to `config/projects.yaml`, `docker compose restart webhook-gateway` |
| `/healthz` or `/metrics` reachable publicly | ingress `path` filter missing | config.yml must have `path: ^/webhook/.*` and end with `http_status:404`; `cloudflared tunnel ingress validate` |
| Tunnel flaps after Windows sleep | WSL2 suspended | disable sleep / use a Linux VM (planned from Phase 3) |
| DNS record wrong | `cloudflared tunnel route dns --overwrite-dns emaw <host>` | |

Logs: `journalctl -u cloudflared -f` (host) · `docker compose logs -f cloudflared` (compose) ·
metrics `http://127.0.0.1:2000/metrics` (`cloudflared_tunnel_ha_connections` should be ≥ 1; Phase 4 alert `tunnel_up`).

## Rotate the tunnel credential

`cloudflared tunnel delete emaw` is destructive — prefer creating `emaw-2`, moving DNS with
`route dns --overwrite-dns`, switching config/token, then deleting the old tunnel after a day.
