# Runbook — Backup & Restore (D4.5 / E10)

## Policy (DECISION-19)

| Item | Value |
|---|---|
| RPO | ≤ 24 h (daily backup; critical change → manual `make backup`) |
| RTO | ≤ 1 h for Postgres + volumes on a healthy host |
| Retention | local `./backups/` keep last 7; optional restic remote keep 30 days |
| Scope | Postgres (`emaw`), Hermes data volumes ×6, MinIO, Redis AOF, adapter outbox |

## Backup

```bash
make backup                 # → backups/<UTC-ts>/postgres.dump + *.tar.gz + manifest.json
# Optional remote:
# RESTIC_REPOSITORY=s3:… RESTIC_PASSWORD=… make backup
```

Verify: `cat backups/<ts>/manifest.json` — `task_count` and `sha256` present.

## Restore drill (safe, non-destructive)

```bash
make restore-drill BACKUP=backups/<ts>
# or: scripts/restore.sh backups/<ts> --drill
```

Spins a temporary Postgres, restores the dump, compares `SELECT count(*) FROM tasks`
to `manifest.task_count`, then removes the temp container. Does **not** touch live volumes.

## Full restore (destructive)

1. Announce maintenance / `/pause all` if Telegram available.
2. `scripts/restore.sh backups/<ts>` — stops agents/adapters, `pg_restore --clean`, untars volumes, restarts.
3. `make phase3-check` and spot-check MinIO / a recent task via `/internal/tasks`.
4. Resume traffic.

## Failure modes

| Symptom | Action |
|---|---|
| `pg_restore` errors on extensions | Ignore "already exists"; re-check task count |
| Volume name mismatch | Set `COMPOSE_PROJECT_NAME` to the compose project prefix |
| Drill task count ≠ manifest | Dump corrupt — use previous backup; do not promote |
