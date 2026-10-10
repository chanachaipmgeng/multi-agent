# Operator Console (DECISION-20)

Thin first-party SPA that wraps gateway `/internal/*` for operators.
Does **not** replace Telegram HITL (DECISION-17) or Grafana / Hermes / GitHost UIs —
except when Telegram is unavailable (air-gap) or not yet enabled (LAN + local LLM hybrid):
Console is the primary HITL (`make up-offline` or `make up-lan`; see
[offline-airgap.md](offline-airgap.md) / [environments.md](environments.md) /
[roadmap-next.md](roadmap-next.md)).

## Run

```bash
# gateway must be up (default compose or make up / up-local-free)
make up-console
# → http://127.0.0.1:8088
# air-gap one-shot: make up-offline  (local-free + console + observability)
# LAN hybrid (online host + local Ollama, Console on LAN IP):
#   CONSOLE_BIND=0.0.0.0 in .env → make up-lan → http://<host-ip>:8088
```

Default bind is loopback. Set `CONSOLE_BIND=0.0.0.0` only on trusted LAN hosts; restrict with
host firewall (`ufw allow from <LAN_CIDR> to any port 8088`). Do not publish Redis/Postgres/
MinIO/Hermes API to the LAN by default.

Compose runs nginx with `read_only` + tmpfs; `cap_add` includes `CHOWN`/`SETUID`/`SETGID` so the
stock entrypoint can prepare cache dirs (otherwise the container crash-loops).

Local vite (dev):

```bash
cd operator-console && npm install && npm run dev
# proxies /api → http://127.0.0.1:8700
```

Login: `HERMES_API_KEY` + Telegram user id from `config/rbac.yaml`.

## Screens (B)

| Page | API |
|---|---|
| Tasks / detail (table + Kanban board) | `GET /internal/tasks`, `GET /internal/tasks/{id}`, `GET /internal/audit` |
| Dispatch (manual create-task) | `POST /internal/tasks`, `GET /internal/projects` |
| Approvals inbox + history | `GET /internal/approvals?status=pending\|decided`, `POST …/decide` (`comment` optional) |
| Audit search | `GET /internal/audit?task_id=\|trace_id=` |
| Control | `GET/POST /internal/control/*` |
| Projects | `GET /internal/projects` |
| Links | Hermes `:9119`, Grafana `:3000` / Explore, MinIO `:9001` |

Task detail shows SCM deep-links from `source.url`, `inputs.repo`, and URLs found in handoffs (`links[]`),
plus Loki Explore links filtered by `task_id` / `trace_id` (see [runbooks/trace-by-event.md](runbooks/trace-by-event.md)).

## Blueprint map (do not rebuild a second presentation layer)

External “dashboard /api + Streamlit” sketches map onto this Console + `/internal/*` only.
Do **not** add a parallel SPA, `/api/tasks` aliases, or Streamlit for the same job.

| Sketch endpoint / UI | EMAW surface |
|---|---|
| `GET /api/tasks` | `GET /internal/tasks` · Tasks table / board |
| `GET /api/tasks/{id}/audit` | `GET /internal/audit?task_id=` · Task detail + Audit |
| `POST /api/tasks/create` | `POST /internal/tasks` · **Dispatch** page |
| `POST /api/tasks/{id}/action` | `POST /internal/approvals/{nonce}/decide` (nonce model; optional `comment`) |
| Metrics | Grafana / Prometheus + gateway `/healthz` (Links page) |
| WebSocket task push | Out of scope — Refresh / short poll in UI |
| Telegram HITL | Cloud path only; air-gap uses this Console ([offline-airgap.md](offline-airgap.md)) |

## Roadmap C (after B stable)

Each step needs its own DECISION note + exit criteria before coding.

### C1 — Deploy center

| Item | Criterion |
|---|---|
| Scope | Queue/filter `type=deploy_request` + approval history for deploy actions |
| Non-goal | No CD engine — still uses skill `deploy-prod` + HITL |
| Exit | Console page lists deploy tasks; decide from inbox; audit trail visible |

### C2 — Review board

| Item | Criterion |
|---|---|
| Scope | Handoffs with `to_agent=reviewer` + artifact / SocratiCode links |
| Non-goal | No new review engine |
| Exit | Filter tasks in REVIEW; open artifact URLs from handoff JSON |

### C3 — Meetings ops ritual

| Item | Criterion |
|---|---|
| Scope | Checklist UI from [runbooks/weekly-log-review.md](runbooks/weekly-log-review.md) + deep-links |
| Non-goal | Not a Zoom/Meet clone; no calendar sync required in v1 |
| Exit | Operator can mark ritual steps and jump to Grafana/audit |

### C4 — Knowledge graph (read-only)

| Item | Criterion |
|---|---|
| Scope | Graph of `trace_id → task → agent → file/artifact` from audit/handoffs (optional Qdrant) |
| Non-goal | Not a second brain / wiki; write path stays agents |
| Exit | Read-only graph view for one project/trace; documented data source |

## Telegram 24/7 checklist (LAN + local LLM — future)

Keep `LLM_MODE=local` / Ollama. Telegram is an extra HITL channel (Hermes long-poll
**outbound** to `api.telegram.org`) — no inbound port publish for the bot.

Do **not** invent tokens or user ids; fill from [org-unblock.md](org-unblock.md).

1. Set `SECRET_TELEGRAM_TOKEN` and `TELEGRAM_ALLOWED_USERS` in `.env` → `make secrets-dev`
   (or decrypt) so `scripts/hermes-seed-env.sh` writes coordinator `/opt/data/.env`
2. Put real Telegram user ids in `config/rbac.yaml` (DECISION-8); restart gateway if needed
3. Confirm coordinator container can reach `api.telegram.org` (host has outbound net)
4. Smoke: message the bot → task appears in Console Tasks / Dispatch still works
5. Optional: Alertmanager `TELEGRAM_CHAT_ID` for alerts (separate from Hermes HITL)

Until those values exist, use Console on LAN (`CONSOLE_BIND=0.0.0.0` + `make up-lan`) as
primary HITL.

## Related

- Design non-goal amendment: `docs/design/system-design-v1.1.md` §2.4
- Decision: `docs/decisions.md` DECISION-20
- Verify: `.cursor/skills/verify-emaw/features/operator-console.md`
- Environments: [environments.md](environments.md) (LAN + local LLM column)
