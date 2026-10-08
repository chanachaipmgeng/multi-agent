# Webhook Gateway (FastAPI)

Ingress service of the Enterprise Multi-Agent Workspace. Dual SCM webhooks + internal control plane.

## GitLab — `POST /webhook/gitlab`

| Step | Behaviour | Response |
|---|---|---|
| Transport guard | JSON only, body ≤ 1 MiB | `415` / `413` |
| Auth | constant-time compare of `X-Gitlab-Token` | `401 invalid_token` |
| Event allowlist | `Issue Hook`, `Pipeline Hook`, `Job Hook` | `200 ignored` otherwise |
| Project allowlist | `project.id` / `path_with_namespace` must exist in `config/projects.yaml` (`scm: gitlab`) | `403 project_not_allowed` |
| Idempotency | `X-Gitlab-Event-UUID` claimed in Redis (`SET NX EX`, TTL 24 h) | `200 duplicate` |
| Normalize | GitLab payload → Task envelope (design §4.3); opt-in label `agent-ready` | `200 recorded` / `200 ignored` |
| Persist + enqueue | row in `tasks` + audit events, `XADD stream:tasks` | `200 queued` / `200 attached` |

## GitHub — `POST /webhook/github`

| Step | Behaviour | Response |
|---|---|---|
| Transport guard | JSON only, body ≤ 1 MiB | `415` / `413` |
| Secret present | `GITHUB_WEBHOOK_SECRET(_FILE)` required | `503 github_webhook_not_configured` |
| Auth | HMAC-SHA256 of raw body vs `X-Hub-Signature-256` (`sha256=<hex>`) | `401 invalid_signature` |
| Event allowlist | `issues`, `workflow_run`, `workflow_job` (`X-GitHub-Event`) | `200 ignored` otherwise |
| Project allowlist | `repository.full_name` / `id` vs `repo` / `repo_id` (`scm: github`) | `403 project_not_allowed` |
| Idempotency | `X-GitHub-Delivery` claimed in Redis (TTL 24 h) | `200 duplicate` |
| Normalize | GitHub payload → Task envelope + `scm` / `scm_context` | `200 recorded` / `200 ignored` / `200 queued` |

Other endpoints: `GET /healthz`, `GET /readyz`, `GET /metrics`.

## Internal API (Phase 3 / DECISION-16 + DECISION-20)

Bearer = `HERMES_API_KEY`; header `X-EMAW-User-Id` = Telegram user id. RBAC from `RBAC_FILE`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/internal/tasks` | Telegram / console → Task envelope → `stream:tasks` |
| GET | `/internal/tasks` · `/internal/tasks/{id}` | status-report + console detail (`payload_summary`, `links`, `paused_agents`) |
| GET | `/internal/approvals` | list pending (Operator Console inbox) |
| POST | `/internal/approvals` · `…/{nonce}/decide` | HITL (DECISION-17) |
| GET | `/internal/control/status` | pause / safe-mode snapshot |
| POST | `/internal/control/pause\|resume\|safe-mode` | kill switch / safe mode |
| GET | `/internal/projects` | allowlist from `projects.yaml` (redacted) |
| GET | `/internal/audit` | recent audit events (filter by `task_id`) |

Operator Console SPA: `make up-console` → http://127.0.0.1:8088 — see [`docs/operator-console.md`](../docs/operator-console.md).

## Configuration (environment)

| Variable | Default | Notes |
|---|---|---|
| `GITLAB_WEBHOOK_SECRET` / `GITLAB_WEBHOOK_SECRET_FILE` | — | **required** at boot |
| `GITHUB_WEBHOOK_SECRET` / `GITHUB_WEBHOOK_SECRET_FILE` | — | optional at boot; required for `/webhook/github` |
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
