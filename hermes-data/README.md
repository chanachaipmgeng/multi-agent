# hermes-data/ — one profile per agent

Each sub-directory is mounted as `/opt/data` into exactly one Hermes container
(design §4.1 "one role, one profile, one data dir"). Layout per profile:

| Path | In git? | Purpose |
|---|---|---|
| `AGENT.md` | yes | agent policy — layer 2 of the rule hierarchy (what this role may / must never do) |
| `config.yaml` | yes | Hermes config for the role (model tier, `terminal.backend: docker`, mounts, budgets). Secrets are referenced as `/run/secrets/*` paths, never inline |
| `skills/` | generated | populated from `skills/<agent>/` by `make skills-sync`; do not edit here (E13) |
| `memory/` | no | sessions, learned facts — runtime data, gitignored |

Config keys follow the source documents (`terminal.backend`, `telegram.allowed_users`,
`gitlab.base_url`, …). **Verify them against `hermes config list` on the version you deploy
(DECISION-1)** — the structure of the profiles does not depend on the exact key names.

Phase 0 runs a single agent. Use `dev-backend` or `dev-frontend` as that agent (they carry the
`dev-flow` / `review-code` skills), or the host-installed Hermes configured by
`scripts/hermes-configure.sh`. The remaining profiles come alive in Phase 3.
