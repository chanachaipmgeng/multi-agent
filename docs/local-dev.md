# Local development (WSL2 / Linux) — Phase 0

## 1. Host

```bash
make prereqs                        # D0.1 — git, docker + compose v2, python3, node 20, sops, age
```

WSL2 extras (from the source guide): `[boot] systemd=true` in `/etc/wsl.conf`, Docker Desktop →
Settings → Resources → WSL Integration enabled for the distro, keep Windows from sleeping.

## 2. Secrets

```bash
make secrets-init                   # age key + .sops.yaml recipient
cp .env.example .env && $EDITOR .env
make secrets-encrypt                # → .env.enc (commit)
make secrets-decrypt                # → secrets/* for compose
```

Quick dev box without SOPS: `cp .env.example .env && make secrets-dev`.

## 3. Platform stack

```bash
make up                             # redis + postgres (+ migrations on first boot) + webhook-gateway
curl -s localhost:8700/readyz       # {"status":"ok","checks":{"redis":true,"task_store":true}}
make webhook-test                   # sample Issue Hook → {"status":"queued", ...}
make webhook-test KIND=pipeline     # → pipeline_failed routed to devops
scripts/send-test-webhook.sh issue --bad-token   # → HTTP 401
docker compose exec redis redis-cli XLEN stream:tasks
docker compose exec postgres psql -U emaw -c 'select task_id,type,state,assigned_to from tasks'
```

Ports (all bound to 127.0.0.1): gateway 8700, redis 6379, postgres 5432, Hermes dashboard 9119.
Override with `GATEWAY_PORT`, `REDIS_PORT`, `POSTGRES_PORT` in `.env`.

## 4. Hermes (single agent for Phase 0)

Option A — host install (as in the source guide):

```bash
curl -fsSLO https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh && bash install.sh
hermes setup                                       # primary + fallback provider
TELEGRAM_ALLOWED_USERS=<your id> make hermes-configure   # terminal.backend=docker, allowlist, tokens
make skills-sync                                   # dev-flow, review-code, human-approval-gate
hermes run "id"                                    # sandbox uid, not yours (checklist #1)
hermes gateway run
```

Option B — container profile:

```bash
docker compose --profile agents up -d dev-backend  # or coordinator / dev-frontend
```

Then on Telegram: `ใช้ dev-flow ใน /workspace/sandbox-smoke เพิ่มฟังก์ชัน subtract พร้อม test`.
Expected: commit on a work branch, `./test.sh` green, and an approval prompt *before* any push.

## 5. Onboard the pilot repo (D0.4)

```bash
make onboard KEY=backend-api URL=git@gitlab.com:acme/backend-api.git TEST="pytest -q"
$EDITOR workspace/backend-api/project-standards.md
$EDITOR config/projects.yaml            # real gitlab_project_id + path_with_namespace
docker compose restart webhook-gateway  # reloads projects.yaml
```

## 6. Tests & checks

```bash
make test               # gateway unit tests (fakeredis, in-memory store)
make test-integration   # needs TEST_DATABASE_URL=postgresql://emaw:<pw>@localhost:5432/emaw
make lint               # ruff
make gitleaks           # secret scan
make verify-phase0      # exit-criteria self-check
make hooks              # pre-commit (gitleaks + ruff) on every commit
```
