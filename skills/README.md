# Skill catalog (design ภาคผนวก B)

Skills are version-controlled here and promoted into `hermes-data/<agent>/skills/<skill>/SKILL.md`
by `make skills-sync` (E13: never the other way round — a skill an agent "learns" in chat must be
exported here and reviewed before it reaches a production profile).

Layout: `skills/<agent>/<skill>.md`, plus `skills/_dev-common/` (shared by `dev-frontend` and
`dev-backend`) and `skills/_shared/` (every agent).

| Skill | Owner | Phase | Status |
|---|---|---|---|
| `dev-flow` | dev-frontend, dev-backend | **0** | implemented (`_dev-common/dev-flow.md`) |
| `review-code` | dev-frontend, dev-backend | **0** | implemented (`_dev-common/review-code.md`) |
| `human-approval-gate` | coordinator | **0** | implemented (`coordinator/human-approval-gate.md`) |
| `resolve-issue` | dev-frontend, dev-backend | **1** | implemented (`_dev-common/resolve-issue.md`) |
| `incident-triage` | devops | **1** | implemented (`devops/incident-triage.md`) |
| `switch-context` | coordinator (single agent in 1–2) | 2 | placeholder |
| `review-with-socraticode`, `deep-review` | reviewer | 2 | placeholder |
| `fix-pipeline`, `deploy-prod` | devops | 3 | placeholder |
| `route-task`, `status-report` | coordinator | 3 | placeholder |
| `write-e2e`, `smoke-test` | qa | 3 | placeholder |

Each skill file has YAML front matter (`name`, `owner`, `phase`, `hitl`) followed by the
instructions the agent executes. Keep steps numbered and explicit about *stop* conditions —
the self-heal limit and the approval gate are what make these safe to run unattended.
