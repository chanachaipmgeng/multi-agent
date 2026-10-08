# Runbook — Immutable audit export (D4.4 prep)

Daily export of Postgres `audit_events` to MinIO bucket `emaw-audit` with **object lock** (GOVERNANCE, 365 days). Vault for secrets remains a separate infra DECISION.

## One-shot

```bash
# Export yesterday (UTC) or a specific day
make audit-export
make audit-export DAY=2026-10-07

# Verify sha256 + that delete is refused
make audit-verify DAY=2026-10-07
```

Objects land at `s3://emaw-audit/audit/YYYY/MM/DD/audit_events.jsonl.gz` (+ `.sha256`).

Local staging copy: `backups/audit-export/<DAY>/` (gitignored under `backups/`).

## First-time bucket

`scripts/audit-export.sh` creates `emaw-audit` with `mc mb --with-lock` if missing.  
Do **not** reuse `emaw-artifacts` (90-day ILM, no lock).

## Cron example (production VM — after DECISION-2)

```cron
15 1 * * * cd /opt/emaw && make audit-export >> /var/log/emaw-audit-export.log 2>&1
30 1 * * * cd /opt/emaw && make audit-verify DAY=$(date -u -d yesterday +\%Y-\%m-\%d) >> /var/log/emaw-audit-export.log 2>&1
```

## Failure modes

| Symptom | Action |
|---|---|
| minio not reachable | `docker compose ps minio`; check `MINIO_ROOT_PASSWORD` |
| empty export | confirm `audit_events` has rows for that UTC day |
| delete succeeds on verify | object lock not active — recreate bucket with `--with-lock` (cannot retrofit) |
| GOVERNANCE bypass | expected for root in some MinIO configs; prefer COMPLIANCE only on prod after legal OK |

## Related

- Schema: `db/migrations/0001_task_store.sql` (`audit_events` append-only trigger)
- Design §6.5 / E6 / D4.4
