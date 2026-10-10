# EMAW — current state & next work (7920 LAN hybrid)

Last updated: **2026-10-11** (UTC date context: install + Console LAN bind).

## Current mode (production-ish on Precision 7920)

| Item | Value |
|---|---|
| Host | `10.50.0.117` (Ubuntu, 2× RTX 5000) |
| Install path | **`/opt/emaw`** (`COMPOSE_PROJECT_NAME=emaw`; was `/home/myhr/emaw`) |
| Stack | `make up-lan` semantics: local-free + console + observability |
| LLM | `LLM_MODE=local` · `qwen2.5-coder:14b` + `nomic-embed-text` (not OpenRouter) |
| Console | `CONSOLE_BIND=0.0.0.0` → **http://10.50.0.117:8088** |
| Grafana | `127.0.0.1:3030` (host `:3000` taken by open-webui) |
| HITL now | Operator Console (Dispatch / Tasks board / Approvals) |
| Telegram | **not enabled** (checklist in [operator-console.md](operator-console.md)) |
| Cloudflare / `up-prod` | **not used** |

Prove notes: [offline-airgap.md](offline-airgap.md) pack-host table. Environments: [environments.md](environments.md) column **LAN + local LLM**.

## Done recently (do not re-plan)

- Offline pack tooling + migrate readiness (phases A–F)
- 7920 host prep, online pull 14b, `offline-acceptance` PASSED
- Blueprint dashboard gaps → Console (Dispatch, Kanban, approval `comment`) — not a second SPA
- LAN hybrid: `CONSOLE_BIND` + `make up-lan` + docs/skills/rules
- Host install path moved to `/opt/emaw` (volumes `emaw_*` preserved)

## Next work (priority order)

### P0 — Operate safely on LAN

1. **Firewall:** host `ufw` was inactive at LAN bind time — enable and  
   `ufw allow from 10.50.0.0/16 to any port 8088` (adjust CIDR to real LAN)
2. **Rotate SSH password** used for install (never commit secrets)
3. **Operator habit:** login Console with `secrets/hermes_api_key` + `rbac.yaml` user; prefer Dispatch over ad-hoc SSH for drills

### P1 — Real project onboard (local-free still)

1. Clone app into `workspace/<key>/` (`make onboard` if URL known)
2. Register in [`config/projects.yaml`](../config/projects.yaml) with `llm_backend: ollama` for sensitive data
3. Restart gateway; Dispatch create-task on that `project` key
4. Fill `project-standards.md` / test command so agents can green-path

### P2 — Telegram 24/7 (same local LLM)

Do **not** switch to OpenRouter. Follow checklist in [operator-console.md](operator-console.md) § Telegram:

1. Real bot token + `TELEGRAM_ALLOWED_USERS` → secrets / hermes-seed  
2. Real Telegram user ids in `config/rbac.yaml` (DECISION-8) — see [org-unblock.md](org-unblock.md)  
3. Outbound net to `api.telegram.org` from coordinator  
4. Smoke: Telegram command → task visible in Console  

Blocked until org fills DECISION-8 values (do not invent ids).

### P3 — Console roadmap C (needs DECISION + exit criteria each)

From [operator-console.md](operator-console.md): C1 Deploy center · C2 Review board · C3 Meetings ritual · C4 Knowledge graph.  
Do not code until a DECISION note exists.

### P4 — Optional later

- Bind Grafana to LAN (or reverse proxy) if operators need it without SSH
- LAN GitLab/GitHub webhooks → gateway `:8700` (still prefer loopback + reverse proxy)
- Re-pack 14b offline kit from 7920 for true air-gap transfer hosts
- Staging/prod cloud path remains [`deploy-linux-vm.md`](deploy-linux-vm.md) + `up-prod` (separate from this host)

## Operator proof commands

```bash
# On 7920
cd /opt/emaw
set -a && source .env && set +a   # so LOCAL_LLM_MODEL=14b is seen by checks
make local-free-check
make offline-acceptance          # honors GRAFANA_PORT
curl -fsS -o /dev/null -w '%{http_code}\n' http://10.50.0.117:8088/

# From laptop / verify-emaw
bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive operator-console
bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive local-free-offline
```

## Explicit non-goals on this host

- No Cloudflare tunnel / OpenRouter / `make up-prod`
- No second Streamlit/React control plane beside Operator Console
- No publishing Redis/Postgres/MinIO/Hermes API on the LAN by default
