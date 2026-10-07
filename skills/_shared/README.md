# skills/_shared

Skills and conventions copied to every agent profile by `make skills-sync`.

## HANDOFF block (Phase 3 / design §4.5)

Every skill that finishes a run **must** end its reply with a YAML block the
queue-adapter router parses to write the `handoffs` table and (when `to_agent`
is set) re-enqueue the task on `stream:<to_agent>`:

```text
HANDOFF:
  to_agent: <role | empty if DONE>
  branch: <branch name>
  worktree_path: <path or empty>
  summary: |
    <short summary>
  artifacts: []
  open_questions: |
    <questions for a human, if any>
  token_spent: 0
  reason: done | review | needs_human | awaiting_approval
```

### Rules

| `reason` | Typical `to_agent` | Router effect |
|---|---|---|
| `review` | `reviewer` | state → `REVIEW`, XADD `stream:reviewer` |
| `done` | empty | state → `DONE` |
| `needs_human` | empty | state → `NEEDS_HUMAN` |
| `awaiting_approval` | empty (or coordinator) | state → `AWAITING_APPROVAL` |

**Fallback (DECISION-16):** if a `dev-frontend` / `dev-backend` run completes
with no `HANDOFF:` block and `reviewer` is in the project's `allowed_workers`,
the router auto-hands off to `reviewer`. Prefer an explicit block.

### Artifact URLs

When MinIO is configured, the worker adapter uploads `run-output.md` and appends
`s3://emaw-artifacts/<project>/<task_id>/…` into `artifacts` before the router
persists the handoff.
