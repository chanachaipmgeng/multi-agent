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

Other endpoints: `GET /healthz`, `GET /readyz`, `GET /metrics`.

## Internal API (Phase 3 / DECISION-16)

Bearer = `HERMES_API_KEY`; header `X-EMAW-User-Id` = Telegram user id. RBAC from `RBAC_FILE`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/internal/tasks` | Telegram → Task envelope → `stream:tasks` |
| GET | `/internal/tasks` · `/internal/tasks/{id}` | status-report |
| POST | `/internal/approvals` · `…/{nonce}/decide` | HITL (DECISION-17) |
| POST | `/internal/control/pause\|resume\|safe-mode` | kill switch / safe mode |

## Configuration (environment)

| Variable | Default | Notes |
|---|---|---|
| `GITLAB_WEBHOOK_SECRET` / `GITLAB_WEBHOOK_SECRET_FILE` | — | **required** |
| `HERMES_API_KEY` / `HERMES_API_KEY_FILE` | — | internal API bearer |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `TASK_STREAM` | `stream:tasks` | |
| `DATABASE_URL` | unset | `${PG_PASSWORD}` from `PG_PASSWORD_FILE` |
| `PROJECTS_FILE` | `/config/projects.yaml` | |
| `RBAC_FILE` | `/config/rbac.yaml` | |
| `CONTROL_PREFIX` | `emaw:control` | pause / safe_mode keys |
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
