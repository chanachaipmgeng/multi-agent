# Phase 4 exit criteria

**Goal:** enterprise hardening — backup, supply chain, observability, secrets, compliance.

## Deliverables

| ID | Item | Status |
|---|---|---|
| D4.1 | OTel + Loki + Tempo + Prometheus + Grafana + Alertmanager → Telegram; 4 dashboards | ✅ profile `observability`, `make up-observability`, `observability/` |
| D4.2 | Redaction pipeline + gitleaks in sandbox | ✅ adapter Telegram/audit redact; Promtail+OTel redaction; `tools/gitleaks` mount; template pre-commit |
| D4.5 | Backup / restore (`pg_dump` + volumes, drill, runbooks) | ✅ `scripts/backup.sh`, `restore.sh`, `make backup|restore-drill|restore`, `docs/runbooks/restore.md` |
| D4.6 | Supply chain (digest pins + Trivy) | ✅ Dockerfiles + compose `${*_IMAGE}`, `scripts/pin-digests.sh`, CI `supply-chain`, `.trivyignore` |
| E14 (partial) | Runbooks | ✅ `restore.md`, `agent-stuck.md`, `rollback-mr.md`, `alerts.md` |

## Live evidence (2026-10-08)

| Check | Result |
|---|---|
| `scripts/backup.sh` | PASS → `backups/20261007T195717Z/` (6 tasks, volumes + dump + manifest) |
| `scripts/restore.sh … --drill` | PASS — restored `task_count=6` matches manifest |
| Digest pins | PASS — `python:3.12-slim@sha256:05cda…` + redis/postgres/minio/ollama/qdrant/cloudflared |
| Unit tests (after §8.2 metrics) | queue-adapter 41 · gateway 44 |

## Live evidence — D4.1 / D4.2 (2026-10-08)

| Check | Result |
|---|---|
| `make up-observability` | PASS — loki/tempo/otel/promtail/prometheus/grafana/alertmanager up |
| Prometheus targets | PASS — webhook-gateway + queue-adapters UP (cloudflared down without ingress) |
| Grafana dashboards | PASS — EMAW Operations / Agents / Cost / Security |
| Alertmanager | PASS — healthy (`noop` receiver when `TELEGRAM_CHAT_ID` empty) |
| Redaction | PASS — Telegram/audit + Promtail pipeline + OTel transform |
| Gitleaks sandbox | PASS — `docker exec emaw-dev-frontend gitleaks version` → 8.21.2 |

## Still pending (next rounds / org-blocked)

| ID | Item | Blocker |
|---|---|---|
| D4.3 | Cloudflare Access / WAF | DECISION-5 |
| D4.4 | Vault + immutable audit export | infra DECISION |
| D4.8 | Compliance review | DECISION-3/9 |
| Flow C | Telegram live + skill acceptance ≥3 | DECISION-8/11 |
| `make up-prod` on VM | — | DECISION-2 |
