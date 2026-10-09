# Operator Console (DECISION-20)

Thin first-party SPA that wraps gateway `/internal/*` for operators.
Does **not** replace Telegram HITL (DECISION-17) or Grafana / Hermes / GitHost UIs —
except on **air-gap** hosts where Telegram is unavailable: Console is the primary HITL
(`make up-offline`; see [offline-airgap.md](offline-airgap.md)).

## Run

```bash
# gateway must be up (default compose or make up / up-local-free)
make up-console
# → http://127.0.0.1:8088
# air-gap one-shot: make up-offline  (local-free + console + observability)
```

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
| Tasks / detail | `GET /internal/tasks`, `GET /internal/tasks/{id}`, `GET /internal/audit` |
| Approvals inbox + history | `GET /internal/approvals?status=pending\|decided`, `POST …/decide` |
| Audit search | `GET /internal/audit?task_id=\|trace_id=` |
| Control | `GET/POST /internal/control/*` |
| Projects | `GET /internal/projects` |
| Links | Hermes `:9119`, Grafana `:3000` / Explore, MinIO `:9001` |

Task detail shows SCM deep-links from `source.url`, `inputs.repo`, and URLs found in handoffs (`links[]`),
plus Loki Explore links filtered by `task_id` / `trace_id` (see [runbooks/trace-by-event.md](runbooks/trace-by-event.md)).

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

## Related

- Design non-goal amendment: `docs/design/system-design-v1.1.md` §2.4
- Decision: `docs/decisions.md` DECISION-20
- Verify: `.cursor/skills/verify-emaw/features/operator-console.md`
