# Phase 4 exit criteria

**Goal:** enterprise hardening — backup, supply chain, observability, secrets, compliance.

## Deliverables (this round)

| ID | Item | Status |
|---|---|---|
| D4.5 | Backup / restore (`pg_dump` + volumes, drill, runbooks) | ✅ `scripts/backup.sh`, `restore.sh`, `make backup|restore-drill|restore`, `docs/runbooks/restore.md` |
| D4.6 | Supply chain (digest pins + Trivy) | ✅ Dockerfiles + compose `${*_IMAGE}`, `scripts/pin-digests.sh`, CI `supply-chain`, `.trivyignore` |
| E14 (partial) | Runbooks | ✅ `restore.md`, `agent-stuck.md`, `rollback-mr.md` |

## Live evidence (2026-10-08)

| Check | Result |
|---|---|
| `scripts/backup.sh` | PASS → `backups/20261007T195717Z/` (6 tasks, volumes + dump + manifest) |
| `scripts/restore.sh … --drill` | PASS — restored `task_count=6` matches manifest |
| Digest pins | PASS — `python:3.12-slim@sha256:05cda…` + redis/postgres/minio/ollama/qdrant/cloudflared |
| Unit tests (after §8.2 metrics) | queue-adapter 41 · gateway 44 |

## Still pending (next rounds / org-blocked)

| ID | Item | Blocker |
|---|---|---|
| D4.1 | OTel + Loki + Prometheus + Grafana + Alertmanager → Telegram; 4 dashboards (E8) | size — separate round |
| D4.2 | Redaction pipeline + gitleaks pre-commit in sandbox | — |
| D4.3 | Cloudflare Access / WAF | DECISION-5 |
| D4.4 | Vault + immutable audit export | infra DECISION |
| D4.8 | Compliance review | DECISION-3/9 |
| Flow C | Telegram live + skill acceptance ≥3 | DECISION-8/11 |
| `make up-prod` on VM | — | DECISION-2 |
