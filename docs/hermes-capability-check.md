# Hermes Agent capability check (DECISION-1)

Recorded against the published image and docs on **2026-10-07**.
Closes the open questions in design §13 DECISION-1 / ASSUMPTION A1–A2.

## Version under test

| Field | Value |
|---|---|
| Image | `nousresearch/hermes-agent:latest` |
| Digest | `sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db` |
| Reported version | **Hermes Agent v0.21.5 (2026.9.24)** · upstream `749220ef` |
| Install method | docker (`/opt/hermes`) |
| Python | 3.13.5 |
| Data dir inside container | `/opt/data` (maps to host `~/.hermes` or a named volume) |
| Image ENTRYPOINT | `/opt/hermes/docker/entrypoint-dispatch.sh` (s6-overlay) |
| Image USER | `root` (runtime drops to non-root for agent work) |
| Default terminal backend | `local` |

Pin recommendation for compose (once validated in staging):

```yaml
image: nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db
```

## Ports

| Port | Purpose | How to enable |
|---|---|---|
| **8642** | OpenAI-compatible API server (`/v1/chat/completions`, `/v1/runs`, `/v1/runs/{id}/events`, `/v1/runs/{id}/approval`) | `API_SERVER_ENABLED=true`, `API_SERVER_KEY=…`, `API_SERVER_HOST=0.0.0.0` (container) / `127.0.0.1` (host) |
| **8644** | Hermes-native webhook adapter (`POST /webhooks/<route>`) | `WEBHOOK_ENABLED=true` — **not used by EMAW** (we keep our FastAPI gateway, DECISION-12) |
| **9119** | Dashboard | `HERMES_DASHBOARD=1` |

## Non-interactive invocation (queue-adapter)

Confirmed interfaces:

1. **HTTP (preferred for adapter)** — `POST http://<host>:8642/v1/runs`
   - Auth: `Authorization: Bearer $API_SERVER_KEY`
   - Idempotency: `Idempotency-Key` header (1–255 ASCII); retries return same `run_id` + `Idempotency-Replayed: true`
   - Progress: `GET /v1/runs/{run_id}` and SSE `GET /v1/runs/{run_id}/events`
   - HITL: `POST /v1/runs/{run_id}/approval` when run is `waiting_for_approval`
2. **CLI** — `hermes -p <profile> chat --oneshot -Q --query-file <path> -s <skill>`
   - `--oneshot` + non-TTY / `-Q` answers and exits
   - `-s` preloads skills; `--query-file` preserves arbitrary prompt text

**Not valid:** `hermes run --file …` (legacy assumption in early EMAW drafts).

Hermes's own GitLab webhook adapter (`:8644`) accepts `X-Gitlab-Token` (plain match) but its default webhook toolset **excludes `terminal`**. EMAW continues to use `webhook-gateway` → Redis Streams → `queue-adapter` (DECISION-12).

## Config schema (real keys)

Secrets live in `/opt/data/.env` (UPPER_SNAKE env vars). Non-secret settings live in `/opt/data/config.yaml`.
`hermes config set KEY VAL` routes UPPER_SNAKE → `.env` and dotted keys → `config.yaml` automatically.

| Concern | Real key / location | Obsolete EMAW assumption |
|---|---|---|
| Telegram bot token | `TELEGRAM_BOT_TOKEN` (`.env`) | `telegram.token` / `hermes config set telegram.token` |
| Telegram allowlist | `TELEGRAM_ALLOWED_USERS` (`.env`, comma-separated ids) | `telegram.allowed_users` as config.yaml key |
| GitLab token for `glab` | `GITLAB_TOKEN` + `GITLAB_HOST` (`.env`) | `gitlab.token` / `gitlab.base_url` as Hermes keys |
| API server | `API_SERVER_ENABLED`, `API_SERVER_PORT`, `API_SERVER_HOST`, `API_SERVER_KEY` | — |
| Terminal backend | `terminal.backend: local \| docker \| …` | still valid; default is `local` |
| Docker sandbox image | `terminal.docker_image` (e.g. `nousresearch/hermes-sandbox:desktop`) | custom `sandbox.image` block we invented |
| Approvals | `approvals.mode`, `approvals.deny` (fnmatch globs) | — |
| Worktrees | `worktree: true` + `worktree_sync: true` | manual `git worktree` only in skills |
| Skills auto-load | `skills.auto_load: [name, …]` | — |
| Identity | `SOUL.md` (primary) + `AGENT.md` / `AGENTS.md` | inventing `identity:` block in config.yaml |
| MCP | `mcp_servers:` in config.yaml | shape compatible; reviewer enables `socraticode` (DECISION-6 local AGPL) |
| SQLite on Windows bind-mount | `database.journal_mode: delete` **or** named Docker volume for `/opt/data` | bind-mount from Windows FS + WAL corrupts `state.db` |

`hermes config list` does **not** exist — use `hermes config show` / `hermes config get` / `hermes config --help`.

## Profiles

- `hermes profile create <name>` creates an isolated data dir under `/opt/data/profiles/<name>/`
- Official Docker image: **one container can supervise many profiles** via s6 (`hermes -p <name> gateway start`)
- EMAW still uses **one compose service per role** (DECISION-1 / O3) for token isolation and mount scoping; profiles remain available for host/WSL single-install setups

## Skills layout

```text
/opt/data/skills/<category>/<skill>/SKILL.md
```

Required frontmatter: `name`, `description`. Optional: `version`, `platforms`, `metadata.hermes.*`.
EMAW promotes reviewed skills from `skills/` → `hermes-data/<agent>/skills/emaw/<skill>/SKILL.md` via `make skills-sync`.

## HITL surface

- Dangerous terminal commands → `/approve` (messaging) or CLI dialog; `approvals.deny` blocks even under `--yolo`
- Agent `clarify` tool → numbered / native buttons on Telegram
- API runs waiting on approval → `POST /v1/runs/{id}/approval`
- EMAW `human-approval-gate` skill remains the policy layer for push/deploy/migration; Hermes approvals are defense-in-depth for shell commands

## Sandbox strategy (see DECISION-14)

On this Windows + Docker Desktop host there is no Ubuntu WSL distro, only `docker-desktop`.
Recommended for local compose: **Hermes-in-container + `terminal.backend: local`** (container already `cap_drop: ALL`, no docker.sock). Host install + `terminal.backend: docker` remains the Phase 0 path on real Linux/WSL2 Ubuntu.

## Commands used for this check

```bash
docker pull nousresearch/hermes-agent:latest
docker run --rm --init --entrypoint hermes nousresearch/hermes-agent:latest --version
docker run --rm --init --entrypoint hermes nousresearch/hermes-agent:latest config --help
docker run --rm --init --entrypoint hermes nousresearch/hermes-agent:latest config show
docker run --rm --init --entrypoint hermes nousresearch/hermes-agent:latest chat --help
docker run --rm --init --entrypoint hermes nousresearch/hermes-agent:latest profile --help
docker image inspect nousresearch/hermes-agent:latest --format '{{index .RepoDigests 0}}'
```

Docs cross-check: [Configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration), [Docker](https://hermes-agent.nousresearch.com/docs/user-guide/docker), [API Server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server), [Webhooks](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/webhooks), [CLI](https://hermes-agent.nousresearch.com/docs/reference/cli-commands).
