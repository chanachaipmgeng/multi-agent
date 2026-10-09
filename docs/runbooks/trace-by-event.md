# Runbook — Trace a GitLab/GitHub event end-to-end

Correlate from webhook ingress → task → adapters using `event_uuid`, `task_id`, and `trace_id`.

## IDs

| ID | Source | Notes |
|---|---|---|
| `event_uuid` | `X-Gitlab-Event-UUID` / GitHub delivery id | Idempotency key; in audit `attrs.event_uuid` and gateway logs |
| `task_id` | Task envelope / console Tasks | Primary key in Postgres `tasks` |
| `trace_id` | Task envelope | Shared across handoffs / audit rows |

## 1. Loki (after `make up-observability`)

Gateway/adapters log structured fields: `task_id=… trace_id=… event_uuid=…`.

```logql
{compose_service="webhook-gateway"} |= `event_uuid=<UUID>`
{compose_service=~"webhook-gateway|router|adapter-.*"} |= `task_id=<TASK_ID>`
{compose_service=~"webhook-gateway|router|adapter-.*"} |= `trace_id=<TRACE_ID>`
```

Grafana Explore → Loki → paste query. Structured metadata may also expose `task_id` /
`trace_id` / `event_uuid` when Promtail parsed the line.

## 2. Control plane / Operator Console (authoritative)

```bash
# CLI
make simulate-operator CMD="audit --task-id <TASK_ID>"
# or
curl -sS -H "Authorization: Bearer $(cat secrets/hermes_api_key)" \
  -H "X-EMAW-User-Id: 987654321" \
  "http://127.0.0.1:8700/internal/audit?trace_id=<TRACE_ID>"
```

Console: `make up-console` → Task detail (per-task audit) or **/audit** (search by
`task_id` / `trace_id`). Export day: `make audit-export DAY=YYYY-MM-DD`.

## 3. Typical path

1. Find `event_uuid` in GitLab webhook delivery log (or `make webhook-test` output UUID).
2. Loki gateway line → read `task_id` / `trace_id`.
3. Follow router `routed task_id=…` then adapter `dispatched task_id=…`.
4. Confirm state/audit in console or `/internal/audit`.
