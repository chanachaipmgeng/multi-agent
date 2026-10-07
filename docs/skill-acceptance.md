# Skill acceptance log (Phase 2 exit — checklist #10 / E13)

Record ≥ 3 clean staging runs per skill before promoting to production profiles.
Blocked skills stay **procedure-complete** in `skills/` until their decision is closed;
do not mark `Promoted?` until live runs pass.

## How to record a run

1. Note environment: host Hermes vs compose profile, project `key`, branch, commit SHA.
2. Trigger the skill (Telegram / `hermes_api` / oneshot) with a fixed scenario from the table.
3. Pass only if stop conditions and HITL rules in the skill file were respected
   (e.g. reviewer never applied a SocratiCode patch; push never skipped the gate).
4. Add a row date + `pass/fail` counts; link a short log snippet or MR iid in Notes.
5. After 3 consecutive passes on staging, set `Promoted?` to `yes` and ensure
   `make skills-sync` has copied the skill into the target profile.

See also [`phase2-exit-criteria.md`](phase2-exit-criteria.md).

| Skill | Scenario | Date | Runs (pass/fail) | Notes | Promoted? |
|---|---|---|---|---|---|
| `dev-flow` | sandbox-smoke subtract + test | | | Phase 0 exit — [`phase0-runbook.md`](phase0-runbook.md) | |
| `review-code` | self-review after dev-flow | | | Phase 0 | |
| `human-approval-gate` | push request → n / timeout / y | | | Phase 0 HITL | |
| `resolve-issue` | Issue `agent-ready` → MR | | | Phase 1 | |
| `incident-triage` | failed job → triage ≤ 2 min | | | Phase 1 | |
| `switch-context` | (deprecated Phase 3) | | | prefer `route-task` | |
| `route-task` | `[Backend] …` → queued task + trace | | | Phase 3 | |
| `status-report` | list open tasks | | | Phase 3 | |
| `pause-resume` / `safe-mode` | admin control keys | | | Phase 3 / E11 | |
| `review-with-socraticode` | diff-scoped `codebase_*` review + handoff patch | | | MCP enabled (local AGPL); record live runs | |
| `deep-review` | `codebase_impact` + `codebase_graph_*` on diff symbols | | | MCP enabled; record live runs | |
| `fix-pipeline` / `deploy-prod` | CI hotfix / prod deploy HITL | | | Phase 3 | |
| `write-e2e` / `smoke-test` | Playwright / smoke on worktree `:e2e_port` | | | Phase 3 | |

## Switch-context vs profiles (Phase 2 review)

Hermes v0.21.5 has first-class **profiles** (`hermes profile create`). EMAW already uses
one compose service per role. Prefer routing via coordinator + Redis streams over
`switch-context` once Phase 3 starts. Keep the skill only for a single-agent Phase 1–2 host install.
