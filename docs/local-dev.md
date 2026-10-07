# Local development (WSL2 / Linux / Docker Desktop) — Phase 0+

## 1. Host

```bash
make prereqs                        # D0.1 — git, docker + compose v2, python3, node 20, sops, age
```

WSL2 extras (from the source guide): `[boot] systemd=true` in `/etc/wsl.conf`, Docker Desktop →
Settings → Resources → WSL Integration enabled for an **Ubuntu** distro (not only `docker-desktop`),
keep Windows from sleeping.

See [`docs/hermes-capability-check.md`](hermes-capability-check.md) and [`docs/decisions.md`](decisions.md)
(DECISION-1, DECISION-14).

## 2. Secrets

```bash
make secrets-init                   # age key + .sops.yaml recipient
cp .env.example .env && $EDITOR .env
# Required for agents: SECRET_TELEGRAM_TOKEN, TELEGRAM_ALLOWED_USERS, SECRET_LLM_KEY_*,
# SECRET_HERMES_API_KEY (Bearer for :8642)
make secrets-encrypt                # → .env.enc (commit)
make secrets-decrypt                # → secrets/* for compose
```

Quick dev box without SOPS: `cp .env.example .env && make secrets-dev`.

## 3. Platform stack

```bash
cp config/rbac.example.yaml config/rbac.yaml
make up                             # redis + postgres + gateway + minio + router + 5 adapters
curl -s localhost:8700/readyz
make webhook-test                   # → queued → router → stream:<role>
make phase3-check                   # after agents are up
```

Ports (all bound to `127.0.0.1`): gateway 8700, redis 6379, postgres 5432, MinIO 9000/9001,
Hermes dashboard 9119, Hermes API 8642 (coordinator) / 8643 (dev-backend).

## 3b. SocratiCode infra (Phase 2 / DECISION-6)

```bash
make up-socraticode                 # Ollama :11435 + Qdrant :16333/:16334 (loopback)
make socraticode-check              # /api/tags + /readyz + embedding model present
```

First-time (or empty volume) — pull the embedding model SocratiCode expects:

```bash
docker exec socraticode-ollama ollama pull nomic-embed-text
make socraticode-check
```

Volumes reuse `socraticode_ollama_data` / `socraticode_qdrant_data` if they already exist.
In-compose URLs for the reviewer MCP: `http://socraticode-ollama:11434`,
`http://socraticode-qdrant:6333`. Host-side MCP: `http://127.0.0.1:11435` /
`http://127.0.0.1:16333`. Confidential LLM stays on profile `onprem-llm`
(`inference-ollama`) — do not share model stores.

`mcp_servers.socraticode` is enabled in the reviewer profile (DECISION-6 local AGPL —
no API key). See `docs/phase2-exit-criteria.md`.

## 3c. Local-free mode (DECISION-15 + DECISION-6)

Runs platform + router/adapters + MinIO + SocratiCode + `inference-ollama` + **all 6 agents**
on a shared local LLM (`qwen2.5-coder:7b` by default). No OpenRouter keys required.

```bash
# .env: SECRET_HERMES_API_KEY=…  (Telegram optional for API-only drills)
make secrets-dev
make up-local-free              # compose -f docker-compose.yml -f docker-compose.local-free.yml
make local-llm-pull             # first time: pull qwen2.5-coder:7b (needs NVIDIA GPU)
make local-free-check && make phase3-check
```

Host ports: inference Ollama `127.0.0.1:11436`, SocratiCode Ollama `11435`, Qdrant `16333`.
Configs: `hermes-data/*/config.local-free.yaml` (mounted over `config.yaml`).

## 4. Hermes (single agent for Phase 0)

### Option A — host install (Ubuntu WSL2 / Linux)

```bash
curl -fsSLO https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh && bash install.sh
hermes setup                                       # primary + fallback provider
TELEGRAM_ALLOWED_USERS=<your id> make hermes-configure   # terminal.backend=docker, env secrets
make skills-sync
# copy or symlink hermes-data/dev-backend/skills → ~/.hermes/skills/
hermes chat --oneshot -Q -q "id"                   # sandbox uid ≠ host (checklist #1)
hermes gateway run                                 # Telegram + API :8642
```

Real CLI keys (v0.21.5): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `GITLAB_TOKEN`,
`API_SERVER_*`, `OPENROUTER_API_KEY` — **not** `telegram.token` / `gitlab.base_url`.

### Option B — compose agents profile (DECISION-14: terminal.backend=local)

```bash
make secrets-dev                    # or secrets-decrypt
make hermes-seed                    # hermes-data/<agent>/.env from secrets
make skills-sync
# Phase 0: start one worker (e.g. dev-backend) + optional coordinator
docker compose --profile agents up -d dev-backend
# or all six: make up-agents
```

Then set `ADAPTER_DISPATCHER=hermes_api` and `HERMES_API_URL=http://dev-backend:8642` in `.env`,
`make up` again, and `make webhook-test` — adapter creates a Hermes `/v1/runs` job.

On Telegram (coordinator): `ใช้ dev-flow ใน /workspace/sandbox-smoke เพิ่มฟังก์ชัน subtract พร้อม test`.
Expected: commit on a work branch, `./test.sh` green, approval prompt *before* any push.

## 5. Onboard the pilot repo (D0.4)

```bash
make onboard KEY=backend-api URL=git@gitlab.com:acme/backend-api.git TEST="pytest -q"
$EDITOR workspace/backend-api/project-standards.md
$EDITOR config/projects.yaml            # real gitlab_project_id + path_with_namespace
$EDITOR config/org.yaml                 # DECISION-5/11 placeholders
docker compose restart webhook-gateway  # reloads projects.yaml
```

## 6. Tests & checks

```bash
make test               # gateway + adapter unit tests
make test-integration   # needs TEST_DATABASE_URL=postgresql://emaw:<pw>@localhost:5432/emaw
make lint
make gitleaks
make verify-phase0
make hooks
```
