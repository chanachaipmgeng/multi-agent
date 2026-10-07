# Phase 0 — Foundation: deliverables and exit criteria

Source: design document §12 "Phase 0 — Foundation (Single Agent บน WSL2)" and checklist §11.1
items **1, 3, 4, 5, 7**. This page maps each item to what exists in this repository and what still
has to be done by a human on real infrastructure.

Legend: ✅ in repo & verified · 🧪 in repo, needs real environment to exercise · ☐ manual step

## Deliverables

| ID | Deliverable | Where | Status |
|---|---|---|---|
| D0.1 | WSL2 Ubuntu 24.04 + Docker Desktop + Node 20 + Python 3 + Git | `scripts/check-prereqs.sh` (`make prereqs`) verifies the host | 🧪 run on the WSL2 machine |
| D0.2 | Hermes installed, `hermes setup` (provider + fallback), sandbox backend | `scripts/hermes-configure.sh` (real v0.21.5 env keys); compose profiles use `terminal.backend: local` (DECISION-14); host path uses `docker`; `fallback_providers` in every `config.yaml`; evidence in `docs/hermes-capability-check.md` | 🧪 needs LLM key + Telegram for live drill — see `docs/phase0-runbook.md` |
| D0.3 | Telegram bot + `telegram.allowed_users` | `.env.example` (`SECRET_TELEGRAM_TOKEN`, `TELEGRAM_ALLOWED_USERS`), `hermes-configure.sh`, `config/rbac.example.yaml` | 🧪 needs bot token + user id |
| D0.4 | Pilot repo with `.agentignore`, `project-standards.md`, correct test exit codes | `workspace/_templates/*`, `scripts/onboard-project.sh`, `examples/sandbox-smoke/` (exit 0/1 verified) | ✅ template & smoke · ☐ onboard the real pilot repo (DECISION-11) |
| D0.5 | Skills `dev-flow`, `review-code`, `human-approval-gate` in git | `skills/_dev-common/dev-flow.md`, `skills/_dev-common/review-code.md`, `skills/coordinator/human-approval-gate.md`; `make skills-sync` | ✅ |
| D0.6 | Secrets with SOPS + age (`.env.enc`) | `.sops.yaml`, `scripts/secrets-*.sh`, `docs/secrets.md`, `.gitleaks.toml`, pre-commit | ✅ tooling · ☐ generate key, encrypt real `.env` |

## Checklist items in scope

| # | Item | Evidence in repo | Remaining |
|---|---|---|---|
| 1 | Docker sandbox enforced | `terminal.backend: docker` in all 6 profiles; compose: `cap_drop ALL`, `read_only`, `no-new-privileges`, no `docker.sock` mount; `verify-phase0.sh` checks | ☐ `hermes run "id"` shows sandbox uid |
| 3 | Strict `.agentignore` | repo-root `.agentignore`, templates, smoke project; gitleaks config + CI job; `verify-phase0.sh` asserts secret patterns present | — |
| 4 | Human-in-the-Loop | `config/policies/platform-policy.yaml#human_in_the_loop` (push → approval, protected branch → forbidden, timeout → EXPIRED); `human-approval-gate` skill; `dev-flow` step 10 never pushes; `approvals` table with `payload_hash` + `nonce` | ☐ rehearse "n" and timeout on Telegram, confirm no push |
| 5 | Clear project rulebook | `workspace/_templates/project-standards.md` (stack, security, anti-patterns, test command, e2e port 3001, branch naming, HITL) | ☐ tailor per pilot repo, quarterly review |
| 7 | Automated tests as safety net | `examples/sandbox-smoke/test.sh` exit 0 / exit 1 (forced) verified in `verify-phase0.sh` and CI; `onboard-project.sh` checks the real repo's command | ☐ confirm pilot repo's command < 10 min |

## Foundation built ahead of Phase 1–3 (so later phases are config, not rewrites — P6)

| Component | Phase it is *used* | What exists now |
|---|---|---|
| Webhook Gateway (FastAPI) `POST /webhook/gitlab` | 1 (hits gateway directly), 3 | token verify (constant-time), event + project allowlist, idempotency (Redis `SET NX EX` 24 h), Task envelope normalization, opt-in `agent-ready`, routing hint (`area:*` → worker, pipeline/job failed → devops), `XADD stream:tasks`, `/healthz` `/readyz` `/metrics`; 40 tests (37 unit + 3 Postgres integration) |
| Task Store (PostgreSQL) | 3 | `db/migrations/0001_task_store.sql` (tasks · handoffs · approvals · audit_events, append-only trigger, one-active-task-per-issue index), `0002_roles.sql` least-privilege roles |
| Task Queue (Redis Streams) | 3 | compose `redis` (AOF), gateway publisher; per-role streams named in each profile config |
| 6 Hermes profiles | 0 (one of them), 3 (all) | `hermes-data/<agent>/{AGENT.md,config.yaml,skills/,memory/}` as separate compose services (`--profile agents`) |
| `projects.yaml` + routing | 2–3 | `config/projects.yaml` validated by the gateway on start |
| cloudflared Named Tunnel | 1 | `cloudflared/config.yml.example`, compose service (`--profile ingress`), README — blocked on DECISION-5 |
| RBAC | 3 | `config/rbac.example.yaml` |

## Exit criterion

> สั่ง `dev-flow` ผ่าน Telegram 3 งาน → ได้ commit บน branch งาน, test ผ่าน, ไม่มีการ push โดยไม่ถาม;
> checklist ข้อ 1, 3, 4, 5, 7 ผ่าน

Record the three runs here once executed on the WSL2 host (requires real Hermes, Telegram bot, LLM key):

| Run | Date | Project | Branch | Commit | Tests | HITL prompt shown? | Pushed without approval? |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | must be **no** |
| 2 | | | | | | | must be **no** |
| 3 | | | | | | | must be **no** |

`make verify-phase0` automates every check that does not need live credentials and prints the
remaining manual items.
