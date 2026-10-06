# Task Store (PostgreSQL 16)

Schema for the task lifecycle (design §3.6), handoff protocol (§4.5), HITL approvals (§4.6)
and the append-only audit log (§6.5).

| Table | Purpose | Writers |
|---|---|---|
| `tasks` | one row per task (state machine), partial unique index = *one active task per issue* | gateway (insert), coordinator (update) |
| `handoffs` | handoff records between agents (worktree, branch, summary, artifacts, tokens) | workers, coordinator |
| `approvals` | HITL requests with `payload_hash` + `nonce`, decision + approver | coordinator |
| `audit_events` | append-only event log keyed by `trace_id` / `task_id`; UPDATE/DELETE raise | everyone (insert only) |
| `schema_migrations` | applied migration versions | `scripts/migrate.sh` |

## How migrations run

* **Fresh database** — `docker-compose.yml` mounts `db/migrations/` into
  `/docker-entrypoint-initdb.d/`, so Postgres applies every `*.sql` in order on first boot.
* **Existing database** — `make migrate` (→ `scripts/migrate.sh`) applies any file whose
  version is not yet in `schema_migrations`. Files are plain SQL, idempotent, numbered
  `NNNN_name.sql`; never edit an applied file, add a new one.

## Roles

`0002_roles.sql` creates NOLOGIN group roles (`emaw_gateway_rw`, `emaw_coordinator`,
`emaw_worker_rw`, `emaw_readonly`). In Phase 0 the single `emaw` login user owns the schema;
in Phase 3 each agent gets its own login user granted the matching group role (E3/E6).
