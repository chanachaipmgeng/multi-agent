# Phase 1 — Permanent Ingress & GitLab Integration: deliverables and exit criteria

Source: design §12 Phase 1, checklist §11.1 items **2, 6, 8, 9** and §11.2 **E1, E2 (secret)**.
Legend: ✅ in repo & verified · 🧪 in repo, needs real environment · ☐ manual / blocked on a decision.

## Deliverables

| ID | Deliverable | Where | Status |
|---|---|---|---|
| D1.1 | `systemd=true`, cloudflared Named Tunnel + DNS + `config.yml` + service | `scripts/tunnel-setup.sh`, `scripts/tunnel-status.sh`, `cloudflared/config.yml.example`, compose `ingress` profile, `docs/runbooks/tunnel.md` | 🧪 scripts ready · ☐ blocked on **DECISION-5** (domain) |
| D1.2 | GitLab Project Access Token (minimum scope) + `gitlab.token` / `gitlab.base_url` | `docs/gitlab-setup.md` §1, `scripts/gitlab-token-check.sh` (rejects scope `api`/admin, warns on expiry), `scripts/hermes-configure.sh` | 🧪 · ☐ create tokens |
| D1.3 | Webhook → `https://…/webhook/gitlab`, secret, Issues/Pipeline/Job, SSL verify | `scripts/gitlab-webhook-register.sh` (idempotent create/update), gateway already enforces secret + event/project allowlist | 🧪 · ☐ run against real project |
| D1.4 | Skills `resolve-issue` (opt-in `agent-ready`), `incident-triage` | `skills/_dev-common/resolve-issue.md`, `skills/devops/incident-triage.md` (full procedures, HITL steps, stop conditions) | ✅ written · ☐ rehearse |
| D1.5 | Fallback model tested | `model.fallback` in every profile; test procedure below | ☐ needs LLM keys |
| D1.6 | Runbooks: tunnel status/restart, token rotation | `docs/runbooks/tunnel.md`, `docs/runbooks/token-rotation.md` | ✅ |
| — | **Queue bridge** so the single Hermes agent actually receives tasks from the gateway | `queue-adapter/` — consumes `stream:tasks`, enriches `job_failed`/`pipeline_failed` with redacted GitLab job traces, builds `run skill <skill> with task <json>`, dispatches via `dryrun` / `http` / `hermes_cli`, retry via `XAUTOCLAIM`, dead-letter after 3, task state + audit, Telegram notice; 22 tests | ✅ verified end-to-end locally (gateway → Redis → adapter → prompt, Postgres states) |

## Checklist items in scope

| # | Item | Evidence | Remaining |
|---|---|---|---|
| 2 | Least privilege | token matrix in `docs/gitlab-setup.md`; `gitlab-token-check.sh` fails on `api`; per-agent token files | ☐ create PATs, fill inventory in `token-rotation.md` |
| 6 | Wide-context LLM + fallback | `max_context_tokens ≥ 128k` and `model.fallback` in all profiles | ☐ block primary (invalid key / network rule) and confirm a task still completes |
| 8 | Branching strategy | `platform-policy.yaml#git`, skills never push without gate, protected-branch instructions | ☐ configure protected branches in GitLab; audit shows no `git.push{branch=main}` |
| 9 | Webhook + alert test | gateway 401 path tested (unit + live); adapter Telegram notice on receipt; `incident-triage` SLA 2 min | ☐ fail a real job in staging, measure time to message |
| E1 | Permanent ingress | tunnel scripts + runbook, `path: ^/webhook/.*` filter, metrics `:2000` | ☐ DECISION-5 |
| E2 (secret) | Webhook hardening (secret) | constant-time compare, idempotency, allowlists, 1 MiB limit — all tested | — (WAF rule is Phase 3/4) |

## Exit criteria

> Issue ทดสอบ → MR พร้อม `Closes #id` + แจ้ง Telegram ภายใน 30 นาที; fail job → ข้อความวิเคราะห์ภายใน 2 นาที;
> checklist ข้อ 2, 6, 8, 9 + E1, E2 (secret) ผ่าน

| Test | Date | Result | Time to MR / message | Notes |
|---|---|---|---|---|
| Issue `agent-ready` → MR `Closes #<iid>` | | | ≤ 30 min | |
| Failed job → triage message | | | ≤ 2 min | |
| Wrong webhook secret → 401 | | | — | `webhook_auth_fail_total` |
| Primary model blocked → task completes on fallback | | | | |

### Fallback test procedure (D1.5)

1. In the agent profile set `model.primary` to a model name that does not exist (or revoke the key temporarily).
2. Send `make webhook-test` (or a Telegram `dev-flow` request) and watch the agent log for the fallback switch.
3. The task must finish; record model names and latency; restore the primary.

## What Phase 1 did *not* change

No gateway behaviour changes were needed — the Phase 0 gateway already met E2 (secret). The
Hermes-facing interface (how the adapter invokes Hermes) is still an assumption (DECISION-1); the
adapter is pluggable so confirming it is an env-var change (`DISPATCHER=hermes_cli|http`).
