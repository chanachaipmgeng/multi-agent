# workspace/ — project clones (not in git)

Mounted as `/workspace` into the agents. Each onboarded repository lives in
`workspace/<project-key>/` and is cloned by `scripts/onboard-project.sh`; the clones themselves
are **gitignored** (GitLab is the source of truth).

```text
workspace/
 ├── _templates/            # rulebook + ignore files copied into every new project (D0.4)
 │    ├── project-standards.md
 │    ├── .agentignore
 │    └── .socraticodeignore
 ├── .worktrees/            # one git worktree per task: /workspace/.worktrees/<task_id> (ephemeral)
 ├── frontend-app/          # clone (gitignored)
 └── backend-api/           # clone (gitignored)
```

Every project must have, at its root: `.agentignore`, `.socraticodeignore`, `project-standards.md`
and a test command that returns exit 0/1 correctly (checklist #3, #5, #7). Stale worktrees older
than 7 days are removed by the cleanup job (Phase 2).
