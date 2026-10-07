# Skill acceptance log (Phase 2 exit — checklist #10 / E13)

Record ≥ 3 clean staging runs per skill before promoting to production profiles.
Blocked skills stay placeholders until their decision is closed.

| Skill | Scenario | Date | Runs (pass/fail) | Notes | Promoted? |
|---|---|---|---|---|---|
| `dev-flow` | sandbox-smoke subtract + test | | | Phase 0 exit | |
| `review-code` | self-review after dev-flow | | | Phase 0 | |
| `human-approval-gate` | push request → n / timeout / y | | | Phase 0 HITL | |
| `resolve-issue` | Issue `agent-ready` → MR | | | Phase 1 | |
| `incident-triage` | failed job → triage ≤ 2 min | | | Phase 1 | |
| `switch-context` | [Frontend]/[Backend] tags | | | Optional if using multi-profile | |
| `review-with-socraticode` | diff-scoped SocratiCode review | | | Blocked on DECISION-6 | |
| `deep-review` | blast radius / deps MCP | | | Blocked on DECISION-6 | |
| `write-e2e` / `smoke-test` | Playwright on worktree :3001 | | | Phase 3 | |

## Switch-context vs profiles (Phase 2 review)

Hermes v0.21.5 has first-class **profiles** (`hermes profile create`). EMAW already uses
one compose service per role. Prefer routing via coordinator + Redis streams over
`switch-context` once Phase 3 starts. Keep the skill only for a single-agent Phase 1–2 host install.
