# Skill catalog (design ภาคผนวก B)

Skills are version-controlled here and promoted into
`hermes-data/<agent>/skills/emaw/<skill>/SKILL.md` by `make skills-sync`
(E13: never the other way round — a skill an agent "learns" in chat must be
exported here and reviewed before it reaches a production profile).

Hermes Agent v0.21.5 expects:

```text
~/.hermes/skills/<category>/<skill>/SKILL.md
```

with YAML front matter including at least `name` and `description`. EMAW stores
extra fields under `metadata.hermes` (`owner`, `phase`, `hitl`, …).

Layout: `skills/<agent>/<skill>.md`, plus `skills/_dev-common/` (shared by
`dev-frontend` and `dev-backend`) and `skills/_shared/` (every agent).

| Skill | Owner | Phase | Status |
|---|---|---|---|
| `dev-flow` | dev-frontend, dev-backend | **0** | implemented |
| `review-code` | dev-frontend, dev-backend | **0** | implemented |
| `human-approval-gate` | coordinator | **0** | implemented |
| `resolve-issue` | dev-frontend, dev-backend | **1** | implemented |
| `incident-triage` | devops | **1** | implemented |
| `switch-context` | coordinator (single agent in 1–2) | 2 | deprecated in Phase 3 — use `route-task` |
| `review-with-socraticode` | reviewer | 2 | implemented — SocratiCode MCP (`codebase_*`), local AGPL |
| `deep-review` | reviewer | 2 | implemented — `codebase_impact` + `codebase_graph_*` |
| `route-task`, `status-report`, `pause-resume`, `safe-mode` | coordinator | 3 | implemented |
| `human-approval-gate` | coordinator | 0→3 | v1.1 — `/internal/approvals` + y/n nonce (DECISION-17) |
| `fix-pipeline`, `deploy-prod` | devops | 3 | implemented |
| `write-e2e`, `smoke-test` | qa | 3 | implemented |
| `open-change-request` | `_shared` → FE/BE/devops/coordinator/reviewer/qa | 1 | implemented — GitLab MR / GitHub PR via `inputs.scm` |

Keep steps numbered and explicit about *stop* conditions — the self-heal limit
and the approval gate are what make these safe to run unattended.
