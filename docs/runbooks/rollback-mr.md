# Runbook — Rollback a bad agent MR

Agents must never push `main` (platform policy + GitLab protected branches). Recovery is always via GitLab.

## Steps

1. Identify the MR / branch from Telegram notice or `audit_events` (`task.dispatched`, handoff summary).
2. Close or mark the MR as draft; remove `agent-ready` label from the Issue if still present.
3. If the branch was merged (human error): revert with a new MR (`git revert -m 1 <merge-sha>`), require approver.
4. If the agent opened a follow-up worktree mess: `make worktree-clean` on the host; delete stale remote branches after review.
5. Record `incident.agent_mistake` in the ops log; adjust `project-standards.md` / skill if pattern repeats.

## Do not

- Force-push `main`
- Re-run the same task without fixing the rulebook if the agent will repeat the mistake
