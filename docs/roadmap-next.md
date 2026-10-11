# EMAW — current state & next work (7920 LAN hybrid)

Last updated: **2026-10-11** (web-ops review against the desktop analysis; code still matches those findings).

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
Operator surfaces guide (TH): [operator-handbook.md](operator-handbook.md).

## Done recently (do not re-plan)

- Offline pack tooling + migrate readiness (phases A–F)
- 7920 host prep, online pull 14b, `offline-acceptance` PASSED
- Blueprint dashboard gaps → Console (Dispatch, Kanban, approval `comment`) — not a second SPA
- LAN hybrid: `CONSOLE_BIND` + `make up-lan` + docs/skills/rules
- Host install path moved to `/opt/emaw` (volumes `emaw_*` preserved)

## Next work (priority order)

Verified against current tree. Console proxies only `/api/internal/*` + `/api/healthz`.
Worker pause is per-message with mid-dispatch heartbeat. Browser auth is DECISION-21
(session cookie); service callers still use Hermes bearer + `X-EMAW-User-Id`.

### W0 — Close the LAN hole

**Repo (done):** nginx + Vite allowlist (`/api/internal/`, `/api/healthz` only).

**Host (7920, `/opt/emaw`) — still open:**

1. **Firewall.** Default deny; allow OpenSSH; allow LAN CIDR to **8088, 3030, 9119**.
2. **Rotate** compose-default passwords + `SECRET_HERMES_API_KEY` → `make secrets-dev` → recreate.
3. **Redeploy** console + adapters after pull: rebuild `operator-console`, recreate workers.
4. Prove from LAN: `/api/metrics` and `/api/webhook/gitlab` → 404; Console login with
   `console_secret` works.

### W1 — Pause must stop the worker

**Done in repo** (`queue-adapter`): pause before each message; requeue unstarted work;
heartbeat every 30s during dispatch. Recreate adapters on the host to pick up the image.

### W2 — Measure Ollama on this host (compose env, not a new server)

`docker-compose.local-free.yml` sets only `OLLAMA_CONTEXT_LENGTH`. On 7920, try
`OLLAMA_NUM_PARALLEL`, `OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`,
`OLLAMA_KEEP_ALIVE`, `OLLAMA_MAX_LOADED_MODELS` **one change at a time** and keep
what `make local-free-check` still passes. Do not copy a guessed set into the
default for every host. vLLM and a second inference stack stay out.

### W3 — Session login (DECISION-21)

**Done in repo:** per-user `console_secret` in `rbac.yaml` → `POST /internal/auth/login`
→ `HttpOnly` cookie + CSRF; SPA uses `credentials: "include"` (no Hermes key in
browser). Service bearer path unchanged. `/internal/rbac/users` is admin-only.

**Host:** copy `console_secret` into live `config/rbac.yaml` (see `rbac.example.yaml`),
rotate off the example values, restart gateway, rebuild console.

Host must set `console_secret` before handing Console to a second person. DLQ
retry/discard (W4) is admin-only and audited; still no settings write / restart UI.

### W4 — See health and the dead-letter stream

**Done in repo:** `GET /internal/ops/health|queues|dead-letter` + admin
`POST …/retry|discard` (audited); Console **System** page at `/system` (poll ~20s).
`ops_summary` version uses package `__version__`.

**Host:** rebuild/recreate gateway + console after pull. Live push / MinIO still out of scope.

### W5 — Host keeps running after reboot (7920 only)

**Done in repo:** `deploy/systemd/` (`emaw.service`, backup + restore-drill timers),
`scripts/host-*-timed.sh`, `make install-host-units`, runbook
[lan-host-7920.md](runbooks/lan-host-7920.md). Prefer `BACKUP_ROOT=/srv/emaw-backups`.

**Host:** `sudo make install-host-units` → `enable --now emaw.service` + both timers.
No restore button on the web. Delete any stray `backups/*;C` on the host if present.

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

### P3 — Console roadmap C (after W3; needs DECISION + exit criteria each)

From [operator-console.md](operator-console.md): C1 Deploy center · C2 Review board · C3 Meetings ritual · C4 Knowledge graph.  
Do not code until a DECISION note exists. Do not start these ahead of W3 — deploy and review actions need a real session.

### P4 — Optional later

- HTTPS reverse proxy in front of Console / Grafana / Hermes, still on the LAN, after W0. Not an IdP.
- LAN GitLab/GitHub webhooks → gateway `:8700` (still prefer loopback + reverse proxy)
- Re-pack 14b offline kit from 7920 for true air-gap transfer hosts
- Staging/prod cloud path remains [`deploy-linux-vm.md`](deploy-linux-vm.md) + `up-prod` (separate from this host)
- Hot-reload of `projects.yaml` / `rbac.yaml` only if restart pain shows up after several real projects. YAML stays the git source. A Postgres settings UI is a separate decision, not the next step.

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
- No publishing Redis/Postgres/MinIO/Hermes API / Prometheus on the LAN
- No web CRUD for projects, RBAC, or secrets (SOPS / `.env` stay off the browser)
- No `ops-runner` and no Console job that runs `docker compose`, `make down`, or `make restore`
- No adapter concurrency bump, vLLM cutover, or priority streams until W2 shows the GPU queue is the limit
- Promtail's read-only `docker.sock` stays (container log discovery). Do not mount the socket on agents.
