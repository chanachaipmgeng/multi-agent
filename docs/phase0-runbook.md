# Phase 0 exit — manual runbook (needs Telegram + LLM key)

Repo prep for DECISION-1 is done (`docs/hermes-capability-check.md`, real Hermes configs,
`DISPATCHER=hermes_api`, compose agents profile). Fill the table in
[`phase0-exit-criteria.md`](phase0-exit-criteria.md) after these steps.

## Prerequisites you must supply

1. Telegram bot token (`@BotFather`) → `SECRET_TELEGRAM_TOKEN`
2. Your Telegram numeric user id → `TELEGRAM_ALLOWED_USERS`
3. OpenRouter (or other) API key → `SECRET_LLM_KEY_DEV_BACKEND` (and coordinator if used)
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

Record results in `phase0-exit-criteria.md`.
