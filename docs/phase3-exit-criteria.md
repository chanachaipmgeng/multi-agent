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
| D3.7 | MinIO + audit | ✅ service + adapter upload + audit writes |
| D3.8 | Linux VM / prod compose | ✅ `docker-compose.prod.yml` + deploy doc (VM site = DECISION-2) |

## Exit checks

```bash
make up-local-free && make local-llm-pull   # once
make local-free-check
make phase3-check
# Optional live drills (need Telegram + DECISION-8/11):
# Flow C: Telegram "[Backend] …" → route-task → stream:dev-backend
# Flow A: issue webhook → router → worker → HANDOFF → reviewer
# E11: /pause all → no new dispatches; /safe-mode on → require_approval
```

| Gate | Evidence |
|---|---|
| E3 secrets scope | per-agent secrets in compose |
| E4 isolation | networks edge/control/workers/inference |
| E5 HITL | approvals table + `/internal/approvals` |
| E6 audit | gateway + router + adapter audit_events |
| E9 budget | breaker token/hour + prompt budgets |
| E11 kill switch | pause / safe-mode keys + circuit breaker |

## Blocked on org input

- DECISION-8 Telegram ids · DECISION-11 pilot repos · DECISION-5 domain · DECISION-2 VM location
