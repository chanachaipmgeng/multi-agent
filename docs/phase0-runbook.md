# Phase 0 exit — manual runbook (needs Telegram + LLM key)

Repo prep for DECISION-1 is done (`docs/hermes-capability-check.md`, real Hermes configs,
`DISPATCHER=hermes_api`, compose agents profile). Phase 2 skill/infra prep can land in
parallel; **this runbook is the ops gate that actually closes Phase 0**. Fill the table in
[`phase0-exit-criteria.md`](phase0-exit-criteria.md) after these steps.

## Track B checklist (secrets → drill → record)

Do these in order once credentials exist:

| Step | Action | Done when |
|---|---|---|
| B1 | Put `SECRET_TELEGRAM_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `SECRET_HERMES_API_KEY` in `.env`. For **cloud** LLM also set `SECRET_LLM_KEY_*`. For **local-free** set `LLM_MODE=local` (no OpenRouter keys — all 6 agents use Ollama) | values non-placeholder where required |
| B2 | `make secrets-dev` (or `secrets-decrypt`) → `cp config/rbac.example.yaml config/rbac.yaml` → seed + skills (`make hermes-seed` **or** `make up-local-free`) | `hermes-data/*/.env` present; skills synced |
| B3a | **Cloud:** `make up` + `make up-agents` (router + 5 adapters already from `make up`) | containers healthy |
| B3b | **Local-free:** `make up-local-free` → `make local-llm-pull` → `make local-free-check` → `make phase3-check` | checks green |
| B4 | Local-free / prod already set `ADAPTER_DISPATCHER=hermes_api`. Cloud-only: set it in `.env` and recreate adapters | adapter logs show hermes_api |
| B5 | Run checklist drills below | all pass rows |
| B6 | Fill the 3-run table in [`phase0-exit-criteria.md`](phase0-exit-criteria.md) | exit criterion closed |

## Prerequisites you must supply

1. Telegram bot token (`@BotFather`) → `SECRET_TELEGRAM_TOKEN` (skip if API-only drills)
2. Your Telegram numeric user id → `TELEGRAM_ALLOWED_USERS`
3. LLM: either OpenRouter keys → `SECRET_LLM_KEY_*` **or** local-free → GPU + `make local-llm-pull` (DECISION-15)
4. Random API bearer → `SECRET_HERMES_API_KEY`

```bash
cp .env.example .env   # if needed
# edit Telegram + Hermes API key (+ LLM keys for cloud path)
make secrets-dev
cp config/rbac.example.yaml config/rbac.yaml
make hermes-seed
make skills-sync
make up                 # redis + postgres + gateway + minio + router + 5 adapters
make up-agents          # or: make up-local-free for free local LLM (all 6 agents)
```

Cloud path — force Hermes API dispatch (local-free / `make up-prod` already do this):

```bash
ADAPTER_DISPATCHER=hermes_api docker compose up -d --force-recreate \
  adapter-dev-backend adapter-dev-frontend adapter-reviewer adapter-qa adapter-devops
```

## Checklist drills

| # | Drill | Pass when |
|---|---|---|
| 1 | `docker compose exec dev-backend hermes config get terminal.backend` | `local` (compose) or `docker` (host) |
| 1b | Ask agent to run `id` | uid is container/sandbox, not Windows host |
| 4 | Request push via Telegram → reply `n` | no push; audit/approval rejected |
| 4b | Request push → ignore until timeout | EXPIRED; no push |
| 7 | Three `dev-flow` runs on `/workspace/sandbox-smoke` | commit on work branch, `./test.sh` green, HITL before push |
| Adapter | `make webhook-test` with `hermes_api` | `stream:results` has dispatched event; Hermes run completes or waits for approval |

Record results in `phase0-exit-criteria.md`. After Phase 0 is closed, unblock Phase 1 with
DECISION-5/11 (`config/org.yaml`). Phase 2 SocratiCode MCP is already wired for local AGPL
([`phase2-exit-criteria.md`](phase2-exit-criteria.md), DECISION-6); rehearse on sandbox-smoke /
pilot diffs and fill [`skill-acceptance.md`](skill-acceptance.md).
