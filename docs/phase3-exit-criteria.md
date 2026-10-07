# Phase 3 exit criteria

**Goal:** multi-agent fan-out, handoff, HITL, RBAC, kill switch, MinIO artifacts.

## Deliverables

| ID | Item | Status in repo |
|---|---|---|
| D3.1 | Webhook gateway | ✅ |
| D3.2 | Streams per role + PG schema | ✅ router fans out; schema from Phase 0 |
| D3.3 | 6 profiles + adapter sidecars | ✅ |
| D3.4 | route-task, status-report, human-approval-gate, pause, safe-mode | ✅ (HITL = y/n+nonce, DECISION-17) |
| D3.5 | rbac.yaml enforcement | ✅ gateway `/internal/*` |
| D3.6 | Docker secrets / networks | ✅ |
| D3.7 | MinIO + audit | ✅ service + adapter SigV4 upload + audit writes |
| D3.8 | Linux VM / prod compose | ✅ `docker-compose.prod.yml` + deploy doc (VM site = DECISION-2) |

## Exit checks

```bash
# If a Phase 2 single-adapter stack is still running, stop it first
# (profile `single` would race router on stream:tasks):
make down

make up-local-free && make local-llm-pull   # once
make local-free-check
make phase3-check

# Live Flow A (API-only; no Telegram):
make webhook-test KIND=issue
# Expect: QUEUED → ASSIGNED → IN_PROGRESS → DONE (+ auto handoff reviewer)
# Redis: stream:tasks → stream:dev-frontend → stream:results → stream:reviewer
# MinIO: s3://emaw-artifacts/<project>/<task_id>/run-output.md

# E11 kill switch (Bearer hermes_api_key + X-EMAW-User-Id admin):
# POST /internal/control/pause {"agent":"all"} → new tasks stay QUEUED / unacked
# POST /internal/control/resume {"agent":"all"} → pending (id=0) drains within seconds
# POST /internal/control/safe-mode {"enabled":true} → constraints.require_approval

# Optional live drills (need Telegram + DECISION-8/11):
# Flow C: Telegram "[Backend] …" → route-task → stream:dev-backend
```

| Gate | Evidence |
|---|---|
| E3 secrets scope | per-agent secrets in compose |
| E4 isolation | networks edge/control/workers/inference |
| E5 HITL | approvals table + `/internal/approvals` |
| E6 audit | gateway + router + adapter audit_events (`task.routed`, `task.handed_off`, …) |
| E9 budget | breaker token/hour + prompt budgets |
| E11 kill switch | pause / safe-mode keys + circuit breaker; router `CONSUMER_NAME=router` + pending read |

## Live drill log (local-free, 2026-10-07)

| Check | Result |
|---|---|
| `local-free-check` / `phase3-check` | PASS (6 agents + router + 5 adapters + MinIO) |
| Flow A webhook → Hermes (Ollama) → results | PASS (`t-20261007-886bba` DONE, handoff `auto_review_fallback` → reviewer) |
| MinIO artifact PUT | PASS after SigV4 fix (`run-output.md` listed in bucket) |
| `/internal/tasks` RBAC | PASS (admin 200, no bearer 401, viewer pause 403) |
| pause all / resume | PASS (task stayed QUEUED while paused; resume drains PEL) |
| `/metrics` on adapter | PASS (`emaw_tasks_dispatched_total`) |
| coordinator → `webhook-gateway:8700` | PASS (healthz 200) |
| Unit tests | queue-adapter 41 · gateway 44 (integration deselected; post §8.2) |

## Close-out (2026-10-08) — A1 / A2 / A3

| Gate | Result |
|---|---|
| Dashboard `:9119` with basic auth (DECISION-18) | PASS — no `Refusing to bind`; protected `/api/*` → 401 without session; login UI served |
| Metrics §8.2 on adapter | PASS — `task_duration_seconds`, `llm_tokens_total{agent}`, `queue_depth`, `queue_oldest_age_seconds`, `agent_heartbeat_timestamp`, `task_state_total` |
| Metrics §8.2 on gateway | PASS — `approval_latency_seconds`, `task_state_total{state}` on scrape |
| Errata CLAIM_MIN_IDLE | Documented — router 30s / workers 10 min |

### Fixes from the drill

- Router must **not** use Redis `BLOCK 0` (means wait forever) — omit `block` for non-blocking reads.
- Hermes ≥0.21 rejects Ollama default 32K context — set `OLLAMA_CONTEXT_LENGTH` + `model.ollama_num_ctx: 65536`.
- Artifact upload needs **AWS SigV4** (HTTP Basic / `x-amz-acl` → MinIO 400).
- Pause-deferred work: read pending with `XREADGROUP … 0` + stable `CONSUMER_NAME=router` + `CLAIM_MIN_IDLE_MS=30000`.

## Blocked on org input

- DECISION-8 Telegram ids · DECISION-11 pilot repos · DECISION-5 domain · DECISION-2 VM location
