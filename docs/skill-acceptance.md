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

### Sandbox harness (no pilot / DECISION-11)

```bash
# Mechanical gates (work branch → test → commit → no push) ×3
docker cp scripts/skill-accept-sandbox-drill.sh emaw-dev-backend:/tmp/
docker exec emaw-dev-backend bash /tmp/skill-accept-sandbox-drill.sh

# Optional Hermes /v1/runs probe (local LLM may complete without executing tools)
docker cp scripts/skill-accept-sandbox.py emaw-dev-backend:/tmp/
docker exec emaw-dev-backend python /tmp/skill-accept-sandbox.py --rounds 3 --timeout 1800
```

Evidence files (gitignored under `examples/sandbox-smoke/`): `.skill-accept-*.json`, `.skill-accept-drill-*.log`.

| Skill | Scenario | Date | Runs (pass/fail) | Notes | Promoted? |
|---|---|---|---|---|---|
| `dev-flow` | sandbox-smoke subtract + test | 2026-10-08 | 2/0 drill + hermes_api incomplete | Drill r1 `c672f8f` subtract, r2 `214987c` multiply; no push. hermes_api runs `run_ab92…`/`run_183d…` status=completed but tools not applied (local LLM). | no (compose drill only; promote after Telegram/cloud) |
| `review-code` | self-review after dev-flow | 2026-10-08 | 1/0 drill | Drill r3 `c4ec473` — `SMOKE_FORCE_FAIL=1` → exit 1 then green; empty commit. hermes_api `run_4929…` incomplete tools. | no |
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

## Live evidence — sandbox-smoke (2026-10-08)

| Check | Result |
|---|---|
| Nested git for worktrees | PASS — `examples/sandbox-smoke/.git` (ignored by parent) |
| `./test.sh` CRLF fixed | PASS — green exit 0 / `SMOKE_FORCE_FAIL=1` exit 1 |
| Drill ≥3 rounds | PASS — `scripts/skill-accept-sandbox-drill.sh` → 3/3 (log `.skill-accept-drill-20261008T031457Z.log`) |
| hermes_api ×3 | PARTIAL — 3/3 HTTP completed; local-free model did not execute tools / no agent commit |
| Code artifacts | `subtract` + `multiply` + tests on sandbox main |
| Pilot Telegram acceptance | BLOCKED — DECISION-8 / 11 ([org-unblock.md](org-unblock.md)) |

## Switch-context vs profiles (Phase 2 review)

Hermes v0.21.5 has first-class **profiles** (`hermes profile create`). EMAW already uses
one compose service per role. Prefer routing via coordinator + Redis streams over
`switch-context` once Phase 3 starts. Keep the skill only for a single-agent Phase 1–2 host install.
