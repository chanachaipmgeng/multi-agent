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

Verified against current tree (not only the analysis note). Console calls only
`/api/internal/*` plus `/api/healthz`. Gateway still trusts a shared bearer plus a
client-supplied `X-EMAW-User-Id`. Worker adapters still pause-check once per batch.

One operator on this host may keep using today's login for drills. Do **not** hand
Console to a second person until W3 (session) is in.

### W0 — Close the LAN hole (do first)

Host (7920, `/opt/emaw`) — no product code:

1. **Firewall.** `ufw` was inactive when Console was bound to the LAN. Default deny,
   allow OpenSSH, then allow the LAN CIDR to **8088, 3030, and 9119** only
   (Console, Grafana, Hermes dashboard all follow `CONSOLE_BIND`). Leave Redis,
   Postgres, MinIO, Hermes API, Prometheus, and gateway `:8700` off the LAN.
2. **Rotate host secrets** that still have compose defaults if `.env` was never
   filled: `GRAFANA_ADMIN_PASSWORD`, `MINIO_ROOT_PASSWORD`,
   `SECRET_DASHBOARD_PASSWORD`, `SECRET_HERMES_API_KEY` (long random), then
   `make secrets-dev` and recreate those services. Rotate the install SSH password.
   Never commit the values.
3. **Stay on CLI for infra.** Backup, restart, onboard, model pull stay `make` on
   the host until a later decision says otherwise.

Repo (small, then redeploy console on the host):

4. **Nginx allowlist.** `operator-console/nginx.conf` `location /api/` proxies the
   whole gateway, so with `CONSOLE_BIND=0.0.0.0` the LAN can reach
   `/api/webhook/gitlab`, `/api/webhook/github`, `/api/metrics`, `/api/readyz`.
   Proxy only `/api/internal/` and `/api/healthz`. Match the Vite dev proxy.
   Exit: from the LAN, `/api/metrics` and `/api/webhook/gitlab` are 404; Home,
   Dispatch, Approvals, and Links health still work.

### W1 — Pause must stop the worker (code, before more Console features)

`queue-adapter` `StreamConsumer.run_once` checks pause once, then `XREADGROUP
count=10` and handles messages one by one. A long dispatch (timeout 1800s) means
later messages in that batch ignore pause, and `emaw:heartbeat:*` (TTL 180s) goes
stale so the adapter looks dead. The router already defers per message; workers do not.

- Check pause (and do not start new work) before each message, including autoclaim.
- Refresh heartbeat on a timer during dispatch, not only after the batch.
- Exit: pause mid-batch does not dispatch the rest; heartbeat key stays fresh across
  a long run; existing consumer tests still pass.
- Do **not** raise per-role concurrency here. Two 16 GB GPUs and `qwen2.5-coder:14b`
  at 64K context already cap the host around one or two in-flight calls.

### W2 — Measure Ollama on this host (compose env, not a new server)

`docker-compose.local-free.yml` sets only `OLLAMA_CONTEXT_LENGTH`. On 7920, try
`OLLAMA_NUM_PARALLEL`, `OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`,
`OLLAMA_KEEP_ALIVE`, `OLLAMA_MAX_LOADED_MODELS` **one change at a time** and keep
what `make local-free-check` still passes. Do not copy a guessed set into the
default for every host. vLLM and a second inference stack stay out.

### W3 — Session login (needs DECISION-21 before coding)

DECISION-20 accepted a shared `HERMES_API_KEY` plus `X-EMAW-User-Id` for loopback
v1, with Cloudflare Access later. LAN bind changed that: anyone with the key can
send another user's id, and `/internal/rbac/users` lists ids and roles to any
viewer. The key is the same one the six agents use, and the SPA stores it in
`localStorage`.

Write **DECISION-21** first. Proposed shape for this host (air-gap capable, no org IdP):

- Gateway issues an `HttpOnly; Secure; SameSite=Strict` session bound to a user in
  `config/rbac.yaml`. The browser never sees `HERMES_API_KEY`.
- Browser requests are not authorized by a client-supplied user id. Coordinator and
  adapters keep a server-side credential.
- Roles stay viewer / developer / maintainer / approver / admin. Map a web user to
  the existing Telegram id field so DECISION-8 still fits when Telegram is turned on.
- CSRF on mutating POSTs.
- Prod/cloud auth stays DECISION-20 (Cloudflare Access). Do not add Authentik,
  Keycloak, or a second user database in this decision.

Exit: a non-admin session cannot decide an approver action or call pause; changing
the user id in the client does nothing; Hermes key is absent from browser storage.

Until W3 lands, do not add admin mutations (DLQ retry, settings write, restart).

### W4 — See health and the dead-letter stream (after W3)

Thin `/internal/*` reads, then a Console page. No second UI.

| Page | Source | v1 actions |
|---|---|---|
| System health | Redis `emaw:heartbeat:*`, gateway `/readyz` | Read-only |
| Queue / DLQ | `XLEN` / `XPENDING` on `stream:*`, `stream:dead-letter` | List. Retry or discard is admin-only and audited |

Live push (SSE/WebSocket) stays out of scope (DECISION-20: short poll). Task
artifacts via a gateway presign can follow; do not publish MinIO.

### W5 — Host keeps running after reboot (7920 only)

- systemd unit: `WorkingDirectory=/opt/emaw`, `ExecStart` the same `make up-lan`
  the host already uses. `restart: unless-stopped` does not recreate profiles.
- Daily `make backup`, weekly `make restore-drill` (DECISION-19). No restore button
  on the web.
- Keep `offline-pack/` and `backups/` outside the git worktree. Delete the stray
  `backups/*;C` directory if it is still on the host (bad Windows path). Do not
  commit those trees.

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
- `ops_summary` version is hardcoded `"0.1.0"` while `webhook-gateway/app/__init__.py` already has `__version__` — fold into a touch of that handler, not its own project.

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
