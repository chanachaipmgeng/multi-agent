# EMAW verification map

Maintained source for proving operator-facing behavior of the Enterprise Multi-Agent Workspace platform.

## Baseline preconditions

- Repo root is the compose project (`docker-compose.yml`).
- Secrets materialised: `secrets/gitlab_webhook_secret`, `secrets/hermes_api_key` (via `make secrets-dev` or decrypt).
- Prefer stack already up from `make up-local-free` + `make up-observability` (or `make up-offline` on air-gap hosts).
- Run `bash .cursor/skills/verify-emaw/bin/verify-emaw.sh doctor` first.
- Evidence goes under `.cursor/skills/verify-emaw/evidence/<RUN_ID>/` and must survive cleanup.
- Air-gap pack/load: [`docs/offline-airgap.md`](../../../../docs/offline-airgap.md).

## Driving conventions

- Harness: `verify-emaw.sh` (curl + make + docker).
- Treat every command as literal.
- Do not `make down` unless the user asked — the local stack is shared.
- RBAC user for internal API defaults to `987654321` (admin in `config/rbac.example.yaml`); override with `VERIFY_EMAW_USER_ID` if your `rbac.yaml` differs.

## Features

- [Gateway health](./gateway-health.md) — `/healthz` + `/metrics`
- [Phase 3 smoke](./phase3-smoke.md) — `make phase3-check` / script
- [Observability](./observability.md) — Prometheus, Alertmanager, Grafana dashboards
- [Webhook enqueue](./webhook-enqueue.md) — sample Issue Hook
- [Pause control](./pause-control.md) — internal pause/resume
- [Operator console](./operator-console.md) — `/internal/projects` + control status + optional `:8088`
- [Local-free / air-gap](./local-free-offline.md) — `make local-free-check` + optional Console after `up-offline`
