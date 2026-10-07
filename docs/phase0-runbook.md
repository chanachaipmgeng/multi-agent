# Phase 0 exit — manual runbook (needs Telegram + LLM key)

Repo prep for DECISION-1 is done (`docs/hermes-capability-check.md`, real Hermes configs,
`DISPATCHER=hermes_api`, compose agents profile). Phase 2 skill/infra prep can land in
parallel; **this runbook is the ops gate that actually closes Phase 0**. Fill the table in
[`phase0-exit-criteria.md`](phase0-exit-criteria.md) after these steps.

## Track B checklist (secrets → drill → record)

Do these in order once credentials exist:

| Step | Action | Done when |
|---|---|---|
| B1 | Put `SECRET_TELEGRAM_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `SECRET_HERMES_API_KEY` in `.env`. For **cloud** LLM also set `SECRET_LLM_KEY_*`. For **local-free** set `LLM_MODE=local` (no OpenRouter keys needed for the three agents) | values non-placeholder where required |
| B2 | `make secrets-dev` (or `secrets-decrypt`) → seed + skills (`make hermes-seed` **or** `make up-local-free` which seeds with `LLM_MODE=local`) | `hermes-data/*/.env` present; skills synced |
| B3a | **Cloud:** `make up` + `docker compose --profile agents up -d dev-backend` (+ `coordinator`) | containers healthy |
| B3b | **Local-free:** `make up-local-free` → `make local-llm-pull` → `make local-free-check` | check green |
| B4 | Set `ADAPTER_DISPATCHER=hermes_api` and `HERMES_API_URL=http://dev-backend:8642`; recreate adapter | adapter logs show hermes_api |
| B5 | Run checklist drills below | all pass rows |
| B6 | Fill the 3-run table in [`phase0-exit-criteria.md`](phase0-exit-criteria.md) | exit criterion closed |

## Prerequisites you must supply

1. Telegram bot token (`@BotFather`) → `SECRET_TELEGRAM_TOKEN` (skip if API-only drills)
2. Your Telegram numeric user id → `TELEGRAM_ALLOWED_USERS`
3. LLM: either OpenRouter keys → `SECRET_LLM_KEY_*` **or** local-free → GPU + `make local-llm-pull` (DECISION-15)
4. Random API bearer → `SECRET_HERMES_API_KEY`

```bash
cp .env.example .env   # if needed
# edit the four values above
make secrets-dev
make hermes-seed
make skills-sync
make up
docker compose --profile agents up -d dev-backend
# optional: coordinator for Telegram front door
docker compose --profile agents up -d coordinator
```

Set in `.env` then recreate adapter:

```bash
ADAPTER_DISPATCHER=hermes_api
HERMES_API_URL=http://dev-backend:8642
```

```bash
docker compose up -d --force-recreate queue-adapter
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
