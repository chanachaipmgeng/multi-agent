# Webhook Gateway (FastAPI)

Ingress service of the Enterprise Multi-Agent Workspace. One canonical endpoint:

```
POST /webhook/gitlab
```

| Step | Behaviour | Response |
|---|---|---|
| Transport guard | JSON only, body ≤ 1 MiB | `415` / `413` |
| Auth | constant-time compare of `X-Gitlab-Token` | `401 invalid_token` |
| Event allowlist | `Issue Hook`, `Pipeline Hook`, `Job Hook` | `200 ignored` otherwise |
| Project allowlist | `project.id` / `path_with_namespace` must exist in `config/projects.yaml` | `403 project_not_allowed` |
| Idempotency | `X-Gitlab-Event-UUID` claimed in Redis (`SET NX EX`, TTL 24 h) | `200 duplicate` |
| Normalize | GitLab payload → Task envelope (design §4.3); opt-in label `agent-ready` | `200 recorded` / `200 ignored` |
| Persist + enqueue | row in `tasks` + audit events, `XADD stream:tasks` | `200 queued` |

Other endpoints: `GET /healthz` (liveness), `GET /readyz` (Redis + task store), `GET /metrics` (Prometheus).

## Configuration (environment)

| Variable | Default | Notes |
|---|---|---|
| `GITLAB_WEBHOOK_SECRET` / `GITLAB_WEBHOOK_SECRET_FILE` | — | **required**; prefer the `_FILE` form (Docker secret) |
| `REDIS_URL` | `redis://localhost:6379/0` | idempotency keys + task stream |
| `TASK_STREAM` | `stream:tasks` | coordinator inbox |
| `DATABASE_URL` | unset | PostgreSQL task store; `${PG_PASSWORD}` is substituted from `PG_PASSWORD_FILE` |
| `PROJECTS_FILE` | `/config/projects.yaml` | project allowlist + routing |
| `IDEMPOTENCY_TTL_SECONDS` | `86400` | |
| `MAX_BODY_BYTES` | `1048576` | |
| `PORT` | `8700` | |

## Develop & test

```bash
cd webhook-gateway
uv venv && uv pip install -e ".[dev]"      # or: python -m venv .venv && pip install -e ".[dev]"
.venv/bin/pytest -q                        # unit tests use fakeredis + in-memory task store
TEST_DATABASE_URL=postgresql://emaw:emaw@localhost:5432/emaw .venv/bin/pytest -q -m integration
```

Run locally against the compose Redis/Postgres:

```bash
GITLAB_WEBHOOK_SECRET=dev-secret PROJECTS_FILE=../config/projects.yaml \
REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m app.main
```
