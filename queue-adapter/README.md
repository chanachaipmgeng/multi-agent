# Queue Adapter (Redis Streams → Hermes)

Bridges the Task Queue to the Hermes agent. In **Phase 1–2** one adapter feeds the single Hermes
instance (`CONSUMER_GROUP=hermes-single`); in **Phase 3** one adapter runs as a sidecar per role,
consuming `stream:<role>` (design §4.3 "queue-adapter").

```text
stream:tasks ──XREADGROUP──▶ adapter ──enrich (GitLab job trace, redacted)──▶ prompt
                                │                                              │
                                │◀──────────── XACK ◀── dispatch OK ◀──────────┘ (dryrun | http | hermes_cli)
                                └── not acked → XAUTOCLAIM after 10 min → max 3 deliveries → stream:dead-letter + FAILED
```

Per task: `tasks.state` QUEUED → ASSIGNED → IN_PROGRESS (or FAILED), audit events
`task.assigned`, `task.dispatched`, `task.dispatch_failed`, `task.failed`, a record on
`stream:results`, optional Telegram notifications.

## Dispatchers

| `DISPATCHER` | What happens | Use |
|---|---|---|
| `dryrun` (default) | prompt written to `OUTBOX_DIR/<ts>-<task_id>.prompt.md` | dev, CI, verifying routing without Hermes |
| `http` | `POST HERMES_HTTP_URL` with `{"task": …, "prompt": …}` (+ `Authorization: Bearer` from `HERMES_HTTP_TOKEN_FILE`) | Hermes gateway webhook / shim |
| `hermes_cli` | runs `HERMES_CLI_TEMPLATE` (default `hermes run --file {prompt_file}`); placeholders `{prompt_file} {prompt} {agent} {task_id} {skill}` | host-installed Hermes |

Hermes' non-interactive interface must be confirmed on the deployed version (DECISION-1);
switch the dispatcher by env var, no code change.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `TASK_STREAM` / `RESULTS_STREAM` / `DEAD_LETTER_STREAM` | `stream:tasks` / `stream:results` / `stream:dead-letter` | |
| `CONSUMER_GROUP` / `CONSUMER_NAME` | `hermes-single` / hostname | |
| `MAX_DELIVERIES` / `CLAIM_MIN_IDLE_MS` | `3` / `600000` | §10.3 retry policy |
| `DATABASE_URL`, `PG_PASSWORD_FILE` | unset | task state + audit (optional) |
| `DISPATCHER`, `OUTBOX_DIR`, `HERMES_HTTP_URL`, `HERMES_CLI_TEMPLATE`, `DISPATCH_TIMEOUT_SECONDS` | see above | |
| `GITLAB_BASE_URL`, `GITLAB_TOKEN_FILE`, `TRACE_MAX_BYTES` | gitlab.com / unset / 64 KiB | read_api token enables job-trace enrichment |
| `TELEGRAM_TOKEN_FILE`, `TELEGRAM_CHAT_ID` | unset | optional notifications |

## Develop & test

```bash
cd queue-adapter
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest -q
DISPATCHER=dryrun OUTBOX_DIR=/tmp/outbox REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m app.main
```
